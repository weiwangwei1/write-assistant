<#
.SYNOPSIS
    执行监控看板生成脚本。

.DESCRIPTION
    读取同目录下的 state.json 与 task_config.json，合并步骤元数据与运行时状态，
    生成一个自包含（内联 CSS + JS）的暗色主题 HTML 执行监控看板：
      1. 顶部 KPI 区域
      2. 步骤详情表格
      3. 并行组可视化
      4. 甘特图时间线（基于依赖关系的预估时序）
      5. 依赖关系图（SVG）

.PARAMETER Workspace
    工作目录，默认为脚本所在目录。脚本会读取该目录下的 state.json 与 task_config.json，
    并将 execution_dashboard.html 输出到同一目录。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File generate_dashboard.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File generate_dashboard.ps1 -Workspace "D:\personFile\write-assistant\auto-runner"
#>
param(
    [string]$Workspace = $PSScriptRoot
)

$ErrorActionPreference = 'Stop'

# 加载快速文件 I/O 模块
. (Join-Path $PSScriptRoot 'fast_io.ps1')

# ----------------------------------------------------------------------------
# 0. 路径与文件检查
# ----------------------------------------------------------------------------
if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = Split-Path -Parent $MyInvocation.MyCommand.Path
}

$statePath  = Join-Path $Workspace 'state.json'
$configPath = Join-Path $Workspace 'task_config.json'
$outputPath = Join-Path $Workspace 'execution_dashboard.html'

if (-not (FastFileExists $statePath)) {
    throw "找不到 state.json: $statePath"
}
if (-not (FastFileExists $configPath)) {
    throw "找不到 task_config.json: $configPath"
}

Write-Host "[Dashboard] 读取数据源:" -ForegroundColor Cyan
Write-Host "  state.json  -> $statePath"
Write-Host "  task_config  -> $configPath"

# ----------------------------------------------------------------------------
# 1. 读取并解析 JSON
# ----------------------------------------------------------------------------
$state  = FastReadJson $statePath
$config = FastReadJson $configPath

# 辅助函数：安全读取可能不存在的属性
function Get-Prop {
    param($Obj, [string]$Name, $Default = $null)
    if ($null -eq $Obj) { return $Default }
    if ($Obj.PSObject.Properties.Name -contains $Name) { return $Obj.$Name }
    return $Default
}

# ----------------------------------------------------------------------------
# 2. 构建合并后的步骤数据（task_config 提供元数据，state 提供运行时状态）
# ----------------------------------------------------------------------------
$cfgStepById = @{}
foreach ($s in $config.steps) { $cfgStepById[[int]$s.id] = $s }

$mergedSteps = @()
foreach ($s in $state.steps) {
    $id  = [int]$s.id
    $cfg = $cfgStepById[$id]

    $isMerger = $false
    if ($null -ne $cfg -and (Get-Prop $cfg 'is_merger' $false)) { $isMerger = $true }

    $parallelGroup = $null
    if ($null -ne $cfg) { $parallelGroup = Get-Prop $cfg 'parallel_group' $null }

    $dependsOn = @()
    if ($null -ne $cfg) {
        $dep = Get-Prop $cfg 'depends_on' @()
        if ($null -ne $dep) { $dependsOn = @($dep) }
    }

    $mergedSteps += [ordered]@{
        id            = $id
        name          = $s.name
        agent         = $s.agent
        status        = $s.status
        retries       = (Get-Prop $s 'retries' 0)
        is_merger     = $isMerger
        parallel_group= $parallelGroup
        depends_on    = @($dependsOn | ForEach-Object { [int]$_ })
        # 运行时时间（实际数据为单一 timestamp；兼容示例中的 started_at/completed_at/error）
        timestamp     = (Get-Prop $s 'timestamp' $null)
        started_at    = (Get-Prop $s 'started_at' $null)
        completed_at  = (Get-Prop $s 'completed_at' $null)
        error         = (Get-Prop $s 'error' $null)
        result        = (Get-Prop $s 'result' $null)
        # 元数据
        instruction   = (Get-Prop $cfg 'instruction' '')
        pass_criteria = (Get-Prop $cfg 'pass_criteria' '')
    }
}

# ----------------------------------------------------------------------------
# 3. 计算拓扑层级（用于关键路径 / 节省时间预估 / 甘特图 / 依赖图）
# ----------------------------------------------------------------------------
$levelCache = @{}
function Get-Level {
    param([int]$Id)
    if ($levelCache.ContainsKey($Id)) { return $levelCache[$Id] }
    $cfg = $cfgStepById[$Id]
    if ($null -eq $cfg) { $levelCache[$Id] = 0; return 0 }
    $deps = @(Get-Prop $cfg 'depends_on' @() | ForEach-Object { [int]$_ })
    if ($deps.Count -eq 0) { $levelCache[$Id] = 0; return 0 }
    $m = 0
    foreach ($d in $deps) { $m = [math]::Max($m, (Get-Level $d) + 1) }
    $levelCache[$Id] = $m
    return $m
}
foreach ($s in $config.steps) { [void](Get-Level ([int]$s.id)) }
$criticalPath = 0
if ($levelCache.Count -gt 0) {
    $criticalPath = (($levelCache.Values | Measure-Object -Maximum).Maximum) + 1
}

# ----------------------------------------------------------------------------
# 4. 构建 KPI
# ----------------------------------------------------------------------------
$total    = [int](Get-Prop $state 'total_steps' $mergedSteps.Count)
if ($total -le 0) { $total = $mergedSteps.Count }

