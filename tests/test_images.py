"""Synthetic images only; no local chat files, keys, or messages are fixtures."""
import base64
from contextlib import closing
import datetime
import hashlib
import io
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from reader import Reader
from image_codec import WxgfDecoder, decode_wxgf
from image_resources import image_hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

TEMP = Path(__file__).resolve().parents[1] / 'private/test-temp'
TEMP.mkdir(parents=True, exist_ok=True)
FIXTURE = Path(__file__).with_name('fixtures') / 'synthetic-static.wxgf'
DIGEST = '1' * 32
OTHER = '2' * 32
CHAT = 'synthetic@chatroom'


def image_bytes(size, format='PNG'):
    output = io.BytesIO()
    Image.new('RGB', size, '#0a9b7d').save(output, format=format)
    return output.getvalue()


def dimensions(uri):
    with Image.open(io.BytesIO(base64.b64decode(uri.split(',', 1)[1]))) as image:
        return image.size


class LocalImageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=TEMP)
        self.addCleanup(self.directory.cleanup)
        self.reader = Reader()
        self.addCleanup(self.reader.close)
        self.reader.user = Path(self.directory.name) / 'wxid_synthetic_abcd'
        self.folder = self.reader.user / 'msg/attach' / hashlib.md5(CHAT.encode()).hexdigest()
        self.folder.mkdir(parents=True)

    def write(self, name, size, month='2026-10'):
        path = self.folder / month / 'Img' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image_bytes(size))
        return path

    def resolve(self, digest=DIGEST, packed=None):
        return self.reader.image(CHAT, f'<msg><img md5="{digest}"/></msg>', packed)

    def test_all_hashes_are_compared_before_thumbnail_is_chosen(self):
        self.write(DIGEST + '_t.dat', (120, 80))
        original = self.write(OTHER + '_h.dat', (1600, 900))
        uri = self.resolve(packed=OTHER.encode())
        self.assertEqual(dimensions(uri), (1600, 900))
        self.assertEqual(self.reader.last_image_info['quality'], 'large')
        self.assertEqual(base64.b64decode(uri.split(',', 1)[1]), original.read_bytes())

    def test_pixel_dimensions_override_filename_tier_and_month_collisions(self):
        self.write(DIGEST + '_h.dat', (300, 200))
        self.write(DIGEST + '.dat', (2400, 1600), month='2026-09')
        self.write(DIGEST + '.dat', (600, 400), month='2026-10')
        self.assertEqual(dimensions(self.resolve()), (2400, 1600))
        self.assertEqual(self.reader.last_image_info['quality'], 'image')

    def test_only_thumbnail_and_undecodable_alternative_are_distinguished(self):
        self.write(DIGEST + '_t.dat', (120, 80))
        self.assertEqual(dimensions(self.resolve()), (120, 80))
        self.assertIn('仅找到缩略图', self.reader.last_image_info['note'])
        path = self.folder / '2026-10/Img' / (DIGEST + '_h.dat')
        path.write_bytes(b'not an image')
        self.reader.image_index.clear()
        self.assertEqual(dimensions(self.resolve()), (120, 80))
        self.assertIn('非缩略图候选暂无法', self.reader.last_image_info['note'])
        self.assertTrue(self.reader.last_image_info['unavailableAlternatives'])

    def test_missing_and_unreadable_are_distinct_and_metadata_does_not_leak(self):
        self.write(DIGEST + '_t.dat', (120, 80))
        self.resolve()
        self.assertIsNone(self.resolve(digest=OTHER))
        self.assertIn('未找到关联', self.reader.last_image_note)
        self.assertEqual(self.reader.last_image_info['width'], 0)
        self.write(OTHER + '_h.dat', (120, 80)).write_bytes(b'bad image')
        self.reader.image_index.clear()
        self.assertIsNone(self.resolve(digest=OTHER))
        self.assertIn('文件存在', self.reader.last_image_note)
        self.assertNotIn(self.directory.name, self.reader.last_image_note)

    def test_other_chat_images_are_not_candidates(self):
        self.write(DIGEST + '_t.dat', (120, 80))
        other_folder = self.reader.user / 'msg/attach' / hashlib.md5(b'other@chatroom').hexdigest()
        other_folder.mkdir()
        (other_folder / (DIGEST + '_h.dat')).write_bytes(image_bytes((1600, 900)))
        self.assertEqual(dimensions(self.resolve()), (120, 80))

    def test_new_local_download_is_seen_on_next_messages_or_export(self):
        self.write(DIGEST + '_t.dat', (120, 80))
        table = 'Msg_' + hashlib.md5(CHAT.encode()).hexdigest()
        database = Path(self.directory.name) / 'messages.db'
        stamp = int(datetime.datetime(2026, 10, 20).timestamp())
        with closing(sqlite3.connect(database)) as db:
            db.execute('CREATE TABLE Name2Id(user_name TEXT)')
            db.execute("INSERT INTO Name2Id VALUES ('wxid_synthetic')")
            db.execute(f'CREATE TABLE "{table}"(local_id INTEGER,local_type INTEGER,sort_seq INTEGER,real_sender_id INTEGER,create_time INTEGER,message_content TEXT)')
            db.execute(f'INSERT INTO "{table}" VALUES (1,3,1,1,?,?)', (stamp, f'<msg><img md5="{DIGEST}"/></msg>'))
            db.commit()
        self.reader.databases = lambda: [(Path('message_0.db'), database)]
        first = self.reader.messages(CHAT)
        self.assertEqual(first[0]['imageQuality'], 'thumbnail')
        self.write(DIGEST + '_h.dat', (1600, 900))
        request = {'chat': CHAT, 'start': '2026-10-20', 'end': '2026-10-20', 'path': str(Path(self.directory.name) / 'export.html')}
        result = self.reader.export(request)
        self.assertEqual(result['thumbnailImages'], 0)
        doc = Path(request['path']).read_text(encoding='utf-8')
        self.assertIn('1600 × 900', doc)
        self.assertIn('<details class="image-view">', doc)
        self.assertIn('查看原始尺寸', doc)
        self.assertEqual(doc.count('data:image/png;base64,'), 1)
        self.assertNotIn('<script', doc)
        self.assertIn("default-src 'none'", doc)

    def test_wxgf_candidate_is_used_without_scaling(self):
        self.write(DIGEST + '_t.dat', (120, 80))
        path = self.folder / '2026-10/Img' / (DIGEST + '.dat')
        path.write_bytes(FIXTURE.read_bytes())
        uri = self.resolve()
        self.assertEqual(dimensions(uri), (960, 540))
        self.assertTrue(self.reader.last_image_info['converted'])
        self.assertIn('保持像素尺寸', self.reader.last_image_note)
        self.assertFalse(self.reader.last_image_info['unavailableAlternatives'])

    def test_corrupt_wxgf_falls_back_and_truncated_dat_does_not_abort(self):
        self.write(DIGEST + '_t.dat', (120, 80))
        path = self.folder / '2026-10/Img' / (DIGEST + '.dat')
        path.write_bytes(b'wxgf' + bytes(100))
        self.assertEqual(dimensions(self.resolve()), (120, 80))
        self.assertIn('候选暂无法', self.reader.last_image_note)
        with self.assertRaises(ValueError):
            self.reader.decode_image(b'\x07\x08V2\x08\x07')

    def test_hashes_include_original_source_and_reject_partial_hex_substrings(self):
        hashes = image_hashes(f'<img originsourcemd5="{DIGEST}" cdnthumbmd5="{OTHER}"/>', (DIGEST + 'a').encode())
        self.assertEqual(hashes, [DIGEST, OTHER])

    def test_valid_thumbnail_recovers_xor_tail_for_larger_encrypted_wxgf(self):
        key, xor = b'0123456789ABCDEF', 167
        self.reader.image_key = key
        self.reader.image_key_attempted = True
        def encrypt(raw):
            prefix = raw[:32] + bytes([16]) * 16
            cipher = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
            return b'\x07\x08V2\x08\x07' + struct.pack('<II', 32, 64) + b'\0' + cipher.update(prefix) + cipher.finalize() + raw[32:-64] + bytes(v ^ xor for v in raw[-64:])
        self.write(DIGEST + '_t.dat', (120, 80)).write_bytes(encrypt(image_bytes((120, 80), 'JPEG')))
        path = self.folder / '2026-10/Img' / (DIGEST + '.dat')
        path.write_bytes(encrypt(FIXTURE.read_bytes()))
        self.assertEqual(dimensions(self.resolve()), (960, 540))
        self.assertEqual(self.reader.image_xor, xor)

    def test_missing_locator_does_not_scan_the_chat_attachment_directory(self):
        with patch('reader.build_image_index', side_effect=AssertionError('unnecessary scan')):
            self.assertIsNone(self.reader.image(CHAT, '<img/>'))
        self.assertIn('缺少', self.reader.last_image_note)


