"""Validate the sealed codec with synthetic data and no external Python PATH."""
import base64
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
from PIL import Image

root = Path(__file__).resolve().parents[1]
executable = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / 'build/reader/ChatReader.exe'
folder = root / 'build/image-package-smoke'
folder.mkdir(exist_ok=True)
environment = {key: value for key, value in os.environ.items() if not key.startswith('PYTHON')}
environment.update(PATH=str(Path(os.environ['SystemRoot']) / 'System32'), TEMP=str(folder), TMP=str(folder), CHATARCHIVE_DATA_ROOT=str(folder))
fixture = (root / 'tests/fixtures/synthetic-static.wxgf').read_bytes()
invalid = b'wxgf' + bytes(32)
request = b''.join(struct.pack('<I', len(raw)) + raw for raw in (fixture, invalid))
process = subprocess.Popen([str(executable), '--image-codec'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, env=environment, cwd=folder, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    output, errors = process.communicate(request, timeout=35)
except subprocess.TimeoutExpired:
    process.kill()
    process.communicate()
    raise RuntimeError('Packaged codec timeout') from None
if process.returncode:
    raise RuntimeError('Packaged codec failed to start')
offset, results = 0, []
while offset < len(output):
    size = struct.unpack_from('<I', output, offset)[0]
    results.append(json.loads(output[offset + 4:offset + 4 + size]))
    offset += 4 + size
assert len(results) == 2 and results[0]['ok'] and not results[1]['ok']
with Image.open(io.BytesIO(base64.b64decode(results[0]['png']))) as image:
    image.load()
    assert image.size == (960, 540) and image.format == 'PNG'
assert not results[0]['firstFrameOnly']
print(json.dumps({'packagedHevcDecodePassed': True, 'syntheticSize': [960, 540], 'invalidImageRejected': True,
                  'pythonRemovedFromPath': True, 'realChatDataRead': False}))
