"""Run synthetic export regressions against modules extracted from the sealed reader.

No WeChat connection, live process scanning, or real chat/cache access is used.
The separate check_image_package.py exercises the native codec in the EXE.
"""
import json
import marshal
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build/python-tools'))
sys.path.insert(0, str(ROOT / 'src'))
from PyInstaller.archive.readers import CArchiveReader


def main():
    executable = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'build/reader/ChatReader.exe'
    archive = CArchiveReader(str(executable))
    pyz = archive.open_embedded_archive('PYZ.pyz')
    names = ['message_content', 'html_export', 'batch_export', 'image_codec', 'image_resources', 'reader']
    for name in names:
        code = marshal.loads(archive.extract(name)) if name == 'reader' else pyz.extract(name)
        module = types.ModuleType(name)
        # Source-relative fixture/runtime paths only; all module code comes from EXE.
        module.__file__ = str(ROOT / 'src' / (name + '.py'))
        sys.modules[name] = module
        exec(code, module.__dict__)
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    print(json.dumps({'ok': result.wasSuccessful(), 'tests': result.testsRun,
                      'sealedModules': names, 'realChatDataRead': False}))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
