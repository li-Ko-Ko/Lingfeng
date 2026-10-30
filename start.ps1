$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$pythonCmd = Get-Command pythonw -ErrorAction SilentlyContinue
if (-not $pythonCmd) { $pythonCmd = Get-Command python -ErrorAction Stop }
Start-Process -FilePath $pythonCmd.Source -ArgumentList ('"' + (Join-Path $projectDir 'main.py') + '"') -WorkingDirectory $projectDir
