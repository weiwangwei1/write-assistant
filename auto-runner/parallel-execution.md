# 并行执行框架 (Parallel Execution Framework) v2.0

## 概述

本框架定义了小说写作系统中可并行执行的8种模式，通过多Agent同时工作大幅提升生产速度。每个模式包含：适用场景、依赖关系、Agent分配策略、合并机制、风险控制、task_config配置示例。

### v2.0变更说明

**v1.0问题**：定义了7种并行模式，但 `task_config.json` 和 `state.json` 均未对接并行字段，`master_instruction.md` 的调度协议仅作概念描述——实际执行时所有步骤100%串行，并行模式停留在"设计文档"层面无法落地。经调研确认：**7种模式定义但0种实施**。

**v2.0改进**：新增**实施层**，使并行框架从"设计文档"升级为"可执行规范"：
- `task_config.json` 并行字段模板：每个模式给出可直接复制的 `parallel_group` / `parallel_index` / `parallel_total` / `is_merger` / `depends_on` 配置片段
- `state.json` 并行状态扩展：新增 `parallel_groups` 数组，追踪每个并行组的实时状态（group_id / status / pending_agents / completed_agents / merger_ready）
- `master_instruction.md` 调度协议：明确的"识别并行组 → 检查依赖 → 同时启动 → 等待完成 → 执行合并 → 更新状态"六步调度流程

**落地验证**：v2.0要求至少1个模式在实际执行中使用，并通过文件末尾的"v2.0落地检查清单"验证。

---

## 依赖关系图

### 当前串行流水线
```
topic-screener → plot-architect → skeptic×3 → outline-editor 
  → character-designer(ALL) → setting-reviewer 
    → chapter-writer Ch1 → detail → quality → de-ai → final 
      → chapter-writer Ch2 → detail → quality → de-ai → final 
        → ...
```

### 并行化后的流水线
```
topic-screener → plot-architect 
  ├─[PARALLEL]─ title-reviewer ─┐
  ├─[PARALLEL]─ skeptic R1 ─────┤
  ├─[PARALLEL]─ setting-reviewer ┘
  ├─[SERIAL]── skeptic R2 → skeptic R3
  ├─[MERGE]─── outline-editor (waits for all above)
  │
  ├─[PARALLEL]─ char-agent: 许愿 ─┐
  ├─[PARALLEL]─ char-agent: 老灯 ─┤
  ├─[PARALLEL]─ char-agent: 豆灯 ─┤
  ├─[PARALLEL]─ char-agent: 温故 ─┤
  ├─[PARALLEL]─ char-agent: 霍东来 ┤
  ├─[PARALLEL]─ char-agent: 封九霄 ┘
  ├─[MERGE]─── relationship-designer (waits for all chars)
  │
  ├─[PARALLEL]─ chapter-writer Ch1 ─┐
  ├─[PARALLEL]─ chapter-writer Ch2 ─┤ (if beat sheets pre-planned)
  ├─[PARALLEL]─ chapter-writer Ch3 ─┘
  ├─[MERGE]─── continuity-checker (cross-chapter consistency)
  │
  ├─[PARALLEL]─ review-agent Ch1 ─┐
  ├─[PARALLEL]─ review-agent Ch2 ─┤ (full pipeline per chapter)
  ├─[PARALLEL]─ review-agent Ch3 ─┘
```

---

## 模式1: 预生产并行 (Pre-production Fan-out)

### 适用场景
plot-architect 产出大纲后，多个独立审核任务可同时执行。

### 依赖关系
- **前置**: plot-architect 完成，`memory/outline.json` 就绪
- **并行任务**: title-reviewer, skeptic R1, setting-reviewer
- **后置**: outline-editor (等待全部完成)

### Agent分配
```
Agent A: title-reviewer → handoff/title_review.json
Agent B: skeptic R1 → handoff/skeptic_review.json (round=1)
Agent C: setting-reviewer → handoff/setting_review.json
```

### task_config配置示例
```json
[
  {
    "id": 10, "name": "书名审核", "agent": "title-reviewer",
    "parallel_group": "preproduction", "parallel_index": 0, "parallel_total": 3,
    "depends_on": [9], "is_merger": false
  },
  {
    "id": 11, "name": "质疑第1轮", "agent": "skeptic",
    "parallel_group": "preproduction", "parallel_index": 1, "parallel_total": 3,
    "depends_on": [9], "is_merger": false
  },
  {
    "id": 12, "name": "设定审核", "agent": "setting-reviewer",
    "parallel_group": "preproduction", "parallel_index": 2, "parallel_total": 3,
    "depends_on": [9], "is_merger": false
  },
  {
    "id": 13, "name": "大纲验收", "agent": "outline-editor",
    "parallel_group": "preproduction", "is_merger": true,
    "depends_on": [10, 11, 12]
  }
]
```

### 合并机制
outline-editor 读取全部3个输出文件后执行验收。

### 风险控制
- skeptic R2/R3 仍串行（依赖前一轮结果）
- 若 title-reviewer 判定需修改书名，outline-editor 需先处理书名修改

### 预期提速
串行3步×15min = 45min → 并行1步×15min = 15min，**提速3x**

---

## 模式2: 角色并行设计 (Character Design Fan-out)

### 适用场景
outline-editor 验收通过后，多个角色可独立设计。

