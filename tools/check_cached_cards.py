"""Bounded, read-only card validation. Prints statistics, never chat content."""
import collections
from contextlib import ExitStack, closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from reader import text
from message_content import parse_message


def check(cache, limit=400):
    counts = collections.Counter()
    kinds = collections.Counter()
    groups, shards = [], []
    started = time.monotonic()
    with ExitStack() as stack:
        for path in cache.glob('*.db'):
            db = stack.enter_context(closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)))
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'SessionTable' in tables:
                groups = [r[0] for r in db.execute("SELECT username FROM SessionTable WHERE is_hidden=0 AND username LIKE '%@chatroom' ORDER BY sort_timestamp DESC LIMIT 30")]
            if any(t.startswith('Msg_') for t in tables):
                shards.append((db, tables))
        for group in groups:
            table = 'Msg_' + hashlib.md5(group.encode()).hexdigest()
            for db, tables in shards:
                if table not in tables:
                    continue
                db.set_progress_handler(lambda: int(time.monotonic() - started > 15), 10000)
                try:
                    for raw_kind, a, b in db.execute(f'SELECT local_type,message_content,compress_content FROM "{table}" WHERE (local_type & 4294967295) IN (49,10000,10002) ORDER BY local_id DESC LIMIT 30'):
                        body = text(a or b)
                        result = parse_message(int(raw_kind) & 0xffffffff, body)
                        counts['sampled'] += 1
                        kinds[result['messageKind']] += 1
                        counts['article_mentions'] += len(result['articles'])
                        counts['article_mentions_with_title'] += sum(bool(a['title']) for a in result['articles'])
                        counts['safe_links'] += len(result['links'])
                        counts['unresolved_pat_placeholders'] += result['messageKind'] == 'pat' and '${' in result['text']
                        counts['raw_xml_in_output'] += any(tag in result['text'] for tag in ('<appmsg', '<patinfo', '<refermsg', '<wcpayinfo', '<sysmsg'))
                        if counts['sampled'] >= limit:
                            return {'counts': dict(counts), 'message_kinds': dict(kinds)}
                except sqlite3.OperationalError:
                    counts['bounded_query_stopped'] += 1
                    return {'counts': dict(counts), 'message_kinds': dict(kinds)}
    return {'counts': dict(counts), 'message_kinds': dict(kinds)}


if __name__ == '__main__':
    report = check(ROOT / 'private' / 'cache')
    print(json.dumps(report, ensure_ascii=False))
    if report['counts'].get('raw_xml_in_output') or report['counts'].get('unresolved_pat_placeholders'):
        sys.exit(1)
