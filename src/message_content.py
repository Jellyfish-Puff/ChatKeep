"""Offline rendering of locally stored WeChat cards; never fetches their URLs."""
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlsplit


MAX_XML = 1024 * 1024
MAX_QUOTE_DEPTH = 3


def safe_url(value):
    value = html.unescape(value).strip()
    if not value or re.search(r'[\s\x00-\x1f\x7f]', value):
        return ''
    try:
        parts = urlsplit(value)
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
            return ''
        if parts.port is not None and not 0 < parts.port < 65536:
            return ''
    except ValueError:
        return ''
    return value


def article_key(url):
    """Only merge proven article IDs, short paths, or identical original URLs."""
    url = safe_url(url)
    if not url:
        return ''
    parts = urlsplit(url)
    if parts.hostname != 'mp.weixin.qq.com' or not (parts.path == '/s' or parts.path.startswith('/s/')):
        return ''
    query = parse_qs(parts.query, keep_blank_values=True)
    identity = ['url', url]
    if parts.path == '/s' and all(len(query.get(k, [])) == 1 and query[k][0] for k in ('__biz', 'mid', 'idx')):
        identity = ['article', query['__biz'][0], query['mid'][0], query['idx'][0]]
    elif re.fullmatch(r'/s/[A-Za-z0-9_-]+', parts.path):
        identity = ['short', parts.path]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def _xml(body):
    if len(body) > MAX_XML or re.search(r'<!\s*(DOCTYPE|ENTITY)', body, re.I):
        return None
    body = body.lstrip('\ufeff \t\r\n')
    # Group messages and quoted cards can retain a sender prefix.
    body = re.sub(r'^[^<\n]{1,256}:\r?\n', '', body, count=1)
    try:
        root = ET.fromstring(body)
        pending = [(root, 0)]
        while pending:
            node, depth = pending.pop()
            if depth > 40:
                return None
            pending.extend((child, depth + 1) for child in node)
        return root
    except (ET.ParseError, ValueError):
        return None


def _field(node, path):
    return (node.findtext(path) or '').strip() if node is not None else ''


def _result(kind, lines, links=(), articles=()):
    return {'messageKind': kind, 'text': '\n'.join(line for line in lines if line),
            'links': list(dict.fromkeys(links)), 'articles': list(articles)}


def _urls(body):
    values = re.findall(r'https?://[^\s<>"\x27\[\]]+', body)
    return list(dict.fromkeys(url for value in values if (url := safe_url(value.rstrip('。，；！？、）)')))))


def _article(url, title='', source=''):
    key = article_key(url)
    return {'key': key, 'url': url, 'title': title, 'source': source} if key else None


def _pat(info, names):
    sender, target = _field(info, 'fromusername'), _field(info, 'pattedusername')
    aliases = dict(names)
    aliases.update(fromusername=names.get(sender, '未知成员'), pattedusername=names.get(target, '未知成员'))
    template = _field(info, 'template')
    if template:
        return re.sub(r'\$\{([^}]+)\}', lambda m: aliases.get(m[1], '未知成员'), template)
    if sender or target:
        return names.get(sender, '未知成员') + ' 拍了拍 ' + names.get(target, '未知成员') + _field(info, 'patsuffix')
    return ''


def _system(root, body, names):
    if root is None:
        # Ordinary system text is useful; unparsed XML must not leak into exports.
        return _result('system', ['[系统消息]', body if '<' not in body else '内容暂无法解析'])
    if root.get('type') == 'revokemsg':
        return _result('revoke', ['[撤回消息]', _field(root, 'revokemsg/content') or _field(root, 'revokemsg/replacemsg')])
    pat = root.find('.//patinfo')
    if pat is not None:
        return _result('pat', ['[拍一拍]', _pat(pat, names)])
    plain = _field(root, './/content_template/plain')
    if not plain:
        template = _field(root, './/content_template/template')
        for link in root.findall('.//link_list/link'):
            members = [(_field(m, 'nickname') or names.get(_field(m, 'username'), '未知成员'))
                       for m in link.findall('.//member')]
            replacement = (_field(link, 'separator') or '、').join(members) or _field(link, 'plain')
            name = link.get('name', '')
            if name and replacement:
                template = template.replace('$' + name + '$', replacement).replace('${' + name + '}', replacement)
        plain = template if '$' not in template else ''
    return _result('system', ['[系统消息]', plain or _field(root, 'content') or '内容暂未支持'])


