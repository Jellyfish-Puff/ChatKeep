"""Decode static WXGF/HEVC locally, isolated from the reader with a timeout."""
import base64
import io
import json
from pathlib import Path
import queue
import re
import struct
import subprocess
import sys
import threading

MAX_INPUT = 64 * 1024 * 1024
MAX_RESPONSE = 96 * 1024 * 1024
MAX_PIXELS = 32_000_000
NAL_START = re.compile(rb'\x00\x00(?:\x00)?\x01(?=\x40[\x01-\x07])')


def load_av():
    # Optional workspace installation; the sealed EXE includes these modules.
    try:
        import av
    except ImportError:
        if getattr(sys, 'frozen', False):
            raise
        directory = Path(__file__).resolve().parents[1] / 'build/python-tools'
        if str(directory) not in sys.path:
            sys.path.append(str(directory))
        import av
    return av


def decode_wxgf(data):
    """Convert a locally stored color frame to PNG without resizing it.

    WXGF may contain additional alpha or animation streams. They are not
    advertised as reconstructed: metadata explicitly records a first-frame view.
    """
    if not data.startswith(b'wxgf') or len(data) > MAX_INPUT:
        raise ValueError('不支持的微信图片容器')
    starts = [m.start() for m in NAL_START.finditer(data)]
    if not starts or len(starts) > 16:
        raise ValueError('未找到可处理的微信图片数据流')
    av = load_av()
    av.logging.set_level(av.logging.PANIC)
    best = None
    frame_count = 0
    # Each VPS begins a new candidate stream, possibly an alpha plane.
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(data)
        context = av.CodecContext.create('hevc', 'r')
        context.thread_count = 1
        context.options = {'max_pixels': str(MAX_PIXELS)}
        first = None
        try:
            packets = context.parse(data[start:end]) + context.parse()
            for packet in packets:
                for frame in context.decode(packet):
                    frame_count += 1
                    if first is None:
                        first = frame
                    if frame_count > 128:
                        raise ValueError('微信图片帧数超出本地预览限制')
            for frame in context.decode(None):
                frame_count += 1
                if first is None:
                    first = frame
        except av.error.FFmpegError:
            continue
        if first is None or not 0 < first.width * first.height <= MAX_PIXELS:
            continue
        score = (not first.format.name.startswith('gray'), first.width * first.height)
        if best is None or score > best[0]:
            best = (score, first)
    if best is None:
        raise ValueError('微信图片数据流暂无法解码')
    image = best[1].to_image()
    output = io.BytesIO()
    image.save(output, format='PNG')
    return output.getvalue(), {'firstFrameOnly': frame_count > 1 or len(starts) > 1}


def _read_exact(stream, length):
    chunks = bytearray()
    while len(chunks) < length:
        part = stream.read(length - len(chunks))
        if not part:
            raise EOFError('图片解码组件已退出')
        chunks.extend(part)
    return bytes(chunks)


def serve_codec():
    source, destination = sys.stdin.buffer, sys.stdout.buffer
    while True:
        header = source.read(4)
        if not header:
            return
        if len(header) != 4:
            return
        size = struct.unpack('<I', header)[0]
        if not 0 < size <= MAX_INPUT:
            return
        data = _read_exact(source, size)
        try:
            png, info = decode_wxgf(data)
            result = {'ok': True, 'png': base64.b64encode(png).decode(), **info}
        except Exception:
            # No payload, filenames, key material, or native decoder logs.
            result = {'ok': False}
        encoded = json.dumps(result).encode('utf-8')
        if len(encoded) > MAX_RESPONSE:
            encoded = b'{"ok":false}'
        destination.write(struct.pack('<I', len(encoded)) + encoded)
        destination.flush()


class WxgfDecoder:
    def __init__(self, timeout=15):
        self.timeout = timeout
        self.process = None
        self.lock = threading.Lock()

    def _start(self):
        args = [sys.executable, '--image-codec'] if getattr(sys, 'frozen', False) else [
            sys.executable, '-X', 'utf8', str(Path(__file__).with_name('reader.py')), '--image-codec']
        self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def close(self):
        process, self.process = self.process, None
        if process is None:
            return
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        for pipe in (process.stdin, process.stdout):
            if pipe:
                try:
                    pipe.close()
                except OSError:
                    pass

    def decode(self, data):
        if not 0 < len(data) <= MAX_INPUT:
            raise ValueError('图片文件超出本地解码限制')
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                self.close()
                self._start()
            process = self.process
            replies = queue.Queue()

            def exchange():
                try:
                    process.stdin.write(struct.pack('<I', len(data)) + data)
                    process.stdin.flush()
                    size = struct.unpack('<I', _read_exact(process.stdout, 4))[0]
                    if not 0 < size <= MAX_RESPONSE:
                        raise ValueError('图片解码返回无效')
                    replies.put(json.loads(_read_exact(process.stdout, size)))
                except Exception:
                    replies.put(None)

            thread = threading.Thread(target=exchange, daemon=True)
            thread.start()
            try:
                result = replies.get(timeout=self.timeout)
            except queue.Empty:
                self.close()
                thread.join(timeout=1)
                raise ValueError('图片解码超时，已保留可用的其他图片') from None
            if not result or not result.get('ok'):
                self.close()
                raise ValueError('微信图片暂无法解码')
            try:
                png = base64.b64decode(result['png'], validate=True)
            except (KeyError, ValueError):
                self.close()
                raise ValueError('图片解码返回无效') from None
            return png, {'firstFrameOnly': bool(result.get('firstFrameOnly'))}
