<#
.SYNOPSIS
    将 handoff 目录从平铺结构迁移到分区结构。

.DESCRIPTION
    本脚本将 handoff/ 目录下的文件从平铺（扁平）结构重新组织为分区结构：

        handoff/
        ├── setup/                   立项期文件（一次性产物）
        │   ├── topic_screening.json
        │   ├── title_candidates.json
        │   ├── title_review.json
        │   ├── outline.json
        │   ├── outline_review.json
        │   ├── outline_adjustment_evaluation.md
        │   ├── skeptic_review.json
        │   ├── setting_review.json
        │   └── characters.json
        ├── chapters/                单章期文件（按章号命名）
        │   ├── draft_ch001.json     草稿元数据（从 chapter_draft 重命名）
        │   ├── merged_review_ch001.json
        │   ├── quality_review_ch001.json
        │   ├── final_review_ch001.json
        │   ├── parallel_assessment.json
        │   └── chapter_review.json
        ├── archive/                 已合并的审核源文件归档
        │   └── ch011/
        │       ├── detail_review_ch11.json
        │       └── deai_analysis_ch11.json
        └── task_plan.json           运行时文件（保留在根目录）

    迁移规则：
      1. 立项期文件 → handoff/setup/
      2. 单章期文件 → handoff/chapters/
         - chapter_draft.json        → draft_ch{NNN}.json（读取 JSON 获取章号）
         - chapter_draft_ch{N}.json  → draft_ch{NNN:03d}.json（从文件名提取章号）
         - 其余审核文件保持原名
      3. 已合并的审核源文件 → handoff/archive/ch{NNN}/
         - 当 merged_review_ch{N}.json 存在时，将 detail_review_ch{N}.json
           和 deai_analysis_ch{N}.json 归档
      4. task_plan.json 保留在 handoff/ 根目录

    特性：
      - 安全检查：移动前检查源文件是否存在
      - 幂等性：可重复运行，已移动的文件不报错
      - 详细日志：输出每一步操作详情
      - UTF-8 编码

.PARAMETER HandoffPath
    handoff 目录的路径。默认为脚本所在目录上一级的 handoff 文件夹。

.PARAMETER DryRun
    仅模拟运行，显示将要执行的操作但不实际移动文件。

.EXAMPLE
    .\migrate_directory_structure.ps1
    使用默认路径执行迁移。

.EXAMPLE
    .\migrate_directory_structure.ps1 -DryRun
    模拟运行，查看将要执行的操作。

.EXAMPLE
    .\migrate_directory_structure.ps1 -HandoffPath "D:\project\handoff"
    指定自定义 handoff 路径执行迁移。
#>

[CmdletBinding()]
param(
    [string]$HandoffPath = "",
    [switch]$DryRun
)

# ============================================================================
# 环境初始化
# ============================================================================

# 设置 UTF-8 编码，确保中文输出正确
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# 确定脚本所在目录
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# 确定 handoff 路径（默认：脚本上一级目录下的 handoff 文件夹）
if ([string]::IsNullOrWhiteSpace($HandoffPath)) {
    $HandoffPath = Join-Path (Split-Path -Parent $ScriptDir) "handoff"
}

# 定义子目录路径
$SetupDir   = Join-Path $HandoffPath "setup"
$ChaptersDir = Join-Path $HandoffPath "chapters"
$ArchiveDir = Join-Path $HandoffPath "archive"

# ============================================================================
# 日志与统计
# ============================================================================

# 统计计数器
$script:Stats = [PSCustomObject]@{
    MovedSetup    = 0
    MovedChapters = 0
    MovedArchive  = 0
    Skipped       = 0
    NotFound      = 0
    Warnings      = 0
    Errors        = 0
}

# 操作记录（用于最终摘要）
$script:Operations = [System.Collections.ArrayList]::new()

