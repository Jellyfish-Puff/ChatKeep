param([switch]$SkipReader)
$ErrorActionPreference = 'Stop'
$workspace = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $workspace
$reader = Join-Path $workspace 'build/reader/ChatReader.exe'
if (-not $SkipReader) {
    $env:PYTHONPATH = Join-Path $workspace 'build/python-tools'
    $icon = Join-Path $workspace 'src/ChatArchive/Assets/chat-archive.ico'
    python -m PyInstaller --noconfirm --onefile --console --noupx --name ChatReader --distpath build/reader --workpath build/pyinstaller --specpath build --icon $icon --exclude-module tkinter --exclude-module numpy --python-option 'X utf8' src/reader.py
    if ($LASTEXITCODE -ne 0) { throw 'Reader packaging failed.' }
}
if (-not (Test-Path -LiteralPath $reader)) { throw 'Missing packaged reader.' }
dotnet publish src/ChatArchive/ChatArchive.csproj -c Release -r win-x64 --self-contained true -o build/publish -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:EnableCompressionInSingleFile=true -p:PublishTrimmed=false -p:DebugType=None -p:DebugSymbols=false "-p:ReaderPayload=$reader" --nologo
if ($LASTEXITCODE -ne 0) { throw 'Desktop packaging failed.' }
New-Item -ItemType Directory -Force dist | Out-Null
Copy-Item -LiteralPath 'build/publish/ChatKeep.exe' -Destination 'dist/ChatKeep.exe' -Force
if (Test-Path -LiteralPath 'dist/微信记录导出.exe') {
    Copy-Item -LiteralPath 'dist/ChatKeep.exe' -Destination 'dist/微信记录导出.exe' -Force
}
Write-Output 'Done: dist/ChatKeep.exe'
python tools/collect_release_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'License collection failed.' }
