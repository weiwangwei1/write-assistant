<#
.SYNOPSIS
  上下文预加载脚本 v1.0
  预读常用文件并生成缓存清单，减少重复文件读取，降低上下文消耗。
  缓存 Skill 的 SKILL.md 摘要，避免每次步骤执行都重新读取完整文件。

.DESCRIPTION
  功能：
  - 预读所有 .trae/skills/*/SKILL.md 文件，提取摘要与规则统计
  - 预读 memory / config / auto-runner 下的常用 JSON 与 Markdown 文件
  - 生成 context_cache.json 缓存清单
  - 基于文件最后修改时间进行缓存验证（命中则跳过，未命中则重新读取）

.PARAMETER Workspace
  工作目录路径（默认：脚本所在目录的父目录，即项目根目录）

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File context_preloader.ps1
  powershell -ExecutionPolicy Bypass -File context_preloader.ps1 -Workspace "d:\path\to\workspace"
#>

param(
    [string]$Workspace = (Split-Path $PSScriptRoot -Parent)
)

$ErrorActionPreference = "Stop"

# ============================================================
#  工作目录验证
# ============================================================
if (-not (Test-Path $Workspace)) {
    Write-Host "[ERROR] 工作目录不存在: $Workspace" -ForegroundColor Red
    exit 1
}

$cachePath = Join-Path $PSScriptRoot "context_cache.json"
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

# ============================================================
#  辅助函数
# ============================================================

# 获取文件信息（大小 + 最后修改时间），一次 Get-Item 获取全部
function Get-FileInfo {
    param([string]$Path)
    $item = Get-Item $Path
    return @{
        Size         = $item.Length
        LastModified = $item.LastWriteTime.ToString("yyyy-MM-ddTHH:mm:sszzz")
    }
}

# 提取 SKILL.md 正文（跳过 YAML frontmatter）
function Get-SkillBody {
    param([string]$Path)
    $content = Get-Content $Path -Raw -Encoding UTF8
    if (-not $content) { return "" }
    # 跳过 YAML frontmatter（--- ... --- 之间的内容）
    if ($content -match '(?s)^---\r?\n.*?\r?\n---\r?\n?(.*)') {
        return $Matches[1]
    }
    return $content
}

# 提取前 N 字符摘要（核心指令提取）
function Get-Summary {
    param([string]$Text, [int]$MaxLength = 500)
    $trimmed = $Text.Trim()
    if ($trimmed.Length -gt $MaxLength) {
        return $trimmed.Substring(0, $MaxLength)
    }
    return $trimmed
}

# 统计关键规则数量（匹配规则关键词的行数，每行最多计1次）
function Get-RuleCount {
    param([string]$Content)
    $ruleKeywords = @(
        '法则', '规则', '要求', '禁令', '必须', '不得', '硬性',
        '检测', '约束', '验证', '硬拦截', '禁止', '严禁', '门禁',
        '强制', '不可跳过', '不超过', '至少', '不可', '一律'
    )
    $count = 0
    $lines = $Content -split "`r?`n"
    foreach ($line in $lines) {
        foreach ($kw in $ruleKeywords) {
            if ($line -match $kw) {
                $count++
                break  # 每行只计一次
            }
        }
    }
    return $count
}

# 提取 JSON 顶层 key 列表
function Get-JsonTopKeys {
    param([string]$Path)
    try {
        $json = Get-Content $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($json -is [System.Array]) {
            # JSON 数组无顶层 key
            return @("__array__")
        }
        $keys = @()
        foreach ($prop in $json.PSObject.Properties) {
            $keys += $prop.Name
        }
        return $keys
    } catch {
        return @("__parse_error__")
    }
}

# 转为相对路径（统一使用正斜杠）
function ConvertTo-RelPath {
    param([string]$FullPath, [string]$BasePath)
    $rel = $FullPath.Substring($BasePath.Length).TrimStart('\', '/')
    return ($rel -replace '\\', '/')
}

# ============================================================
#  加载现有缓存（用于缓存验证）
# ============================================================
$existingCache = $null
if (Test-Path $cachePath) {
    try {
        $existingCache = Get-Content $cachePath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Write-Host "[WARN] 缓存文件解析失败，将全量重建" -ForegroundColor DarkYellow
        $existingCache = $null
    }
}

# 构建缓存查找表（以相对路径为 key）
$skillLookup = @{}
$fileLookup = @{}
if ($existingCache -and $existingCache.skills) {
    foreach ($s in $existingCache.skills) {
        $skillLookup[$s.path] = $s
    }
}
if ($existingCache -and $existingCache.files) {
    foreach ($f in $existingCache.files) {
        $fileLookup[$f.path] = $f
    }
}

$cacheHits = 0
$cacheMisses = 0
$skillsCache = @()
$filesCache = @()

# ============================================================
#  输出头部
# ============================================================
Write-Host ""
Write-Host "=== 上下文预加载 v1.0 ===" -ForegroundColor Cyan
Write-Host "工作目录: $Workspace"
Write-Host "缓存文件: $cachePath"
Write-Host ""

# ============================================================
#  1. 预读 Skill 文件（.trae/skills/*/SKILL.md）
# ============================================================
Write-Host "[1/2] 预读 Skill 文件..." -ForegroundColor Yellow