function Write-Log {
    <#
        统一日志输出函数。
        级别：INFO / SUCCESS / WARN / ERROR / SKIP / DRYRUN
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Message,

        [ValidateSet('INFO', 'SUCCESS', 'WARN', 'ERROR', 'SKIP', 'DRYRUN')]
        [string]$Level = 'INFO'
    )

    $timestamp = Get-Date -Format "HH:mm:ss"
    $prefix = "[$timestamp]"

    switch ($Level) {
        'INFO'    { $color = 'Gray';    $tag = '[INFO]   ' }
        'SUCCESS' { $color = 'Green';   $tag = '[SUCCESS]' }
        'WARN'    { $color = 'Yellow';  $tag = '[WARN]   ' }
        'ERROR'   { $color = 'Red';     $tag = '[ERROR]  ' }
        'SKIP'    { $color = 'DarkGray';$tag = '[SKIP]   ' }
        'DRYRUN'  { $color = 'Cyan';    $tag = '[DRY-RUN]' }
    }

    $line = "$prefix $tag $Message"
    Write-Host $line -ForegroundColor $color
}

function Record-Operation {
    <#
        记录一条操作到操作列表，供最终摘要使用。
    #>
    param(
        [string]$Category,
        [string]$Source,
        [string]$Destination,
        [string]$Status,
        [string]$Note = ""
    )
    [void]$script:Operations.Add([PSCustomObject]@{
        Category    = $Category
        Source      = $Source
        Destination = $Destination
        Status      = $Status
        Note        = $Note
    })
}

# ============================================================================
# 工具函数
# ============================================================================

function Format-ChapterNum {
    <#
        将章号格式化为 3 位零填充字符串。
        例：1 → "001"，11 → "011"，123 → "123"
    #>
    param([int]$Number)
    return ('{0:D3}' -f $Number)
}

function Move-FileSafely {
    <#
        安全移动文件，具备幂等性。
        - 源文件不存在 → 跳过（不报错）
        - 目标文件已存在 → 跳过（不覆盖）
        - DryRun 模式 → 仅打印不执行
        返回：'moved' | 'skipped_exists' | 'skipped_notfound'
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Source,

        [Parameter(Mandatory)]
        [string]$DestinationDir,

        [string]$DestinationName,  # 可选：目标文件名（为空则保持原名）

        [string]$Category  # 用于统计分类
    )

    # 确定目标完整路径
    if ($DestinationName) {
        $destFile = Join-Path $DestinationDir $DestinationName
    } else {
        $destFile = Join-Path $DestinationDir (Split-Path -Leaf $Source)
    }

    # 检查源文件是否存在
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        Write-Log "源文件不存在，跳过: $Source" -Level 'SKIP'
        Record-Operation -Category $Category -Source $Source -Destination $destFile -Status 'not_found'
        $script:Stats.NotFound++
        return 'skipped_notfound'
    }

    # 检查目标文件是否已存在（幂等性）
    if (Test-Path -LiteralPath $destFile -PathType Leaf) {
        Write-Log "目标已存在，跳过: $destFile" -Level 'SKIP'
        Record-Operation -Category $Category -Source $Source -Destination $destFile -Status 'skipped_exists'
        $script:Stats.Skipped++
        return 'skipped_exists'
    }

    # DryRun 模式
    if ($DryRun) {
        $leaf = Split-Path -Leaf $Source
        $destLeaf = Split-Path -Leaf $destFile
        if ($leaf -eq $destLeaf) {
            Write-Log "将移动: $Source -> $DestinationDir\" -Level 'DRYRUN'
        } else {
            Write-Log "将移动并重命名: $Source -> $destFile" -Level 'DRYRUN'
        }
        Record-Operation -Category $Category -Source $Source -Destination $destFile -Status 'dryrun'
        return 'moved'
    }

    # 实际移动
    try {
        Move-Item -LiteralPath $Source -Destination $destFile -ErrorAction Stop
        $leaf = Split-Path -Leaf $Source
        $destLeaf = Split-Path -Leaf $destFile
        if ($leaf -eq $destLeaf) {
            Write-Log "已移动: $leaf -> $DestinationDir\" -Level 'SUCCESS'
        } else {
            Write-Log "已移动并重命名: $leaf -> $destLeaf" -Level 'SUCCESS'
        }
        Record-Operation -Category $Category -Source $Source -Destination $destFile -Status 'moved'
        return 'moved'
    } catch {
        Write-Log "移动失败: $Source -> $destFile : $_" -Level 'ERROR'
        Record-Operation -Category $Category -Source $Source -Destination $destFile -Status 'error' -Note $_.ToString()
        $script:Stats.Errors++
        return 'error'
    }
}

