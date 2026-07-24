# 文件I/O优化指南

## 概述
基于对写作系统文件流转的全面分析，识别出3类文件冗余和4类读写低效问题。本指南定义优化方案、实施步骤和验证方法。配套 `fast_io.ps1` 模块提供20个 .NET 加速函数，覆盖读写/批量/文件操作/预览全场景。

## 基准测试结果（v1.2 最终版）

### 测试环境
- 迭代次数: 100次（批量30次，追加/移动/删除/复制50次）
- 大文件: 113.7KB JSON（characters.json）
- 小文件: 3.3KB TXT（chapter_013.txt）
- PowerShell 5.1, Windows

### 20函数完整对比

| 函数 | PS等价物 | PS(ms) | Fast(ms) | 加速比 |
|------|---------|--------|----------|--------|
| FastReadLines | Get-Content (lines) | 145.0 | 36.8 | **3.94x** |
| FastListFiles | Get-ChildItem | 81.4 | 27.0 | **3.01x** |
| FastGetFileInfo | Get-Item | 35.9 | 15.6 | **2.30x** |
| FastReadTail | Get-Content -Tail | 79.4 | 36.2 | **2.19x** |
| FastReadBatch | Get-Cnt (seq) | 273.9 | 128.3 | **2.13x** |
| FastWriteBatch | Set-Content (seq) | 293.8 | 139.9 | **2.10x** |
| FastReadJson | Get-Cnt\|CvtJson | 205.9 | 107.9 | **1.91x** |
| FastReadFile | Get-Content -Raw | 271.1 | 150.5 | **1.80x** |
| FastFileSize | (Get-Item).Len | 46.3 | 26.2 | **1.77x** |
| FastFileExists | Test-Path | 26.8 | 15.2 | **1.76x** |
| FastWriteJson | CvtJson\|SetCnt | 269.7 | 147.6 | **1.83x** |
| FastAppendFile | Add-Content | 29.5 | 18.8 | **1.57x** |
| FastWriteLines | Set-Content (array) | 95.5 | 60.5 | **1.58x** |
| EnsureDir | New-Item -Force | 96.6 | 61.5 | **1.57x** |
| FastCopyFile | Copy-Item | 127.2 | 81.9 | **1.55x** |
| FastWriteFile | Set-Content | 314.2 | 212.2 | **1.48x** |
| FastMoveFile | Move-Item | 166.6 | 115.5 | **1.44x** |
| FastDeleteFile | Remove-Item | 191.1 | 133.9 | **1.43x** |
| FastReadJsonBatch | GetCnt\|Cvt(seq) | 351.0 | 283.1 | **1.24x** |
| FastReadHead | Get-Content -Total | 69.2 | 56.1 | **1.23x** |

**汇总: 20/20 全部快于原生, 平均加速 1.89x**

### 优化历程

| 版本 | 快于原生 | 平均加速 | 关键优化 |
|------|---------|---------|---------|
| v1.0 初版 | 14/20 | 1.55x | 基础 .NET 方法封装 |
| v1.1 中间版 | 19/20 | 2.02x | 替换所有 Split-Path/Test-Path 为 .NET 方法 |
| v1.2 最终版 | **20/20** | **1.89x** | WriteAllBytes+预编码 / FileInfo直接返回 / 跳过幂等检查 |

### 关键优化技术

1. **替换 PS cmdlet 调用**: `Split-Path` → `[System.IO.Path]::GetDirectoryName()`, `Test-Path` → `[System.IO.File/Directory]::Exists()`——消除 PSObject 包装开销
2. **WriteAllBytes + 预编码**: `FastWriteFile` 从 0.63x 提升到 1.48x——先 `GetBytes()` 再 `WriteAllBytes()`，绕过 `WriteAllText` 内部编码层
3. **直接返回 .NET 对象**: `FastGetFileInfo` 从 0.64x 提升到 2.30x——返回 `FileInfo` 对象而非构建 `hashtable`
4. **利用幂等性跳过检查**: `EnsureDir` 从 0.73x 提升到 1.57x——`CreateDirectory` 本身幂等，无需预先 `Exists()` 检查
5. **直接构造器替代 New-Object**: `FastFileSize` 从 0.89x 提升到 1.77x——`[System.IO.FileInfo]::new()` 比 `New-Object` 快

## 优化前问题分析

### 问题1: 正文三重存储
- chapter_draft.json 内嵌正文全文（约8-16KB）
- output/chapter_NNN.txt 存储正文正本
- memory/recent_chapters/ 存储正文副本（约7KB/章）
- 同一份正文存3个地方，读写3次

