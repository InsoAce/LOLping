import argparse
import ctypes
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import filedialog
from urllib.parse import quote

from lcu import LCU, ClientError, SendLimiter, discover, format_message, selected_players, validate_selection

BG = '#121925'
CARD = '#1e2939'
FG = '#edf3fc'
MUTED = '#98a9c2'
BLUE = '#65bcff'
ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
CONFIG = Path(os.environ.get('APPDATA', str(Path.home()))) / 'LoLQuickChat/settings.json'


class Worker(threading.Thread):
    def __init__(self, events, commands, demo=False):
        super().__init__(daemon=True)
        self.events, self.commands, self.demo = events, commands, demo
        self.client = None
        self.manual_path = ''
        self.names = json.loads((ROOT / 'champions_zh.json').read_text(encoding='utf-8'))
        self.limiter = SendLimiter()
        self.last_diagnostic = None
        try:
            self.manual_path = json.loads(CONFIG.read_text(encoding='utf-8')).get('lockfile', '')
        except (OSError, ValueError):
            pass

    def name(self, champion_id):
        key = str(champion_id)
        if key in self.names:
            return self.names[key]
        if self.client:
            try:
                info = self.client.request('GET', '/lol-game-data/assets/v1/champions/{}.json'.format(champion_id))
                name = info.get('name')
                if name:
                    self.names[key] = name
                    return name
            except ClientError:
                pass
        return None

    def snapshot(self):
        if self.demo:
            session = {'localPlayerCellId': 0, 'myTeam': [
                {'cellId': i, 'championId': cid} for i, cid in enumerate((22, 17, 0, 64, 99))]}
            conversation = 'demo'
        else:
            if not self.client:
                self.client = LCU(discover(self.manual_path))
                # Prefer the current client's localized hero names.
                try:
                    heroes = self.client.request('GET', '/lol-game-data/assets/v1/champion-summary.json')
                    for hero in heroes:
                        if hero.get('id', 0) > 0 and hero.get('name'):
                            self.names[str(hero['id'])] = hero['name']
                except ClientError:
                    pass
            phase = self.client.request('GET', '/lol-gameflow/v1/gameflow-phase')
            if phase != 'ChampSelect':
                return {'status': '已连接 · 等待进入选人阶段', 'players': []}
            session = self.client.request('GET', '/lol-champ-select/v1/session')
            try:
                conversation = self.client.conversation(session)
            except ClientError:
                # A delayed/unavailable chat service must not hide the selection overlay.
                conversation = None
        players = selected_players(session)
        for p in players:
            p['name'] = self.name(p['champion_id']) if p['champion_id'] else None
            p['conversation'] = conversation
        return {'status': '演示模式 · 不会发送真实消息' if self.demo else
                ('选人中 · 聊天室已连接' if conversation else '选人中 · 等待聊天室就绪'), 'players': players}

    def send(self, expected):
        if self.limiter.remaining() > 0:
            raise ClientError('发送冷却中，请稍后再试')
        if not expected.get('name') or not expected.get('champion_id'):
            raise ClientError('该队友尚未选择英雄，或英雄名尚未读取')
        if self.demo:
            self.limiter.consume()
            return '演示预览：' + format_message(expected['floor'], expected['name'])
        if not self.client:
            raise ClientError('客户端未连接')
        phase = self.client.request('GET', '/lol-gameflow/v1/gameflow-phase')
        if phase != 'ChampSelect':
            raise ClientError('已离开选人阶段，取消发送')
        session = self.client.request('GET', '/lol-champ-select/v1/session')
        conversation = self.client.conversation(session)
        player = validate_selection(expected, session, conversation)
        message = format_message(player['floor'], self.name(player['champion_id']))
        # Reserve cooldown before a write: network timeouts must not trigger automatic retries.
        self.limiter.consume()
        try:
            self.client.request('POST', '/lol-chat/v1/conversations/{}/messages'.format(quote(conversation, safe='')),
                                {'body': message, 'type': 'chat'})
        except ClientError as exc:
            raise ClientError(str(exc) + '；发送结果未确认，请先检查聊天框') from None
        return '已发送：' + message

    def run(self):
        next_poll = 0
        while True:
            try:
                action, data = self.commands.get(timeout=0.2)
                if action == 'stop':
                    return
                if action == 'connect':
                    self.manual_path, self.client = data, None
                    try:
                        CONFIG.parent.mkdir(parents=True, exist_ok=True)
                        CONFIG.write_text(json.dumps({'lockfile': data}, ensure_ascii=False), encoding='utf-8')
                    except OSError:
                        pass
                    next_poll = 0
                elif action == 'send':
                    try:
                        self.events.put(('sent', self.send(data)))
                    except ClientError as exc:
                        self.events.put(('send_error', str(exc)))
            except queue.Empty:
                pass
            if time.monotonic() >= next_poll:
                try:
                    snapshot = self.snapshot()
                    self.publish(snapshot)
                    next_poll = time.monotonic() + 1
                except ClientError as exc:
                    self.client = None
                    self.publish({'status': str(exc), 'players': []})
                    next_poll = time.monotonic() + 5
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    self.client = None
                    self.publish({'status': '客户端数据读取失败（{}），正在重试'.format(type(exc).__name__), 'players': []})
                    next_poll = time.monotonic() + 5

    def publish(self, snapshot):
        self.events.put(('snapshot', snapshot))
        # Only connection state and counts are persisted; no account data or credentials.
        diagnostic = (snapshot['status'], len(snapshot['players']))
        if diagnostic != self.last_diagnostic:
            try:
                CONFIG.parent.mkdir(parents=True, exist_ok=True)
                CONFIG.with_name('status.json').write_text(json.dumps({
                    'updated': datetime.now().isoformat(timespec='seconds'),
                    'status': diagnostic[0], 'player_count': diagnostic[1]
                }, ensure_ascii=False, indent=2), encoding='utf-8')
            except OSError:
                pass
            self.last_diagnostic = diagnostic


if __name__ == '__main__':
    from overlay import Overlay
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true')
    Overlay(parser.parse_args().demo).root.mainloop()
