$ErrorActionPreference = "Stop"
$PROJECT_ROOT = Split-Path -Parent $PSScriptRoot
Push-Location $PROJECT_ROOT
try {
    Write-Host "[1/5] Validating source topology..." -ForegroundColor Cyan
    if (Get-Command python -ErrorAction SilentlyContinue) { python scripts\validate_source.py }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { py -3 scripts\validate_source.py }
    else { throw "Python not found. Please install Python 3 and add to PATH." }

    Write-Host "[2/5] Checking committed 30-intersection road network..." -ForegroundColor Cyan
    if (-not (Test-Path .\sumo_files\xiongan_30.net.xml)) { throw "sumo_files\xiongan_30.net.xml is missing." }

    Write-Host "[3/5] Regenerating 30-intersection lane/TLS contracts..." -ForegroundColor Cyan
    if (Get-Command python -ErrorAction SilentlyContinue) {
        python scripts\generate_lane_mapping.py
        python scripts\generate_tls_mapping.py
        python scripts\validate_network.py --net .\sumo_files\xiongan_30.net.xml --lane-mapping .\docs\lane_mapping.json --report .\docs\compatibility_report.md
    } else {
        py -3 scripts\generate_lane_mapping.py
        py -3 scripts\generate_tls_mapping.py
        py -3 scripts\validate_network.py --net .\sumo_files\xiongan_30.net.xml --lane-mapping .\docs\lane_mapping.json --report .\docs\compatibility_report.md
    }

    Write-Host "[4/5] Checking SUMO configuration is loadable..." -ForegroundColor Cyan
    $sumo = (Get-Command sumo -ErrorAction SilentlyContinue).Source
    if (-not $sumo -and $env:SUMO_HOME) { $sumo = Join-Path $env:SUMO_HOME "bin\sumo.exe" }
    if (-not $sumo -or -not (Test-Path $sumo)) { throw "sumo.exe not found." }
    & $sumo -c .\sumo_files\xiongan_30.sumocfg --end 60 --no-step-log true
    if ($LASTEXITCODE -ne 0) { throw "SUMO runtime check failed." }

    Write-Host "[5/5] Done." -ForegroundColor Green
    Write-Host "Network: sumo_files\xiongan_30.net.xml" -ForegroundColor Green
    Write-Host "Report: docs\compatibility_report.md" -ForegroundColor Green
    Write-Host "Tip: Run sumo-gui -c sumo_files\xiongan_30.sumocfg to visualize." -ForegroundColor Green
}
finally { Pop-Location }