### 依赖关系
- **前置**: outline-editor 完成，角色需求清单确认
- **并行任务**: 每个角色1个agent
- **后置**: relationship-designer (等待全部角色卡完成)

### Agent分配
```
Agent 1: 设计 许愿(主角) → memory/characters/许愿.json
Agent 2: 设计 老灯(古龙) → memory/characters/老灯.json
Agent 3: 设计 豆灯(萌宠) → memory/characters/豆灯.json
Agent 4: 设计 温故(终极反派) → memory/characters/温故.json
Agent 5: 设计 霍东来(隐藏反派) → memory/characters/霍东来.json
Agent 6: 设计 封九霄(灰色角色) → memory/characters/封九霄.json
--- MERGE ---
Agent 7: 关系网络设计 → memory/characters.json (合并所有角色卡+关系网络+成长弧线)
```

### task_config配置示例
```json
[
  {
    "id": 20, "name": "角色设计-许愿", "agent": "character-designer",
    "parallel_group": "char_design", "parallel_index": 0, "parallel_total": 6,
    "depends_on": [13], "is_merger": false
  },
  {
    "id": 21, "name": "角色设计-老灯", "agent": "character-designer",
    "parallel_group": "char_design", "parallel_index": 1, "parallel_total": 6,
    "depends_on": [13], "is_merger": false
  },
  {
    "id": 22, "name": "角色设计-豆灯", "agent": "character-designer",
    "parallel_group": "char_design", "parallel_index": 2, "parallel_total": 6,
    "depends_on": [13], "is_merger": false
  },
  {
    "id": 23, "name": "角色设计-温故", "agent": "character-designer",
    "parallel_group": "char_design", "parallel_index": 3, "parallel_total": 6,
    "depends_on": [13], "is_merger": false
  },
  {
    "id": 24, "name": "角色设计-霍东来", "agent": "character-designer",
    "parallel_group": "char_design", "parallel_index": 4, "parallel_total": 6,
    "depends_on": [13], "is_merger": false
  },
  {
    "id": 25, "name": "角色设计-封九霄", "agent": "character-designer",
    "parallel_group": "char_design", "parallel_index": 5, "parallel_total": 6,
    "depends_on": [13], "is_merger": false
  },
  {
    "id": 26, "name": "关系网络设计", "agent": "relationship-designer",
    "parallel_group": "char_design", "is_merger": true,
    "depends_on": [20, 21, 22, 23, 24, 25]
  }
]
```

### 单角色Agent指令模板
```
你是角色设计专家。设计角色「{角色名}」的完整角色卡。
读取以下文件：
- memory/outline.json (获取角色需求和大纲)
- .trae/skills/character-designer/SKILL.md (获取设计规范)
- config/novel_config.json (获取风格设定)

设计要求（必须包含）：
1. 外貌+气质描写（立体形象，非标签化）
2. 性格极致特征 (personality_extreme)
3. 反差设计 (identity_contrast + appearance_contrast)
4. 独立目标（非纯工具人）
5. story_driver（性格如何驱动剧情）
6. personal_habits（≥3个与剧情无关的习惯）
7. weaknesses（≥2个弱点）
8. show_events（≥3个展示事件）
9. 角色形象渐入法则（主角前3章视觉锚点）

输出到 memory/characters/{角色名}.json
不要设计关系网络——关系网络将由独立的合并Agent处理。
```

### 关系合并Agent指令模板
```
你是角色关系网络设计师。读取所有已完成的单个角色卡：
- memory/characters/许愿.json
- memory/characters/老灯.json
- ... (所有角色)

任务：
1. 设计角色之间的关系类型与动态演变
2. 规划成长弧线交叉点
3. 检查角色间的性格冲突与互补
4. 确保2-3个核心关系有明确演变阶段
5. 合并所有角色卡为统一的 memory/characters.json
6. 输出交接卡 handoff/characters.json

关系网络必须包含：
- 关系类型（盟友/敌对/师徒/利用/暗恋等）
- 当前演变阶段
- 演变触发条件
- 冲突点设计
```

### 风险控制
- 每个角色Agent必须读取相同的outline.json，确保世界观一致
- 合并Agent需检查角色间是否有设定冲突（如两个角色背景矛盾）
- 若合并发现冲突，标记 conflict 并退回对应角色Agent修改

### 预期提速
串行6角色×15min = 90min → 并行1轮×15min + 合并1轮×15min = 30min，**提速3x**

---

## 模式3: 多章并行审核 (Multi-chapter Review Fan-out)

### 适用场景
多个章节已完成初稿，需同时进入审核流水线。

### 依赖关系
- **前置**: 多章初稿已完成 (chapter_001.txt ~ chapter_00N.txt)
- **并行任务**: 每章1个agent，执行完整审核流水线 (detail→quality→de-ai→final)
- **后置**: 无（各章独立完成）

### Agent分配
```
Agent 1: Ch1 完整审核 → detail_review_ch1.json + quality_review_ch1.json + de_ai_ch1.json + final_review_ch1.json
Agent 2: Ch2 完整审核 → ...ch2.json
Agent 3: Ch3 完整审核 → ...ch3.json
Agent 4: Ch4 完整审核 → ...ch4.json
Agent 5: Ch5 完整审核 → ...ch5.json
```

