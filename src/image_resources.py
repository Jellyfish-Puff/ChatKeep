"""Find message-associated files and select the largest valid local image."""
import base64
import io
import re
from PIL import Image
from image_codec import MAX_INPUT, MAX_PIXELS

RESOURCE_NAME = re.compile(r'^([a-f0-9]{32})(_h|_t)?\.(dat|jpe?g|png|gif|webp)$', re.I)


def image_hashes(body, packed=None):
    hashes = re.findall(r'(?<![\w])(?:md5|cdnthumbmd5|originsourcemd5)\s*=\s*["\x27]([a-fA-F0-9]{32})["\x27]', body)
    hashes.extend(v.decode() for v in re.findall(rb'(?<![a-fA-F0-9])[a-fA-F0-9]{32}(?![a-fA-F0-9])', bytes(packed or b'')[:4*1024*1024]))
    return list(dict.fromkeys(h.lower() for h in hashes))


def build_image_index(folder):
    index = {}
    for path in folder.rglob('*'):
        match = RESOURCE_NAME.fullmatch(path.name)
        if match and path.is_file():
            # Preserve equal basenames across monthly folders instead of overwriting.
            tier = 'thumbnail' if (match[2] or '').lower() == '_t' else 'large' if match[2] else 'image'
            index.setdefault(match[1].lower(), []).append((path, tier))
    return index


def select_image(hashes, index, decrypt, convert):
    best = None
    failed = []
    candidates = list(dict.fromkeys(candidate for digest in hashes for candidate in index.get(digest, [])))
    # A readable JPEG thumbnail can also validate the account's XOR tail byte.
    # This affects decoding order only; selection still compares every candidate.
    for path, tier in sorted(candidates, key=lambda item: (item[1] != 'thumbnail', str(item[0]).lower())):
        try:
            if path.stat().st_size > MAX_INPUT:
                raise ValueError('图片超过本地解码大小限制')
            raw = decrypt(path.read_bytes())
            converted = raw.startswith(b'wxgf')
            conversion = {}
            if converted:
                raw, conversion = convert(raw)
            with Image.open(io.BytesIO(raw)) as image:
                width, height = image.size
                if not 0 < width * height <= MAX_PIXELS:
                    raise ValueError('图片超过本地像素限制')
                mime = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'GIF': 'image/gif', 'WEBP': 'image/webp'}.get(image.format)
                if not mime:
                    raise ValueError('图片格式暂不支持')
                image.load()
            score = (width * height, min(width, height), {'large': 2, 'image': 1, 'thumbnail': 0}[tier])
            if best is None or score > best[0]:
                best = (score, raw, mime, width, height, tier, converted, conversion)
        except (ValueError, OSError, Image.DecompressionBombError):
            failed.append(tier)
    if best is None:
        note = '本地图片文件存在，但暂无法读取或解码' if candidates else '未找到关联的本地图片文件'
        if not hashes:
            note = '消息缺少可用的图片定位信息'
        return {'uri': None, 'note': note, 'quality': 'missing', 'width': 0, 'height': 0,
                'converted': False, 'unavailableAlternatives': bool(candidates)}
    _, raw, mime, width, height, tier, converted, conversion = best
    label = {'large': '本地大图', 'image': '本地图片', 'thumbnail': '本地缩略图'}[tier]
    note = f'{label} · {width} × {height} 像素'
    if converted:
        note += ' · 微信格式已转为 PNG，保持像素尺寸'
    if conversion.get('firstFrameOnly'):
        note += ' · 仅保留首帧，动画或透明效果未完整还原'
    failed_non_thumbnail = any(tier != 'thumbnail' for tier in failed)
    if tier == 'thumbnail':
        if failed_non_thumbnail:
            note += ' · 另有非缩略图候选暂无法读取或解码'
        elif all(tier == 'thumbnail' for _, tier in candidates):
            note += ' · 当前关联资源仅找到缩略图'
        else:
            note += ' · 已选择可读取候选中像素最多的版本'
    elif failed:
        note += ' · 另有图片候选暂无法读取或解码'
    return {'uri': 'data:' + mime + ';base64,' + base64.b64encode(raw).decode(), 'note': note,
            'quality': tier, 'width': width, 'height': height, 'converted': converted,
            'unavailableAlternatives': bool(failed)}