def parse_message(kind, body, names=None, depth=0):
    """Return display text and safe link/article metadata, excluding opaque payloads."""
    names = names or {}
    if depth > MAX_QUOTE_DEPTH:
        return _result('quote', ['[引用内容层级过多，未展开]'])
    if kind == 1:
        links = _urls(body)
        articles = [a for url in links if (a := _article(url))]
        return _result('text', [body], links, articles)
    if kind not in (49, 10000, 10002):
        labels = {3: '图片', 34: '语音', 43: '视频', 47: '表情'}
        return _result('other', ['[' + labels.get(kind, '暂未支持的消息') + ']'])
    root = _xml(body)
    if kind in (10000, 10002):
        return _system(root, body, names)
    app = root if root is not None and root.tag == 'appmsg' else (root.find('appmsg') if root is not None else None)
    if app is None:
        # Recover only safe visible URLs, never an XML payload or native payment URI.
        links = _urls(body) if len(body) <= MAX_XML and not re.search(r'<!\s*(DOCTYPE|ENTITY)', body, re.I) else []
        articles = [a for url in links if (a := _article(url))]
        return _result('unknown', ['[卡片：内容暂无法解析]'] + ['链接：' + u for u in links], links, articles)
    subtype = _field(app, 'type')
    title, description = _field(app, 'title'), _field(app, 'des')
    if subtype == '5':
        url = safe_url(_field(app, 'url'))
        source = _field(app, 'sourcedisplayname')
        article = _article(url, title, source)
        is_article = bool(article) or _field(app, 'sourceusername').startswith('gh_')
        lines = ['[公众号文章]' if is_article else '[链接]', '标题：' + (title or '本地消息未提供'),
                 '公众号：' + source if is_article and source else '',
                 '摘要：' + description if description else '',
                 '链接：' + url if url else '链接：本地消息未提供有效网址']
        return _result('article' if is_article else 'link', lines, [url] if url else [], [article] if article else [])
    if subtype == '57':
        ref = app.find('refermsg')
        if ref is None:
            return _result('quote', ['[引用回复]', title, '引用内容：本地消息未提供'])
        ref_type = _field(ref, 'type')
        content = _field(ref, 'content')
        quoted = parse_message(int(ref_type) & 0xffffffff if re.fullmatch(r'[0-9]{1,20}', ref_type) else 0,
                               content, names, depth + 1) if content else _result('unknown', ['[引用内容：本地消息未提供]'])
        sender = _field(ref, 'displayname') or names.get(_field(ref, 'fromusr'), '未知发送者')
        return _result('quote', ['[引用回复]', title, '引用 ' + sender + '：', quoted['text']], quoted['links'], quoted['articles'])
    if subtype == '62':
        return _result('pat', ['[拍一拍]', _pat(app.find('patinfo'), names)])
    if subtype in ('2000', '2001'):
        red_packet = subtype == '2001'
        memo = _field(app, 'wcpayinfo/pay_memo')
        hint = _field(app, 'wcpayinfo/hinttext')
        # Values describe this message only, not a live payment or receipt status.
        lines = ['[红包]' if red_packet else '[转账]'] + list(dict.fromkeys(v for v in (title, description, hint) if v))
        if memo and memo not in lines:
            lines.append('备注：' + memo)
        return _result('red_packet' if red_packet else 'transfer', lines)
    if subtype == '6':
        return _result('file', ['[文件]', '文件名：' + (title or '本地消息未提供')])
    labels = {'19': ('record', '合并聊天记录'), '33': ('miniapp', '小程序'), '36': ('miniapp', '小程序'),
              '51': ('channels', '视频号'), '3': ('music', '音乐分享')}
    if subtype in labels:
        category, label = labels[subtype]
        summary = title or (_field(app, 'finderFeed/desc') if subtype == '51' else '')
        return _result(category, ['[' + label + ']', summary, description if description != summary else ''])
    url = safe_url(_field(app, 'url'))
    return _result('unknown', ['[暂未支持的卡片' + ('（类型 ' + subtype + '）' if subtype.isdigit() else '') + ']',
                               title, '链接：' + url if url else ''], [url] if url else [])


def export_text(message, article_numbers):
    """Assign article numbers within this export, including quoted/pasted articles."""
    labels = []
    for article in message.get('articles', []):
        key = article['key']
        if key not in article_numbers:
            article_numbers[key] = f'A{len(article_numbers) + 1:03d}'
        label = article_numbers[key]
        if label not in labels:
            labels.append(label)
    return message['text'] + ('\n文章编号：' + '、'.join(labels) if labels else '')


def html_text(value, links):
    """Escape everything, turning only known HTTP(S) links into manual navigation."""
    urls = sorted({u for u in links if safe_url(u) == u}, key=len, reverse=True)
    if not urls:
        return html.escape(value)
    pattern = re.compile('|'.join(re.escape(u) for u in urls))
    output, offset = [], 0
    for match in pattern.finditer(value):
        output.append(html.escape(value[offset:match.start()]))
        escaped = html.escape(match[0], quote=True)
        output.append('<a href="' + escaped + '" target="_blank" rel="noopener noreferrer">' + escaped + '</a>')
        offset = match.end()
    output.append(html.escape(value[offset:]))
    return ''.join(output)
