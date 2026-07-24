# 上下文优化策略 (Context Optimization Strategy) v1.0

## 概述

本策略定义 Skill 缓存机制与文件预读策略，旨在减少自动执行流程中的重复文件读取，降低上下文窗口消耗。通过缓存 SKILL.md 摘要、分类预读文件、分级降级策略，预计节省 80% 的上下文占用。

**配套脚本**：`auto-runner/context_preloader.ps1`
**缓存文件**：`auto-runner/context_cache.json`

---

## 1. 优化目标

| 目标 | 说明 | 量化指标 |
|------|------|---------|
| 减少重复读取 | SKILL.md 每次步骤执行都重新读取完整文件，内容重复加载 | 每步减少 ~2000 字读取 |
| 降低上下文消耗 | 大纲/角色卡等文件全文占用过多上下文窗口 | 每步减少 ~8000 字占用 |
| 加速步骤启动 | 缓存命中时跳过文件读取，直接使用摘要 | 步骤启动提速 30-50% |
| 保留关键信息 | 缓存摘要提取核心指令，不丢失关键规则 | 规则覆盖率 ≥ 95% |

---

## 2. Skill 缓存策略

### 2.1 缓存内容

每个 Skill 的 SKILL.md 首次读取后缓存以下信息：

| 字段 | 说明 | 示例 |
|------|------|------|
| `name` | Skill 名称（目录名） | `chapter-writer` |
| `path` | 文件相对路径 | `.trae/skills/chapter-writer/SKILL.md` |
| `size` | 文件大小（字节） | `8421` |
| `last_modified` | 最后修改时间（ISO 8601） | `2026-07-24T10:00:00+08:00` |
| `summary` | 正文前 500 字符摘要（跳过 YAML frontmatter） | `# 写手 (Chapter Writer) v2.3 ...` |
| `rule_count` | 关键规则数量统计（匹配规则关键词的行数） | `47` |

### 2.2 缓存使用方式

```
步骤执行前：
1. 检查 context_cache.json 中是否有该 Skill 的缓存
2. 若缓存有效（last_modified 未变更）：
   → 引用缓存摘要（~500字），不读取完整 SKILL.md（~2000-5000字）
3. 若缓存失效或不存在：
   → 读取完整 SKILL.md，更新缓存
```

### 2.3 缓存失效条件

| 条件 | 触发动作 | 说明 |
|------|---------|------|
| 文件修改时间变更 | 该文件缓存标记为 miss，重新读取 | 最常见场景：Skill 版本升级 |
| 缓存文件不存在 | 全量重建 | 首次运行或缓存被删除 |
| 缓存文件解析失败 | 全量重建 | 缓存文件损坏 |
| cache_version 不匹配 | 全量重建 | 缓存格式升级 |

### 2.4 规则关键词统计口径

`rule_count` 统计正文中包含以下关键词的行数（每行最多计 1 次）：

```
法则, 规则, 要求, 禁令, 必须, 不得, 硬性, 检测, 约束, 验证,
硬拦截, 禁止, 严禁, 门禁, 强制, 不可跳过, 不超过, 至少, 不可, 一律
```

该统计用于快速评估 Skill 的规则密度，辅助上下文预算估算。

---

## 3. 文件预读策略

### 3.1 文件分类

| 分类 | 文件 | 预读时机 | 说明 |
|------|------|---------|------|
| **必读文件** | `memory/outline.json` | 任务启动时 | 大纲，全局剧情骨架 |
| | `memory/characters.json` | 任务启动时 | 角色卡索引，角色一致性基础 |
| | `memory/goal_tracker.json` | 任务启动时 | 目标闭环+主线进度+悬念窗口 |
| | `memory/session_pointer.json` | 任务启动时 | 会话指针，当前进度定位 |
| **按需文件** | `memory/foreshadowing_tracker.json` | 伏笔相关步骤执行前 | 伏笔追踪表，避免跨章遗漏 |
| | `memory/chapter_summaries/chapter_NNN.json` | 章节写作/审核前 | 最近章节摘要，衔接上下文 |
| | `memory/recent_chapters/chapter_NNN.txt` | 章节写作前 | 最近章节全文，细粒度衔接 |
| **参考文件** | `config/novel_config.json` | 写作/审核步骤前 | 写作规则+平台配置 |
| | `auto-runner/unified_review_spec.md` | 统一审核步骤前 | 12维评分规范 |
| | `auto-runner/parallel_task_config_template.json` | 并行任务配置前 | 并行模板参考 |

