# Dot-source this script from PowerShell:
# . .\scripts\activate_c_environment.ps1

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonHome = Join-Path $projectRoot '..\.venv-xiongan-c'
$sumoHome = Join-Path $projectRoot '..\tools\sumo-1.27.1\sumo-1.27.1'
$pythonExe = Join-Path $pythonHome 'python.exe'
$sumoBin = Join-Path $sumoHome 'bin'

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Project Python environment not found: $pythonExe"
}

if (-not (Test-Path -LiteralPath (Join-Path $sumoBin 'sumo.exe'))) {
    throw "SUMO installation not found: $sumoBin"
}

$env:SUMO_HOME = $sumoHome
$env:Path = "$sumoBin;$pythonHome\Scripts;$env:Path"
$env:PYTHONUTF8 = '1'

Write-Host "Project environment enabled"
Write-Host "  Python: $pythonExe"
Write-Host "  SUMO_HOME: $env:SUMO_HOME"
Write-Host "  PYTHONUTF8: $env:PYTHONUTF8"
Write-Host "Run Python with: & $pythonExe <script-path>"