$skillsDir = Join-Path $Workspace ".trae\skills"
if (Test-Path $skillsDir) {
    $skillDirs = Get-ChildItem $skillsDir -Directory | Sort-Object Name
    foreach ($dir in $skillDirs) {
        $skillFile = Join-Path $dir.FullName "SKILL.md"
        if (-not (Test-Path $skillFile)) {
            continue  # 文件不存在时跳过而非报错
        }

        $relPath = ConvertTo-RelPath -FullPath $skillFile -BasePath $Workspace
        $info = Get-FileInfo -Path $skillFile

        # 缓存验证：比较最后修改时间
        $cached = $skillLookup[$relPath]
        if ($cached -and $cached.last_modified -eq $info.LastModified) {
            # 缓存命中，直接复用缓存数据
            $skillsCache += $cached
            $cacheHits++
            Write-Host "  cache hit : $relPath" -ForegroundColor Green
        } else {
            # 缓存未命中，重新读取文件
            $body = Get-SkillBody -Path $skillFile
            $summary = Get-Summary -Text $body -MaxLength 500
            $ruleCount = Get-RuleCount -Content $body

            $skillEntry = [PSCustomObject]@{
                name          = $dir.Name
                path          = $relPath
                size          = $info.Size
                last_modified = $info.LastModified
                summary       = $summary
                rule_count    = $ruleCount
            }
            $skillsCache += $skillEntry
            $cacheMisses++
            Write-Host "  cache miss: $relPath (重新读取, $($ruleCount) 条规则)" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "  [SKIP] .trae\skills 目录不存在" -ForegroundColor DarkGray
}

# ============================================================
#  2. 预读其他文件
# ============================================================
Write-Host ""
Write-Host "[2/2] 预读其他文件..." -ForegroundColor Yellow

# 预读文件列表
$otherFiles = @(
    "memory/outline.json",
    "memory/characters.json",
    "memory/goal_tracker.json",
    "memory/session_pointer.json",
    "memory/foreshadowing_tracker.json",
    "config/novel_config.json",
    "auto-runner/unified_review_spec.md",
    "auto-runner/parallel_task_config_template.json"
)

foreach ($relFile in $otherFiles) {
    $fullPath = Join-Path $Workspace ($relFile -replace '/', '\')
    if (-not (Test-Path $fullPath)) {
        Write-Host "  skip      : $relFile (文件不存在)" -ForegroundColor DarkGray
        continue  # 文件不存在时跳过而非报错
    }

    $info = Get-FileInfo -Path $fullPath

    # 缓存验证
    $cached = $fileLookup[$relFile]
    if ($cached -and $cached.last_modified -eq $info.LastModified) {
        # 缓存命中
        $filesCache += $cached
        $cacheHits++
        Write-Host "  cache hit : $relFile" -ForegroundColor Green
    } else {
        # 缓存未命中，重新读取
        $isJson = $relFile -match '\.json$'
        $topKeys = @()
        $fileType = "markdown"
        if ($isJson) {
            $topKeys = Get-JsonTopKeys -Path $fullPath
            $fileType = "json"
        }

        $fileEntry = [PSCustomObject]@{
            path           = $relFile
            size           = $info.Size
            last_modified  = $info.LastModified
            type           = $fileType
            top_level_keys = $topKeys
        }
        $filesCache += $fileEntry
        $cacheMisses++
        if ($isJson) {
            $keyStr = "keys: $($topKeys -join ', ')"
        } else {
            $keyStr = "markdown"
        }
        Write-Host "  cache miss: $relFile ($keyStr)" -ForegroundColor Yellow
    }
}

# ============================================================
#  3. 生成缓存文件 (context_cache.json)
# ============================================================
$totalSize = 0
foreach ($s in $skillsCache) { $totalSize += $s.size }
foreach ($f in $filesCache)   { $totalSize += $f.size }

$cacheData = [PSCustomObject]@{
    cache_version = "1.0"
    generated_at  = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
    workspace     = $Workspace
    skills        = @($skillsCache)
    files         = @($filesCache)
    stats         = [PSCustomObject]@{
        total_skills     = $skillsCache.Count
        total_files      = $filesCache.Count
        cache_hits       = $cacheHits
        cache_misses     = $cacheMisses
        total_size_bytes = $totalSize
    }
}

# 写入 UTF-8 BOM 编码的 JSON
$json = $cacheData | ConvertTo-Json -Depth 10
$utf8Bom = New-Object System.Text.UTF8Encoding($true)
[System.IO.File]::WriteAllText($cachePath, $json, $utf8Bom)

$stopwatch.Stop()

# ============================================================
#  输出汇总
# ============================================================
Write-Host ""
Write-Host "=== 预加载完成 ===" -ForegroundColor Cyan
Write-Host "Skill 数量  : $($skillsCache.Count)"
Write-Host "其他文件    : $($filesCache.Count)"
Write-Host "缓存命中    : $cacheHits"
Write-Host "缓存未命中  : $cacheMisses"
Write-Host "总大小      : $([math]::Round($totalSize / 1KB, 1)) KB"
Write-Host "耗时        : $($stopwatch.Elapsed.TotalSeconds.ToString('F2')) 秒"
Write-Host "缓存文件    : $cachePath"
Write-Host ""