### task_config配置示例
```json
[
  {
    "id": 30, "name": "Ch1完整审核", "agent": "multi-reviewer",
    "parallel_group": "batch_review", "parallel_index": 0, "parallel_total": 5,
    "depends_on": [], "is_merger": false
  },
  {
    "id": 31, "name": "Ch2完整审核", "agent": "multi-reviewer",
    "parallel_group": "batch_review", "parallel_index": 1, "parallel_total": 5,
    "depends_on": [], "is_merger": false
  },
  {
    "id": 32, "name": "Ch3完整审核", "agent": "multi-reviewer",
    "parallel_group": "batch_review", "parallel_index": 2, "parallel_total": 5,
    "depends_on": [], "is_merger": false
  },
  {
    "id": 33, "name": "Ch4完整审核", "agent": "multi-reviewer",
    "parallel_group": "batch_review", "parallel_index": 3, "parallel_total": 5,
    "depends_on": [], "is_merger": false
  },
  {
    "id": 34, "name": "Ch5完整审核", "agent": "multi-reviewer",
    "parallel_group": "batch_review", "parallel_index": 4, "parallel_total": 5,
    "depends_on": [], "is_merger": false
  },
  {
    "id": 35, "name": "伏笔追踪器合并", "agent": "chief-editor",
    "parallel_group": "batch_review", "is_merger": true,
    "depends_on": [30, 31, 32, 33, 34]
  }
]
```

### 单章审核Agent指令模板
```
你是章节审核专家，负责第{N}章的完整审核流水线。
读取以下文件：
- output/chapter_00{N}.txt (章节正文)
- .trae/skills/detail-reviewer/SKILL.md
- .trae/skills/quality-reviewer/SKILL.md
- .trae/skills/de-ai-processor/SKILL.md
- .trae/skills/final-reviewer/SKILL.md
- memory/outline.json (大纲)
- memory/characters.json (角色卡)
- memory/foreshadowing_tracker.json (伏笔追踪)
- output/chapter_00{N-1}.txt (前一章，衔接检查)

按顺序执行4步审核：
1. detail-reviewer: 逐句微观打磨 → handoff/detail_review_ch{N}.json
   - 修复所有critical/major问题
   - 更新 chapter_00{N}.txt
2. quality-reviewer: 8维评分 → handoff/quality_review_ch{N}.json
   - 技术分≥9.5则通过，否则标注退回原因
3. de-ai-processor: 去AI化 → handoff/de_ai_polish_ch{N}.json
   - 更新 chapter_00{N}.txt
4. final-reviewer: 终审 → handoff/final_review_ch{N}.json
   - 均分≥9.5则放行

如任何步骤未通过，在报告中标注并停止后续步骤。
更新 memory/foreshadowing_tracker.json 中本章相关伏笔状态。
```

### 风险控制
- 各章审核Agent独立工作，不修改共享文件（除各自的chapter_00N.txt）
- foreshadowing_tracker.json 的更新需在最后由主控Agent合并（避免并发写入冲突）
- 若某章审核失败，不影响其他章节的审核进程

### 预期提速
串行5章×(4步×15min) = 300min → 并行1章×60min = 60min，**提速5x**

---

## 模式4: 单章审核内部并行 (Intra-chapter Review Parallel)

### 适用场景
单章审核中，部分步骤可并行执行。

### 依赖关系
```
detail-reviewer ─┐
                 ├─→ quality-reviewer → final-reviewer
de-ai-processor ─┘
```

### 说明
- detail-reviewer 和 de-ai-processor 检查不同维度（内容 vs 语言），可并行
- quality-reviewer 需读取 detail_review 结果，必须串行在后
- final-reviewer 需读取全部结果，必须最后执行

### Agent分配
```
Agent A: detail-reviewer → handoff/detail_review_ch{N}.json (修复critical/major, 更新txt)
Agent B: de-ai-processor → handoff/de_ai_polish_ch{N}.json (检测AI痕迹, 更新txt)
--- WAIT BOTH ---
Agent C: quality-reviewer → handoff/quality_review_ch{N}.json (8维评分)
--- WAIT C ---
Agent D: final-reviewer → handoff/final_review_ch{N}.json (终审)
```

### task_config配置示例
```json
[
  {
    "id": 40, "name": "Ch{N}细节审核", "agent": "detail-reviewer",
    "parallel_group": "intra_review_{N}", "parallel_index": 0, "parallel_total": 2,
    "depends_on": [], "is_merger": false
  },
  {
    "id": 41, "name": "Ch{N}去AI化", "agent": "de-ai-processor",
    "parallel_group": "intra_review_{N}", "parallel_index": 1, "parallel_total": 2,
    "depends_on": [], "is_merger": false
  },
  {
    "id": 42, "name": "Ch{N}质量审核", "agent": "quality-reviewer",
    "parallel_group": null, "depends_on": [40, 41], "is_merger": false
  },
  {
    "id": 43, "name": "Ch{N}终审", "agent": "final-reviewer",
    "parallel_group": null, "depends_on": [42], "is_merger": false
  }
]
```
注：quality-reviewer 和 final-reviewer 的 `parallel_group` 为 `null`，表示它们不参与并行，串行等待前序完成。

### 风险控制
- detail-reviewer 和 de-ai-processor 都会修改 chapter_00N.txt
- **解决方案**: 两个Agent分别输出修改建议（不直接改文件），由quality-reviewer前的合并步骤统一应用
- 或: de-ai-processor 在 detail-reviewer 完成后再执行（退化为串行，但仍可并行读取分析）

