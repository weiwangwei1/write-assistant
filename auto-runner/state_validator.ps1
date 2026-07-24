<#
.SYNOPSIS
  State.json validator and repair script (v2.1)
#>

param(
    [string]$StateFile = "auto-runner\state.json",
    [string]$TaskConfigFile = "auto-runner\task_config.json",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$workspace = $PSScriptRoot | Split-Path -Parent

$statePath = Join-Path $workspace $StateFile
$configPath = Join-Path $workspace $TaskConfigFile

if (-not (Test-Path $statePath)) {
    Write-Host "[ERROR] state.json not found: $statePath" -ForegroundColor Red
    exit 1
}

$state = Get-Content $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
$taskConfig = $null
if (Test-Path $configPath) {
    $taskConfig = Get-Content $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
}

$issuesFound = 0
$issuesFixed = 0
$details = [System.Collections.ArrayList]::new()

function Get-StepOutputFiles {
    param($stepId, $config)
    $files = @()
    if ($config) {
        $configStep = $config.steps | Where-Object { $_.id -eq $stepId }
        if ($configStep -and $configStep.output_files) {
            $files = $configStep.output_files
        }
    }
    return $files
}

function Test-AllFilesExist {
    param($filePaths, $workspace)
    $allExist = $true
    $missing = @()
    foreach ($fp in $filePaths) {
        $full = Join-Path $workspace $fp
        if (Test-Path $full) {
            $sz = (Get-Item $full).Length
            if ($sz -eq 0) {
                $allExist = $false
                $missing += "$fp (empty)"
            }
        } else {
            $allExist = $false
            $missing += "$fp (missing)"
        }
    }
    $result = New-Object PSObject -Property @{
        AllExist = $allExist
        Missing = $missing
        Count = $filePaths.Count
    }
    return $result
}

Write-Host ""
Write-Host "=== State Validator v2.1 ===" -ForegroundColor Cyan
Write-Host "Workspace: $workspace"
Write-Host "State file: $statePath"
Write-Host "Dry run: $($DryRun.IsPresent)"
Write-Host ""

# 1. Check running steps
$runningSteps = @($state.steps | Where-Object { $_.status -eq "running" })
Write-Host "[1/4] Checking running steps ($($runningSteps.Count) found)..." -ForegroundColor Yellow

foreach ($step in $runningSteps) {
    $outputFiles = Get-StepOutputFiles -stepId $step.id -config $taskConfig
    if ($outputFiles.Count -eq 0) {
        Write-Host "  Step $($step.id) ($($step.name)): no output_files, skipping" -ForegroundColor DarkGray
        continue
    }
    $check = Test-AllFilesExist -filePaths $outputFiles -workspace $workspace
    if ($check.AllExist) {
        $issuesFound++
        Write-Host "  Step $($step.id) ($($step.name)): RUNNING but outputs exist -> FIX to completed" -ForegroundColor Green
        $details.Add("Step $($step.id): running_but_outputs_exist -> fix_to_completed") | Out-Null
        if (-not $DryRun) {
            $step.status = "completed"
            $step.result = "recovered by state_validator"
            $step.timestamp = (Get-Date).ToString("o")
            $issuesFixed++
        }
    } else {
        $issuesFound++
        Write-Host "  Step $($step.id) ($($step.name)): RUNNING, outputs missing -> FIX to pending" -ForegroundColor Red
        $details.Add("Step $($step.id): running_outputs_missing -> fix_to_pending") | Out-Null
        if (-not $DryRun) {
            $step.status = "pending"
            $issuesFixed++
        }
    }
}

# 2. Verify completed steps
Write-Host ""
Write-Host "[2/4] Verifying completed steps outputs..." -ForegroundColor Yellow
$completedSteps = @($state.steps | Where-Object { $_.status -eq "completed" })
foreach ($step in $completedSteps) {
    $outputFiles = Get-StepOutputFiles -stepId $step.id -config $taskConfig
    if ($outputFiles.Count -gt 0) {
        $check = Test-AllFilesExist -filePaths $outputFiles -workspace $workspace
        if (-not $check.AllExist) {
            $issuesFound++
            Write-Host "  Step $($step.id) ($($step.name)): COMPLETED but outputs missing" -ForegroundColor Red
            $details.Add("Step $($step.id): completed_but_outputs_missing") | Out-Null
        }
    }
}

# 3. Fix current_step
Write-Host ""
Write-Host "[3/4] Fixing current_step..." -ForegroundColor Yellow
$firstIncomplete = $state.steps | Where-Object { $_.status -ne "completed" } | Select-Object -First 1
if ($firstIncomplete) {
    if ($firstIncomplete.id -ne $state.current_step) {
        $oldVal = $state.current_step
        $issuesFound++
        Write-Host "  current_step: $oldVal -> $($firstIncomplete.id)" -ForegroundColor Green
        $details.Add("current_step: $oldVal -> $($firstIncomplete.id)") | Out-Null
        if (-not $DryRun) {
            $state.current_step = $firstIncomplete.id
            $issuesFixed++
        }
    } else {
        Write-Host "  current_step ($($state.current_step)) is correct" -ForegroundColor DarkGray
    }
} else {
    if ($state.status -ne "completed") {
        $issuesFound++
        Write-Host "  All steps done but status != completed -> FIX" -ForegroundColor Green
        $details.Add("all_done_but_not_completed") | Out-Null
        if (-not $DryRun) {
            $state.status = "completed"
            $state.current_step = $state.total_steps
            $issuesFixed++
        }
    } else {
        Write-Host "  All steps completed, status correct" -ForegroundColor DarkGray
    }
}

# 4. Fix parallel groups
Write-Host ""
Write-Host "[4/4] Fixing parallel_groups..." -ForegroundColor Yellow
if ($state.parallel_groups -and $state.parallel_groups.Count -gt 0) {
    foreach ($group in $state.parallel_groups) {
        $groupSteps = @()
        if ($taskConfig) {
            $groupSteps = @($taskConfig.steps | Where-Object { $_.parallel_group -eq $group.group_id -and -not $_.is_merger })
        }
        $actualCompleted = @()
        $actualPending = @()
        foreach ($gStep in $groupSteps) {
            $st = $state.steps | Where-Object { $_.id -eq $gStep.id }
            if ($st) {
                if ($st.status -eq "completed") {
                    $actualCompleted += $gStep.name
                } else {
                    $actualPending += $gStep.name
                }
            }
        }
        $needsFix = ($group.completed_agents.Count -ne $actualCompleted.Count) -or ($group.pending_agents.Count -ne $actualPending.Count)
        if ($needsFix) {
            $issuesFound++
            Write-Host "  Group '$($group.group_id)': mismatch -> FIX" -ForegroundColor Green
            $details.Add("Group $($group.group_id): parallel_group_mismatch") | Out-Null
            if (-not $DryRun) {
                $group.completed_agents = $actualCompleted
                $group.pending_agents = $actualPending
                if ($actualPending.Count -eq 0) {
                    $group.merger_ready = $true
                    if ($actualCompleted.Count -eq $group.parallel_total) {
                        $group.status = "completed"
                    }
                }
                $issuesFixed++
            }
        } else {
            Write-Host "  Group '$($group.group_id)': state correct" -ForegroundColor DarkGray
        }
    }
} else {
    Write-Host "  No parallel groups" -ForegroundColor DarkGray
}

# Write fixed state
Write-Host ""
if (-not $DryRun -and $issuesFixed -gt 0) {
    $state.last_run = (Get-Date).ToString("o")
    $state.last_run_result = "state_validator: fixed $issuesFixed issues"
    $state | ConvertTo-Json -Depth 10 | Set-Content $statePath -Encoding UTF8
    Write-Host "[OK] state.json updated with $issuesFixed fixes" -ForegroundColor Green
} elseif ($DryRun) {
    Write-Host "[DRY RUN] $issuesFound issues would be fixed." -ForegroundColor Yellow
} else {
    Write-Host "[OK] No issues found. state.json is consistent." -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Issues found: $issuesFound"
Write-Host "Issues fixed: $issuesFixed"
Write-Host ""
