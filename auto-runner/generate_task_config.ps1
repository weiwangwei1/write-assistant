<#
.SYNOPSIS
  task_config auto-generator v1.0
  Generates task_config.json and state.json from outline.json

.PARAMETER StartChapter
  Start chapter number

.PARAMETER EndChapter
  End chapter number

.PARAMETER ReviewMode
  unified (default) or traditional

.PARAMETER Workspace
  Workspace path (default: parent of script directory)
#>

param(
    [Parameter(Mandatory=$true)]
    [int]$StartChapter,
    [Parameter(Mandatory=$true)]
    [int]$EndChapter,
    [ValidateSet("unified", "traditional")]
    [string]$ReviewMode = "unified",
    [string]$Workspace = (Split-Path $PSScriptRoot -Parent)
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot 'fast_io.ps1')

$outlinePath = Join-Path $Workspace "memory\outline.json"
$configPath = Join-Path $Workspace "config\novel_config.json"
$outputTaskConfig = Join-Path $Workspace "auto-runner\task_config.json"
$outputState = Join-Path $Workspace "auto-runner\state.json"

if (-not (FastFileExists $outlinePath)) {
    Write-Host "[ERROR] outline.json not found: $outlinePath" -ForegroundColor Red
    exit 1
}
$outline = FastReadJson $outlinePath
$novelTitle = if ($outline.title) { $outline.title } else { "Untitled" }

function Find-TanghuluUnit {
    param($chapterNum, $outlineData)
    $tanghuluProps = $outlineData.PSObject.Properties | Where-Object { $_.Name -like "tanghulu_vol*" }
    foreach ($prop in $tanghuluProps) {
        foreach ($unit in $prop.Value) {
            if ($unit.chapters -match "^(\d+)-(\d+)$") {
                $start = [int]$Matches[1]
                $end = [int]$Matches[2]
                if ($chapterNum -ge $start -and $chapterNum -le $end) {
                    return @{ Unit = $unit; VolKey = $prop.Name; UnitIndex = [array]::IndexOf($prop.Value, $unit) }
                }
            }
        }
    }
    return $null
}

function Format-Ch3 { param([int]$num); return $num.ToString("000") }

$openingStyles = @("action", "sensory", "dialogue", "scene_action", "suspense", "atmosphere")
$endingStyles = @("ambiguity_reversal", "action_unfinished", "info_reveal", "dialogue_ending", "scene_description", "anticipation")

$steps = [System.Collections.ArrayList]::new()
$stepId = 0
$chapters = $StartChapter..$EndChapter
$totalChapters = $chapters.Count
$prevChapterDetailId = $null
$prevChapterDeaiId = $null

Write-Host ""
Write-Host "=== Task Config Generator v1.0 ===" -ForegroundColor Cyan
Write-Host "Novel: $novelTitle"
Write-Host "Range: Ch$StartChapter - Ch$EndChapter ($totalChapters chapters)"
Write-Host "Mode: $ReviewMode"
Write-Host ""

