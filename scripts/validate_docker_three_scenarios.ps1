param(
    [string]$ApiBaseUrl = "http://localhost:8000/api/v1",
    [string]$EdgeBaseUrl = "http://localhost:8001",
    [string]$OutputPath = "logs/docker_validation_20260827/three_scenario_acceptance.json",
    [int]$Seed = 20260827
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$resolvedOutput = Join-Path $projectRoot $OutputPath
$outputDirectory = Split-Path -Parent $resolvedOutput
$expectedIds = @(1..30 | ForEach-Object { "J{0:D2}" -f $_ })
$scenarioSpecs = @(
    [pscustomobject]@{ scenario = "real_peak"; model_id = "edge-real-peak-onnx-v1" },
    [pscustomobject]@{ scenario = "real_offpeak"; model_id = "edge-real-offpeak-via-evening-onnx-v1" },
    [pscustomobject]@{ scenario = "real_evening"; model_id = "edge-real-evening-onnx-v1" }
)

function Assert-Equal {
    param(
        [Parameter(Mandatory = $true)]$Actual,
        [Parameter(Mandatory = $true)]$Expected,
        [Parameter(Mandatory = $true)][string]$Label
    )
    if ($Actual -ne $Expected) {
        throw "$Label expected '$Expected', got '$Actual'"
    }
}

function Get-ObjectProperties {
    param([Parameter(Mandatory = $true)]$Value)
    return @($Value.PSObject.Properties)
}

$startedAt = Get-Date
$results = @()
$health = $null
$overallStatus = "PASS"

try {
    $edgeHealth = Invoke-RestMethod -Uri "$EdgeBaseUrl/health" -TimeoutSec 10
    $apiHealth = Invoke-RestMethod -Uri "$ApiBaseUrl/health" -TimeoutSec 10
    $apiEdgeHealth = Invoke-RestMethod -Uri "$ApiBaseUrl/edge/health" -TimeoutSec 10

    Assert-Equal $edgeHealth.status "healthy" "Direct edge health"
    Assert-Equal $edgeHealth.backend "onnx" "Edge backend"
    Assert-Equal $edgeHealth.input_dimension 26 "Edge input dimension"
    Assert-Equal $edgeHealth.state_dimension 22 "Edge state dimension"
    Assert-Equal $edgeHealth.action_count 4 "Edge action count"
    Assert-Equal $apiHealth.status "healthy" "API health"
    Assert-Equal $apiHealth.sumo_available $true "SUMO availability"
    Assert-Equal $apiEdgeHealth.status "healthy" "API-to-edge health"

    if ($apiHealth.active_session_id) {
        throw "API already owns active session '$($apiHealth.active_session_id)'"
    }

    $health = [ordered]@{
        status = "PASS"
        edge = $edgeHealth
        api = $apiHealth
        api_to_edge = $apiEdgeHealth
    }

    foreach ($spec in $scenarioSpecs) {
        $sessionId = $null
        $scenarioStartedAt = Get-Date
        Write-Host "[RUN] $($spec.scenario) -> $($spec.model_id)" -ForegroundColor Cyan
        try {
            $startPayload = @{
                scenario = $spec.scenario
                use_gui = $false
                seed = $Seed
            } | ConvertTo-Json
            $session = Invoke-RestMethod -Uri "$ApiBaseUrl/simulation/start" -Method Post -ContentType "application/json" -Body $startPayload -TimeoutSec 60
            $sessionId = $session.session_id
            Assert-Equal $session.state_dimension 660 "$($spec.scenario) session state dimension"
            Assert-Equal @($session.intersection_order).Count 30 "$($spec.scenario) session intersection count"

            $initialState = Invoke-RestMethod -Uri "$ApiBaseUrl/simulation/state?session_id=$sessionId" -TimeoutSec 30
            Assert-Equal @($initialState.state_vector).Count 660 "$($spec.scenario) initial state dimension"
            Assert-Equal @($initialState.intersections).Count 30 "$($spec.scenario) initial intersection count"
            Assert-Equal $initialState.transition_id 0 "$($spec.scenario) initial transition"

            $predictPayload = @{
                session_id = $sessionId
                model_id = $spec.model_id
            } | ConvertTo-Json
            $prediction = Invoke-RestMethod -Uri "$ApiBaseUrl/edge/predict" -Method Post -ContentType "application/json" -Body $predictPayload -TimeoutSec 30
            $actionProperties = @(Get-ObjectProperties $prediction.actions)
            Assert-Equal $actionProperties.Count 30 "$($spec.scenario) predicted action count"
            Assert-Equal $prediction.transition_id 0 "$($spec.scenario) prediction transition"
            Assert-Equal $prediction.edge_backend "onnx" "$($spec.scenario) edge backend"

            $actualIds = @($actionProperties.Name)
            $idDifference = @(Compare-Object $expectedIds $actualIds)
            Assert-Equal $idDifference.Count 0 "$($spec.scenario) action ID difference count"
            $invalidActions = @($actionProperties | Where-Object { [int]$_.Value -lt 0 -or [int]$_.Value -gt 3 })
            Assert-Equal $invalidActions.Count 0 "$($spec.scenario) invalid action count"

            $actionsPayload = @{
                session_id = $sessionId
                expected_transition_id = $prediction.transition_id
                actions = $prediction.actions
                step_seconds = 5
            } | ConvertTo-Json -Depth 5
            $applied = Invoke-RestMethod -Uri "$ApiBaseUrl/simulation/actions" -Method Post -ContentType "application/json" -Body $actionsPayload -TimeoutSec 60
            $appliedProperties = @(Get-ObjectProperties $applied.applied_actions)
            Assert-Equal $appliedProperties.Count 30 "$($spec.scenario) applied action count"
            Assert-Equal $applied.transition_id 1 "$($spec.scenario) applied transition"

            $nextState = Invoke-RestMethod -Uri "$ApiBaseUrl/simulation/state?session_id=$sessionId" -TimeoutSec 30
            Assert-Equal @($nextState.state_vector).Count 660 "$($spec.scenario) next state dimension"
            Assert-Equal @($nextState.intersections).Count 30 "$($spec.scenario) next intersection count"
            Assert-Equal $nextState.transition_id 1 "$($spec.scenario) next transition"

            $rewards = Invoke-RestMethod -Uri "$ApiBaseUrl/simulation/rewards?session_id=$sessionId&transition_id=1" -TimeoutSec 30
            $rewardProperties = @(Get-ObjectProperties $rewards.rewards)
            Assert-Equal $rewardProperties.Count 30 "$($spec.scenario) reward count"

            $results += [ordered]@{
                scenario = $spec.scenario
                model_id = $spec.model_id
                status = "PASS"
                session_id = $sessionId
                seed = $Seed
                initial_transition_id = $initialState.transition_id
                predicted_action_count = $actionProperties.Count
                action_ids = $actualIds
                invalid_action_count = $invalidActions.Count
                edge_backend = $prediction.edge_backend
                inference_latency_ms = $prediction.latency_ms
                applied_action_count = $appliedProperties.Count
                final_transition_id = $nextState.transition_id
                simulation_time_seconds = $nextState.simulation_time
                state_dimension = @($nextState.state_vector).Count
                intersection_count = @($nextState.intersections).Count
                reward_count = $rewardProperties.Count
                global_reward = $rewards.global_reward
                duration_seconds = [math]::Round(((Get-Date) - $scenarioStartedAt).TotalSeconds, 3)
            }
            Write-Host "[PASS] $($spec.scenario): 30 actions, 660-D state, transition 0->1" -ForegroundColor Green
        }
        catch {
            $overallStatus = "FAIL"
            $results += [ordered]@{
                scenario = $spec.scenario
                model_id = $spec.model_id
                status = "FAIL"
                session_id = $sessionId
                error = $_.Exception.Message
                duration_seconds = [math]::Round(((Get-Date) - $scenarioStartedAt).TotalSeconds, 3)
            }
            Write-Host "[FAIL] $($spec.scenario): $($_.Exception.Message)" -ForegroundColor Red
        }
        finally {
            if ($sessionId) {
                try {
                    $stopPayload = @{ session_id = $sessionId } | ConvertTo-Json
                    $stopResult = Invoke-RestMethod -Uri "$ApiBaseUrl/simulation/stop" -Method Post -ContentType "application/json" -Body $stopPayload -TimeoutSec 30
                    $matchingResult = $results | Where-Object { $_.session_id -eq $sessionId } | Select-Object -Last 1
                    if ($matchingResult) {
                        $matchingResult["session_stopped"] = $true
                    }
                }
                catch {
                    $overallStatus = "FAIL"
                    $matchingResult = $results | Where-Object { $_.session_id -eq $sessionId } | Select-Object -Last 1
                    if ($matchingResult) {
                        $matchingResult["session_stopped"] = $false
                        $matchingResult["stop_error"] = $_.Exception.Message
                        $matchingResult["status"] = "FAIL"
                    }
                    Write-Host "[FAIL] stop $($spec.scenario): $($_.Exception.Message)" -ForegroundColor Red
                }
            }
        }
    }
}
catch {
    $overallStatus = "FAIL"
    $health = [ordered]@{
        status = "FAIL"
        error = $_.Exception.Message
    }
    Write-Host "[FAIL] deployment health: $($_.Exception.Message)" -ForegroundColor Red
}

$report = [ordered]@{
    schema_version = "1.0"
    generated_at = (Get-Date).ToString("o")
    started_at = $startedAt.ToString("o")
    project_commit = (git -C $projectRoot rev-parse HEAD).Trim()
    overall_status = $overallStatus
    acceptance_scope = @(
        "API health and SUMO availability",
        "API-to-edge container communication",
        "three formal scenario/model mappings",
        "660-D state and 30-junction contract",
        "30 masked ONNX actions applied through TraCI",
        "transition 0 to 1 and 30 rewards",
        "session cleanup"
    )
    health = $health
    scenarios = $results
    total_duration_seconds = [math]::Round(((Get-Date) - $startedAt).TotalSeconds, 3)
}

New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $resolvedOutput -Encoding UTF8
Write-Host "[REPORT] $resolvedOutput" -ForegroundColor Cyan
Write-Host "[RESULT] $overallStatus" -ForegroundColor $(if ($overallStatus -eq "PASS") { "Green" } else { "Red" })

if ($overallStatus -ne "PASS") {
    exit 1
}
