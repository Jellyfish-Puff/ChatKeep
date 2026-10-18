"""Collect supplied license texts for the dependencies embedded in the Windows release."""
import importlib.metadata as metadata
import json, sys, zipfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'build/python-tools'))
target=root/'dist/ThirdPartyLicenses.zip'
texts={}
for file in (root/'licenses').glob('*.txt'):
    texts['source-references/'+file.name]=file
texts['THIRD_PARTY_NOTICES.md']=root/'THIRD_PARTY_NOTICES.md'
python_license=Path(sys.base_prefix)/'LICENSE.txt'
if python_license.exists():texts['Python/LICENSE.txt']=python_license
for name in ('cryptography','Pillow','PyInstaller'):
    distribution=metadata.distribution(name)
    for relative in distribution.files or []:
        if 'licenses' in relative.parts:
            file=Path(distribution.locate_file(relative))
            if file.is_file():texts[name+'/'+file.name]=file
assets=json.loads((root/'src/ChatArchive/obj/project.assets.json').read_text(encoding='utf-8'))
runtime_config=json.loads((root/'src/ChatArchive/bin/Release/net10.0-windows/win-x64/ChatKeep.runtimeconfig.json').read_text(encoding='utf-8'))
for framework in runtime_config['runtimeOptions'].get('includedFrameworks',[]):
    package_name=framework['name'].lower()+'.runtime.win-x64'
    for folder in assets['packageFolders']:
        package=Path(folder)/package_name/framework['version']
        if package.exists():
            for file in package.iterdir():
                if file.is_file() and any(word in file.name.upper() for word in ('LICENSE','THIRD-PARTY','NOTICE')):
                    texts[framework['name']+'/'+file.name]=file
for name,entry in assets['libraries'].items():
    if not name.startswith(('Microsoft.NETCore.App.Runtime.','Microsoft.WindowsDesktop.App.Runtime.')):continue
    for folder in assets['packageFolders']:
        package=Path(folder)/entry['path']
        if package.exists():
            for file in package.iterdir():
                if file.is_file() and any(word in file.name.upper() for word in ('LICENSE','THIRD-PARTY','NOTICE')):
                    texts[name+'/'+file.name]=file
with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as archive:
    for name,file in sorted(texts.items()):archive.write(file,name)
print(json.dumps({'licenseFiles':len(texts),'file':target.name,'bytes':target.stat().st_size}))
