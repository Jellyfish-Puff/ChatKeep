"""Offline HTML rendering shared by single and batch exports."""
import datetime
import html
import os
from pathlib import Path
import tempfile

from message_content import export_text, html_text


def date_range(request):
    start = datetime.datetime.strptime(request['start'], '%Y-%m-%d')
    last = datetime.datetime.strptime(request['end'], '%Y-%m-%d')
    if start > last:
        raise ValueError('开始日期不能晚于结束日期')
    return start, last + datetime.timedelta(days=1)


def document_start(title, start, end, description):
    title = html.escape(title)
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'">
<title>''' + title + '''</title><style>
body{font:15px/1.65 "Microsoft YaHei",sans-serif;background:#f4f5f7;color:#202724;margin:0}
main{max-width:920px;margin:auto;padding:32px}h1{font-size:24px}h2{font-size:20px}
p,header{color:#59665f}article{margin:24px 0}
article div{display:inline-block;background:white;border-radius:10px;padding:12px 16px;white-space:pre-wrap;overflow-wrap:anywhere;max-width:85%}
.self{text-align:right}.self div{background:#d9f2dc;text-align:left}header{font-size:12px;margin:6px}
img{max-width:100%;max-height:600px}footer{margin-top:40px;color:#59665f}
section{border-top:1px solid #d9e2dd;margin-top:32px;padding-top:16px}nav a{display:block;color:#087f65;overflow-wrap:anywhere}
.image-frame{overflow:auto;max-height:85vh}.image-view summary{list-style:none;cursor:zoom-in}
.image-view summary:focus-visible{outline:2px solid #087f65}.image-view[open] summary{cursor:zoom-out}
.image-view[open] img{max-width:none;max-height:none}.image-view span{font-size:12px;color:#087f65}
.image-original-label{display:none}.image-view[open] .image-fit-label{display:none}.image-view[open] .image-original-label{display:inline}
</style><main><h1>''' + title + '</h1><p>' + html.escape(start + ' — ' + end + ' · ' + description) + '</p>'


def document_end():
    return '<footer>由聊存 ChatKeep 生成 · 图片已嵌入文件 · 本地缺失资源会保留占位说明</footer></main></html>'


def render_messages(records, article_numbers):
    blocks = []
    for m in records:
        content = ('<details class="image-view"><summary><span class="image-fit-label">点击图片查看原始尺寸</span><span class="image-original-label">点击图片恢复页面预览</span><br><img src="' + html.escape(m['image'], quote=True) + '" alt="聊天图片"></summary></details>') if m['image'] else html_text(export_text(m, article_numbers), m.get('links', []))
        if m['image'] and m.get('imageNote'):
            content += '<br><small>' + html.escape(m['imageNote']) + '</small>'
        stamp = datetime.datetime.fromtimestamp(m['time']).strftime('%Y-%m-%d %H:%M:%S')
        blocks.append('<article class="' + ('self' if m['self'] else '') + '"><header>' + html.escape(m['sender']) + ' · ' + stamp + '</header><div' + (' class="image-frame"' if m['image'] else '') + '>' + content + '</div></article>')
    return ''.join(blocks)


def record_stats(records):
    return {'count': len(records),
            'missingImages': sum(m['type'] == 3 and not m['image'] for m in records),
            'thumbnailImages': sum(bool(m['image']) and m.get('imageQuality') == 'thumbnail' for m in records),
            'convertedImages': sum(bool(m['image']) and bool(m.get('imageConverted')) for m in records),
            'imagesWithUnavailableAlternatives': sum(bool(m['image']) and bool(m.get('imageUnavailableAlternatives')) for m in records)}


def write_document(destination, parts):
    """Stage next to the destination; leave existing exports intact on errors."""
    destination = Path(destination)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destination.parent,
                                         prefix='.chatkeep-', suffix='.partial', delete=False) as output:
            temporary = Path(output.name)
            for part in parts:
                output.write(part)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
