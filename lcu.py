"""Local League client transport. No game injection or memory access."""
import base64
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field


class ClientError(Exception):
    pass


class PermissionRequired(ClientError):
    pass


class SendLimiter:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.last = None
        self.count = 0
        self.blocked_until = 0

    def remaining(self):
        if self.last is None:
            return 0
        return max(0, self.blocked_until - self.clock())

    def consume(self):
        now = self.clock()
        if self.remaining() > 0:
            raise ClientError('发送冷却中，请稍后再试')
        if self.last is None or now - self.last >= 2:
            self.count = 0
        self.last = now
        self.count += 1
        if self.count == 4:
            self.blocked_until = now + 2


@dataclass
class Credentials:
    port: int
    password: str = field(repr=False)


def read_lockfile(path):
    path = Path(path)
    if path.is_dir():
        path = path / 'lockfile'
    parts = path.read_text(encoding='utf-8').strip().split(':')
    if len(parts) != 5 or parts[4] != 'https':
        raise ClientError('不是有效的客户端 lockfile')
    port = int(parts[2])
    if not 1 <= port <= 65535 or not parts[3]:
        raise ClientError('客户端连接信息无效')
    return Credentials(port, parts[3])


def discover(manual_path=''):
    # Command line is captured internally, never logged or displayed.
    try:
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
             "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
             "Get-CimInstance Win32_Process -Filter \"Name='LeagueClientUx.exe'\" | "
             'Select-Object CommandLine,ExecutablePath | ConvertTo-Json -Compress'],
            capture_output=True, timeout=8, creationflags=0x08000000)
        data = json.loads(result.stdout.decode('utf-8-sig', errors='replace') or 'null')
        processes = data if isinstance(data, list) else [data] if data else []
        for proc in processes:
            command = proc.get('CommandLine') or ''
            port = re.search(r'--app-port[= ]"?(\d+)', command)
            token = re.search(r'--remoting-auth-token[= ]"?([^"\s]+)', command)
            if port and token:
                return Credentials(int(port.group(1)), token.group(1))
    except (OSError, ValueError, subprocess.SubprocessError):
        processes = []

    candidates = []
    if manual_path:
        candidates.append(Path(manual_path))
    for proc in processes:
        if proc.get('ExecutablePath'):
            candidates.append(Path(proc['ExecutablePath']).parent / 'lockfile')
    installs = Path(os.environ.get('PROGRAMDATA', 'C:/ProgramData')) / 'Riot Games/RiotClientInstalls.json'
    try:
        info = json.loads(installs.read_text(encoding='utf-8'))
        candidates.extend(Path(p) / 'lockfile' for p in info.get('associated_client', {}))
    except (OSError, ValueError):
        pass
    for drive in ('C:', 'D:', 'E:', 'F:'):
        for folder in ('Riot Games/League of Legends', 'Program Files/Riot Games/League of Legends',
                       '英雄联盟/LeagueClient', 'WeGameApps/英雄联盟/LeagueClient',
                       'Program Files (x86)/腾讯游戏/英雄联盟/LeagueClient',
                       '腾讯游戏/英雄联盟/LeagueClient'):
            candidates.append(Path(drive + '/') / folder / 'lockfile')
    for candidate in candidates:
        try:
            return read_lockfile(candidate)
        except (OSError, ValueError, ClientError):
            continue
    if processes and all(not p.get('CommandLine') for p in processes):
        raise PermissionRequired('连接被权限阻止：请以管理员身份运行本程序')
    raise ClientError('未找到连接信息，请确认已登录客户端，或选择有效的 lockfile')


class LCU:
    def __init__(self, credentials):
        self.credentials = credentials
        # Self-signed TLS is permitted only for this fixed loopback endpoint.
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))

    def request(self, method, path, payload=None):
        if not path.startswith('/') or path.startswith('//'):
            raise ClientError('无效的本地接口路径')
        auth = base64.b64encode(('riot:' + self.credentials.password).encode()).decode()
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(
            'https://127.0.0.1:{}{}'.format(self.credentials.port, path), data=body,
            headers={'Authorization': 'Basic ' + auth, 'Content-Type': 'application/json'}, method=method)
        try:
            with self.opener.open(req, timeout=3) as response:
                raw = response.read()
                return json.loads(raw.decode('utf-8')) if raw else None
        except urllib.error.HTTPError as exc:
            raise ClientError('客户端接口返回 HTTP {}'.format(exc.code)) from None
        except (OSError, ValueError, urllib.error.URLError):
            raise ClientError('无法连接客户端，请确认已登录或重新连接') from None

    def conversation(self, session):
        chat_id = (session.get('chatDetails') or {}).get('multiUserChatId')
        conversations = self.request('GET', '/lol-chat/v1/conversations') or []
        matches = [c for c in conversations if c.get('type') == 'championSelect']
        if chat_id:
            exact = [c for c in matches if c.get('id') == chat_id or c.get('name') == chat_id]
            if len(exact) == 1:
                return exact[0]['id']
        if len(matches) == 1:
            return matches[0]['id']
        return None


def selected_players(session):
    """Preserve vacant floors and support every slot actually reported by myTeam."""
    team = session.get('myTeam') or []
    if any(not isinstance(p, dict) or not isinstance(p.get('cellId'), int) or
           isinstance(p['cellId'], bool) or p['cellId'] < 0 for p in team):
        raise ClientError('选人楼层数据无效，已停止显示')
    team = sorted(team, key=lambda p: p['cellId'])
    if len({p['cellId'] for p in team}) != len(team):
        raise ClientError('选人楼层重复，已停止显示')
    base = (team[0]['cellId'] // 5) * 5 if team else 0
    return [dict(cell_id=p['cellId'], floor=p['cellId'] - base + 1,
                 champion_id=p.get('championId') or p.get('championPickIntent') or 0,
                 is_self=p['cellId'] == session.get('localPlayerCellId'))
            for p in team]


def format_message(floor, name):
    return '{}楼 ({}) - 存活'.format(floor, name)


def validate_selection(expected, actual, conversation_id):
    if not expected.get('conversation') or expected['conversation'] != conversation_id:
        raise ClientError('选人聊天室已变化，请重新选择')
    player = next((p for p in selected_players(actual) if p['cell_id'] == expected['cell_id']), None)
    if not player or not player['champion_id'] or player['champion_id'] != expected['champion_id'] or player['floor'] != expected['floor']:
        raise ClientError('该队友的英雄或楼层已变化，请重新选择后发送')
    return player