function Get-ChapterNumFromDraftJson {
    <#
        从 chapter_draft.json 中读取章号。
        尝试多个可能的字段路径：
          content.chapter_num
          chapter_num
          chapter_number
          chapter
          chapter_id
          content.chapter
          content.chapter_number
        返回：章号（int），找不到返回 -1
    #>
    param([string]$FilePath)

    try {
        $raw = Get-Content -LiteralPath $FilePath -Raw -Encoding UTF8
        $json = $raw | ConvertFrom-Json
    } catch {
        Write-Log "无法解析 JSON: $FilePath : $_" -Level 'WARN'
        $script:Stats.Warnings++
        return -1
    }

    # 按优先级尝试多个字段路径
    $fieldPaths = @(
        'chapter_num',
        'chapter_number',
        'chapter',
        'chapter_id',
        'chapter_no',
        'content.chapter_num',
        'content.chapter_number',
        'content.chapter',
        'content.chapter_id'
    )

    foreach ($path in $fieldPaths) {
        $parts = $path -split '\.'
        $value = $json
        foreach ($part in $parts) {
            if ($null -eq $value) { break }
            $value = $value.$part
        }
        if ($null -ne $value) {
            $num = 0
            if ([int]::TryParse($value.ToString(), [ref]$num)) {
                return $num
            }
        }
    }

    return -1
}

function Find-FileInLocations {
    <#
        在多个候选位置中查找文件（用于幂等性支持）。
        返回找到的第一个完整路径，未找到返回 $null。
    #>
    param(
        [string[]]$Locations,
        [string]$FileName
    )

    foreach ($loc in $Locations) {
        $candidate = Join-Path $loc $FileName
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }
    return $null
}

# ============================================================================
# 主流程
# ============================================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  handoff 目录结构迁移脚本" -ForegroundColor Cyan
Write-Host "  平铺结构 → 分区结构 (setup / chapters / archive)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

Write-Log "脚本目录: $ScriptDir"
Write-Log "Handoff 路径: $HandoffPath"

if ($DryRun) {
    Write-Log "*** DryRun 模式已启用 —— 不会实际移动任何文件 ***" -Level 'WARN'
}

# 验证 handoff 目录存在
if (-not (Test-Path -LiteralPath $HandoffPath -PathType Container)) {
    Write-Log "handoff 目录不存在: $HandoffPath" -Level 'ERROR'
    Write-Log "请确认路径正确，或使用 -HandoffPath 参数指定。" -Level 'ERROR'
    exit 1
}

# ----------------------------------------------------------------------------
# 步骤 1-3：创建子目录
# ----------------------------------------------------------------------------

Write-Host ""
Write-Log "--- 步骤 1/6: 创建子目录 ---"

$subDirs = @(
    @{ Path = $SetupDir;   Name = 'setup' },
    @{ Path = $ChaptersDir; Name = 'chapters' },
    @{ Path = $ArchiveDir; Name = 'archive' }
)

foreach ($dir in $subDirs) {
    if (Test-Path -LiteralPath $dir.Path -PathType Container) {
        Write-Log "目录已存在: $($dir.Path)" -Level 'SKIP'
    } else {
        if ($DryRun) {
            Write-Log "将创建目录: $($dir.Path)" -Level 'DRYRUN'
        } else {
            New-Item -Path $dir.Path -ItemType Directory -Force | Out-Null
            Write-Log "已创建目录: $($dir.Path)" -Level 'SUCCESS'
        }
    }
}

# ----------------------------------------------------------------------------
# 步骤 4：迁移立项期文件 → handoff/setup/
# ----------------------------------------------------------------------------

Write-Host ""
Write-Log "--- 步骤 2/6: 迁移立项期文件 → setup/ ---"

$setupFiles = @(
    'topic_screening.json',
    'title_candidates.json',
    'title_review.json',
    'outline.json',
    'outline_review.json',
    'outline_adjustment_evaluation.md',
    'skeptic_review.json',
    'setting_review.json',
    'characters.json'
)

foreach ($fileName in $setupFiles) {
    $src = Join-Path $HandoffPath $fileName
    $result = Move-FileSafely -Source $src -DestinationDir $SetupDir -Category 'setup'
    if ($result -eq 'moved') {
        $script:Stats.MovedSetup++
    }
}