### 3.2 预读时机

```
任务启动（初始化阶段）：
  → 预读全部必读文件（outline + characters + goal_tracker + session_pointer）
  → 运行 context_preloader.ps1 生成/更新缓存清单

步骤执行前：
  → 根据步骤类型预读按需文件
  → 检查 context_cache.json 中对应文件的缓存状态

步骤执行中：
  → 优先引用缓存摘要，仅在需要全文时才读取完整文件
```

### 3.3 预读文件清单与缓存

`context_preloader.ps1` 预读以下文件并生成缓存：

| # | 文件路径 | 类型 | 缓存内容 |
|---|---------|------|---------|
| 1-N | `.trae/skills/*/SKILL.md` | Skill | 摘要 + 规则统计 |
| N+1 | `memory/outline.json` | JSON | 顶层 key 列表 |
| N+2 | `memory/characters.json` | JSON | 顶层 key 列表 |
| N+3 | `memory/goal_tracker.json` | JSON | 顶层 key 列表 |
| N+4 | `memory/session_pointer.json` | JSON | 顶层 key 列表 |
| N+5 | `memory/foreshadowing_tracker.json` | JSON | 顶层 key 列表 |
| N+6 | `config/novel_config.json` | JSON | 顶层 key 列表 |
| N+7 | `auto-runner/unified_review_spec.md` | Markdown | 元数据 |
| N+8 | `auto-runner/parallel_task_config_template.json` | JSON | 顶层 key 列表 |

---

## 4. 上下文窗口管理

### 4.1 每步上下文预算估算

| 步骤类型 | 无缓存预算 | 有缓存预算 | 节省 |
|---------|-----------|-----------|------|
| 轻量审核（title/skeptic/outline/setting） | ~12000 字 | ~2500 字 | 79% |
| 角色设计（character-designer） | ~10000 字 | ~2000 字 | 80% |
| 章节撰写（chapter-writer） | ~15000 字 | ~5000 字 | 67% |
| 章节审核（detail/quality/de-ai/final） | ~12000 字 | ~3000 字 | 75% |
| 统一审核（unified_review） | ~14000 字 | ~3500 字 | 75% |

> 注：章节撰写因需读取前章全文+角色卡全文，缓存节省比例较低，但绝对节省量仍约 10000 字。

### 4.2 超预算降级策略

当步骤上下文消耗接近窗口上限时，按以下优先级降级：

```
降级触发条件：当前步骤已加载内容 > 预算上限的 80%

降级顺序（从低优先级开始移除）：
  1. 移除参考文件全文 → 替换为缓存元数据（~100字）
  2. 移除按需文件全文 → 替换为缓存顶层key列表（~200字）
  3. 移除必读文件全文 → 替换为缓存顶层key列表（~300字）
  4. 移除 SKILL.md 全文 → 替换为缓存摘要（~500字）
  5. 最后保留：当前步骤的 input_files（正文/反馈卡）+ SKILL.md 缓存摘要
```

### 4.3 优先级规则

步骤执行时，上下文加载优先级从高到低：

```
P0（最高）：当前步骤的 input_files
            → 章节正文、审核反馈卡、beat_sheet 等
            → 必须完整加载，不可降级

P1：SKILL.md 规则
    → 优先使用缓存摘要（~500字），包含核心指令
    → 若摘要不足以覆盖当前步骤需求，读取完整文件

P2（最低）：上下文文件
    → outline / characters / goal_tracker / session_pointer
    → 优先使用缓存顶层key列表定位，按需读取具体字段
```

---

## 5. 缓存更新协议

### 5.1 触发条件

| 触发场景 | 更新方式 | 执行时机 |
|---------|---------|---------|
| 任务初始化 | 增量更新 | 每次会话启动时 |
| Skill 版本升级 | 增量更新（仅变更文件） | 检测到 last_modified 变更 |
| 缓存文件缺失 | 全量重建 | context_cache.json 不存在 |
| 缓存文件损坏 | 全量重建 | JSON 解析失败 |
| 手动触发 | 全量重建 | 删除 context_cache.json 后重新运行 |

### 5.2 增量更新 vs 全量重建

#### 增量更新（默认）

```
context_preloader.ps1 运行时：
1. 加载现有 context_cache.json
2. 对每个文件，比较缓存的 last_modified 与文件实际修改时间
3. 时间一致 → cache hit，直接复用缓存数据
4. 时间不一致 → cache miss，重新读取该文件
5. 仅变更的文件重新读取，其余文件复用缓存
6. 重新写入 context_cache.json（更新 generated_at 时间戳）
```

