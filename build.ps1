# Build script for TTS Downloader (Nuitka, Windows)
#
# Uses --standalone (folder output) instead of --onefile.
# Onefile binaries unpack a Python runtime to %TEMP% at startup, which is
# exactly what malware packers do, so AV heuristics flag them aggressively.
# Standalone outputs a regular folder + .exe and is much less suspicious.
#
# Distribution: zip the resulting app.dist/ folder and ship that.

$ErrorActionPreference = 'Stop'

$version     = '1.4.0.0'
$company     = 'Slaytonw'
$product     = 'TTS Downloader'
$description = 'Downloader for Tabletop Simulator Steam Workshop items'
$copyright   = 'Copyright (c) Slaytonw'

python -m nuitka `
    --standalone `
    --windows-console-mode=disable `
    --enable-plugin=tk-inter `
    --windows-icon-from-ico=icon.ico `
    --include-data-files=icon.ico=icon.ico `
    --company-name="$company" `
    --product-name="$product" `
    --file-description="$description" `
    --file-version=$version `
    --product-version=$version `
    --copyright="$copyright" `
    --output-filename="TTS Downloader.exe" `
    --remove-output `
    --assume-yes-for-downloads `
    app.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Build complete." -ForegroundColor Green
Write-Host "Distribute the app.dist\ folder (zip it for users)."
