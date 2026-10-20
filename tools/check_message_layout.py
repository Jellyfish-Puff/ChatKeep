"""Exercise real WPF layout, optionally with cached data held only in memory.

Build tools/MessageLayoutCheck first. No WeChat UI, live process access, database
refresh, video decoding, screenshots, clipboard changes, or chat files are used.
"""
import argparse
import base64
from collections import Counter
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def synthetic():
    from PIL import Image
    encoded = io.BytesIO()
    Image.new('RGB', (960, 540), '#dbf2df').save(encoded, format='PNG')
    image = 'data:image/png;base64,' + base64.b64encode(encoded.getvalue()).decode()
    body = '[链接]\n标题：工作安排\n摘要：' + ('宣传安排1️⃣2️⃣3️⃣请按时间完成。' * 30)
    body += '\n链接：https://example.org/' + 'abcdef0123456789' * 25
    result = []
    for i in range(100):
        result.append({'id': str(i), 'time': 1792249200 + i, 'sender': '合成示例', 'self': False,
                       'type': 49 if i == 73 else (3 if i % 2 == 0 else 43),
                       'text': body if i == 73 else ('[视频]' if i % 2 else '[图片]'),
                       'image': image if i % 2 == 0 else None, 'imageWidth': 960,
                       'imageQuality': ('thumbnail', 'image', 'large')[i % 6 // 2]})
    return result


def cached(group, pages):
    import reader as mod
    users = []
    def cache_path(path):
        return ROOT / 'private/cache' / (hashlib.sha256(str(path).encode()).hexdigest()[:20] + '.db')
    for user in mod.accounts():
        if cache_path(user / 'db_storage/session/session.db').exists():
            users.append(user)
    if len(users) != 1:
        raise RuntimeError('需要唯一的已有账号缓存')
    user = users[0]
    contact = cache_path(user / 'db_storage/contact/contact.db')
    with closing(sqlite3.connect(contact.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        groups = [r[0] for r in db.execute('SELECT username FROM contact WHERE username LIKE ? AND (nick_name=? OR remark=?)', ('%@chatroom', group, group))]
        names = {r[0]: r[2] or r[1] or r[0] for r in db.execute('SELECT username,nick_name,remark FROM contact')}
    if len(groups) != 1:
        raise RuntimeError('缓存中没有唯一匹配的群聊')
    reader = mod.Reader()
    reader.user = user
    reader.names = names
    reader.shards = [(p, cache_path(p)) for p in sorted((user / 'db_storage/message').glob('message_*.db'))
                     if p.stem[8:].isdigit() and cache_path(p).exists()]
    if not reader.shards:
        raise RuntimeError('没有已有消息缓存')
    # Do not permit live image-key scanning during this local check.
    mod.processes = lambda: iter(())
    data, before = [], None
    try:
        for _ in range(pages):
            page = reader.messages(groups[0], before=before)
            if not page:
                break
            data = page + data
            before = min(m['time'] for m in page)
    finally:
        reader.close()
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', help='仅验证指定群的已有缓存，不打印群名或正文')
    parser.add_argument('--pages', type=int, choices=range(1, 4), default=1)
    parser.add_argument('--viewer-screenshots', help='仅保存自行生成的图片查看器测试画面')
    args = parser.parse_args()
    started = time.monotonic()
    data = cached(args.group, args.pages) if args.group else synthetic()
    read_seconds = round(time.monotonic() - started, 3)
    executable = ROOT / 'tools/MessageLayoutCheck/bin/Release/net10.0-windows/MessageLayoutCheck.dll'
    try:
        command = ['dotnet', str(executable)]
        if args.viewer_screenshots:
            command.append(str(Path(args.viewer_screenshots).resolve()))
        run = subprocess.run(command, input=json.dumps(data).encode(),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        report = {'ok': run.returncode == 0, 'source': 'cached' if args.group else 'synthetic',
                  'messages': len(data), 'types': dict(Counter(m.get('type', 0) for m in data)),
                  'read_seconds': read_seconds, 'exit_code': run.returncode}
        if run.stdout:
            report['layout'] = json.loads(run.stdout.decode('utf-8'))
    except subprocess.TimeoutExpired:
        report = {'ok': False, 'error': 'layout_timeout'}
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
