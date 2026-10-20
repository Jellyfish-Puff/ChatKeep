"""Bounded, read-only local image comparison. Output contains only statistics."""
from contextlib import ExitStack, closing
import collections
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from PIL import Image
import reader as mod
from image_resources import image_hashes


def check(limit=50):
    counts = collections.Counter()
    resolutions = []
    users = []
    for user in mod.accounts():
        session = ROOT / 'private/cache' / (hashlib.sha256(str(user / 'db_storage/session/session.db').encode()).hexdigest()[:20] + '.db')
        if session.exists():
            users.append((user, session))
    if len(users) != 1:
        return {'cachedAccounts': len(users), 'status': 'no_unique_cached_account'}
    user, session = users[0]
    reader = mod.Reader()
    reader.user = user
    original_processes = mod.processes
    # No live memory scanning, database refresh, network, or exported real images.
    mod.processes = lambda: iter(())
    started = time.monotonic()
    try:
        with ExitStack() as stack:
            db = stack.enter_context(closing(sqlite3.connect(session.resolve().as_uri() + '?mode=ro', uri=True)))
            groups = [row[0] for row in db.execute("SELECT username FROM SessionTable WHERE is_hidden=0 AND username LIKE '%@chatroom' ORDER BY sort_timestamp DESC LIMIT 20")]
            shards = []
            for path in (ROOT / 'private/cache').glob('*.db'):
                db = stack.enter_context(closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)))
                tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if any(t.startswith('Msg_') for t in tables):
                    db.set_progress_handler(lambda: int(time.monotonic() - started > 60), 10000)
                    shards.append((db, tables))
            for chat in groups:
                table = 'Msg_' + hashlib.md5(chat.encode()).hexdigest()
                for db, tables in shards:
                    if table not in tables:
                        continue
                    for a, b, packed in db.execute(f'SELECT message_content,compress_content,packed_info_data FROM "{table}" WHERE (local_type & 4294967295)=3 ORDER BY local_id DESC LIMIT 5'):
                        body = mod.text(a or b)
                        uri = reader.image(chat, body, packed)
                        info = reader.last_image_info
                        counts['sampled'] += 1
                        counts['selected_' + info['quality']] += 1
                        counts['converted_wxgf'] += info['converted']
                        counts['with_unavailable_alternatives'] += info['unavailableAlternatives']
                        # Reproduce the old first-readable-hash behavior for a size comparison.
                        old_size = (0, 0)
                        for digest in image_hashes(body, packed):
                            matches = reader.image_index[chat].get(digest, [])
                            for tier in ('large', 'image', 'thumbnail'):
                                match = next((p for p, t in reversed(matches) if t == tier), None)
                                if match is None:
                                    continue
                                try:
                                    with Image.open(io.BytesIO(reader.decode_image(match.read_bytes()))) as image:
                                        image.verify()
                                        old_size = image.size
                                except (ValueError, OSError):
                                    continue
                                break
                            if old_size != (0, 0):
                                break
                        area = info['width'] * info['height']
                        counts['larger_than_old_selection'] += area > old_size[0] * old_size[1]
                        counts['smaller_than_old_selection'] += bool(uri) and area < old_size[0] * old_size[1]
                        if uri:
                            resolutions.append((info['width'], info['height']))
                        if counts['sampled'] >= limit or time.monotonic() - started > 60:
                            return report(counts, resolutions)
    finally:
        reader.close()
        mod.processes = original_processes
    return report(counts, resolutions)


def report(counts, resolutions):
    return {'counts': dict(counts), 'largest_selected_pixels': max(resolutions, key=lambda size: size[0] * size[1]) if resolutions else None,
            'live_memory_scan': False, 'real_images_exported': False}


if __name__ == '__main__':
    result = check()
    print(json.dumps(result, ensure_ascii=False))
    if result.get('counts', {}).get('smaller_than_old_selection'):
        sys.exit(1)