# ----------------------------------------------------------------------------
# 步骤 5：迁移单章期文件 → handoff/chapters/
# ----------------------------------------------------------------------------

Write-Host ""
Write-Log "--- 步骤 3/6: 迁移单章期文件 → chapters/ ---"

# 5a. chapter_draft_ch{N}.json → draft_ch{NNN:03d}.json
#     从文件名提取章号并重命名
Write-Log "处理 chapter_draft_ch{N}.json 系列文件..."

$draftPattern = '^chapter_draft_ch(\d+)\.json$'
$rootFiles = Get-ChildItem -LiteralPath $HandoffPath -File -ErrorAction SilentlyContinue

foreach ($file in $rootFiles) {
    if ($file.Name -match $draftPattern) {
        $chapterNum = [int]$Matches[1]
        $paddedNum = Format-ChapterNum -Number $chapterNum
        $destName = "draft_ch${paddedNum}.json"
        $src = $file.FullName

        $result = Move-FileSafely -Source $src -DestinationDir $ChaptersDir -DestinationName $destName -Category 'chapters'
        if ($result -eq 'moved') {
            $script:Stats.MovedChapters++
        }
    }
}

# 5b. chapter_draft.json（无章号后缀）→ draft_ch{NNN}.json
#     读取 JSON 获取章号；若无章号则保持原名移动
Write-Log "处理 chapter_draft.json（无后缀）..."

$plainDraft = Join-Path $HandoffPath 'chapter_draft.json'
if (Test-Path -LiteralPath $plainDraft -PathType Leaf) {
    $chapterNum = Get-ChapterNumFromDraftJson -FilePath $plainDraft
    if ($chapterNum -gt 0) {
        $paddedNum = Format-ChapterNum -Number $chapterNum
        $destName = "draft_ch${paddedNum}.json"
        Write-Log "从 JSON 中读取到章号: $chapterNum -> $paddedNum"
        $result = Move-FileSafely -Source $plainDraft -DestinationDir $ChaptersDir -DestinationName $destName -Category 'chapters'
        if ($result -eq 'moved') {
            $script:Stats.MovedChapters++
        }
    } else {
        Write-Log "chapter_draft.json 中未找到章号，保持原名移动到 chapters/" -Level 'WARN'
        $script:Stats.Warnings++
        $result = Move-FileSafely -Source $plainDraft -DestinationDir $ChaptersDir -Category 'chapters'
        if ($result -eq 'moved') {
            $script:Stats.MovedChapters++
        }
    }
} else {
    Write-Log "chapter_draft.json 不存在，跳过" -Level 'SKIP'
    $script:Stats.NotFound++
}

# 5c. 保持原名的单章期文件
Write-Log "处理保持原名的单章期文件..."

$keepNameChapterFiles = @(
    'parallel_assessment.json',
    'chapter_review.json'
)

# 审核文件使用通配符匹配，保持原名
$reviewPatterns = @(
    'detail_review_ch*.json',
    'deai_analysis_ch*.json',
    'merged_review_ch*.json',
    'quality_review_ch*.json',
    'final_review_ch*.json'
)

# 先处理通配符匹配的审核文件
foreach ($pattern in $reviewPatterns) {
    $matchedFiles = Get-ChildItem -LiteralPath $HandoffPath -Filter $pattern -File -ErrorAction SilentlyContinue
    foreach ($file in $matchedFiles) {
        $result = Move-FileSafely -Source $file.FullName -DestinationDir $ChaptersDir -Category 'chapters'
        if ($result -eq 'moved') {
            $script:Stats.MovedChapters++
        }
    }
}

# 再处理固定名称的文件
foreach ($fileName in $keepNameChapterFiles) {
    $src = Join-Path $HandoffPath $fileName
    $result = Move-FileSafely -Source $src -DestinationDir $ChaptersDir -Category 'chapters'
    if ($result -eq 'moved') {
        $script:Stats.MovedChapters++
    }
}

# ----------------------------------------------------------------------------
# 步骤 6：归档已合并的审核源文件 → handoff/archive/ch{NNN}/
# ----------------------------------------------------------------------------

Write-Host ""
Write-Log "--- 步骤 4/6: 归档已合并的审核源文件 → archive/ ---"