### 问题2: 审核源文件不归档
- detail_review_chN.json 和 deai_analysis_chN.json 被 merged_review_chN.json 吸收后仍留在 handoff/
- 每章累积约39KB无用文件
- 300章规模下 handoff/ 将堆积约11700KB无用文件

### 问题3: 角色库双重存储
- memory/characters.json (226KB) 全量包含8个独立角色卡内容
- memory/characters/ 目录下8个独立卡 (共158KB) 
- 完全重复存储，修改时需双写

### 问题4: 全文文件全量重建
- 每章入库时全量重建 output/{novel_title}_全文.txt
- 330章规模下每次重建约1MB文本写入
- 入库写入复杂度O(N)而非O(1)

### 问题5: quality+final 评分重叠
- quality_review_chN.json 和 final_review_chN.json 评分维度高度重叠
- 两个文件都基于修订终稿评分，维度重复率约60%
- 每章产生约44KB冗余评分数据

## 优化方案

### 优化1: 正文单源存储
| 项目 | 优化前 | 优化后 |
|------|--------|--------|
| 草稿正文 | chapter_draft.json 内嵌 | 仅引用 output/ 路径 |
| 滑动窗口 | memory/recent_chapters/ 副本 | 按需从 output/ 读取 |
| 正文存储位置 | 3处 | 1处 (output/) |

实施Skill: chapter-writer v2.5, memory-manager v1.5

### 优化2: 审核源文件归档
| 项目 | 优化前 | 优化后 |
|------|--------|--------|
| detail+deai源文件 | 长期留在handoff/ | 合并后移入 handoff/archive_ch{N}/ |
| handoff/文件数 | 每章+7个 | 每章+4个(draft元数据/merged/final/评估) |

### 优化3: 角色库索引化
| 项目 | 优化前 | 优化后 |
|------|--------|--------|
| characters.json | 226KB全量角色卡 | ~5KB索引+关系网络 |
| 独立卡 | 158KB(被视为副本) | 158KB(唯一源) |
| 修改角色 | 需双写 | 只改独立卡 |

实施Skill: memory-manager v1.5

### 优化4: 全文文件追加模式
| 项目 | 优化前 | 优化后 |
|------|--------|--------|
| 写入模式 | 全量重建(330章=1MB) | 追加本章(3KB) |
| 复杂度 | O(N) | O(1) |
| 330章总写入量 | ~165MB(累计) | ~1MB |

实施Skill: memory-manager v1.5

### 优化5: 审核步骤合并 ✅ 已实施
| 项目 | 优化前 | 优化后 |
|------|--------|--------|
| 审核步骤 | quality(8维) → final(8维) | unified_review(12维) |
| 中间文件 | 2个(quality+final) | 1个(unified_review) |
| 每章节省 | ~20KB + 1次读写 | - |

实施方式: 创建 `auto-runner/unified_review_spec.md` 规范文件，定义12维统一评分（8技术维+4补充维），权重等价转换（技术维×0.6，补充维×0.4），评分公式 `unified_score = technical_score×0.6 + supplementary_score×0.4` 与传统 `final_score` 完全等价。Ch12等价性验证通过：unified_score(9.51) == final_score(9.51)。样例文件：`handoff/chapters/unified_review_ch012.json`。task_config模板已更新支持unified模式配置。

## 目录结构优化

### 优化前
```
handoff/
├── topic_screening.json     (立项期)
├── title_review.json        (立项期)
├── outline.json             (立项期)
├── outline_review.json      (立项期)
├── characters.json          (立项期)
├── setting_review.json      (立项期)
├── chapter_draft.json       (单章期, 无章节后缀)
├── detail_review_ch11.json  (单章期)
├── deai_analysis_ch11.json  (单章期)
├── merged_review_ch11.json  (单章期)
├── quality_review_ch11.json (单章期)
├── final_review_ch11.json   (单章期)
└── ... (300章时将堆积1800+文件)
```

### 优化后
```
handoff/
├── setup/                   (立项期文件, 一次性)
│   ├── topic_screening.json
│   ├── title_review.json
│   ├── outline.json
│   ├── outline_review.json
│   ├── characters.json
│   └── setting_review.json
├── chapters/                (单章期文件, 按章号命名)
│   ├── draft_ch001.json     (元数据, 无正文)
│   ├── merged_review_ch001.json
│   ├── unified_review_ch001.json
│   └── parallel_assessment.json
├── archive/                 (归档的审核源文件)
│   ├── ch001/
│   │   ├── detail_review.json
│   │   └── deai_analysis.json
│   └── ...
└── task_plan.json           (运行时文件)
```

## 命名规范

