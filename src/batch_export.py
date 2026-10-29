"""Export date ranges without loading conversations in the desktop view."""
import datetime
import html
from pathlib import Path
import re

from html_export import date_range, document_start, document_end, render_messages, record_stats, write_document


def export_single(reader, request):
    start, end = date_range(request)
    selected = request.get('selected')
    records = reader.messages(request['chat'], int(start.timestamp()), int(end.timestamp()),
                              limit=None, selected=set(selected) if selected is not None else None)
    if not records:
        raise ValueError('所选范围没有消息，请调整日期或勾选范围。')
    destination = Path(request['path'])
    write_document(destination, [document_start(reader.names.get(request['chat'], request['chat']),
                                               request['start'], request['end'], f'{len(records)} 条消息'),
                                 render_messages(records, {}), document_end()])
    return dict(record_stats(records), path=str(destination))


class _EmptyBatch(Exception):
    pass


def export_batch(reader, request, progress=None):
    start, end = date_range(request)
    chats = request.get('chats')
    if not isinstance(chats, list) or not chats or any(not isinstance(c, str) or not c for c in chats):
        raise ValueError('请至少选择一个群聊。')
    chats = list(dict.fromkeys(chats))
    mode = request.get('mode')
    if mode not in ('merged', 'separate'):
        raise ValueError('请选择合并导出或分开导出。')
    parent = Path(request['folder'])
    if not parent.is_dir():
        raise ValueError('请选择存在的保存文件夹。')
    # A fresh directory also separates duplicate/sanitized names and repeated runs.
    stem = '批量导出_' + start.strftime('%Y%m%d') + '_' + (end - datetime.timedelta(days=1)).strftime('%Y%m%d')
    folder = parent / (stem + '_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    folder.mkdir()
    results, article_numbers = [], {}
    totals = dict.fromkeys(('count', 'missingImages', 'thumbnailImages', 'convertedImages', 'imagesWithUnavailableAlternatives'), 0)
    merged_path = folder / (stem + '_合并.html')

    def parts():
        if mode == 'merged':
            yield document_start('批量群聊记录', request['start'], request['end'], f'{len(chats)} 个群聊 · 按群聊分区')
            yield '<nav aria-label="群聊目录">' + ''.join('<a href="#group-' + str(i) + '">' + html.escape(reader.names.get(c, c)) + '</a>' for i, c in enumerate(chats, 1)) + '</nav>'
        for index, chat in enumerate(chats, 1):
            name = reader.names.get(chat, chat)
            if progress:
                progress({'index': index, 'total': len(chats), 'name': name})
            result = {'chat': chat, 'name': name, 'status': 'empty', 'count': 0}
            content = ''
            try:
                records = reader.messages(chat, int(start.timestamp()), int(end.timestamp()), limit=None)
                if records:
                    numbers = dict(article_numbers) if mode == 'merged' else {}
                    content = render_messages(records, numbers)
                    stats = record_stats(records)
                    if mode == 'separate':
                        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')[:80] or '群聊'
                        destination = folder / f'{index:02d}_{safe}_{start:%Y%m%d}_{end - datetime.timedelta(days=1):%Y%m%d}.html'
                        write_document(destination, [document_start(name, request['start'], request['end'], f'{len(records)} 条消息'), content, document_end()])
                        result['path'] = str(destination)
                    article_numbers.update(numbers)
                    result.update(stats, status='exported')
                    for key in totals:
                        totals[key] += stats[key]
                del records
            except Exception as exc:
                result.update(status='failed', error=str(exc))
                content = ''
            results.append(result)
            if mode == 'merged':
                yield '<section id="group-' + str(index) + '"><h2>' + html.escape(name) + '</h2>'
                if result['status'] == 'exported':
                    yield '<p>' + str(result['count']) + ' 条消息</p>' + content
                else:
                    yield '<p>' + html.escape('所选日期范围没有消息。' if result['status'] == 'empty' else '此群导出失败：' + result['error']) + '</p>'
                yield '</section>'
        if mode == 'merged':
            if not totals['count']:
                raise _EmptyBatch()
            yield '<p>合计 ' + str(totals['count']) + ' 条消息 · ' + str(sum(r['status'] == 'failed' for r in results)) + ' 个群聊导出失败</p>' + document_end()

    try:
        if mode == 'merged':
            try:
                write_document(merged_path, parts())
            except _EmptyBatch:
                pass
        else:
            for _ in parts():
                pass
    finally:
        if not any(folder.iterdir()):
            folder.rmdir()
    return dict(totals, results=results, folder=str(folder) if totals['count'] else None,
                path=str(merged_path) if mode == 'merged' and totals['count'] else None)
