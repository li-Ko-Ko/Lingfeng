param([string]$Python = 'python', [string]$DistRoot = '')
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    $iconFile = Join-Path $projectRoot 'assets\popscore.ico'
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $projectRoot 'build\cache'
    if (-not $DistRoot) {
        $releaseVersion = (& $Python -c 'from popscore import __version__; print(__version__)').Trim()
        if ($LASTEXITCODE -ne 0) { throw 'Unable to read release version.' }
        $DistRoot = Join-Path $projectRoot "dist\$releaseVersion"
    }
    # Run with a Python environment containing requirements-build.txt.
    & $Python -m PyInstaller --noconfirm --clean --windowed --onedir --name Lingfeng --icon $iconFile --add-data "$(Join-Path $projectRoot 'assets');assets" --add-data "$(Join-Path $projectRoot 'popscore\en.json');popscore" --collect-data soundcard --hidden-import _cffi_backend --distpath $DistRoot --workpath build --specpath build --exclude-module tkinter --exclude-module matplotlib --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick main.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    & $Python scripts/package_release.py (Join-Path $DistRoot 'Lingfeng')
    if ($LASTEXITCODE -ne 0) { throw 'Release packaging failed.' }
} finally { Pop-Location }
