from contextlib import closing
from compression import zstd
import hashlib
import datetime
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from reader import Reader
import reader as reader_module

TEST_TEMP = Path(__file__).resolve().parents[1] / 'private' / 'test-temp'
TEST_TEMP.mkdir(parents=True, exist_ok=True)


class ConversationSearchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=TEST_TEMP)
        self.addCleanup(self.temporary.cleanup)
        self.reader = Reader()
        self.reader.user = Path('wxid_synthetic_abcd')
        self.addCleanup(self.reader.close)
        self.shards = []
        self.reader.databases = lambda: self.shards

    def add_shard(self, rows, group='synthetic@chatroom'):
        name = f'message_{len(self.shards)}.db'
        path = Path(self.temporary.name) / name
        table = 'Msg_' + hashlib.md5(group.encode()).hexdigest()
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE Name2Id(user_name TEXT)')
            db.execute("INSERT INTO Name2Id VALUES ('wxid_synthetic')")
            db.execute(f'CREATE TABLE "{table}"(local_id INTEGER,local_type INTEGER,sort_seq INTEGER,real_sender_id INTEGER,create_time INTEGER,message_content BLOB)')
            db.executemany(f'INSERT INTO "{table}" VALUES (?,?,?,1,?,?)', rows)
            db.commit()
        self.shards.append((Path(name), path))

    def test_search_reaches_history_older_than_loaded_page_and_stays_in_group(self):
        self.add_shard([(i, 1, i, i, '近期普通消息') for i in range(1, 401)] + [(0, 1, 0, 0, '很早的摄影安排')])
        self.add_shard([(1, 1, 1, 1000, '其他群的摄影安排')], 'other@chatroom')
        self.assertNotIn('很早的摄影安排', [m['text'] for m in self.reader.messages('synthetic@chatroom')])
        found = self.reader.messages('synthetic@chatroom', query='摄影')
        self.assertEqual([m['text'] for m in found], ['很早的摄影安排'])

    def test_search_uses_visible_decoded_card_quote_and_text_not_hidden_xml(self):
        article = '<msg><appmsg><type>5</type><title>摄影征稿</title><unused>hidden-secret</unused><url>https://example.org</url></appmsg></msg>'
        quote = '<msg><appmsg><type>57</type><title>请参考</title><refermsg><type>1</type><displayname>合成作者</displayname><content>摄影初稿明天交</content></refermsg></appmsg></msg>'
        self.add_shard([(1, 1, 1, 100, 'MiXeD Case Straße'), (2, 49, 2, 101, article),
                        (3, (1 << 32) + 49, 3, 102, quote), (4, 1, 4, 103, zstd.compress('摄影压缩文字'.encode()))])
        self.assertEqual(len(self.reader.messages('synthetic@chatroom', query='  mixed case STRASSE  ')), 1)
        found = self.reader.messages('synthetic@chatroom', query='摄影')
        self.assertEqual(len(found), 3)
        self.assertIn('摄影征稿', found[0]['text'])
        self.assertIn('摄影初稿明天交', found[1]['text'])
        self.assertEqual(found[2]['text'], '摄影压缩文字')
        self.assertEqual(self.reader.messages('synthetic@chatroom', query='hidden-secret'), [])

    def test_pagination_keeps_all_same_second_matches_across_shards(self):
        self.add_shard([(i, 1, i, 1000, f'摄影{i}') for i in range(1, 176)] + [(0, 1, 0, 999, '摄影较早')])
        self.add_shard([(i, 1, i, 1000, f'摄影另片{i}') for i in range(1, 176)])
        page = self.reader.messages('synthetic@chatroom', query='摄影')
        self.assertEqual(len(page), 350)
        self.assertEqual(len({m['id'] for m in page}), 350)
        older = self.reader.messages('synthetic@chatroom', query='摄影', before=min(m['time'] for m in page))
        self.assertEqual([m['text'] for m in older], ['摄影较早'])

    def test_pagination_does_not_limit_unmatched_rows_before_filtering(self):
        self.add_shard([(i, 1, i, i, '命中' if i % 5 == 0 else '无关') for i in range(1, 1201)])
        all_ids = []
        before = None
        while True:
            page = self.reader.messages('synthetic@chatroom', query='命中', before=before)
            if not page:
                break
            self.assertLessEqual(len(page), 100)
            all_ids.extend(m['id'] for m in page)
            before = min(m['time'] for m in page)
        self.assertEqual(len(all_ids), 240)
        self.assertEqual(len(set(all_ids)), 240)

    def test_literal_search_does_not_decode_images_or_treat_sql_symbols_as_patterns(self):
        self.add_shard([(1, 3, 1, 100, '<img md5="synthetic"/>'), (2, 1, 2, 101, "100%_摄影'安排")])
        self.reader.image = lambda *args: self.fail('Text search must not scan or decode images')
        self.assertEqual(len(self.reader.messages('synthetic@chatroom', query="%_摄影'")), 1)
        self.assertEqual(self.reader.messages('synthetic@chatroom', query='md5'), [])
        self.assertEqual(self.reader.messages('synthetic@chatroom', query="' OR 1=1 --"), [])

    def test_empty_invalid_or_excessive_queries_are_rejected(self):
        for query in ('', '   ', 'x' * 257, 123):
            with self.assertRaises(ValueError):
                self.reader.messages('synthetic@chatroom', query=query)

    def test_search_protocol_then_selected_export_does_not_reapply_search_filter(self):
        stamp = int(datetime.datetime(2026, 10, 30, 12).timestamp())
        self.add_shard([(1, 1, 1, stamp, '摄影安排'), (2, 1, 2, stamp + 1, '需要导出的另一条工作消息')])
        path = Path(self.temporary.name) / 'selected.html'
        requests = [{'action': 'search', 'chat': 'synthetic@chatroom', 'query': '摄影'},
                    {'action': 'export', 'chat': 'synthetic@chatroom', 'start': '2026-10-30', 'end': '2026-10-30',
                     'selected': ['message_0.db:2'], 'path': str(path)}]
        output = io.StringIO()
        with patch.object(reader_module, 'Reader', return_value=self.reader), \
             patch.object(sys, 'stdin', io.StringIO('\n'.join(json.dumps(r) for r in requests))), \
             patch.object(sys, 'stdout', output):
            reader_module.serve()
        frames = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertTrue(all(f['ok'] for f in frames))
        self.assertEqual(frames[0]['data'][0]['text'], '摄影安排')
        self.assertEqual(frames[1]['data']['count'], 1)
        html = path.read_text(encoding='utf-8')
        self.assertIn('需要导出的另一条工作消息', html)
        self.assertNotIn('摄影安排', html)


if __name__ == '__main__':
    unittest.main()