### 预期提速
串行4步×15min = 60min → 并行(detail+de-ai)15min + quality 15min + final 15min = 45min，**提速1.3x**

---

## 模式5: 多章并行写作 (Multi-chapter Writing Fan-out)

### 适用场景
大纲和分镜(beat sheet)已详细规划，多章可同时写作。

### 依赖关系
- **前置**: 大纲验收通过 + 每章beat sheet已设计
- **并行任务**: 每章1个writing agent
- **后置**: continuity-checker (跨章连续性检查)

### Agent分配
```
Agent 1: 写 Ch1 (基于 beat_sheet_ch1) → output/chapter_001.txt
Agent 2: 写 Ch2 (基于 beat_sheet_ch2) → output/chapter_002.txt
Agent 3: 写 Ch3 (基于 beat_sheet_ch3) → output/chapter_003.txt
--- MERGE ---
Agent 4: 连续性检查 → handoff/continuity_check.json
  - 检查跨章衔接（Ch1结尾→Ch2开头）
  - 检查角色状态连续性
  - 检查伏笔埋设/回收一致性
  - 检查时间线连贯性
```

### task_config配置示例
```json
[
  {
    "id": 50, "name": "写Ch1", "agent": "chapter-writer",
    "parallel_group": "batch_write", "parallel_index": 0, "parallel_total": 3,
    "depends_on": [], "is_merger": false
  },
  {
    "id": 51, "name": "写Ch2", "agent": "chapter-writer",
    "parallel_group": "batch_write", "parallel_index": 1, "parallel_total": 3,
    "depends_on": [], "is_merger": false
  },
  {
    "id": 52, "name": "写Ch3", "agent": "chapter-writer",
    "parallel_group": "batch_write", "parallel_index": 2, "parallel_total": 3,
    "depends_on": [], "is_merger": false
  },
  {
    "id": 53, "name": "跨章连续性检查", "agent": "quality-reviewer",
    "parallel_group": "batch_write", "is_merger": true,
    "depends_on": [50, 51, 52]
  }
]
```

### 单章写作Agent指令模板
```
你是章节写作专家，负责第{N}章的撰写。
读取以下文件：
- .trae/skills/chapter-writer/SKILL.md (写作规范)
- memory/outline.json (大纲)
- memory/characters.json (角色卡)
- handoff/beat_sheet_ch{N}.json (本章分镜)
- output/chapter_00{N-1}.txt (前一章，衔接用) [如存在]
- output/chapter_00{N-2}.txt (前两章，节奏参考) [如存在]

严格按照 beat_sheet 的 scene 顺序和 word_budget 执行。
开头方式: {指定类型}（与前一章不同）
结尾类型: {指定类型}（与前一章不同）

输出到 output/chapter_00{N}.txt
每句话单独一行。
不要修改其他章节的文件。
```

### 连续性检查Agent指令模板
```
你是跨章连续性检查专家。读取所有已完成的章节：
- output/chapter_001.txt ~ chapter_00{N}.txt

检查项：
1. 衔接检查: 每章结尾→下章开头是否自然衔接
2. 角色状态: 角色的情绪/位置/能力是否连续
3. 伏笔一致性: 伏笔埋设和回收是否跨章一致
4. 时间线: 事件时序是否合理
5. 开头/结尾轮换: 是否有连续相同类型
6. 称呼一致性: 角色称呼是否跨章统一

输出到 handoff/continuity_check.json
对每个问题给出具体修改建议。
```

### 风险控制
- **高风险模式**: 多章并行写作最容易出现衔接问题
- **前提条件**: beat sheet 必须非常详细（每个beat的scene/action/purpose/word_budget）
- **必须执行**: 连续性检查Agent的输出必须由主控审阅，critical问题必须修复
- **建议**: 最多并行3章，不宜过多

### 预期提速
串行3章×30min = 90min → 并行1轮×30min + 检查1轮×15min = 45min，**提速2x**

---

## 模式6: 研究并行 (Research Fan-out)

### 适用场景
需要多方面参考资料时，多个搜索agent同时工作。

### Agent分配
```
Agent 1: 搜索"白金作者X的写作技法" → research/technique_X.md
Agent 2: 搜索"番茄平台读者偏好2026" → research/platform_prefs.md
Agent 3: 搜索"同类题材竞品分析" → research/competitors.md
Agent 4: 搜索"龙空论坛写作经验精华" → research/longkong_tips.md
```

### task_config配置示例
```json
[
  {
    "id": 60, "name": "搜索写作技法", "agent": "researcher",
    "parallel_group": "research", "parallel_index": 0, "parallel_total": 4,
    "depends_on": [], "is_merger": false
  },
  {
    "id": 61, "name": "搜索平台偏好", "agent": "researcher",
    "parallel_group": "research", "parallel_index": 1, "parallel_total": 4,
    "depends_on": [], "is_merger": false
  },
  {
    "id": 62, "name": "搜索竞品分析", "agent": "researcher",
    "parallel_group": "research", "parallel_index": 2, "parallel_total": 4,
    "depends_on": [], "is_merger": false
  },
  {
    "id": 63, "name": "搜索论坛经验", "agent": "researcher",
    "parallel_group": "research", "parallel_index": 3, "parallel_total": 4,
    "depends_on": [], "is_merger": false
  }
]
```
注：模式6无合并步骤，各Agent独立输出，`is_merger` 均为 `false`。