for ($i = 0; $i -lt $totalChapters; $i++) {
    $chNum = $chapters[$i]
    $ch3 = Format-Ch3 $chNum
    $prevCh3 = if ($chNum -gt 1) { Format-Ch3 ($chNum - 1) } else { "" }
    $hasPrev = ($chNum -gt 1)
    $isFirst = ($i -eq 0)
    $isLast = ($i -eq $totalChapters - 1)

    $unitInfo = Find-TanghuluUnit -chapterNum $chNum -outlineData $outline
    $unitTitle = if ($unitInfo) { $unitInfo.Unit.title } else { "N/A" }
    $unitRef = if ($unitInfo) { "$($unitInfo.VolKey)[$($unitInfo.UnitIndex)]" } else { "N/A" }
    $beats = if ($unitInfo) {
        if ($unitInfo.Unit.climax) { $unitInfo.Unit.climax }
        elseif ($unitInfo.Unit.core_beats) { $unitInfo.Unit.core_beats }
        else { "See outline" }
    } else { "See outline" }

    $openIdx = ($chNum - 1) % 6
    $endIdx = ($chNum - 1) % 6
    $openStyle = $openingStyles[$openIdx]
    $endStyle = $endingStyles[$endIdx]

    # --- Step A: Write ---
    $writeInstr = "Read auto-runner/context_cache.json (reference cached summary for chapter-writer) OR Read .trae/skills/chapter-writer/SKILL.md if cache miss. Read memory/outline.json ($unitRef) for Ch$chNum beats. Core: $beats."
    if ($hasPrev) { $writeInstr += " Read output/chapter_$prevCh3.txt for continuity." }
    $writeInstr += " Write ~2800 words, one sentence per line. Opening: $openStyle. Ending: $endStyle. Follow all writing rules."

    $writeInputs = @("memory/outline.json", "memory/characters.json", "memory/goal_tracker.json", ".trae/skills/chapter-writer/SKILL.md")
    if ($hasPrev) { $writeInputs = @("memory/outline.json", "memory/characters.json", "memory/goal_tracker.json", "output/chapter_$prevCh3.txt", ".trae/skills/chapter-writer/SKILL.md") }

    $writeOutputs = @("output/chapter_$ch3.txt")

    if ($isFirst) {
        $writeStep = @{
            id = $stepId; name = "Ch$chNum Write"; agent = "chapter-writer"
            instruction = $writeInstr
            input_files = $writeInputs; output_files = $writeOutputs
            pass_criteria = "chapter_$ch3.txt exists, wordcount>=2500, opening=$openStyle"
            max_retries = 2; parallel_group = $null; depends_on = @()
        }
    } else {
        $prevChNum = $chapters[$i - 1]
        $pipelineGroup = "pipeline_${prevChNum}_$chNum"
        $writeStep = @{
            id = $stepId; name = "Ch$chNum Write (parallel w/ Ch$prevChNum review)"; agent = "chapter-writer"
            instruction = $writeInstr + " This step runs in parallel with Ch$prevChNum review."
            input_files = $writeInputs; output_files = $writeOutputs
            pass_criteria = "chapter_$ch3.txt exists, wordcount>=2500, opening=$openStyle (differs from prev)"
            max_retries = 2; parallel_group = $pipelineGroup; parallel_index = 1; parallel_total = 2
            depends_on = @($prevChapterDetailId, $prevChapterDeaiId)
        }
    }
    $null = $steps.Add($writeStep)
    $stepId++

    # --- Step B: Detail Review (parallel) ---
    $reviewGroup = "review_ch$chNum"
    $detailInstr = "Read auto-runner/context_cache.json (reference cached summary for detail-reviewer) OR Read .trae/skills/detail-reviewer/SKILL.md if cache miss. Analyze Ch$chNum (analysis mode, do NOT edit text). Read output/chapter_$ch3.txt"
    if ($hasPrev) { $detailInstr += " and output/chapter_$prevCh3.txt for continuity." }
    $detailInstr += ". Check: opening/ending variety, rhythm, character anchors, Show vs Tell, attraction elements, hook strength(>=B), cross-chapter facts, darkline pacing. Output to handoff/chapters/detail_review_ch$ch3.json."

    $detailInputs = @("output/chapter_$ch3.txt", "memory/outline.json", "memory/characters.json", "memory/foreshadowing_tracker.json", ".trae/skills/detail-reviewer/SKILL.md")
    if ($hasPrev) { $detailInputs = @("output/chapter_$ch3.txt", "output/chapter_$prevCh3.txt", "memory/outline.json", "memory/characters.json", "memory/foreshadowing_tracker.json", ".trae/skills/detail-reviewer/SKILL.md") }

    $detailStep = @{
        id = $stepId; name = "Ch$chNum Detail Review (parallel)"; agent = "detail-reviewer"
        instruction = $detailInstr
        input_files = $detailInputs; output_files = @("handoff/chapters/detail_review_ch$ch3.json")
        pass_criteria = "Output contains graded issues (critical/major/minor) and cross-chapter variety check"
        max_retries = 2; parallel_group = $reviewGroup; parallel_index = 0; parallel_total = 2
        depends_on = @($stepId - 1)
    }
    $null = $steps.Add($detailStep)
    $stepId++

    # --- Step C: De-AI Analysis (parallel) ---
    $deaiStep = @{
        id = $stepId; name = "Ch$chNum De-AI Analysis (parallel)"; agent = "de-ai-processor"
        instruction = "Read auto-runner/context_cache.json (reference cached summary for de-ai-processor) OR Read .trae/skills/de-ai-processor/SKILL.md if cache miss. Analyze Ch$chNum (analysis_mode=true, do NOT edit). Read output/chapter_$ch3.txt. Detect 14 AI patterns: Show vs Tell, formulaic words, repetition, flat emotion, logic chains, emotion-telling, meaningless actions. Output to handoff/chapters/de_ai_analysis_ch$ch3.json."
        input_files = @("output/chapter_$ch3.txt", ".trae/skills/de-ai-processor/SKILL.md")
        output_files = @("handoff/chapters/de_ai_analysis_ch$ch3.json")
        pass_criteria = "Output contains ai_score(<=2.0 pass) and detection details"
        max_retries = 2; parallel_group = $reviewGroup; parallel_index = 1; parallel_total = 2
        depends_on = @($stepId - 2)
    }
    $null = $steps.Add($deaiStep)
    $stepId++

    # --- Step D: Unified Review + Merge (v2.5: Merge integrated into Review) ---
    if ($ReviewMode -eq "unified") {
        $reviewInstr = "Read auto-runner/context_cache.json (reference cached summary for quality-reviewer) OR Read .trae/skills/quality-reviewer/SKILL.md if cache miss. Unified review+merge mode for Ch$chNum. Read auto-runner/unified_review_spec.md for 12-dimension spec. PHASE 1 (Merge): Read handoff/chapters/detail_review_ch$ch3.json and handoff/chapters/de_ai_analysis_ch$ch3.json. Apply conflict rules: same-loc diff-cause -> take higher severity; same-loc conflict -> detail priority; one-sided -> keep. Fix critical first, then major. Apply to output/chapter_$ch3.txt. Output merged_review to handoff/chapters/merged_review_ch$ch3.json. PHASE 2 (Review): Based on the MERGED text, execute 8 technical + 4 supplementary dimensions + monitoring + cross-check. unified_score = technical_score x 0.6 + supplementary_score x 0.4. >= 9.5 = approved."
        $reviewInputs = @("output/chapter_$ch3.txt", "memory/outline.json", "memory/characters.json", "memory/goal_tracker.json", "memory/foreshadowing_tracker.json", "config/novel_config.json", "handoff/chapters/detail_review_ch$ch3.json", "handoff/chapters/de_ai_analysis_ch$ch3.json", "auto-runner/unified_review_spec.md")
        $reviewOutputs = @("output/chapter_$ch3.txt", "handoff/chapters/merged_review_ch$ch3.json", "handoff/chapters/unified_review_ch$ch3.json")
        $reviewPass = "All critical fixed, 12-dimension scores + unified_score + verdict present, unified_score >= 9.5 = approved"

        if ($isLast) {
            $reviewStep = @{
                id = $stepId; name = "Ch$chNum Unified Review+Merge"; agent = "quality-reviewer"
                instruction = $reviewInstr
                input_files = $reviewInputs; output_files = $reviewOutputs
                pass_criteria = $reviewPass; max_retries = 3; parallel_group = $null
                depends_on = @(($stepId - 2), ($stepId - 1))
            }
        } else {
            $nextChNum = $chapters[$i + 1]
            $pipelineGroup = "pipeline_${chNum}_$nextChNum"
            $reviewStep = @{
                id = $stepId; name = "Ch$chNum Unified Review+Merge (parallel w/ Ch$nextChNum write)"; agent = "quality-reviewer"
                instruction = $reviewInstr + " This step runs in parallel with Ch$nextChNum write."
                input_files = $reviewInputs; output_files = $reviewOutputs
                pass_criteria = $reviewPass; max_retries = 3
                parallel_group = $pipelineGroup; parallel_index = 0; parallel_total = 2
                depends_on = @(($stepId - 2), ($stepId - 1))
            }
        }
        $null = $steps.Add($reviewStep)
        $reviewId = $stepId
        $stepId++
    } else {
        $qInstr = "Read auto-runner/context_cache.json (reference cached summary for quality-reviewer) OR Read .trae/skills/quality-reviewer/SKILL.md if cache miss. Quality review+merge Ch$chNum. PHASE 1 (Merge): Read handoff/chapters/detail_review_ch$ch3.json and handoff/chapters/de_ai_analysis_ch$ch3.json. Apply conflict rules, fix critical first. Apply to output/chapter_$ch3.txt. Output merged_review to handoff/chapters/merged_review_ch$ch3.json. PHASE 2 (Quality): Score 8 dimensions (attraction/shuang/rhythm/hook/character/plot/logic/writing). technical_score >= 9.5 = pass. Output to handoff/chapters/quality_review_ch$ch3.json."
        $qInputs = @("output/chapter_$ch3.txt", "memory/outline.json", "memory/characters.json", "memory/goal_tracker.json", "handoff/chapters/detail_review_ch$ch3.json", "handoff/chapters/de_ai_analysis_ch$ch3.json", ".trae/skills/quality-reviewer/SKILL.md")
        $qStep = @{
            id = $stepId; name = "Ch$chNum Quality Review+Merge"; agent = "quality-reviewer"
            instruction = $qInstr; input_files = $qInputs
            output_files = @("output/chapter_$ch3.txt", "handoff/chapters/merged_review_ch$ch3.json", "handoff/chapters/quality_review_ch$ch3.json")
            pass_criteria = "All critical fixed, output has 8-dim scores, technical_score >= 9.5, verdict = pass"
            max_retries = 3; parallel_group = $null; depends_on = @(($stepId - 2), ($stepId - 1))
        }
        $null = $steps.Add($qStep)
        $qId = $stepId
        $stepId++

        $fInstr = "Read auto-runner/context_cache.json (reference cached summary for final-reviewer) OR Read .trae/skills/final-reviewer/SKILL.md if cache miss. Final review Ch$chNum. Reference quality technical_score x 0.6 + supplementary 4-dim x 0.4 = final_score. >= 9.5 = approved."
        $fInputs = @("output/chapter_$ch3.txt", "handoff/chapters/quality_review_ch$ch3.json", "memory/foreshadowing_tracker.json", ".trae/skills/final-reviewer/SKILL.md")
        $fOutputs = @("handoff/chapters/final_review_ch$ch3.json")
        $fPass = "Output has final_score >= 9.5, verdict = approved"

        if ($isLast) {
            $finalStep = @{
                id = $stepId; name = "Ch$chNum Final Review"; agent = "final-reviewer"
                instruction = $fInstr; input_files = $fInputs; output_files = $fOutputs
                pass_criteria = $fPass; max_retries = 3; parallel_group = $null
                depends_on = @($qId)
            }
        } else {
            $nextChNum = $chapters[$i + 1]
            $pipelineGroup = "pipeline_${chNum}_$nextChNum"
            $finalStep = @{
                id = $stepId; name = "Ch$chNum Final Review (parallel w/ Ch$nextChNum write)"; agent = "final-reviewer"
                instruction = $fInstr + " This step runs in parallel with Ch$nextChNum write."
                input_files = $fInputs; output_files = $fOutputs
                pass_criteria = $fPass; max_retries = 3
                parallel_group = $pipelineGroup; parallel_index = 0; parallel_total = 2
                depends_on = @($qId)
            }
        }
        $null = $steps.Add($finalStep)
        $reviewId = $stepId
        $stepId++
    }

    # --- Step F: Memory Manager ---
    if ($ReviewMode -eq "unified") {
        $memInputs = @("output/chapter_$ch3.txt", "handoff/chapters/unified_review_ch$ch3.json", "memory/goal_tracker.json", "memory/session_pointer.json", ".trae/skills/memory-manager/SKILL.md")
    } else {
        $memInputs = @("output/chapter_$ch3.txt", "handoff/chapters/final_review_ch$ch3.json", "memory/goal_tracker.json", "memory/session_pointer.json", ".trae/skills/memory-manager/SKILL.md")
    }
    $memStep = @{
        id = $stepId; name = "Ch$chNum Memory Commit"; agent = "memory-manager"
        instruction = "Read auto-runner/context_cache.json (reference cached summary for memory-manager) OR Read .trae/skills/memory-manager/SKILL.md if cache miss. Commit Ch${chNum}: 1) Generate chapter summary 2) Update goal_tracker 3) Update session_pointer 4) Append to full-text file 5) Update character states 6) Log."
        input_files = $memInputs
        output_files = @("memory/chapter_summaries/chapter_$ch3.json", "memory/goal_tracker.json", "memory/session_pointer.json")
        pass_criteria = "Chapter summary generated, goal_tracker updated, session_pointer updated"
        max_retries = 2; parallel_group = $null; depends_on = @($reviewId)
    }
    $null = $steps.Add($memStep)
    $stepId++

    $prevChapterDetailId = $stepId - 4
    $prevChapterDeaiId = $stepId - 3
    Write-Host "  Ch${chNum}: $unitTitle ($openStyle / $endStyle)" -ForegroundColor Green
}