**优势**：仅读取变更文件，执行时间 < 1 秒（大部分文件 cache hit）

#### 全量重建

```
触发条件：
  - context_cache.json 不存在
  - context_cache.json 解析失败
  - cache_version 不匹配

执行方式：
  - 忽略现有缓存，逐个重新读取所有文件
  - 全量写入 context_cache.json
```

**优势**：确保缓存与文件系统完全一致
**耗时**：~2-3 秒（取决于文件数量与大小）

### 5.3 缓存生命周期

```
创建 → 首次运行 context_preloader.ps1
  ↓
使用 → 步骤执行时引用缓存摘要
  ↓
验证 → 下次运行时检查 last_modified
  ↓
更新 → 文件变更时增量更新（cache miss）
  ↓
重建 → 缓存损坏/缺失时全量重建
```

---

## 6. 效果量化

### 6.1 无缓存场景（基线）

每个步骤执行时需读取的文件及大小估算：

| 读取项 | 文件 | 估算大小 |
|--------|------|---------|
| SKILL.md | 当前步骤对应的 Skill | ~2000-5000 字 |
| 大纲 | `memory/outline.json` | ~5000 字 |
| 角色卡 | `memory/characters.json` | ~3000 字（索引模式）或 ~22000 字（全量模式） |
| 目标追踪 | `memory/goal_tracker.json` | ~3000 字 |
| 会话指针 | `memory/session_pointer.json` | ~2000 字 |
| 配置 | `config/novel_config.json` | ~1000 字 |
| **合计** | | **~10000-15000 字/步** |

### 6.2 有缓存场景（优化后）

| 读取项 | 来源 | 估算大小 |
|--------|------|---------|
| SKILL.md 摘要 | context_cache.json 缓存 | ~500 字 |
| 大纲 key 列表 | context_cache.json 缓存 | ~200 字 |
| 角色卡 key 列表 | context_cache.json 缓存 | ~100 字 |
| 目标追踪 key 列表 | context_cache.json 缓存 | ~100 字 |
| 按需文件（步骤相关） | 实际读取 | ~1000-1500 字 |
| **合计** | | **~2000-2500 字/步** |

### 6.3 节省效果

| 指标 | 无缓存 | 有缓存 | 改善 |
|------|--------|--------|------|
| 每步上下文消耗 | ~10000-15000 字 | ~2000-2500 字 | **节省 ~80%** |
| 文件读取次数 | 6-8 次/步 | 1-2 次/步 | **减少 75%** |
| 步骤启动耗时 | 文件 I/O ~1-2 秒 | 缓存命中 ~0.1 秒 | **提速 80%** |
| 单次会话可执行步数 | 4-6 步 | 6-8 步 | **提升 33%** |

### 6.4 300 章规模累计节省

| 项目 | 无缓存 | 有缓存 | 节省 |
|------|--------|--------|------|
| 总读取量 | ~3,000,000-4,500,000 字 | ~600,000-750,000 字 | ~2,400,000-3,750,000 字 |
| 总文件 I/O 次数 | ~1800-2400 次 | ~300-600 次 | ~1200-1800 次 |
| 会话触发次数（6步/会话） | ~50-75 次 | ~38-50 次 | ~12-25 次 |

---

## 7. 缓存文件格式

### 7.1 context_cache.json 结构

```json
{
  "cache_version": "1.0",
  "generated_at": "2026-07-24T10:00:00+08:00",
  "workspace": "d:\\personFile\\write-assistant",
  "skills": [
    {
      "name": "chapter-writer",
      "path": ".trae/skills/chapter-writer/SKILL.md",
      "size": 8421,
      "last_modified": "2026-07-20T10:00:00+08:00",
      "summary": "前500字符摘要...",
      "rule_count": 47
    }
  ],
  "files": [
    {
      "path": "memory/outline.json",
      "size": 12345,
      "last_modified": "2026-07-24T20:00:00+08:00",
      "type": "json",
      "top_level_keys": ["title", "genre", "theme", "volumes", "..."]
    }
  ],
  "stats": {
    "total_skills": 18,
    "total_files": 8,
    "cache_hits": 20,
    "cache_misses": 6,
    "total_size_bytes": 234567
  }
}
```

### 7.2 字段说明