# 查找所有 merged_review_ch{N}.json 文件（可能在 chapters/ 或 handoff 根目录）
$mergedSearchDirs = @($ChaptersDir, $HandoffPath)
$mergedFiles = [System.Collections.ArrayList]::new()

foreach ($dir in $mergedSearchDirs) {
    if (Test-Path -LiteralPath $dir -PathType Container) {
        $found = Get-ChildItem -LiteralPath $dir -Filter 'merged_review_ch*.json' -File -ErrorAction SilentlyContinue
        foreach ($f in $found) {
            # 避免重复添加
            $existing = $mergedFiles | Where-Object { $_.Name -eq $f.Name }
            if (-not $existing) {
                [void]$mergedFiles.Add($f)
            }
        }
    }
}

if ($mergedFiles.Count -eq 0) {
    Write-Log "未找到任何 merged_review_ch{N}.json 文件，跳过归档步骤" -Level 'SKIP'
} else {
    Write-Log "找到 $($mergedFiles.Count) 个 merged_review 文件，检查可归档的源文件..."

    $mergedPattern = '^merged_review_ch(\d+)\.json$'

    foreach ($mergedFile in $mergedFiles) {
        if ($mergedFile.Name -match $mergedPattern) {
            $chapterNum = [int]$Matches[1]
            $paddedNum = Format-ChapterNum -Number $chapterNum
            $archiveSubDir = Join-Path $ArchiveDir "ch${paddedNum}"

            Write-Log "处理章号 $chapterNum (归档目录: ch${paddedNum})"

            # 需要归档的源文件
            $sourceFileNames = @(
                "detail_review_ch${chapterNum}.json",
                "deai_analysis_ch${chapterNum}.json"
            )

            # 候选搜索位置：chapters/ 和 handoff 根目录（不含 archive，避免重复归档）
            $searchLocations = @($ChaptersDir, $HandoffPath)
            $anyMoved = $false

            foreach ($srcFileName in $sourceFileNames) {
                $foundPath = Find-FileInLocations -Locations $searchLocations -FileName $srcFileName

                if ($foundPath) {
                    # 创建归档子目录
                    if (-not (Test-Path -LiteralPath $archiveSubDir -PathType Container)) {
                        if ($DryRun) {
                            Write-Log "将创建归档子目录: $archiveSubDir" -Level 'DRYRUN'
                        } else {
                            New-Item -Path $archiveSubDir -ItemType Directory -Force | Out-Null
                            Write-Log "已创建归档子目录: $archiveSubDir" -Level 'SUCCESS'
                        }
                    }

                    $result = Move-FileSafely -Source $foundPath -DestinationDir $archiveSubDir -Category 'archive'
                    if ($result -eq 'moved') {
                        $script:Stats.MovedArchive++
                        $anyMoved = $true
                    }
                } else {
                    Write-Log "  源文件不存在（可能已归档）: $srcFileName" -Level 'SKIP'
                }
            }

            if (-not $anyMoved) {
                Write-Log "  章 $chapterNum 无需归档的文件（均已归档或不存在）" -Level 'SKIP'
            }
        } else {
            Write-Log "文件名不匹配章号模式，跳过: $($mergedFile.Name)" -Level 'WARN'
            $script:Stats.Warnings++
        }
    }
}

# ----------------------------------------------------------------------------
# 步骤 7：确认 task_plan.json 保留在根目录
# ----------------------------------------------------------------------------

Write-Host ""
Write-Log "--- 步骤 5/6: 确认 task_plan.json 保留在根目录 ---"

$taskPlanPath = Join-Path $HandoffPath 'task_plan.json'
if (Test-Path -LiteralPath $taskPlanPath -PathType Leaf) {
    Write-Log "task_plan.json 已在根目录，无需移动" -Level 'SUCCESS'
} else {
    Write-Log "task_plan.json 不存在（可能是尚未创建），无需操作" -Level 'SKIP'
}

# ----------------------------------------------------------------------------
# 步骤 8：输出迁移摘要
# ----------------------------------------------------------------------------

Write-Host ""
Write-Log "--- 步骤 6/6: 迁移摘要 ---"
Write-Host ""

if ($DryRun) {
    Write-Host "  [DRY-RUN 模式] 以下为模拟结果，实际未移动任何文件。" -ForegroundColor Cyan
    Write-Host ""
}