$statuses = @($mergedSteps | ForEach-Object { $_.status })
$completed = @($statuses | Where-Object { $_ -eq 'completed' }).Count
$running   = @($statuses | Where-Object { $_ -eq 'running' }).Count
$pending   = @($statuses | Where-Object { $_ -eq 'pending' }).Count
$failed    = @($statuses | Where-Object { $_ -eq 'failed' }).Count
# 兜底：无法识别的状态归入 pending
$known = $completed + $running + $pending + $failed
if ($known -lt $total) { $pending += ($total - $known) }

$progressPct = if ($total -gt 0) { [math]::Round($completed / $total * 100, 1) } else { 0 }

# 并行组：实际数据中 state.parallel_groups 为数组
$pgCount = 0
if ($null -ne $state.parallel_groups) {
    $pgCount = @($state.parallel_groups).Count
}

# 预估节省时间百分比 = (顺序总步数 - 关键路径长度) / 顺序总步数
$savingsPct = if ($total -gt 0) { [math]::Round(($total - $criticalPath) / $total * 100, 1) } else { 0 }

$kpis = [ordered]@{
    total          = $total
    completed      = $completed
    running        = $running
    pending        = $pending
    failed         = $failed
    progress_pct   = $progressPct
    parallel_groups= $pgCount
    savings_pct    = $savingsPct
    critical_path  = $criticalPath
}

# ----------------------------------------------------------------------------
# 5. 构建并行组可视化数据
#    members 从 task_config.steps 按 parallel_group 派生（可靠），
#    运行时状态从 state.parallel_groups 按 group_id 取（若存在）。
# ----------------------------------------------------------------------------
$stepsByGroup = @{}
foreach ($s in $config.steps) {
    $g = Get-Prop $s 'parallel_group' $null
    if ([string]::IsNullOrWhiteSpace($g)) { continue }
    if (-not $stepsByGroup.ContainsKey($g)) { $stepsByGroup[$g] = @() }
    $stepsByGroup[$g] += $s
}

$statePgById = @{}
if ($null -ne $state.parallel_groups) {
    foreach ($g in @($state.parallel_groups)) {
        $gid = Get-Prop $g 'group_id' $null
        if ($null -ne $gid) { $statePgById[$gid] = $g }
    }
}

$pgSummary = Get-Prop $config 'parallel_groups_summary' $null

$parallelGroups = @()
foreach ($gid in ($stepsByGroup.Keys | Sort-Object)) {
    $members = @($stepsByGroup[$gid])
    $parallelMembers = @($members | Where-Object { -not (Get-Prop $_ 'is_merger' $false) })
    $mergerMembers   = @($members | Where-Object { (Get-Prop $_ 'is_merger' $false) })

    $mode = 'mode7'
    if ($null -ne $pgSummary -and ($pgSummary.PSObject.Properties.Name -contains $gid)) {
        $mode = Get-Prop $pgSummary.$gid 'type' 'mode7'
    }

    $sg = $statePgById[$gid]
    $mergerStepId = $null
    if ($null -ne $sg) { $mergerStepId = Get-Prop $sg 'merger_step_id' $null }
    if ($null -eq $mergerStepId -and $mergerMembers.Count -gt 0) { $mergerStepId = [int]$mergerMembers[0].id }

    $parallelGroups += [ordered]@{
        group_id          = $gid
        mode              = $mode
        status            = if ($null -ne $sg) { Get-Prop $sg 'status' 'pending' } else { 'pending' }
        parallel_total    = if ($null -ne $sg) { (Get-Prop $sg 'parallel_total' $parallelMembers.Count) } else { $parallelMembers.Count }
        merger_step_id    = $mergerStepId
        merger_ready      = if ($null -ne $sg) { [bool](Get-Prop $sg 'merger_ready' $false) } else { $false }
        merger_executed   = if ($null -ne $sg) { [bool](Get-Prop $sg 'merger_executed' $false) } else { $false }
        parallel_step_ids = @($parallelMembers | ForEach-Object { [int]$_.id })
        parallel_step_names = @($parallelMembers | ForEach-Object { $_.name })
        merger_step_ids   = @($mergerMembers | ForEach-Object { [int]$_.id })
        merger_step_names = @($mergerMembers | ForEach-Object { $_.name })
        completed_agents  = @(Get-Prop $sg 'completed_agents' @())
        pending_agents    = @(Get-Prop $sg 'pending_agents' @())
        failed_agents     = @(Get-Prop $sg 'failed_agents' @())
    }
}

# ----------------------------------------------------------------------------
# 6. 组装最终数据对象
# ----------------------------------------------------------------------------
$meta = [ordered]@{
    task_name        = (Get-Prop $state 'task_name' (Get-Prop $config 'task_name' 'Execution Dashboard'))
    task_description = (Get-Prop $config 'task_description' (Get-Prop $state 'task_description' ''))
    review_mode      = (Get-Prop $config 'review_mode' '')
    workspace        = (Get-Prop $config 'workspace' $Workspace)
    created_at       = (Get-Prop $state 'created_at' $null)
    last_run         = (Get-Prop $state 'last_run' $null)
    overall_status   = (Get-Prop $state 'status' 'pending')
    current_step     = (Get-Prop $state 'current_step' 0)
    stop_reason      = (Get-Prop $state 'stop_reason' $null)
    generated_at     = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz')
    has_real_timestamps = ($mergedSteps | Where-Object { $_.timestamp -or $_.started_at -or $_.completed_at }).Count -gt 0
}