| 层级 | 字段 | 类型 | 说明 |
|------|------|------|------|
| 根 | `cache_version` | string | 缓存格式版本，不匹配时触发全量重建 |
| 根 | `generated_at` | string | 缓存生成时间（ISO 8601） |
| 根 | `workspace` | string | 工作目录绝对路径 |
| 根 | `skills` | array | Skill 缓存列表 |
| skills[] | `name` | string | Skill 名称（目录名） |
| skills[] | `path` | string | SKILL.md 相对路径（正斜杠） |
| skills[] | `size` | number | 文件大小（字节） |
| skills[] | `last_modified` | string | 最后修改时间（ISO 8601） |
| skills[] | `summary` | string | 正文前 500 字符摘要 |
| skills[] | `rule_count` | number | 关键规则数量 |
| 根 | `files` | array | 其他文件缓存列表 |
| files[] | `path` | string | 文件相对路径（正斜杠） |
| files[] | `size` | number | 文件大小（字节） |
| files[] | `last_modified` | string | 最后修改时间（ISO 8601） |
| files[] | `type` | string | 文件类型：`json` 或 `markdown` |
| files[] | `top_level_keys` | array | JSON 顶层 key 列表（仅 JSON 文件） |
| 根 | `stats` | object | 缓存统计 |
| stats | `total_skills` | number | 缓存的 Skill 总数 |
| stats | `total_files` | number | 缓存的其他文件总数 |
| stats | `cache_hits` | number | 本次运行缓存命中数 |
| stats | `cache_misses` | number | 本次运行缓存未命中数 |
| stats | `total_size_bytes` | number | 所有文件总大小（字节） |

---

## 8. 使用方法

### 8.1 自动模式（推荐）

在 `master_instruction.md` 的初始化阶段自动调用：

```
初始化步骤 7（上下文缓存检查）：
  → 运行 context_preloader.ps1 或检查 context_cache.json 有效性
  → 后续步骤引用缓存摘要
```

### 8.2 手动模式

```powershell
# 默认工作目录（脚本父目录的父目录）
powershell -ExecutionPolicy Bypass -File context_preloader.ps1

# 指定工作目录
powershell -ExecutionPolicy Bypass -File context_preloader.ps1 -Workspace "d:\path\to\workspace"
```

### 8.3 强制全量重建

删除缓存文件后重新运行：

```powershell
Remove-Item auto-runner\context_cache.json
powershell -ExecutionPolicy Bypass -File context_preloader.ps1
```

### 8.4 输出示例

```
=== 上下文预加载 v1.0 ===
工作目录: d:\personFile\write-assistant
缓存文件: d:\personFile\write-assistant\auto-runner\context_cache.json

[1/2] 预读 Skill 文件...
  cache hit : .trae/skills/chapter-writer/SKILL.md
  cache miss: .trae/skills/quality-reviewer/SKILL.md (重新读取, 52 条规则)
  ...

[2/2] 预读其他文件...
  cache hit : memory/outline.json
  cache miss: memory/goal_tracker.json (keys: card_type, novel_title, goals, ...)
  ...

=== 预加载完成 ===
Skill 数量  : 18
其他文件    : 8
缓存命中    : 20
缓存未命中  : 6
总大小      : 156.3 KB
耗时        : 0.85 秒
```

---

## 9. 与 master_instruction.md 的集成

### 9.1 初始化阶段集成

在 `master_instruction.md` 的初始化流程中，新增步骤 7：

```
7. 上下文缓存检查（v2.2新增）：
   - 检查 auto-runner/context_cache.json 是否存在
   - 若不存在或已过期：运行 context_preloader.ps1 重建缓存
   - 若缓存有效：后续步骤引用缓存中的 SKILL.md 摘要
```

### 9.2 步骤执行集成

在主循环的步骤执行中，修改为：

```
5. 执行该步骤：
   a. 检查 context_cache.json → 获取 SKILL.md 缓存摘要
   b. 读取 input_files（当前步骤必需的输入文件）
   c. 引用 SKILL.md 缓存摘要（或按需读取完整文件）
   d. 执行步骤逻辑
   e. 写入 output_files
```

### 9.3 降级触发集成

当步骤上下文消耗接近窗口上限时：

```
降级策略（按优先级从低到高移除）：
  1. 参考文件全文 → 替换为缓存元数据
  2. 按需文件全文 → 替换为缓存 key 列表
  3. 必读文件全文 → 替换为缓存 key 列表
  4. SKILL.md 全文 → 替换为缓存摘要
  5. 保留：input_files + SKILL.md 缓存摘要
```