# --- Build parallel groups summary ---
$pgSummary = @{}
foreach ($step in $steps) {
    if ($step.parallel_group -and -not $step.is_merger) {
        if (-not $pgSummary.ContainsKey($step.parallel_group)) {
            $pgSummary[$step.parallel_group] = @{
                type = if ($step.parallel_group -like "review_*") { "mode7" } elseif ($step.parallel_group -like "pipeline_*") { "mode8" } else { "?" }
                steps = @()
            }
        }
        $pgSummary[$step.parallel_group].steps += $step.name
    }
}

# --- Build task_config ---
$modeDesc = if ($ReviewMode -eq "unified") {
    "Unified review+merge mode (v2.5). 5 steps/chapter: write -> (detail+deai parallel) -> unified_review+merge -> memory_commit. Pipeline: Ch(N) review+merge parallel with Ch(N+1) write."
} else {
    "Traditional 2-step review+merge (v2.5). 6 steps/chapter: write -> (detail+deai parallel) -> quality+merge -> final -> memory_commit. Pipeline: Ch(N) final parallel with Ch(N+1) write."
}

$taskConfig = @{
    task_name = "$novelTitle Ch${StartChapter}-${EndChapter} Parallel Production"
    task_description = "Auto-generated. $modeDesc Total $($steps.Count) steps, covering Ch$StartChapter-Ch$EndChapter ($totalChapters chapters)."
    workspace = $Workspace
    review_mode = $ReviewMode
    generated_at = (Get-Date).ToString("o")
    generated_by = "generate_task_config.ps1 v2.5"
    steps = $steps
    parallel_groups_summary = $pgSummary
}

