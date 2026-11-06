import io
import json
import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app import Worker
from lcu import Credentials, LCU, ClientError, PermissionRequired, SendLimiter, discover, format_message, read_lockfile, selected_players, validate_selection


def session(champion=22):
    return {'localPlayerCellId': 5, 'myTeam': [{'cellId': 6, 'championId': 17},
            {'cellId': 5, 'championId': champion, 'championPickIntent': 0}]}


class Checks(unittest.TestCase):
    def test_restricted_client_reports_permission_required(self):
        result = Mock(stdout=b'{"CommandLine":null,"ExecutablePath":null}')
        with patch('lcu.subprocess.run', return_value=result), patch('lcu.read_lockfile', side_effect=OSError):
            with self.assertRaises(PermissionRequired):
                discover()

    def test_chat_unavailable_does_not_hide_players(self):
        self.client.conversation.side_effect = ClientError('chat unavailable')
        snapshot = self.worker.snapshot()
        self.assertEqual(len(snapshot['players']), 2)
        self.assertIsNone(snapshot['players'][0]['conversation'])

    def setUp(self):
        self.worker = Worker(queue.Queue(), queue.Queue())
        self.expected = dict(cell_id=5, floor=1, champion_id=22, name='寒冰射手', conversation='room1')
        self.client = Mock()
        self.worker.client = self.client
        self.client.conversation.return_value = 'room1'
        self.client.request.side_effect = lambda method, path, payload=None: (
            'ChampSelect' if path.endswith('gameflow-phase') else session() if path.endswith('/session') else None)

    def test_exact_unicode_payload_and_single_write(self):
        self.worker.send(self.expected)
        writes = [c for c in self.client.request.call_args_list if c.args[0] == 'POST']
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0].args[2], {'body': '1楼 (寒冰射手) - 存活', 'type': 'chat'})

    def test_hero_changed_no_write(self):
        self.expected['champion_id'] = 17
        with self.assertRaises(ClientError):
            self.worker.send(self.expected)
        self.assertFalse(any(c.args[0] == 'POST' for c in self.client.request.call_args_list))

    def test_new_lobby_no_write(self):
        self.client.conversation.return_value = 'room2'
        with self.assertRaises(ClientError):
            self.worker.send(self.expected)
        self.assertFalse(any(c.args[0] == 'POST' for c in self.client.request.call_args_list))

    def test_outside_champ_select_no_write(self):
        self.client.request.side_effect = lambda *a: 'InProgress'
        with self.assertRaises(ClientError):
            self.worker.send(self.expected)
        self.assertEqual(self.client.request.call_count, 1)

    def test_cooldown(self):
        for _ in range(4):
            self.worker.send(self.expected)
        with self.assertRaises(ClientError):
            self.worker.send(self.expected)
        self.assertEqual(len([c for c in self.client.request.call_args_list if c.args[0] == 'POST']), 4)

    def test_failed_send_is_not_retried(self):
        def request(method, path, payload=None):
            if method == 'POST':
                raise ClientError('timeout')
            return 'ChampSelect' if path.endswith('phase') else session()
        self.client.request.side_effect = request
        with self.assertRaisesRegex(ClientError, '发送结果未确认'):
            self.worker.send(self.expected)
        self.assertEqual(len([c for c in self.client.request.call_args_list if c.args[0] == 'POST']), 1)

    def test_slot_normalization_and_hover(self):
        value = session(0)
        value['myTeam'][1]['championPickIntent'] = 22
        self.assertEqual(selected_players(value)[0], dict(cell_id=5, floor=1, champion_id=22, is_self=True))

    def test_no_champion_no_send(self):
        self.expected['champion_id'] = 0
        with self.assertRaises(ClientError):
            self.worker.send(self.expected)
        self.client.request.assert_not_called()

    def test_demo_never_uses_client(self):
        self.worker.demo = True
        self.worker.send(self.expected)
        self.client.request.assert_not_called()

    def test_transport_loopback_and_encoding(self):
        client = LCU(Credentials(12345, 'secret'))
        response = io.BytesIO(b'{}')
        client.opener = Mock()
        client.opener.open.return_value = response
        client.request('POST', '/test', {'body': format_message(1, '寒冰射手')})
        req = client.opener.open.call_args.args[0]
        self.assertEqual(req.full_url, 'https://127.0.0.1:12345/test')
        self.assertEqual(json.loads(req.data)['body'], '1楼 (寒冰射手) - 存活')
        self.assertNotIn('secret', repr(client.credentials))

    def test_lockfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'lockfile'
            file.write_text('LeagueClient:111:54321:password:https')
            self.assertEqual(read_lockfile(tmp).port, 54321)
            file.write_text('')
            with self.assertRaises(ClientError):
                read_lockfile(tmp)

    def test_four_sends_then_two_second_cooldown(self):
        now = [100.0]
        limiter = SendLimiter(lambda: now[0])
        for index in range(4):
            limiter.consume()
        with self.assertRaises(ClientError):
            limiter.consume()
        now[0] = 101.99
        with self.assertRaises(ClientError):
            limiter.consume()
        now[0] = 102.01
        limiter.consume()
        self.assertEqual(limiter.count, 1)

    def test_no_minimum_interval_and_idle_reset(self):
        now = [100.0]
        limiter = SendLimiter(lambda: now[0])
        limiter.consume()
        limiter.consume()
        now[0] += 2
        limiter.consume()
        self.assertEqual(limiter.count, 1)


if __name__ == '__main__':
    unittest.main()