# 注：levels（拓扑层级）由 JS 端 computeSchedule() 独立重算，无需序列化传入；
# critical_path 已单独存入 KPI。避免 ConvertTo-Json 对整型键字典报错。
$dashboardData = [ordered]@{
    meta           = $meta
    kpis           = $kpis
    steps          = @($mergedSteps)
    parallel_groups= @($parallelGroups)
}

$dataJson = $dashboardData | ConvertTo-Json -Depth 20
# 防止 </script> 注入（JSON 中合法转义 \/）
$safeJson = $dataJson.Replace('</', '<\/')

Write-Host "[Dashboard] 数据合并完成: 步骤=$total, 并行组=$pgCount, 关键路径=$criticalPath, 节省预估=$savingsPct%" -ForegroundColor Green

# ----------------------------------------------------------------------------
# 7. HTML 模板（单引号 here-string，无变量插值；数据通过 JSON script 标签注入）
# ----------------------------------------------------------------------------
$htmlTemplate = @'
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>执行监控看板</title>
<style>
:root{
  --bg:#0f1117; --card:#1a1d27; --card2:#20232f; --border:#2a2d3a;
  --text:#e5e7eb; --muted:#9ca3af; --dim:#6b7280;
  --brand:#7c5cfc; --green:#34d399; --blue:#60a5fa; --red:#f87171;
  --yellow:#fbbf24; --cyan:#22d3ee; --gray:#6b7280;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--bg);color:var(--text)}
body{
  font-family:'Noto Sans SC','Microsoft YaHei','PingFang SC','Segoe UI',sans-serif;
  line-height:1.6;padding:24px 20px 60px;-webkit-font-smoothing:antialiased;
}
.container{max-width:1440px;margin:0 auto}
a{color:var(--brand);text-decoration:none}

/* ---------- Header ---------- */
.header{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:16px;margin-bottom:24px}
.header h1{font-size:24px;font-weight:700;display:flex;align-items:center;gap:12px}
.header h1 .logo{width:14px;height:14px;border-radius:4px;background:linear-gradient(135deg,var(--brand),var(--cyan));display:inline-block;box-shadow:0 0 16px rgba(124,92,252,.5)}
.header .meta{display:flex;flex-wrap:wrap;gap:10px;align-items:center;font-size:13px;color:var(--muted)}
.pill{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid var(--border);background:var(--card2)}
.pill .dot{width:8px;height:8px;border-radius:50%}
.pill.pending{color:var(--gray)} .pill.pending .dot{background:var(--gray)}
.pill.running{color:var(--blue)} .pill.running .dot{background:var(--blue);box-shadow:0 0 8px var(--blue)}
.pill.completed{color:var(--green)} .pill.completed .dot{background:var(--green)}
.pill.failed{color:var(--red)} .pill.failed .dot{background:var(--red)}

/* ---------- Card ---------- */
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:24px}
.section-title{font-size:16px;font-weight:700;margin-bottom:16px;display:flex;align-items:center;gap:10px;color:#f3f4f6}
.section-title .idx{width:24px;height:24px;border-radius:6px;background:var(--brand);color:#fff;font-size:13px;display:flex;align-items:center;justify-content:center;font-weight:700}
.section-title .sub{font-weight:400;color:var(--muted);font-size:13px}

/* ---------- KPI ---------- */
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px}
.kpi-card{background:var(--card2);border:1px solid var(--border);border-radius:12px;padding:16px 18px;position:relative;overflow:hidden}
.kpi-card .label{font-size:12px;color:var(--muted);margin-bottom:6px;display:flex;align-items:center;gap:6px}
.kpi-card .value{font-size:28px;font-weight:700;line-height:1.1}
.kpi-card .hint{font-size:11px;color:var(--dim);margin-top:4px}
.kpi-card::after{content:'';position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--brand)}
.kpi-card.green::after{background:var(--green)} .kpi-card.blue::after{background:var(--blue)}
.kpi-card.red::after{background:var(--red)} .kpi-card.yellow::after{background:var(--yellow)}
.kpi-card.cyan::after{background:var(--cyan)} .kpi-card.gray::after{background:var(--gray)}
.kpi-card.green .value{color:var(--green)} .kpi-card.blue .value{color:var(--blue)}
.kpi-card.red .value{color:var(--red)} .kpi-card.yellow .value{color:var(--yellow)}
.kpi-card.cyan .value{color:var(--cyan)}