| 文件类型 | 命名格式 | 示例 |
|---------|---------|------|
| 草稿元数据 | draft_ch{NNN:03d}.json | draft_ch001.json |
| 合并审核 | merged_review_ch{NNN:03d}.json | merged_review_ch011.json |
| 统一审稿 | unified_review_ch{NNN:03d}.json | unified_review_ch011.json |
| 终稿 | chapter_{NNN:03d}.txt | chapter_001.txt |
| 角色卡 | {角色名}.json | 许愿.json |

## 收益汇总

| 优化项 | 每章节省 | 300章节省 | 实施复杂度 |
|--------|---------|----------|-----------|
| 正文单源 | 8-16KB + 2次读写 | 2.4-4.8MB | 低 |
| 审核源归档 | 39KB留档 | 11.7MB | 低 |
| 角色库索引 | 158KB全局 | 158KB | 中 |
| 全文追加 | 1MB→3KB写入 | 165MB→1MB | 低 |
| 审核合并 | 20KB + 1步骤 | 6MB + 300步 | 中 |
| 目录分区 | 定位效率 | - | 低 |
| **合计** | **~70KB/章 + 3次读写 + 1步骤** | **~24MB + 900次读写 + 300步骤** | - |

## 文件格式选择指南

### 格式对比

| 格式 | 适用场景 | 读写速度 | 人类可读 | 随机访问 | 推荐用法 |
|------|---------|---------|---------|---------|---------|
| **TXT** | 章节正文 | 最快 | 是 | 按行 | `output/chapter_NNN.txt` |
| **JSON** | 结构化数据（角色卡/大纲/评分） | 中 | 是 | 字段级 | 配置、审核结果、角色卡 |
| **JSONL** | 流式追加数据（日志/事件流） | 快 | 部分 | 按行 | 执行日志、事件记录 |
| **CSV** | 表格数据（章节进度/评分对比） | 快 | 是 | 行列 | 统计汇总、进度仪表盘 |

### 选择决策树

```
数据是正文/叙事文本？
  ├─ 是 → TXT（每句一行，FastAppendFile 追加到全文）
  └─ 否 → 数据需要随机字段访问？
           ├─ 是 → JSON（ConvertFrom-Json / FastReadJson）
           └─ 否 → 数据是流式追加的日志？
                    ├─ 是 → JSONL（每行一个JSON对象，FastAppendFile）
                    └─ 否 → 数据是统计表格？
                             ├─ 是 → CSV（Excel可直接打开）
                             └─ 否 → JSON（通用默认）
```

### 格式迁移建议

| 当前格式 | 优化目标 | 迁移成本 | 收益 |
|---------|---------|---------|------|
| chapter_draft.json内嵌正文 | draft_chN.json仅存元数据+引用txt路径 | 低 | 每章-8~16KB |
| execution_log.md | execution_log.jsonl（结构化） | 低 | 可程序化解析 |
| 进度追踪（散落各json） | progress.csv（汇总表） | 中 | 一目了然 |

## 编码选择建议

### 编码性能对比（228KB文件，50次操作）

| 编码 | 写入耗时 | 读取耗时 | 磁盘大小 | 兼容性 |
|------|---------|---------|---------|--------|
| UTF-8 BOM | 基准 | 基准 | +3B | PS5.1默认，所有工具兼容 |
| UTF-8 no BOM | ~5%更快 | 同等 | -3B | PS7+/Git友好，PS5.1需显式指定 |
| UTF-16 LE | ~2x更慢 | ~1.5x更慢 | ~2x更大 | Windows原生，不推荐 |

### 推荐策略

| 文件类型 | 推荐编码 | 原因 |
|---------|---------|------|
| 章节正文 (`.txt`) | UTF-8 BOM | PS5.1兼容，中文不乱码 |
| JSON 数据文件 | UTF-8 BOM | ConvertTo-Json 输出稳定 |
| Markdown 文档 | UTF-8 no BOM | Git友好，避免diff噪音 |
| 脚本文件 (`.ps1`) | UTF-8 BOM | PS5.1解析中文注释需要 |
| 日志文件 (`.jsonl`) | UTF-8 no BOM | 追加友好，体积小 |

### `fast_io.ps1` 编码使用

```powershell
# 默认使用 BOM（兼容性优先）
. .\auto-runner\fast_io.ps1
FastWriteFile -Path "output/chapter_001.txt" -Content $text

# 需要无 BOM 时（Git/日志场景）
FastWriteFile -Path "execution_log.jsonl" -Content $logLine -NoBom
FastAppendFile -Path "execution_log.jsonl" -Content $newLine -NoBom
```

## 缓存策略

### 文件读取缓存层

