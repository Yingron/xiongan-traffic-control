$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    Write-Host "[1/5] 检查源拓扑..." -ForegroundColor Cyan
    if (Get-Command python -ErrorAction SilentlyContinue) { python .\tools\validate_source.py }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { py -3 .\tools\validate_source.py }
    else { throw "未找到 Python。请安装 Python 3 并加入 PATH。" }

    $netconvert = (Get-Command netconvert -ErrorAction SilentlyContinue).Source
    if (-not $netconvert -and $env:SUMO_HOME) { $netconvert = Join-Path $env:SUMO_HOME "bin\netconvert.exe" }
    if (-not $netconvert -or -not (Test-Path $netconvert)) { throw "未找到 netconvert。请确认 SUMO_HOME 或 PATH 已配置。" }

    Write-Host "[2/5] 生成双向20路口路网与信号连接..." -ForegroundColor Cyan
    & $netconvert --node-files .\sumo_files\xiongan.nod.xml --edge-files .\sumo_files\xiongan.edg.xml --output-file .\sumo_files\xiongan.net.xml --no-turnarounds true --tls.default-type static --tls.layout opposites --junctions.corner-detail 5 --junctions.internal-link-detail 5
    if ($LASTEXITCODE -ne 0) { throw "netconvert 生成失败。" }

    Write-Host "[3/5] 强制 J01-J20 全部采用统一4动作相位..." -ForegroundColor Cyan
    if (Get-Command python -ErrorAction SilentlyContinue) {
        python .\tools\normalize_tls.py --net .\sumo_files\xiongan.net.xml --lane-mapping .\docs\lane_mapping.json --tls-mapping .\docs\tls_mapping.json
        python .\tools\validate_network.py --net .\sumo_files\xiongan.net.xml --lane-mapping .\docs\lane_mapping.json --report .\docs\compatibility_report.md
    } else {
        py -3 .\tools\normalize_tls.py --net .\sumo_files\xiongan.net.xml --lane-mapping .\docs\lane_mapping.json --tls-mapping .\docs\tls_mapping.json
        py -3 .\tools\validate_network.py --net .\sumo_files\xiongan.net.xml --lane-mapping .\docs\lane_mapping.json --report .\docs\compatibility_report.md
    }

    Write-Host "[4/5] 检查 SUMO 配置可加载..." -ForegroundColor Cyan
    $sumo = (Get-Command sumo -ErrorAction SilentlyContinue).Source
    if (-not $sumo -and $env:SUMO_HOME) { $sumo = Join-Path $env:SUMO_HOME "bin\sumo.exe" }
    if (-not $sumo -or -not (Test-Path $sumo)) { throw "未找到 sumo.exe。" }
    & $sumo -c .\sumo_files\xiongan.sumocfg --end 60 --no-step-log true
    if ($LASTEXITCODE -ne 0) { throw "SUMO 运行检查失败。" }

    Write-Host "[5/5] 完成。" -ForegroundColor Green
    Write-Host "已生成: sumo_files\xiongan.net.xml" -ForegroundColor Green
    Write-Host "验证报告: docs\compatibility_report.md" -ForegroundColor Green
    Write-Host "可双击 启动早高峰.bat 查看车辆和信号灯。" -ForegroundColor Green
}
finally { Pop-Location }
