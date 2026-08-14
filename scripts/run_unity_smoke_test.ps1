$ErrorActionPreference = "Stop"
$PROJECT_ROOT = Split-Path -Parent $PSScriptRoot
$PYTHON = "D:\ChallengeCup2026\.venv-xiongan-c\python.exe"
$SMOKE_TEST = Join-Path $PROJECT_ROOT "frontend\pymarl\src\tools\unity_tcp_smoke_test.py"

if (-not (Test-Path $PYTHON)) {
    throw "Python environment not found: $PYTHON"
}

$listener = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if (-not $listener) {
    $listener = netstat -ano | Select-String -Pattern '^\s*TCP\s+127\.0\.0\.1:5000\s+.*LISTENING'
}
if (-not $listener) {
    throw "Unity TCP port 5000 is not listening. Open frontend/CitySimulation and enter Play Mode first."
}

Write-Host "[1/2] Unity TCP port 5000 is listening." -ForegroundColor Cyan
Write-Host "[2/2] Running init/reset(xiongan_30)/step/close smoke test..." -ForegroundColor Cyan
& $PYTHON $SMOKE_TEST --host 127.0.0.1 --port 5000 --steps 3 --timeout 10
if ($LASTEXITCODE -ne 0) {
    throw "Unity TCP smoke test failed with exit code $LASTEXITCODE."
}
Write-Host "Unity-PyMARL smoke test passed." -ForegroundColor Green