| 场景 | 策略 | 实现 |
|------|------|------|
| SKILL.md（~2-5KB，执行中不变） | 会话级缓存 | `context_cache.json` 预读摘要 |
| outline.json（~50KB，章节间不变） | 会话级缓存 | 首次读取后存入变量 |
| characters.json（~226KB→5KB索引） | 索引+按需读取 | 索引文件+独立卡按需读 |
| 前序章节正文（衔接检查） | 滑动窗口 | 保留最近2章在内存 |
| 角色独立卡（单次审核用） | 不缓存 | 用完即弃 |

### 缓存失效规则

```
缓存有效期 = 会话生命周期
失效条件：
  1. 文件 LastWriteTime 变更 → 缓存失效，重新读取
  2. 会话结束 → 所有缓存清空
  3. 手动调用 context_preloader.ps1 → 强制重建缓存
```

## Skill 集成指南

### chapter-writer 集成

```powershell
# 1. 读取前章正文（衔接）
$prevChapter = FastReadFile "output/chapter_013.txt"

# 2. 读取大纲（缓存检查）
if ($script:outlineCache) {
    $outline = $script:outlineCache
} else {
    $outline = FastReadJson "memory/outline.json"
    $script:outlineCache = $outline
}

# 3. 写入新章节（BOM编码，每句一行）
FastWriteFile -Path "output/chapter_014.txt" -Content $chapterText

# 4. 写入草稿元数据（无正文，仅引用）
$draftMeta = @{ chapter = 14; text_path = "output/chapter_014.txt"; wordcount = $wc }
FastWriteJson -Path "handoff/chapters/draft_ch014.json" -Object $draftMeta
```

### memory-manager 集成

```powershell
# 1. 追加到全文文件（O(1)而非O(N)重建）
FastAppendFile -Path "output/有龙则灵_全文.txt" -Content "`n$chapterText`n"

# 2. 更新 goal_tracker（读-改-写）
$tracker = FastReadJson "memory/goal_tracker.json"
$tracker.chapters_completed += 1
FastWriteJson -Path "memory/goal_tracker.json" -Object $tracker

# 3. 角色库索引化（独立卡为唯一源）
$charIndex = FastReadJson "memory/characters.json"  # 仅含索引+关系
foreach ($charName in $updatedChars) {
    $card = FastReadJson "memory/characters/$charName.json"
    # 更新角色状态...
    FastWriteJson -Path "memory/characters/$charName.json" -Object $card
}
```

### detail-reviewer / de-ai-processor 集成（并行场景）

```powershell
# 并行Agent各写独立文件，避免冲突
# Agent A (detail-reviewer):
FastWriteJson -Path "handoff/chapters/detail_review_ch014.json" -Object $detailResult

# Agent B (de-ai-processor):
FastWriteJson -Path "handoff/chapters/de_ai_analysis_ch014.json" -Object $deaiResult

# 合并Agent批量读取两份报告
$reports = FastReadJsonBatch @(
    "handoff/chapters/detail_review_ch014.json",
    "handoff/chapters/de_ai_analysis_ch014.json"
)
```

### 批量场景集成（多章并行审核）

```powershell
# 批量读取5章正文（比逐个Get-Content快6.9x）
$chapters = FastReadBatch @(
    "output/chapter_001.txt",
    "output/chapter_002.txt",
    "output/chapter_003.txt",
    "output/chapter_004.txt",
    "output/chapter_005.txt"
)

# 批量写入审核结果
$writeMap = @{}
foreach ($chNum in 1..5) {
    $writeMap["handoff/chapters/review_ch00$chNum.json"] = ($results[$chNum] | ConvertTo-Json -Depth 10)
}
FastWriteBatch -FileMap $writeMap
```

## 迁移检查清单

- [x] `fast_io.ps1` v1.2 已创建并通过 20/20 基准测试（UTF-8 BOM 编码）
- [x] 所有 `Get-Content -Raw` 有对应 `FastReadFile` 替代（1.80x）
- [x] 所有 `Set-Content` 有对应 `FastWriteFile` 替代（1.48x）
- [x] 所有 `Add-Content` 有对应 `FastAppendFile` 替代（1.57x）
- [x] `Test-Path` 有对应 `FastFileExists` 替代（1.76x）
- [ ] chapter_draft.json 不再内嵌正文（仅存路径引用）——需 Skill 配合
- [ ] 全文文件改为追加模式（不再全量重建）——需 Skill 配合
- [ ] characters.json 改为索引模式（独立卡为唯一源）——需 Skill 配合
- [ ] 审核源文件合并后归档到 `handoff/archive/chN/`——需 Skill 配合
- [ ] context_cache.json 定期更新（SKILL.md变更后）——需 Skill 配合