class CodecTests(unittest.TestCase):
    def test_static_hevc_conversion_preserves_size_and_color(self):
        png, info = decode_wxgf(FIXTURE.read_bytes())
        with Image.open(io.BytesIO(png)) as image:
            self.assertEqual(image.size, (960, 540))
            red, green, blue = image.getpixel((100, 100))
            self.assertGreater(green, red + 60)
            self.assertGreater(green, blue + 20)
        self.assertFalse(info['firstFrameOnly'])

    def test_multiple_streams_are_explicitly_labelled_first_frame_only(self):
        fixture = FIXTURE.read_bytes()
        png, info = decode_wxgf(fixture + fixture[16:])
        self.assertTrue(info['firstFrameOnly'])
        with Image.open(io.BytesIO(png)) as image:
            self.assertEqual(image.size, (960, 540))

    def test_isolated_decoder_reuses_worker_and_closes_it(self):
        decoder = WxgfDecoder()
        try:
            first, _ = decoder.decode(FIXTURE.read_bytes())
            process = decoder.process
            second, _ = decoder.decode(FIXTURE.read_bytes())
            self.assertIs(process, decoder.process)
            self.assertEqual(first, second)
        finally:
            decoder.close()
        self.assertIsNotNone(process.poll())

    def test_native_decoder_timeout_stops_only_its_worker(self):
        decoder = WxgfDecoder(timeout=0.1)
        def start():
            decoder.process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        started = time.monotonic()
        with patch.object(decoder, '_start', start):
            with self.assertRaisesRegex(ValueError, '超时'):
                decoder.decode(FIXTURE.read_bytes())
        self.assertLess(time.monotonic() - started, 5)
        self.assertIsNone(decoder.process)


if __name__ == '__main__':
    unittest.main()
