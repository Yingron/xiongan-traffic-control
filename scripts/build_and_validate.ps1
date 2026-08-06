$ErrorActionPreference = "Stop"
$PROJECT_ROOT = Split-Path -Parent $PSScriptRoot
Push-Location $PROJECT_ROOT
try {
    Write-Host "[1/5] Validating source topology..." -ForegroundColor Cyan
    if (Get-Command python -ErrorAction SilentlyContinue) { python scripts\validate_source.py }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { py -3 scripts\validate_source.py }
    else { throw "Python not found. Please install Python 3 and add to PATH." }

    $netconvert = (Get-Command netconvert -ErrorAction SilentlyContinue).Source
    if (-not $netconvert -and $env:SUMO_HOME) { $netconvert = Join-Path $env:SUMO_HOME "bin\netconvert.exe" }
    if (-not $netconvert -or -not (Test-Path $netconvert)) { throw "netconvert not found. Please confirm SUMO_HOME or PATH is configured." }

    Write-Host "[2/5] Generating 20-intersection road network..." -ForegroundColor Cyan
    & $netconvert --node-files .\sumo_files\xiongan.nod.xml --edge-files .\sumo_files\xiongan.edg.xml --output-file .\sumo_files\xiongan.net.xml --no-turnarounds true --tls.default-type static --tls.layout opposites --junctions.corner-detail 5 --junctions.internal-link-detail 5
    if ($LASTEXITCODE -ne 0) { throw "netconvert generation failed." }

    Write-Host "[3/5] Normalizing traffic light phases (unified 4 actions)..." -ForegroundColor Cyan
    if (Get-Command python -ErrorAction SilentlyContinue) {
        python scripts\normalize_tls.py --net .\sumo_files\xiongan.net.xml --lane-mapping .\docs\lane_mapping.json --tls-mapping .\docs\tls_mapping.json
        python scripts\validate_network.py --net .\sumo_files\xiongan.net.xml --lane-mapping .\docs\lane_mapping.json --report .\docs\compatibility_report.md
    } else {
        py -3 scripts\normalize_tls.py --net .\sumo_files\xiongan.net.xml --lane-mapping .\docs\lane_mapping.json --tls-mapping .\docs\tls_mapping.json
        py -3 scripts\validate_network.py --net .\sumo_files\xiongan.net.xml --lane-mapping .\docs\lane_mapping.json --report .\docs\compatibility_report.md
    }

    Write-Host "[4/5] Checking SUMO configuration is loadable..." -ForegroundColor Cyan
    $sumo = (Get-Command sumo -ErrorAction SilentlyContinue).Source
    if (-not $sumo -and $env:SUMO_HOME) { $sumo = Join-Path $env:SUMO_HOME "bin\sumo.exe" }
    if (-not $sumo -or -not (Test-Path $sumo)) { throw "sumo.exe not found." }
    & $sumo -c .\sumo_files\xiongan.sumocfg --end 60 --no-step-log true
    if ($LASTEXITCODE -ne 0) { throw "SUMO runtime check failed." }

    Write-Host "[5/5] Done." -ForegroundColor Green
    Write-Host "Generated: sumo_files\xiongan.net.xml" -ForegroundColor Green
    Write-Host "Report: docs\compatibility_report.md" -ForegroundColor Green
    Write-Host "Tip: Run sumo-gui -c sumo_files\xiongan.sumocfg to visualize." -ForegroundColor Green
}
finally { Pop-Location }
