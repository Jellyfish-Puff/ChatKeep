import datetime
from contextlib import closing
import hashlib
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
from html_export import write_document
from message_content import parse_message

TEST_TEMP = Path(__file__).resolve().parents[1] / 'private' / 'test-temp'
TEST_TEMP.mkdir(parents=True, exist_ok=True)
URL = 'https://mp.weixin.qq.com/s?__biz=synthetic&mid=123&idx=1'


def message(identity, text, hour=12, **extra):
    result = {'id': identity, 'time': int(datetime.datetime(2026, 10, 17, hour).timestamp()),
              'sender': '<合成发送者>', 'self': False, 'type': 1, 'image': None}
    result.update(parse_message(1, text))
    result.update(extra)
    return result


class BatchExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TEST_TEMP)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.reader = Reader()
        self.addCleanup(self.reader.close)
        self.reader.names = {'a': '<工作群A>', 'b': '工作群B', 'empty': '空群', 'bad': '失败群'}
        self.rows = {'a': [message('same-id', URL), message('image', '[图片]', image='data:image/png;base64,YQ==', type=3, imageQuality='thumbnail')],
                     'b': [message('same-id', URL, hour=23)], 'empty': []}

        def messages(chat, start=None, end=None, limit=None, selected=None):
            if chat == 'bad':
                raise RuntimeError('<合成读取错误>')
            return [m for m in self.rows[chat] if start <= m['time'] < end]
        self.reader.messages = messages

    def request(self, mode='merged', chats=None):
        return {'chats': chats if chats is not None else ['a', 'b'], 'start': '2026-10-17',
                'end': '2026-10-17', 'mode': mode, 'folder': str(self.folder)}

    def test_merged_groups_share_article_numbers_escape_content_and_report_partial_results(self):
        self.rows['a'].append(message('unsafe', '<script>alert(1)</script>'))
        self.rows['b'].append(message('missing', '[图片缺失]', type=3))
        progress = []
        result = self.reader.export_batch(self.request(chats=['a', 'empty', 'bad', 'b', 'a']), progress.append)
        output = Path(result['path']).read_text(encoding='utf-8')
        self.assertEqual([r['status'] for r in result['results']], ['exported', 'empty', 'failed', 'exported'])
        self.assertEqual([p['index'] for p in progress], [1, 2, 3, 4])
        self.assertTrue(all(p['total'] == 4 for p in progress))
        self.assertEqual(result['count'], 5)
        self.assertEqual(result['thumbnailImages'], 1)
        self.assertEqual(result['missingImages'], 1)
        self.assertEqual(output.count('文章编号：A001'), 2)
        self.assertNotIn('A002', output)
        self.assertEqual(output.count('data:image/png;base64,YQ=='), 1)
        self.assertIn('&lt;script&gt;', output)
        self.assertNotIn('<script>', output)
        self.assertIn('&lt;工作群A&gt;', output)
        self.assertIn('&lt;合成读取错误&gt;', output)
        self.assertIn('default-src \'none\'', output)
        self.assertIn('href="#group-4"', output)
        self.assertLess(output.index('<section id="group-1"'), output.index('<section id="group-4"'))
        self.assertEqual(len(list(Path(result['folder']).glob('*.html'))), 1)
        self.assertFalse(list(self.folder.rglob('*.partial')))

    def test_separate_files_handle_duplicate_names_and_repeat_exports_without_overwriting(self):
        self.reader.names.update(a='CON<>/同名群.', b='CON<>/同名群.')
        first = self.reader.export_batch(self.request('separate'))
        paths = [Path(r['path']) for r in first['results']]
        self.assertEqual(len(set(paths)), 2)
        original = {p: p.read_bytes() for p in paths}
        for p in paths:
            self.assertFalse(any(c in p.name for c in '<>:"/\\|?*'))
            self.assertIn('文章编号：A001', p.read_text(encoding='utf-8'))
        self.rows['a'].clear()
        second = self.reader.export_batch(self.request('separate'))
        self.assertNotEqual(first['folder'], second['folder'])
        self.assertEqual([r['status'] for r in second['results']], ['empty', 'exported'])
        self.assertEqual(len(list(Path(second['folder']).glob('*.html'))), 1)
        for p, data in original.items():
            self.assertEqual(p.read_bytes(), data)

    def test_empty_or_failed_batches_leave_existing_files_and_no_partial_outputs(self):
        old = self.folder / 'old.html'
        old.write_text('保留旧文件', encoding='utf-8')
        for mode in ('merged', 'separate'):
            result = self.reader.export_batch(self.request(mode, ['empty', 'bad']))
            self.assertEqual(result['count'], 0)
            self.assertIsNone(result['folder'])
            self.assertIsNone(result['path'])
            self.assertEqual(list(self.folder.iterdir()), [old])
            self.assertEqual(old.read_text(encoding='utf-8'), '保留旧文件')

    def test_invalid_configuration_does_not_create_output(self):
        for change in ({'start': '2026-10-18'}, {'end': 'invalid'}, {'mode': 'unknown'},
                       {'chats': []}, {'chats': ['a', None]}, {'folder': str(self.folder / 'missing')}):
            request = self.request()
            request.update(change)
            with self.assertRaises(ValueError):
                self.reader.export_batch(request)
            self.assertEqual(list(self.folder.iterdir()), [])

    def test_render_failure_does_not_prevent_other_groups_exporting(self):
        self.rows['a'][0]['sender'] = None  # Broken synthetic record fails during rendering.
        for mode in ('merged', 'separate'):
            result = self.reader.export_batch(self.request(mode))
            self.assertEqual([r['status'] for r in result['results']], ['failed', 'exported'])
            self.assertEqual(result['count'], 1)
        self.assertFalse(list(self.folder.rglob('*.partial')))

    def test_atomic_html_write_preserves_old_destination_on_failure(self):
        destination = self.folder / 'existing.html'
        destination.write_text('old', encoding='utf-8')

        def parts():
            yield 'incomplete'
            raise RuntimeError('synthetic failure')
        with self.assertRaises(RuntimeError):
            write_document(destination, parts())
        self.assertEqual(destination.read_text(encoding='utf-8'), 'old')
        self.assertFalse(list(self.folder.glob('*.partial')))

    def test_actual_database_filters_each_group_including_end_day_last_second(self):
        path = self.folder / 'synthetic.db'
        groups = ['a@chatroom', 'b@chatroom']
        day = datetime.datetime(2026, 10, 17)
        stamp = int(day.timestamp())
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE Name2Id(user_name TEXT)')
            db.execute("INSERT INTO Name2Id VALUES ('wxid_synthetic')")
            for group in groups:
                table = 'Msg_' + hashlib.md5(group.encode()).hexdigest()
                db.execute(f'CREATE TABLE "{table}"(local_id INTEGER,local_type INTEGER,sort_seq INTEGER,real_sender_id INTEGER,create_time INTEGER,message_content TEXT)')
                db.executemany(f'INSERT INTO "{table}" VALUES (?,1,?,1,?,?)',
                               [(i, i, stamp + delta, group + label) for i, (delta, label) in enumerate(
                                   [(-1, 'before'), (0, 'first'), (86399, 'last'), (86400, 'after')])])
            db.commit()
        reader = Reader()
        self.addCleanup(reader.close)
        reader.user = Path('wxid_synthetic_abcd')
        reader.databases = lambda: [(Path('message_0.db'), path)]
        reader.names = dict(zip(groups, ['合成群一', '合成群二']))
        result = reader.export_batch(self.request(chats=groups))
        self.assertEqual(result['count'], 4)
        self.assertEqual([r['count'] for r in result['results']], [2, 2])
        output = Path(result['path']).read_text(encoding='utf-8')
        for group in groups:
            self.assertIn(group + 'first', output)
            self.assertIn(group + 'last', output)
            self.assertNotIn(group + 'before', output)
            self.assertNotIn(group + 'after', output)

    def test_serve_streams_progress_then_result_and_accepts_next_single_export(self):
        requests = [dict(self.request(), action='export_batch'),
                    {'action': 'export', 'chat': 'a', 'start': '2026-10-17', 'end': '2026-10-17',
                     'path': str(self.folder / 'single.html')}]
        output = io.StringIO()
        with patch.object(reader_module, 'Reader', return_value=self.reader), \
             patch.object(sys, 'stdin', io.StringIO('\n'.join(json.dumps(r) for r in requests))), \
             patch.object(sys, 'stdout', output):
            reader_module.serve()
        frames = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([f.get('event', 'result') for f in frames], ['progress', 'progress', 'result', 'result'])
        self.assertEqual(frames[2]['data']['count'], 3)
        self.assertEqual(frames[3]['data']['count'], 2)
        self.assertTrue(frames[2]['ok'] and frames[3]['ok'])


if __name__ == '__main__':
    unittest.main()