# --- Build state.json ---
$stateSteps = @()
foreach ($step in $steps) {
    $stateSteps += @{
        id = $step.id; name = $step.name; agent = $step.agent
        status = "pending"; retries = 0; result = $null; timestamp = $null; auto_approved = $false
    }
}

$stateParallelGroups = @()
foreach ($key in $pgSummary.Keys) {
    $groupSteps = $steps | Where-Object { $_.parallel_group -eq $key -and -not $_.is_merger }
    $mergerStep = $steps | Where-Object { $_.parallel_group -eq $key -and $_.is_merger }
    $stateParallelGroups += @{
        group_id = $key; status = "pending"
        parallel_total = $groupSteps.Count
        pending_agents = @($groupSteps.name)
        completed_agents = @(); failed_agents = @()
        merger_step_id = if ($mergerStep) { $mergerStep.id } else { $null }
        merger_ready = $false; merger_executed = $false
    }
}

$state = @{
    task_name = $taskConfig.task_name
    task_description = $taskConfig.task_description
    status = "pending"
    created_at = (Get-Date).ToString("o")
    last_run = $null; last_run_result = $null
    current_step = 0; total_steps = $steps.Count
    stop_reason = $null
    parallel_groups = $stateParallelGroups
    steps = $stateSteps
}

# --- Write files ---
FastWriteJson -Path $outputTaskConfig -Object $taskConfig
FastWriteJson -Path $outputState -Object $state

$stepsPerCh = if ($ReviewMode -eq "unified") { 5 } else { 6 }
Write-Host ""
Write-Host "=== Generation Complete ===" -ForegroundColor Cyan
Write-Host "task_config.json: $outputTaskConfig"
Write-Host "state.json: $outputState"
Write-Host "Total steps: $($steps.Count) ($stepsPerCh steps/ch x $totalChapters ch)"
Write-Host "Parallel groups: $($pgSummary.Count)"
foreach ($key in ($pgSummary.Keys | Sort-Object)) {
    $info = $pgSummary[$key]
    Write-Host "  $key ($($info.type)): $($info.steps -join ' + ')"
}
if ($ReviewMode -eq "unified") {
    Write-Host "v2.5: Merge integrated into Review (5 steps/ch, -1 vs v2.4)"
}
Write-Host ""
