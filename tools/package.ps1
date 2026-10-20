param([switch]$SkipReader, [string]$OutputDirectory = 'dist')
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
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$outputExe = Join-Path $OutputDirectory 'ChatKeep.exe'
$outputLicenses = Join-Path $OutputDirectory 'ThirdPartyLicenses.zip'
Copy-Item -LiteralPath 'build/publish/ChatKeep.exe' -Destination $outputExe -Force
$legacyExe = Join-Path $OutputDirectory '微信记录导出.exe'
if (Test-Path -LiteralPath $legacyExe) {
    Copy-Item -LiteralPath $outputExe -Destination $legacyExe -Force
}
python tools/collect_release_licenses.py $outputLicenses
if ($LASTEXITCODE -ne 0) { throw 'License collection failed.' }
$checksumLines = foreach ($outputFile in @($outputExe, $outputLicenses)) {
    (Get-FileHash -LiteralPath $outputFile -Algorithm SHA256).Hash.ToLowerInvariant() + '  ' + (Split-Path $outputFile -Leaf)
}
$checksumPath = Join-Path (Resolve-Path -LiteralPath $OutputDirectory).Path 'SHA256SUMS.txt'
[IO.File]::WriteAllText($checksumPath, ($checksumLines -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
Write-Output "Done: $outputExe"
