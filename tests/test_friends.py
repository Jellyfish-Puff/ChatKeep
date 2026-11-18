"""Synthetic personal-conversation regressions; never access WeChat or real caches."""
from contextlib import closing
import datetime
import hashlib
import io
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from reader import Reader
import reader as reader_module

TEST_TEMP = Path(__file__).resolve().parents[1] / 'private/test-temp'
TEST_TEMP.mkdir(parents=True, exist_ok=True)


class FriendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TEST_TEMP)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.reader = Reader()
        self.addCleanup(self.reader.close)
        self.reader.user = self.folder / 'wxid_self_abcd'
        self.reader.names = {'wxid_self': '我', 'wxid_friend': '小林（备注）', 'legacy_username': '小周', 'room@chatroom': '工作群'}
        self.path = self.folder / 'messages.db'
        self.stamp = int(datetime.datetime(2026, 11, 12).timestamp())
        self.digest = '0123456789abcdef0123456789abcdef'
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE Name2Id(user_name TEXT)')
            db.executemany('INSERT INTO Name2Id VALUES (?)', [('wxid_self',), ('wxid_friend',), ('legacy_username',)])
            for chat, sender in [('wxid_friend', 2), ('legacy_username', 3), ('room@chatroom', 2)]:
                table = 'Msg_' + hashlib.md5(chat.encode()).hexdigest()
                db.execute(f'CREATE TABLE "{table}"(local_id INTEGER,local_type INTEGER,sort_seq INTEGER,real_sender_id INTEGER,create_time INTEGER,message_content TEXT)')
                db.executemany(f'INSERT INTO "{table}" VALUES (?,?,?,?,?,?)', [
                    (1, 1, 1, sender, self.stamp - 1, '范围之前'),
                    (2, 1, 2, sender, self.stamp, 'wxid_friend:\n摄影安排'),
                    (3, 1, 3, 1, self.stamp + 86399, '收到，明天见'),
                    (4, 1, 4, sender, self.stamp + 86400, '范围之后'),
                    (5, 3, 5, sender, self.stamp + 60, f'<msg><img md5="{self.digest}"/></msg>')])
            db.commit()
        self.reader.databases = lambda: [(Path('message_0.db'), self.path)]

    def test_visible_sessions_include_friends_legacy_ids_and_groups_but_skip_services(self):
        with closing(sqlite3.connect(':memory:')) as db:
            db.execute('CREATE TABLE SessionTable(username TEXT,summary TEXT,last_timestamp INTEGER,sort_timestamp INTEGER,is_hidden INTEGER)')
            users = ['room@chatroom', 'wxid_friend', 'legacy_username', 'gh_service', 'weixin',
                     'filehelper', 'brandsessionholder', 'notification_messages', 'corp@openim', '', None, 'hidden']
            db.executemany('INSERT INTO SessionTable VALUES (?,?,1,?,?)',
                           [(user, '合成摘要', i, int(user == 'hidden')) for i, user in enumerate(users)])
            chats = self.reader.conversations(db)
        self.assertEqual([c['id'] for c in chats], ['legacy_username', 'wxid_friend', 'room@chatroom'])
        self.assertEqual([c['kind'] for c in chats], ['friend', 'friend', 'group'])
        self.assertEqual(chats[1]['name'], '小林（备注）')

    def test_connect_returns_both_categories_and_counts(self):
        user = self.reader.user
        session = user / 'db_storage/session/session.db'
        session.parent.mkdir(parents=True)
        salt = bytes(range(16))
        session.write_bytes(salt)
        contacts = self.folder / 'contacts.db'
        sessions = self.folder / 'sessions.db'
        with closing(sqlite3.connect(contacts)) as db:
            db.execute('CREATE TABLE contact(username TEXT,nick_name TEXT,remark TEXT)')
            db.executemany('INSERT INTO contact VALUES (?,?,?)', [('wxid_friend', '小林', '好友备注'), ('room@chatroom', '工作群', '')])
            db.commit()
        with closing(sqlite3.connect(sessions)) as db:
            db.execute('CREATE TABLE SessionTable(username TEXT,summary TEXT,last_timestamp INTEGER,sort_timestamp INTEGER,is_hidden INTEGER)')
            db.executemany('INSERT INTO SessionTable VALUES (?,NULL,1,1,0)', [('wxid_friend',), ('room@chatroom',)])
            db.commit()
        def snapshot(path, keys):
            return contacts if path.name == 'contact.db' else sessions
        with patch.object(reader_module, 'probe', return_value=({}, {salt: b'synthetic'}, [user])), patch.object(reader_module, 'snapshot', side_effect=snapshot):
            result = self.reader.connect()
        self.assertEqual({c['kind'] for c in result['chats']}, {'friend', 'group'})
        self.assertIn('1 个群聊 · 1 个好友会话', result['status'])
        self.assertEqual(next(c for c in result['chats'] if c['kind'] == 'friend')['name'], '好友备注')

    def test_friend_sender_direction_literal_text_and_search_stay_in_conversation(self):
        rows = self.reader.messages('wxid_friend', query='摄影')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['sender'], '小林（备注）')
        self.assertFalse(rows[0]['self'])
        self.assertEqual(rows[0]['text'], 'wxid_friend:\n摄影安排')
        sent = self.reader.messages('wxid_friend', query='收到')
        self.assertTrue(sent[0]['self'])
        self.assertEqual(sent[0]['sender'], '我')
        self.assertEqual(self.reader.messages('room@chatroom', query='摄影')[0]['text'], '摄影安排')
        self.assertEqual(self.reader.messages('legacy_username', query='摄影')[0]['sender'], '小周')

    def add_image(self, chat, size):
        folder = self.reader.user / 'msg/attach' / hashlib.md5(chat.encode()).hexdigest() / '2026-11/Img'
        folder.mkdir(parents=True, exist_ok=True)
        encoded = io.BytesIO()
        Image.new('RGB', size, '#0a9b7d').save(encoded, format='PNG')
        (folder / (self.digest + '.dat')).write_bytes(encoded.getvalue())

    def request(self, chat='wxid_friend'):
        return {'chat': chat, 'start': '2026-11-12', 'end': '2026-11-12', 'path': str(self.folder / 'friend.html')}

    def test_friend_export_includes_end_day_sender_and_local_image_without_other_chats(self):
        self.add_image('wxid_friend', (320, 180))
        self.add_image('room@chatroom', (640, 360))
        request = self.request()
        result = self.reader.export(request)
        self.assertEqual(result['count'], 3)
        output = Path(request['path']).read_text(encoding='utf-8')
        for content in ['小林（备注）', '摄影安排', '收到，明天见', '23:59:59', '320 × 180', 'data:image/png;base64,']:
            self.assertIn(content, output)
        for content in ['范围之前', '范围之后', '640 × 360', '小周', '<script']:
            self.assertNotIn(content, output)

    def test_selected_friend_export_uses_ids_and_dates(self):
        request = self.request()
        request['selected'] = ['message_0.db:1', 'message_0.db:3', 'message_0.db:4']
        self.assertEqual(self.reader.export(request)['count'], 1)
        output = Path(request['path']).read_text(encoding='utf-8')
        self.assertIn('收到，明天见', output)
        self.assertNotIn('摄影安排', output)

    def test_multiple_friend_exports_in_both_modes(self):
        for mode in ('merged', 'separate'):
            result = self.reader.export_batch({'chats': ['wxid_friend', 'legacy_username'], 'start': '2026-11-12', 'end': '2026-11-12', 'folder': str(self.folder), 'mode': mode})
            self.assertEqual(result['count'], 6)
            self.assertEqual([r['count'] for r in result['results']], [3, 3])
            paths = [Path(result['path'])] if mode == 'merged' else [Path(r['path']) for r in result['results']]
            output = ''.join(p.read_text(encoding='utf-8') for p in paths)
            self.assertIn('小林（备注）', output)
            self.assertIn('小周', output)
            self.assertNotIn('工作群', output)


if __name__ == '__main__':
    unittest.main()