$summaryTable = @"
  ================================================================
                       迁移摘要
  ================================================================
  立项期文件移动 (setup)      : $($script:Stats.MovedSetup)
  单章期文件移动 (chapters)   : $($script:Stats.MovedChapters)
  归档文件移动   (archive)    : $($script:Stats.MovedArchive)
  ----------------------------------------------------------------
  跳过（已存在/幂等）         : $($script:Stats.Skipped)
  未找到（源文件不存在）       : $($script:Stats.NotFound)
  警告                         : $($script:Stats.Warnings)
  错误                         : $($script:Stats.Errors)
  ================================================================
"@

Write-Host $summaryTable -ForegroundColor White

# 输出操作明细表
if ($script:Operations.Count -gt 0) {
    Write-Host ""
    Write-Log "操作明细:"
    Write-Host ""

    $grouped = $script:Operations | Group-Object -Property Category
    foreach ($group in $grouped) {
        $categoryName = switch ($group.Name) {
            'setup'    { '立项期 → setup/' }
            'chapters' { '单章期 → chapters/' }
            'archive'  { '归档   → archive/' }
            default    { $group.Name }
        }
        Write-Host "  [$categoryName]" -ForegroundColor Cyan
        foreach ($op in $group.Group) {
            $srcLeaf = if ($op.Source) { Split-Path -Leaf $op.Source } else { '-' }
            $destLeaf = if ($op.Destination) { Split-Path -Leaf $op.Destination } else { '-' }
            $statusColor = switch ($op.Status) {
                'moved'          { 'Green' }
                'dryrun'         { 'Cyan' }
                'skipped_exists' { 'DarkGray' }
                'not_found'      { 'DarkGray' }
                'error'          { 'Red' }
                default          { 'White' }
            }
            $statusText = switch ($op.Status) {
                'moved'          { '已移动' }
                'dryrun'         { '将移动' }
                'skipped_exists' { '已存在' }
                'not_found'      { '不存在' }
                'error'          { '错误' }
                default          { $op.Status }
            }
            if ($srcLeaf -eq $destLeaf) {
                $detail = "$srcLeaf"
            } else {
                $detail = "$srcLeaf -> $destLeaf"
            }
            Write-Host "    $detail" -NoNewline
            Write-Host " [$statusText]" -ForegroundColor $statusColor
        }
        Write-Host ""
    }
}

# 最终状态
Write-Host "  ================================================================" -ForegroundColor Cyan
if ($script:Stats.Errors -gt 0) {
    Write-Host "  迁移完成（含 $($script:Stats.Errors) 个错误，请检查日志）" -ForegroundColor Yellow
} elseif ($DryRun) {
    Write-Host "  DryRun 模拟完成。如需执行实际迁移，请去掉 -DryRun 参数重新运行。" -ForegroundColor Cyan
} else {
    Write-Host "  迁移完成。" -ForegroundColor Green
}
Write-Host "  ================================================================" -ForegroundColor Cyan
Write-Host ""

# 列出迁移后的目录结构
Write-Log "迁移后 handoff 目录结构:"
Write-Host ""

function Show-DirectoryTree {
    param([string]$Path, [string]$Prefix = "  ")

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        return
    }

    $items = Get-ChildItem -LiteralPath $Path -ErrorAction SilentlyContinue | Sort-Object -Property @{Expression={!$_.PSIsContainer}}, Name

    for ($i = 0; $i -lt $items.Count; $i++) {
        $item = $items[$i]
        $isLast = ($i -eq $items.Count - 1)
        $connector = if ($isLast) { '└── ' } else { '├── ' }

        if ($item.PSIsContainer) {
            Write-Host "$Prefix$connector$($item.Name)/" -ForegroundColor Blue
            if ($isLast) {
                $childPrefix = $Prefix + '    '
            } else {
                $childPrefix = $Prefix + ([char]0x2502 + '   ')
            }
            Show-DirectoryTree -Path $item.FullName -Prefix $childPrefix
        } else {
            Write-Host "$Prefix$connector$($item.Name)"
        }
    }
}

Show-DirectoryTree -Path $HandoffPath

Write-Host ""
Write-Log "脚本执行结束。"