/* ---------- Progress ---------- */
.progress-wrap{margin-top:18px}
.progress-top{display:flex;justify-content:space-between;font-size:13px;color:var(--muted);margin-bottom:8px}
.progress-top b{color:var(--brand);font-size:15px}
.progress-bar{height:14px;background:var(--card2);border-radius:999px;overflow:hidden;border:1px solid var(--border)}
.progress-fill{height:100%;background:linear-gradient(90deg,var(--brand),var(--cyan));border-radius:999px;transition:width .6s ease;display:flex;align-items:center;justify-content:flex-end;padding-right:8px;font-size:10px;font-weight:700;color:#0f1117;min-width:0}
.progress-fill.empty{background:var(--card2)}

/* ---------- Table ---------- */
.table-wrap{overflow-x:auto;border-radius:10px;border:1px solid var(--border)}
table.steps{width:100%;border-collapse:collapse;font-size:13px;min-width:980px}
table.steps th{background:var(--card2);color:var(--muted);text-align:left;padding:11px 12px;font-weight:600;white-space:nowrap;border-bottom:1px solid var(--border);position:sticky;top:0}
table.steps td{padding:10px 12px;border-bottom:1px solid var(--border);white-space:nowrap;color:#d1d5db}
table.steps tr:hover td{background:rgba(124,92,252,.06)}
table.steps tr.merger-row td{background:rgba(251,191,36,.05)}
table.steps td.col-name{white-space:normal;max-width:280px}
table.steps td.col-id{color:var(--muted);font-variant-numeric:tabular-nums}
.badge{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:600}
.badge .dot{width:7px;height:7px;border-radius:50%}
.badge.pending{background:rgba(107,114,128,.15);color:#cbd5e1} .badge.pending .dot{background:var(--gray)}
.badge.running{background:rgba(96,165,250,.15);color:var(--blue)} .badge.running .dot{background:var(--blue);box-shadow:0 0 6px var(--blue)}
.badge.completed{background:rgba(52,211,153,.15);color:var(--green)} .badge.completed .dot{background:var(--green)}
.badge.failed{background:rgba(248,113,113,.15);color:var(--red)} .badge.failed .dot{background:var(--red)}
.tag{display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600;margin-right:4px}
.tag.merger{background:rgba(251,191,36,.15);color:var(--yellow);border:1px solid rgba(251,191,36,.3)}
.tag.group{background:rgba(124,92,252,.15);color:#c4b5fd;border:1px solid rgba(124,92,252,.3)}
.tag.group.mode8{background:rgba(34,211,238,.12);color:var(--cyan);border-color:rgba(34,211,238,.3)}
.dep-chip{display:inline-block;background:var(--card2);border:1px solid var(--border);border-radius:5px;padding:1px 6px;font-size:11px;color:var(--muted);margin:0 2px}
.muted{color:var(--dim)} .mono{font-variant-numeric:tabular-nums}

/* ---------- Parallel Groups ---------- */
.pg-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}
.pg-card{background:var(--card2);border:1px solid var(--border);border-radius:12px;padding:16px;position:relative;overflow:hidden}
.pg-card .pg-accent{position:absolute;left:0;top:0;right:0;height:3px}
.pg-card.mode7 .pg-accent{background:var(--brand)} .pg-card.mode7{border-color:rgba(124,92,252,.35)}
.pg-card.mode8 .pg-accent{background:var(--cyan)} .pg-card.mode8{border-color:rgba(34,211,238,.35)}
.pg-head{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:10px}
.pg-head .gid{font-weight:700;font-size:14px;word-break:break-all}
.pg-mode{font-size:10px;font-weight:700;padding:2px 8px;border-radius:5px}
.pg-mode.mode7{background:rgba(124,92,252,.18);color:#c4b5fd}
.pg-mode.mode8{background:rgba(34,211,238,.18);color:var(--cyan)}
.pg-sub{font-size:12px;color:var(--muted);margin:6px 0}
.pg-sub .lbl{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.5px}
.pg-step{display:flex;align-items:center;gap:8px;font-size:12px;padding:4px 0;color:#d1d5db}
.pg-step .sid{width:22px;height:22px;border-radius:5px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;background:var(--card);color:var(--muted);flex-shrink:0}
.pg-step.merger .sid{background:rgba(251,191,36,.18);color:var(--yellow)}
.pg-step .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pg-agents{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.ag-chip{font-size:10px;padding:2px 7px;border-radius:5px}
.ag-chip.done{background:rgba(52,211,153,.15);color:var(--green)}
.ag-chip.wait{background:rgba(107,114,128,.15);color:#cbd5e1}
.ag-chip.fail{background:rgba(248,113,113,.15);color:var(--red)}

/* ---------- Gantt ---------- */
.gantt-note{font-size:12px;color:var(--muted);margin-bottom:12px;display:flex;align-items:center;gap:8px}
.scroll-x{overflow-x:auto;border:1px solid var(--border);border-radius:10px;padding:10px;background:var(--card2)}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:14px;font-size:12px;color:var(--muted)}
.legend .li{display:flex;align-items:center;gap:6px}
.legend .sw{width:14px;height:10px;border-radius:3px}

/* ---------- Dependency Graph ---------- */
.graph-scroll{overflow:auto;border:1px solid var(--border);border-radius:10px;background:var(--card2);max-height:560px}
svg text{font-family:'Noto Sans SC','Microsoft YaHei',sans-serif}

/* ---------- Footer ---------- */
.footer{text-align:center;color:var(--dim);font-size:12px;margin-top:30px;padding-top:18px;border-top:1px solid var(--border)}
@media(max-width:640px){
  body{padding:14px 10px 40px}
  .header h1{font-size:20px}
  .kpi-card .value{font-size:22px}
}
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <h1><span class="logo"></span><span id="hd-title">执行监控看板</span></h1>
    <div class="meta" id="hd-meta"></div>
  </div>

  <!-- 1. KPI -->
  <div class="card">
    <div class="section-title"><span class="idx">1</span>关键指标 KPI<span class="sub" id="kpi-sub"></span></div>
    <div class="kpi-grid" id="kpi-grid"></div>
    <div class="progress-wrap">
      <div class="progress-top"><span>整体完成进度</span><b id="prog-pct">0%</b></div>
      <div class="progress-bar"><div class="progress-fill" id="prog-fill"></div></div>
    </div>
  </div>

  <!-- 2. Steps Table -->
  <div class="card">
    <div class="section-title"><span class="idx">2</span>步骤详情<span class="sub">按 ID 排序</span></div>
    <div class="table-wrap">
      <table class="steps">
        <thead><tr>
          <th>ID</th><th>步骤名</th><th>Agent</th><th>状态</th><th>并行组 / 合并</th>
          <th>依赖</th><th>开始时间</th><th>完成时间</th><th>耗时</th>
        </tr></thead>
        <tbody id="steps-body"></tbody>
      </table>
    </div>
  </div>

  <!-- 3. Parallel Groups -->
  <div class="card">
    <div class="section-title"><span class="idx">3</span>并行组可视化<span class="sub" id="pg-sub"></span></div>
    <div class="pg-grid" id="pg-grid"></div>
  </div>

  <!-- 4. Gantt -->
  <div class="card">
    <div class="section-title"><span class="idx">4</span>甘特图时间线<span class="sub">基于依赖关系的执行时序</span></div>
    <div class="gantt-note" id="gantt-note"></div>
    <div class="scroll-x" id="gantt"></div>
    <div class="legend" id="gantt-legend"></div>
  </div>

  <!-- 5. Dependency Graph -->
  <div class="card">
    <div class="section-title"><span class="idx">5</span>依赖关系图<span class="sub">分层布局 · 虚线框为并行组</span></div>
    <div class="graph-scroll" id="depgraph"></div>
    <div class="legend" id="graph-legend"></div>
  </div>

  <div class="footer" id="footer"></div>
</div>

<script type="application/json" id="dashboard-data">__DATA_JSON__</script>
<script>
(function(){
  'use strict';
  const DATA = JSON.parse(document.getElementById('dashboard-data').textContent);

  // ---------- helpers ----------
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function trunc(s,n){s=String(s==null?'':s);return s.length>n?s.slice(0,n-1)+'…':s;}
  function statusColor(s){return {pending:'#6b7280',running:'#60a5fa',completed:'#34d399',failed:'#f87171'}[s]||'#6b7280';}
  function nodeFill(s){return {pending:'#262a36',running:'#1b2f4a',completed:'#14352a',failed:'#3a1f24'}[s]||'#262a36';}
  function statusZh(s){return {pending:'待执行',running:'运行中',completed:'已完成',failed:'失败'}[s]||s;}
  function fmtTime(t){ if(!t) return '-'; try{ const d=new Date(t); if(isNaN(d.getTime())) return t; return d.toLocaleString('zh-CN',{hour12:false}); }catch(e){ return t; } }
  function duration(a,b){ if(!a||!b) return '-'; try{ const ms=new Date(b)-new Date(a); if(isNaN(ms)||ms<0) return '-'; const s=Math.round(ms/1000); if(s<60) return s+'s'; const m=Math.floor(s/60); return m+'m '+(s%60)+'s'; }catch(e){ return '-'; } }
  function stepById(id){ return DATA.steps.filter(function(s){return s.id===id;})[0]; }

  // 拓扑层级 + 预估时序
  function computeSchedule(){
    const byId={}; DATA.steps.forEach(function(s){byId[s.id]=s;});
    const lvl={};
    function level(id){
      if(lvl[id]!==undefined) return lvl[id];
      const s=byId[id]; if(!s) return 0;
      const deps=s.depends_on||[];
      if(!deps.length) return lvl[id]=0;
      return lvl[id]=Math.max.apply(null,deps.map(function(d){return level(d)+1;}));
    }
    const sched={};
    DATA.steps.forEach(function(s){
      let start=0;
      (s.depends_on||[]).forEach(function(d){ if(sched[d]) start=Math.max(start,sched[d].end); });
      sched[s.id]={start:start,end:start+1,level:level(s.id)};
    });
    const maxEnd=Math.max.apply(null,DATA.steps.map(function(s){return sched[s.id].end;}));
    return {sched:sched,maxEnd:maxEnd,levels:lvl};
  }

  // ---------- Header ----------
  function renderHeader(){
    document.getElementById('hd-title').textContent = DATA.meta.task_name || '执行监控看板';
    const m=DATA.meta;
    const parts=[];
    if(m.review_mode) parts.push('<span class="pill"><span class="dot" style="background:#7c5cfc"></span>Review: '+esc(m.review_mode)+'</span>');
    parts.push('<span class="pill '+esc(m.overall_status)+'"><span class="dot"></span>整体: '+esc(statusZh(m.overall_status))+'</span>');
    parts.push('<span class="pill"><span class="dot" style="background:#9ca3af"></span>当前步: #'+esc(m.current_step)+'</span>');
    if(m.created_at) parts.push('<span class="pill"><span class="dot" style="background:#9ca3af"></span>创建: '+esc(fmtTime(m.created_at))+'</span>');
    parts.push('<span class="pill"><span class="dot" style="background:#34d399"></span>生成: '+esc(m.generated_at)+'</span>');
    document.getElementById('hd-meta').innerHTML=parts.join('');
    document.getElementById('footer').innerHTML='有龙则灵 Auto-Runner · 执行监控看板 · 生成于 '+esc(m.generated_at)+' · 数据源 state.json + task_config.json';
  }

  // ---------- KPI ----------
  function renderKPI(){
    const k=DATA.kpis;
    const cards=[
      {label:'总步骤数',value:k.total,cls:'',hint:'全部任务步骤'},
      {label:'已完成',value:k.completed,cls:'green',hint:'status = completed'},
      {label:'运行中',value:k.running,cls:'blue',hint:'status = running'},
      {label:'待执行',value:k.pending,cls:'gray',hint:'status = pending'},
      {label:'失败',value:k.failed,cls:'red',hint:'status = failed'},
      {label:'并行组',value:k.parallel_groups,cls:'cyan',hint:'mode7 + mode8'},
      {label:'关键路径',value:k.critical_path+' 步',cls:'yellow',hint:'最长依赖链'},
      {label:'预估节省时间',value:k.savings_pct+'%',cls:'',hint:'相对顺序执行'}
    ];
    document.getElementById('kpi-grid').innerHTML=cards.map(function(c){
      return '<div class="kpi-card '+c.cls+'"><div class="label">'+esc(c.label)+'</div><div class="value">'+esc(c.value)+'</div><div class="hint">'+esc(c.hint)+'</div></div>';
    }).join('');
    document.getElementById('kpi-sub').textContent='完成 '+k.completed+'/'+k.total;
    document.getElementById('prog-pct').textContent=k.progress_pct+'%';
    const fill=document.getElementById('prog-fill');
    fill.style.width=Math.max(k.progress_pct,0)+'%';
    fill.textContent=k.progress_pct>6?(k.progress_pct+'%'):'';
    if(k.progress_pct<=0) fill.classList.add('empty'); else fill.classList.remove('empty');
  }

  // ---------- Steps Table ----------
  function renderSteps(){
    const rows=DATA.steps.slice().sort(function(a,b){return a.id-b.id;});
    const modeByGroup={};
    DATA.parallel_groups.forEach(function(g){modeByGroup[g.group_id]=g.mode;});
    document.getElementById('steps-body').innerHTML=rows.map(function(s){
      let pgCell='<span class="muted">-</span>';
      if(s.parallel_group){
        const mode=modeByGroup[s.parallel_group]||'mode7';
        pgCell='<span class="tag group '+(mode==='mode8'?'mode8':'')+'">'+esc(s.parallel_group)+'</span>';
      }
      if(s.is_merger) pgCell+='<span class="tag merger">合并</span>';
      const dep=(s.depends_on&&s.depends_on.length)?s.depends_on.map(function(d){return '<span class="dep-chip">#'+d+'</span>';}).join(''):'<span class="muted">-</span>';
      const dur=duration(s.started_at||s.timestamp,s.completed_at);
      const badge='<span class="badge '+s.status+'"><span class="dot"></span>'+esc(statusZh(s.status))+'</span>';
      const cls=s.is_merger?'merger-row':'';
      return '<tr class="'+cls+'">'
        +'<td class="col-id">#'+s.id+'</td>'
        +'<td class="col-name">'+esc(s.name)+'</td>'
        +'<td>'+esc(s.agent)+'</td>'
        +'<td>'+badge+'</td>'
        +'<td>'+pgCell+'</td>'
        +'<td>'+dep+'</td>'
        +'<td class="mono">'+esc(fmtTime(s.started_at||s.timestamp))+'</td>'
        +'<td class="mono">'+esc(fmtTime(s.completed_at))+'</td>'
        +'<td class="mono">'+esc(dur)+'</td>'
        +'</tr>';
    }).join('');
  }

  // ---------- Parallel Groups ----------
  function renderPg(){
    const groups=DATA.parallel_groups.slice().sort(function(a,b){return a.group_id.localeCompare(b.group_id);});
    document.getElementById('pg-sub').textContent='共 '+groups.length+' 组';
    document.getElementById('pg-grid').innerHTML=groups.map(function(g){
      const parallelSteps=g.parallel_step_ids.map(function(id){return stepById(id);}).filter(Boolean);
      const mergerSteps=g.merger_step_ids.map(function(id){return stepById(id);}).filter(Boolean);
      let stepsHtml=parallelSteps.map(function(s){
        return '<div class="pg-step"><span class="sid">'+s.id+'</span><span class="nm">'+esc(trunc(s.name,40))+'</span><span class="badge '+s.status+'" style="margin-left:auto"><span class="dot"></span></span></div>';
      }).join('');
      if(mergerSteps.length){
        stepsHtml+='<div class="pg-sub" style="margin-top:8px"><span class="lbl">合并步骤</span></div>';
        stepsHtml+=mergerSteps.map(function(s){
          return '<div class="pg-step merger"><span class="sid">M</span><span class="nm">'+esc(trunc(s.name,40))+'</span><span class="badge '+s.status+'" style="margin-left:auto"><span class="dot"></span></span></div>';
        }).join('');
      } else {
        stepsHtml+='<div class="pg-sub"><span class="lbl">合并步骤</span> <span class="muted">无（mode8 流水线）</span></div>';
      }
      const agents=[];
      g.completed_agents.forEach(function(a){agents.push('<span class="ag-chip done">✓ '+esc(trunc(a,18))+'</span>');});
      g.pending_agents.forEach(function(a){agents.push('<span class="ag-chip wait">○ '+esc(trunc(a,18))+'</span>');});
      g.failed_agents.forEach(function(a){agents.push('<span class="ag-chip fail">✕ '+esc(trunc(a,18))+'</span>');});
      const agentsHtml=agents.length?'<div class="pg-agents">'+agents.join('')+'</div>':'';
      return '<div class="pg-card '+g.mode+'">'
        +'<div class="pg-accent"></div>'
        +'<div class="pg-head"><div class="gid">'+esc(g.group_id)+'</div><span class="pg-mode '+g.mode+'">'+esc(g.mode)+'</span></div>'
        +'<div class="pg-sub"><span class="lbl">状态</span> <span class="badge '+g.status+'"><span class="dot"></span>'+esc(statusZh(g.status))+'</span> · 并行 '+g.parallel_total+' · '+(g.merger_step_id!=null?'合并 #'+g.merger_step_id:'无合并')+'</div>'
        +stepsHtml
        +agentsHtml
        +'</div>';
    }).join('');
  }

  // ---------- Gantt ----------
  function renderGantt(){
    const comp=computeSchedule();
    const sched=comp.sched, maxEnd=comp.maxEnd;
    const steps=DATA.steps.slice().sort(function(a,b){return a.id-b.id;});
    const unitW=64, rowH=28, labelW=230, padTop=42, padBottom=20;
    const width=labelW+maxEnd*unitW+30;
    const height=padTop+steps.length*rowH+padBottom;
    const hasReal=DATA.meta.has_real_timestamps;
    document.getElementById('gantt-note').innerHTML='<span style="color:#fbbf24">●</span> '
      +(hasReal?'时间轴含真实时间戳，未记录的步骤使用依赖预估时序':'当前无真实时间戳，时间轴为<b>基于依赖关系的预估执行时序</b>（每步占 1 个时间单位 T），同列步骤表示并行执行。');
    let svg='<svg width="'+width+'" height="'+height+'" viewBox="0 0 '+width+' '+height+'" xmlns="http://www.w3.org/2000/svg" style="display:block">';
    // axis grid
    for(let t=0;t<=maxEnd;t++){
      const x=labelW+t*unitW;
      svg+='<line x1="'+x+'" y1="'+(padTop-12)+'" x2="'+x+'" y2="'+(height-padBottom+4)+'" stroke="#2a2d3a" stroke-width="1"/>';
      svg+='<text x="'+x+'" y="'+(padTop-18)+'" fill="#9ca3af" font-size="11" text-anchor="middle">T'+t+'</text>';
    }
    // rows
    steps.forEach(function(s,i){
      const y=padTop+i*rowH;
      const sc=sched[s.id];
      // zebra
      if(i%2===0) svg+='<rect x="0" y="'+y+'" width="'+width+'" height="'+rowH+'" fill="#1a1d27" opacity="0.4"/>';
      svg+='<text x="8" y="'+(y+rowH/2+4)+'" fill="#cbd5e1" font-size="12">#'+s.id+' '+esc(trunc(s.name,24))+'</text>';
      const bx=labelW+sc.start*unitW+3;
      const bw=(sc.end-sc.start)*unitW-6;
      const fill=statusColor(s.status);
      svg+='<rect x="'+bx+'" y="'+(y+5)+'" width="'+bw+'" height="'+(rowH-10)+'" rx="5" fill="'+fill+'" opacity="0.88" stroke="'+fill+'">';
      svg+='<title>#'+s.id+' '+esc(s.name)+' ['+esc(statusZh(s.status))+'] T'+sc.start+'→T'+sc.end+'</title></rect>';
      if(s.is_merger){ svg+='<text x="'+(bx+bw/2)+'" y="'+(y+rowH/2+4)+'" fill="#0f1117" font-size="11" text-anchor="middle" font-weight="700">M</text>'; }
      if(s.parallel_group){ svg+='<circle cx="'+(bx+bw-5)+'" cy="'+(y+9)+'" r="3" fill="#fff" opacity="0.85"/>'; }
    });
    svg+='</svg>';
    document.getElementById('gantt').innerHTML=svg;
    document.getElementById('gantt-legend').innerHTML=
      ['pending','running','completed','failed'].map(function(st){return '<span class="li"><span class="sw" style="background:'+statusColor(st)+'"></span>'+esc(statusZh(st))+'</span>';}).join('')
      +'<span class="li"><span class="sw" style="background:#fbbf24"></span>合并步骤(M)</span>'
      +'<span class="li"><span class="sw" style="background:#fff;opacity:.6"></span>并行组成员</span>';
  }

  // ---------- Dependency Graph ----------
  function renderGraph(){
    const comp=computeSchedule();
    const levels=comp.levels;
    const steps=DATA.steps;
    const byLevel={};
    steps.forEach(function(s){const l=levels[s.id]; (byLevel[l]=byLevel[l]||[]).push(s);});
    const colW=190, rowH=62, padX=40, padY=44, nodeW=152, nodeH=42;
    const maxLevel=Math.max.apply(null,Object.keys(byLevel).map(Number));
    let maxRows=0; for(const l in byLevel) maxRows=Math.max(maxRows,byLevel[l].length);
    const width=padX*2+(maxLevel+1)*colW;
    const height=padY*2+maxRows*rowH;
    const pos={};
    steps.forEach(function(s){const l=levels[s.id]; const idx=byLevel[l].indexOf(s); pos[s.id]={x:padX+l*colW,y:padY+idx*rowH};});

    const modeByGroup={}; DATA.parallel_groups.forEach(function(g){modeByGroup[g.group_id]=g.mode;});

    let svg='<svg width="'+width+'" height="'+height+'" viewBox="0 0 '+width+' '+height+'" xmlns="http://www.w3.org/2000/svg" style="display:block;min-width:760px">';
    svg+='<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#6b7280"/></marker>';
    svg+='<marker id="arrowg" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#34d399"/></marker></defs>';

    // group bounding boxes
    DATA.parallel_groups.forEach(function(g){
      const members=g.parallel_step_ids.concat(g.merger_step_ids).filter(function(id){return pos[id];});
      if(!members.length) return;
      let minX=1e9,minY=1e9,maxX=-1e9,maxY=-1e9;
      members.forEach(function(id){const p=pos[id]; minX=Math.min(minX,p.x);minY=Math.min(minY,p.y);maxX=Math.max(maxX,p.x+nodeW);maxY=Math.max(maxY,p.y+nodeH);});
      const color=g.mode==='mode8'?'#22d3ee':'#7c5cfc';
      svg+='<rect x="'+(minX-12)+'" y="'+(minY-16)+'" width="'+(maxX-minX+24)+'" height="'+(maxY-minY+28)+'" rx="10" fill="'+color+'" fill-opacity="0.04" stroke="'+color+'" stroke-width="1.5" stroke-dasharray="6 4" opacity="0.85"/>';
      svg+='<text x="'+(minX-6)+'" y="'+(minY-20)+'" fill="'+color+'" font-size="11" font-weight="600">'+esc(g.group_id)+' ('+esc(g.mode)+')</text>';
    });

    // edges
    steps.forEach(function(s){
      (s.depends_on||[]).forEach(function(d){
        if(!pos[d]||!pos[s.id]) return;
        const p1=pos[d],p2=pos[s.id];
        const x1=p1.x+nodeW, y1=p1.y+nodeH/2, x2=p2.x, y2=p2.y+nodeH/2;
        const dep=stepById(d);
        const bothDone=(dep&&dep.status==='completed'&&s.status==='completed');
        const col=bothDone?'#34d399':'#4b5563';
        const midX=(x1+x2)/2;
        svg+='<path d="M'+x1+' '+y1+' C'+midX+' '+y1+', '+midX+' '+y2+', '+(x2-6)+' '+y2+'" fill="none" stroke="'+col+'" stroke-width="1.5" marker-end="url('+(bothDone?'#arrowg':'#arrow')+')" opacity="0.85"/>';
      });
    });

    // nodes
    steps.forEach(function(s){
      const p=pos[s.id];
      const fill=nodeFill(s.status);
      const border=statusColor(s.status);
      svg+='<rect x="'+p.x+'" y="'+p.y+'" width="'+nodeW+'" height="'+nodeH+'" rx="8" fill="'+fill+'" stroke="'+border+'" stroke-width="1.6"/>';
      svg+='<text x="'+(p.x+9)+'" y="'+(p.y+17)+'" fill="'+border+'" font-size="12" font-weight="700">#'+s.id+'</text>';
      svg+='<text x="'+(p.x+34)+'" y="'+(p.y+17)+'" fill="#e5e7eb" font-size="11">'+esc(trunc(s.name,14))+'</text>';
      svg+='<text x="'+(p.x+9)+'" y="'+(p.y+33)+'" fill="#9ca3af" font-size="10">'+esc(trunc(s.agent,16))+'</text>';
      if(s.is_merger) svg+='<circle cx="'+(p.x+nodeW-11)+'" cy="'+(p.y+11)+'" r="6" fill="#fbbf24"><title>合并步骤</title></circle>';
      else if(s.parallel_group){ const mc=modeByGroup[s.parallel_group]==='mode8'?'#22d3ee':'#7c5cfc'; svg+='<circle cx="'+(p.x+nodeW-11)+'" cy="'+(p.y+11)+'" r="5" fill="none" stroke="'+mc+'" stroke-width="1.5"><title>并行组 '+esc(s.parallel_group)+'</title></circle>'; }
    });

    svg+='</svg>';
    document.getElementById('depgraph').innerHTML=svg;
    document.getElementById('graph-legend').innerHTML=
      '<span class="li"><span class="sw" style="background:#34d399"></span>已完成节点/边</span>'
      +'<span class="li"><span class="sw" style="background:#6b7280"></span>待执行节点/边</span>'
      +'<span class="li"><span class="sw" style="background:#fbbf24"></span>合并步骤</span>'
      +'<span class="li"><span class="sw" style="background:#7c5cfc"></span>mode7 并行组</span>'
      +'<span class="li"><span class="sw" style="background:#22d3ee"></span>mode8 并行组</span>';
  }

  // ---------- init ----------
  renderHeader();
  renderKPI();
  renderSteps();
  renderPg();
  renderGantt();
  renderGraph();
})();
</script>
</body>
</html>
'@

# ----------------------------------------------------------------------------
# 8. 注入数据并写出（UTF-8 BOM）
# ----------------------------------------------------------------------------
$html = $htmlTemplate.Replace('__DATA_JSON__', $safeJson)

$utf8Bom = New-Object System.Text.UTF8Encoding($true)
[System.IO.File]::WriteAllText($outputPath, $html, $utf8Bom)

Write-Host "[Dashboard] 看板已生成: $outputPath" -ForegroundColor Green
Write-Host ("[Dashboard] 文件大小: {0:N1} KB" -f ((FastFileSize $outputPath) / 1KB)) -ForegroundColor Green