### 预期提速
串行4搜索×10min = 40min → 并行1轮×10min = 10min，**提速4x**

---

## 并行执行配置格式

在 `task_config.json` 中，并行步骤使用 `parallel_group` 字段标识：

```json
{
  "steps": [
    {
      "id": 5,
      "name": "大纲验收",
      "agent": "outline-editor",
      "parallel_group": null,
      "depends_on": [2, 3, 4]
    },
    {
      "id": 6,
      "name": "角色设计-许愿",
      "agent": "character-designer",
      "parallel_group": "char_design",
      "parallel_index": 0,
      "parallel_total": 6,
      "depends_on": [5]
    },
    {
      "id": 12,
      "name": "关系网络设计",
      "agent": "relationship-designer",
      "parallel_group": "char_design",
      "is_merger": true,
      "depends_on": [6, 7, 8, 9, 10, 11]
    }
  ]
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `parallel_group` | 并行组标识，同组步骤可同时执行 |
| `parallel_index` | 组内序号 |
| `parallel_total` | 组内总数 |
| `is_merger` | 是否为合并步骤（等待同组全部完成后执行） |
| `depends_on` | 依赖的步骤ID列表 |

---

## 实施层规范 (Implementation Layer) v2.0

v1.0仅定义了并行模式的设计，但 `task_config.json` / `state.json` / `master_instruction.md` 三者均未对接，导致实际执行100%串行。本节定义实施层的三个组件，使并行模式真正可执行。

### state.json 并行状态扩展格式

在 `state.json` 顶层新增 `parallel_groups` 数组，追踪每个并行组的实时状态：

```json
{
  "task_name": "...",
  "status": "running",
  "current_step": 20,
  "total_steps": 26,
  "parallel_groups": [
    {
      "group_id": "char_design",
      "status": "in_progress",
      "parallel_total": 6,
      "pending_agents": ["角色设计-霍东来", "角色设计-封九霄"],
      "completed_agents": ["角色设计-许愿", "角色设计-老灯", "角色设计-豆灯", "角色设计-温故"],
      "failed_agents": [],
      "merger_step_id": 26,
      "merger_ready": false
    }
  ],
  "steps": [ ... ]
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `group_id` | string | 并行组标识，与 `task_config.json` 中的 `parallel_group` 对应 |
| `status` | string | `pending` / `in_progress` / `merging` / `completed` / `failed` |
| `parallel_total` | int | 组内并行Agent总数 |
| `pending_agents` | string[] | 尚未完成的Agent名称列表 |
| `completed_agents` | string[] | 已完成的Agent名称列表 |
| `failed_agents` | string[] | 失败的Agent名称列表（不阻塞其他Agent） |
| `merger_step_id` | int | 合并步骤的ID（若无合并步骤则为null） |
| `merger_ready` | bool | 是否所有并行Agent已完成，合并步骤可启动 |

**状态流转**：
```
pending → in_progress (首个Agent启动) → merging (全部完成，合并启动) → completed
                                                    ↘ failed (合并检测到不可恢复缺失)
```

### master_instruction 调度协议

在 `master_instruction.md` 的主循环中，将原"单步串行执行"升级为"六步并行调度协议"：

```
WHILE true:
    1. 识别并行组：扫描 task_config.json 的 steps[current_step:]，
       找出 parallel_group 相同且 is_merger != true 的连续步骤
       
    2. 检查依赖：确认该并行组所有步骤的 depends_on 指向的步骤均已完成
       - 若依赖未满足 → 跳过本组，执行依赖步骤
       - 若依赖已满足 → 进入步骤3
    
    3. 同时启动：在同一条消息中发送多个 Task 工具调用（最多5个），
       将 state.json 中 parallel_groups[group_id].status 设为 "in_progress"
    
    4. 等待完成：所有并行Agent返回后，逐个检查输出文件
       - 成功的Agent加入 completed_agents
       - 失败的Agent加入 failed_agents（不中断其他Agent）
       - 更新 pending_agents 列表
    
    5. 执行合并：当 pending_agents 为空时，将 merger_ready 设为 true
       - 若存在 is_merger=true 的步骤 → 执行合并Agent
       - 合并Agent检查 completed_agents 数量是否等于 parallel_total
         · 缺失项（failed_agents中的）→ 标记为 missing，在合并报告中列出
       - 若无合并步骤 → 直接推进 current_step
    
    6. 更新状态：将并行组所有步骤标记为 completed（失败的标记为 retry），
       推进 current_step 跳过本组所有步骤
END WHILE
```

**与v1.0的区别**：v1.0的 `master_instruction.md` 中"并行步骤执行策略"仅作概念描述，调度器实际仍按 `current_step` 逐个串行执行。v2.0要求调度器在步骤3真正发起并行 Task 调用。

### 失败处理升级

v1.0的失败处理为"并行组中1个Agent失败不影响其他"，但未定义合并Agent如何处理缺失项。v2.0明确以下规则：

| 场景 | 处理方式 |
|------|---------|
| **单Agent失败** | 记录到 `failed_agents`，同组其他Agent继续执行，不中断 |
| **合并Agent检测到缺失项** | 合并报告中列出所有 `failed_agents` 对应的缺失输出，标注 `missing_items` |
| **缺失项为非关键** | 合并Agent跳过缺失项，继续合并已完成部分，`verdict=pass_with_note` |
| **缺失项为关键**（如主角角色卡缺失） | 合并Agent标注 `verdict=fail`，退回失败的Agent重试（max_retries次） |
| **重试超限** | 该并行组 `status` 设为 `failed`，停止执行，记录 `stop_reason` |
| **无合并步骤的组** | 失败的Agent单独退回重试，不影响同组其他Agent的已完成状态 |

**关键原则**：单Agent失败不阻塞同组其他Agent，合并Agent负责检查缺失项并决定是跳过还是退回。

---

## 并行执行调度规则

### 1. 调度优先级
1. 检查所有 `depends_on` 是否已完成
2. 若有 `parallel_group`，同组步骤同时启动
3. `is_merger=true` 的步骤等待同组全部完成后再执行
4. 无依赖的步骤立即执行

### 2. 并发限制
- 单次最多并行 **5个Agent**（避免资源过载）
- 角色设计并行：最多6个角色Agent + 1个合并Agent
- 章节审核并行：最多5章同时审核
- 章节写作并行：最多3章同时写作（高风险，需严格beat sheet）

### 3. 失败处理
- 并行组中1个Agent失败：不影响其他Agent继续执行
- 合并Agent检查所有并行输出：若某Agent输出缺失，标记并退回
- 质量门禁失败：仅退回失败章节的角色Agent/审核Agent

### 4. 文件冲突控制
- **只读共享文件**（outline.json, characters.json等）：并行Agent可同时读
- **写入隔离**：每个并行Agent只写自己的输出文件（如 characters/许愿.json）
- **合并写入**：只有合并Agent或主控Agent可写共享输出文件（如 characters.json）
- **禁止并发修改同一文件**：如两个Agent不能同时修改 chapter_001.txt

---

## 全流程提速估算

| 阶段 | 串行耗时 | v1.0设计耗时 | v2.0实施后耗时 | 提速(v2.0) |
|------|---------|-------------|---------------|-----------|
| 预生产 (topic→outline) | 105min | 45min | 50min | 2.1x |
| 角色设计 | 90min | 30min | 35min | 2.6x |
| 黄金三章写作 | 90min | 45min | 50min | 1.8x |
| 黄金三章审核 | 180min | 45min | 55min | 3.3x |
| **总计** | **465min** | **165min** | **190min** | **2.4x** |

注：v2.0实施后耗时略高于v1.0设计耗时，因增加了状态管理（parallel_groups更新）、合并协调和失败检查的开销（每阶段约+5-10min）。但相比串行465min仍有2.4x提速。

### 与当前auto-runner对比

| 方案 | 全流程耗时 | 触发次数 |
|------|-----------|---------|
| 旧方案（每触发1步） | 330min (5.5h) | 22次 |
| 当前方案（连续执行） | 120min (2h) | 8次 |
| v1.0并行方案（设计值，未实施） | 165min (2.75h) | 6次 |
| **v2.0并行方案（实施后）** | **190min (3.2h)** | **6次** |

注：v2.0并行方案总耗时略高于v1.0设计值，因包含实施层的状态管理和合并协调开销。但v2.0是可实际执行的方案，而v1.0从未落地。v2.0在**多章审核**场景下优势巨大（5章审核从300min降至55min）。

---

## 适用场景推荐

| 场景 | 推荐模式 | 原因 |
|------|---------|------|
| 新书启动（选题→大纲→角色） | 模式1+模式2 | 预生产和角色设计并行 |
| 黄金三章生产 | 模式5+模式3 | 先并行写3章，再并行审核3章 |
| 日常连更（已有存稿） | 模式3 | 多章已写好，并行审核最快 |
| 日常连更（无存稿） | 模式5 | 并行写2-3章+连续性检查 |
| 日常连更（流水线） | 模式8 | 前章审核时同时写后章，边审边写提速1.5x |
| 研究/竞品分析 | 模式6 | 多维度同时搜索 |
| 单章精修 | 模式4 | detail+de-ai并行加速单章审核 |
| 日常单章生产（通用） | 模式7 | 审核并行+统一合并，每章省10-15min |

---

## 模式7: 审核并行+统一合并 (Review Parallel + Merge) v1.1

### 适用场景

单章生产中的审核阶段。将 detail-reviewer 和 de-ai-processor 从串行改为并行，各自输出修改建议（不改文本），由合并步骤统一处理。

### 核心改造

将 de-ai-processor 拆分为两阶段：**分析阶段**（只检测输出报告）+ **应用阶段**（合并后统一改文本）。

### 依赖关系

```
chapter-writer 产出草稿
    ↓
┌───────────────────────────────────────────┐
│  PARALLEL (同时启动，各出意见，不改文本)    │
│  Agent A: detail-reviewer (内容分析)      │
│    → 逐句/逐梗/逐伏笔/逻辑/事实表/暗线      │
│    → 输出 detail_review.json (建议清单)    │
│                                           │
│  Agent B: de-ai-processor 分析模式        │
│    → 14类AI痕迹检测（只检测不修改）         │
│    → 输出 de_ai_analysis.json (建议清单)   │
└───────────────────────────────────────────┘
    ↓
review-merger (5min) → 合并两份建议，解决冲突，输出统一修改清单
    ↓
chapter-writer 按统一清单修改 (10min)
    ↓
quality-reviewer (15min) → 8维评分
    ↓
final-reviewer (15min) → 终审裁决
```

### 合并冲突处理规则

| 场景 | detail 意见 | de-ai 意见 | 合并策略 |
|------|------------|-----------|---------|
| 同句不同因 | 第3段逻辑断裂 | 第3段句式工整 | 合为一条，两个reason，取severity更高的改法 |
| 同句不冲突 | 第5段伏笔太明显 | 第5段情绪直说 | 两条独立建议，分别处理 |
| 仅一方有 | 第7段角色台词串味 | 无 | 保留单方建议 |
| 冲突修改 | 建议改为A句 | 建议改为B句 | detail优先（内容正确性>语言自然度），de-ai降级为备选 |

### Agent分配

```
Agent A: detail-reviewer → handoff/detail_review_ch{N}.json (建议清单，不改文本)
Agent B: de-ai-processor (分析模式) → handoff/de_ai_analysis_ch{N}.json (检测报告，不改文本)
--- MERGE ---
Agent C (主控/chief-editor): 合并两份建议 → handoff/merged_review_ch{N}.json (统一修改清单)
```

### task_config配置示例
```json
[
  {
    "id": 70, "name": "Ch{N}细节审核", "agent": "detail-reviewer",
    "parallel_group": "merge_review_{N}", "parallel_index": 0, "parallel_total": 2,
    "depends_on": [], "is_merger": false
  },
  {
    "id": 71, "name": "Ch{N}去AI化分析", "agent": "de-ai-processor",
    "parallel_group": "merge_review_{N}", "parallel_index": 1, "parallel_total": 2,
    "depends_on": [], "is_merger": false
  },
  {
    "id": 72, "name": "Ch{N}修改合并", "agent": "chief-editor",
    "parallel_group": "merge_review_{N}", "is_merger": true,
    "depends_on": [70, 71]
  },
  {
    "id": 73, "name": "Ch{N}质量审核", "agent": "quality-reviewer",
    "parallel_group": null, "depends_on": [72], "is_merger": false
  },
  {
    "id": 74, "name": "Ch{N}终审", "agent": "final-reviewer",
    "parallel_group": null, "depends_on": [73], "is_merger": false
  }
]
```

### 预期提速

串行4步×15min = 60min → 并行(detail+de-ai)15min + merger 5min + quality 15min + final 15min = 50min，**提速1.2x**

多章连审时收益更大：3章从210min降到150min，**提速1.4x**

### 风险控制

- de-ai 分析模式只输出检测报告，不修改文本，避免与 detail-reviewer 的修改冲突
- 合并步骤必须检查两份报告是否有同一句子的冲突修改建议
- quality-reviewer 仍需读取 detail_review 确认问题已修复（合并后的修改清单作为参考）

---

## 模式8: 流水线写作审核 (Pipeline Write-Review) v2.0

### 适用场景
日常连更场景：前一章进入审核流水线的同时，后一章开始写作，实现"边审边写"的流水线效果。适用于剧情中等耦合（章节间有衔接但不强依赖前章结局）的日常更新。

### 依赖关系
```
Ch(N) 写作完成
    ↓
┌───────────────────────────────────────────┐
│  PARALLEL                                  │
│  Agent A: Ch(N) 审核 (detail→quality)      │
│  Agent B: Ch(N+1) 写作 (读Ch(N)终稿衔接)   │
└───────────────────────────────────────────┘
    ↓
Ch(N) 入库 (de-ai→final→memory-manager)
    ↓
Ch(N+1) 审核 (detail→quality→de-ai→final)
```

### Agent分配
```
Agent A: Ch(N) 审核 → handoff/detail_review_ch{N}.json + handoff/quality_review_ch{N}.json
Agent B: Ch(N+1) 写作 → output/chapter_00{N+1}.txt (读 output/chapter_00{N}.txt 衔接)
--- WAIT BOTH ---
Agent C: Ch(N) 去AI化 → handoff/de_ai_polish_ch{N}.json (更新 chapter_00{N}.txt)
Agent D: Ch(N) 终审 → handoff/final_review_ch{N}.json
Agent E: Ch(N) 入库 → memory-manager 更新 (若终审通过)
--- THEN ---
Agent F: Ch(N+1) 审核 (完整4步流水线)
```

### task_config配置示例
```json
[
  {
    "id": 80, "name": "Ch{N}细节+质量审核", "agent": "multi-reviewer",
    "parallel_group": "pipeline_{N}", "parallel_index": 0, "parallel_total": 2,
    "depends_on": [], "is_merger": false
  },
  {
    "id": 81, "name": "Ch{N+1}撰写", "agent": "chapter-writer",
    "parallel_group": "pipeline_{N}", "parallel_index": 1, "parallel_total": 2,
    "depends_on": [], "is_merger": false
  },
  {
    "id": 82, "name": "Ch{N}去AI化", "agent": "de-ai-processor",
    "parallel_group": null, "depends_on": [80], "is_merger": false
  },
  {
    "id": 83, "name": "Ch{N}终审", "agent": "final-reviewer",
    "parallel_group": null, "depends_on": [82], "is_merger": false
  },
  {
    "id": 84, "name": "Ch{N}入库", "agent": "memory-manager",
    "parallel_group": null, "depends_on": [83, 81], "is_merger": false
  },
  {
    "id": 85, "name": "Ch{N+1}审核", "agent": "multi-reviewer",
    "parallel_group": null, "depends_on": [84], "is_merger": false
  }
]
```
注：Ch{N+1}审核依赖 Ch{N}入库（id=84），而入库又依赖 Ch{N+1}写作完成（id=81），形成流水线闭环。`parallel_group: "pipeline_{N}"` 仅覆盖审核+写作的并行阶段。

### 风险控制
- **写作Agent需读取前章终稿**：Ch(N+1)写作Agent必须读取 `output/chapter_00{N}.txt`（此时Ch(N)可能尚未完成去AI化/终审，但初稿已稳定），确保衔接自然
- **审核不通过时需回退**：若 Ch(N) 终审未通过（id=83 verdict≠pass），则：
  1. Ch(N+1)写作结果保留但标记为 `pending_revision`（可能需根据Ch(N)修改调整衔接）
  2. Ch(N) 退回 chapter-writer 修订
  3. Ch(N) 修订完成后重新走审核，再决定 Ch(N+1) 是否需要同步调整
- **去AI化与终审串行**：Ch(N)的去AI化（id=82）和终审（id=83）不参与并行，必须等审核Agent（id=80）完成后串行执行
- **入库门禁**：Ch(N)入库（id=84）同时依赖终审通过和Ch(N+1)写作完成，确保流水线节奏可控

### 预期提速
串行2章×(写作30min + 审核60min) = 180min → 流水线(写作30min + 并行审核30min + 入库后审核60min) = 120min，**提速1.5x**

多章连更时收益累积：5章连更从900min降至600min，**提速1.5x**

---

## 并行写作可行性评估 (Parallel Writing Assessment) v1.1

### 触发时机

每批章节（2-5章）写作前，由 chief-editor 触发评估，决定采用串行、流水线还是并行写作。

### 评估维度与评分

| 维度 | 评估内容 | 评分标准 | 权重 |
|------|---------|---------|------|
| **剧情耦合度** | 后章是否依赖前章结局 | 死局→翻盘=高耦合(9-10)；独立案件=低耦合(1-3) | 40% |
| **角色状态连续性** | 前章结尾角色状态是否决定后章走向 | 被捕→审讯=强依赖(8-10)；日常=弱依赖(1-3) | 25% |
| **悬念窗口约束** | 悬念闭环是否影响后续章节 | 需先闭环才能开新悬念=约束(7-10) | 20% |
| **伏笔状态依赖** | 本章伏笔动作是否依赖前章结果 | 揭示需要前章铺垫=依赖(7-10) | 15% |

### 耦合度判定

| 加权总分 | 判定 | 处理 |
|---------|------|------|
| ≥7.0 | **高耦合** | 串行写作，不可并行 |
| 4.0-6.9 | **中耦合** | 流水线模式（前章写完→审核时同时写后章） |
| <4.0 | **低耦合** | 可并行写作（同时启动2-3章） |

### 保守原则

- 不确定时按高耦合处理（串行）
- 评估误判的代价远大于串行的额外耗时
- 首次使用并行写作时，最多2章并行，不用3章

### 评估报告格式

```json
{
  "card_type": "parallel_assessment",
  "assessed_chapters": [11, 12, 13],
  "overall_recommendation": "mixed",
  "groups": [
    {
      "chapters": [11],
      "mode": "parallel_writable",
      "coupling_score": 2.0,
      "reason": "叙事起点，无前序依赖"
    },
    {
      "chapters": [12],
      "mode": "serial",
      "coupling_score": 9.0,
      "reason": "翻盘方式直接依赖前章死局细节",
      "depends_on": [11]
    }
  ],
  "execution_plan": "Ch11先写 → Ch11审核时同时写Ch12 → 串行入库"
}
```

### 评估数据源

- `memory/outline.json` 的 beat_breakdown（章节beat规划）
- `memory/goal_tracker.json`（目标依赖、悬念窗口状态）
- `memory/foreshadowing_tracker.json`（伏笔状态依赖）

---

## v2.0落地检查清单

v2.0的核心目标是将并行框架从"设计文档"变为"可执行规范"。以下检查清单用于验证v2.0是否真正落地：

- [ ] `task_config.json` 包含 `parallel_group` 字段（至少1个步骤使用）
- [ ] `state.json` 包含 `parallel_groups` 数组（运行时能追踪并行组状态）
- [ ] `master_instruction.md` 包含并行调度协议（六步调度流程已写入指令）
- [ ] 至少1个模式已在实际执行中使用（非模拟、非设计，真实跑通）

**验证方法**：

| 检查项 | 验证方式 | 通过标准 |
|--------|---------|---------|
| task_config并行字段 | 检查 `auto-runner/task_config.json` 的 steps 中是否有 `parallel_group != null` | 至少1个步骤 |
| state并行状态 | 检查 `auto-runner/state.json` 是否有 `parallel_groups` 数组 | 数组存在且非空 |
| 调度协议 | 检查 `auto-runner/master_instruction.md` 是否包含"并行调度协议"或"六步"描述 | 协议已写入 |
| 实际执行 | 检查 `execution_log.md` 中是否有同一时间戳下多个并行步骤的记录 | 至少1组并行执行记录 |

**未通过时的处理**：
- 若仅前3项未通过 → 补充实施层文件配置，重新检查
- 若第4项未通过（无实际执行记录）→ 选择最安全的模式（模式7或模式8）进行首次试运行
