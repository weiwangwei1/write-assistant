# 统一审核规范 (Unified Review Specification) v1.0

## 概述

将 quality-reviewer（8维技术分）和 final-reviewer（4维补充分+发布裁决）合并为单步统一审核，减少1步骤+1文件/章。

### 设计原则

1. **评分公式不变**：unified_score = technical_score×0.6 + supplementary_score×0.4
2. **维度全覆盖**：12维一次评完（8技术维+4补充维），无遗漏
3. **权重等价转换**：技术维权重×0.6，补充维权重×0.4，总权重=1.0
4. **裁决标准不变**：unified_score ≥ 9.5 为 approved
5. **向后兼容**：传统2步模式（quality→final）仍可用，unified为可选加速模式

---

## 12维统一评分表

### 技术维度（源自 quality-reviewer v1.8，权重×0.6）

| # | 维度 | 原权重 | 统一权重 | 评分标准来源 |
|---|------|--------|---------|-------------|
| T1 | attraction（吸引力） | 0.20 | 0.12 | quality-reviewer SKILL.md |
| T2 | shuang_point（爽点密度） | 0.15 | 0.09 | quality-reviewer SKILL.md v1.7爽点定义 |
| T3 | rhythm（节奏控制） | 0.125 | 0.075 | quality-reviewer SKILL.md |
| T4 | hook（章末钩子） | 0.125 | 0.075 | quality-reviewer SKILL.md v1.7悬念限流 |
| T5 | character（角色一致性） | 0.10 | 0.06 | quality-reviewer SKILL.md |
| T6 | plot（剧情连贯性） | 0.10 | 0.06 | quality-reviewer SKILL.md |
| T7 | logic（逻辑自洽） | 0.10 | 0.06 | quality-reviewer SKILL.md |
| T8 | writing（文笔质量） | 0.10 | 0.06 | quality-reviewer SKILL.md |
| | **技术小计** | **1.00** | **0.60** | |

### 补充维度（源自 final-reviewer v1.1，权重×0.4）

| # | 维度 | 原权重 | 统一权重 | 评分标准来源 |
|---|------|--------|---------|-------------|
| S1 | commercial_potential（商业潜力） | 0.30 | 0.12 | final-reviewer SKILL.md |
| S2 | reader_abandon_risk（读者弃书风险） | 0.25 | 0.10 | final-reviewer SKILL.md |
| S3 | platform_compliance（平台合规终检） | 0.20 | 0.08 | final-reviewer SKILL.md |
| S4 | cross_chapter_consistency（跨章一致性终检） | 0.25 | 0.10 | final-reviewer SKILL.md |
| | **补充小计** | **1.00** | **0.40** | |

### 总权重验证

```
技术维: 0.12+0.09+0.075+0.075+0.06+0.06+0.06+0.06 = 0.60
补充维: 0.12+0.10+0.08+0.10 = 0.40
总计: 0.60 + 0.40 = 1.00 ✓
```

---

## 输入规范

| 文件路径 | 说明 | 必需 |
|---------|------|------|
| `output/chapter_{NNN}.txt` | 修订终稿（经merged_review后） | 是 |
| `output/chapter_{NNN-1}.txt` | 前一章（衔接检查） | 是（第2章起） |
| `memory/outline.json` | 大纲 | 是 |
| `memory/characters.json` | 角色卡 | 是 |
| `memory/goal_tracker.json` | 目标+悬念窗口（v1.7监控） | 是（第2章起） |
| `memory/foreshadowing_tracker.json` | 伏笔追踪表 | 是 |
| `config/novel_config.json` | 写作规则+平台配置 | 是 |
| `handoff/chapters/merged_review_ch{NNN}.json` | 合并审核结果（引用修订状态） | 是 |

---

## 输出规范

输出到 `handoff/chapters/unified_review_ch{NNN}.json`

### 输出格式

```json
{
  "card_type": "unified_review",
  "chapter": 12,
  "chapter_title": "章节标题",
  "review_mode": "unified",
  "review_basis": "quality-reviewer v1.8 + final-reviewer v1.1 merged",

  "technical_dimensions": {
    "attraction": {
      "score": 9.6,
      "weight": 0.12,
      "weighted": 1.152,
      "detail": "评分理由..."
    },
    "shuang_point": {
      "score": 9.5,
      "weight": 0.09,
      "weighted": 0.855,
      "detail": "评分理由..."
    },
    "rhythm": {
      "score": 9.5,
      "weight": 0.075,
      "weighted": 0.7125,
      "detail": "评分理由..."
    },
    "hook": {
      "score": 8.0,
      "weight": 0.075,
      "weighted": 0.60,
      "detail": "评分理由..."
    },
    "character": {
      "score": 9.6,
      "weight": 0.06,
      "weighted": 0.576,
      "detail": "评分理由..."
    },
    "plot": {
      "score": 9.5,
      "weight": 0.06,
      "weighted": 0.57,
      "detail": "评分理由..."
    },
    "logic": {
      "score": 9.4,
      "weight": 0.06,
      "weighted": 0.564,
      "detail": "评分理由..."
    },
    "writing": {
      "score": 9.5,
      "weight": 0.06,
      "weighted": 0.57,
      "detail": "评分理由..."
    }
  },
  "technical_score": 9.42,

  "supplementary_dimensions": {
    "commercial_potential": {
      "score": 9.6,
      "weight": 0.12,
      "weighted": 1.152,
      "detail": "评分理由..."
    },
    "reader_abandon_risk": {
      "score": 9.5,
      "weight": 0.10,
      "weighted": 0.95,
      "detail": "评分理由..."
    },
    "platform_compliance": {
      "score": 9.8,
      "weight": 0.08,
      "weighted": 0.784,
      "detail": "评分理由..."
    },
    "cross_chapter_consistency": {
      "score": 9.7,
      "weight": 0.10,
      "weighted": 0.97,
      "detail": "评分理由..."
    }
  },
  "supplementary_score": 9.64,

  "unified_score": 9.51,
  "retention_index": 9.0,
  "pass_threshold": 9.5,
  "verdict": "approved",

  "monitoring": {
    "shuang_type_check": "pass — 描述...",
    "three_chapter_rolling": "Ch10(A)—Ch11(B)—Ch12(A) — 描述...",
    "suspense_throttle": "FAIL — active=4/3超限。描述...",
    "goal_stall_check": "pass — 描述...",
    "padawan_protection": {
      "consecutive_padawan": "0 — 描述...",
      "small_payoff": "有 — 描述...",
      "expectation_anchor": "有 — 描述..."
    }
  },

  "cross_check": {
    "dialogue_consistency": "pass",
    "terminology_consistency": "pass",
    "cross_chapter_continuity": "pass",
    "foreshadowing_status": "pass"
  },

  "abandon_risk_assessment": {
    "risk_level": "low",
    "risk_points": [
      "风险点1...",
      "风险点2..."
    ]
  },

  "reader_profiles": {
    "retention_index": 9.0,
    "market_risk": false,
    "risk_readers": [],
    "profiles": [
      {"name": "爽感猎人·阿爽", "追读意愿": 9, "弃书概率": "10%", "verdict": "追读", "feedback": "..."},
      {"name": "逻辑警察·老缜", "追读意愿": 9, "弃书概率": "5%", "verdict": "追读", "feedback": "..."},
      {"name": "角色粉·小迷", "追读意愿": 9, "弃书概率": "8%", "verdict": "追读", "feedback": "..."},
      {"name": "氛围党·画师", "追读意愿": 10, "弃书概率": "2%", "verdict": "追读", "feedback": "..."},
      {"name": "碎片党·地铁客", "追读意愿": 8, "弃书概率": "15%", "verdict": "追读", "feedback": "..."},
      {"name": "老书虫·毒舌", "追读意愿": 9, "弃书概率": "8%", "verdict": "追读", "feedback": "..."}
    ]
  },

  "rework_instructions": {
    "needed": false,
    "reason": "",
    "target_agents": [],
    "priority_fixes": []
  },

  "summary": "统一审核结论：通过/退回。unified_score=X.XX（阈值9.5）。..."
}
```

---

## 评分计算公式

### 技术分（technical_score）

```
technical_score = Σ(technical_dimensions[i].score × technical_dimensions[i].original_weight)
                = Σ(technical_dimensions[i].weighted / 0.6)
```

注：technical_score 使用原始权重计算（8维权重和=1.0），与 quality-reviewer v1.8 完全一致。

### 补充分（supplementary_score）

```
supplementary_score = Σ(supplementary_dimensions[i].score × supplementary_dimensions[i].original_weight)
                    = Σ(supplementary_dimensions[i].weighted / 0.4)
```

注：supplementary_score 使用原始权重计算（4维权重和=1.0），与 final-reviewer v1.1 完全一致。

### 统一分（unified_score）

```
unified_score = technical_score × 0.6 + supplementary_score × 0.4
```

这与 final-reviewer v1.1 的 `final_score = quality_technical_score × 0.6 + supplementary_score × 0.4` 完全等价。

### 等价性验证

以 Ch12 为例：
- technical_score = 9.42（与 quality_review_ch012.json 一致）
- supplementary_score = 9.64（与 final_review_ch012.json 一致）
- unified_score = 9.42 × 0.6 + 9.64 × 0.4 = 5.652 + 3.856 = 9.508 ≈ 9.51 ✓

---

## 监控检测项（继承自 quality-reviewer v1.7+v1.6）

### v1.7 配比监控（4项）

| 检测项 | 数据源 | 规则 | 违反后果 |
|--------|--------|------|---------|
| shuang_type_check | chapter shuang_type标注 | reveal不计入爽点数量 | shuang_density≤8.5 |
| three_chapter_rolling | goal_tracker.json | 任意连续3章含≥1个S/A级爽点 | 标记high |
| suspense_throttle | goal_tracker.json | active悬念≤3 | hook≤8.0 |
| goal_stall_check | goal_tracker.json | chapters_since_progress<4 | 标记high |

### v1.6 铺垫单元保护（3项）

| 检测项 | 规则 |
|--------|------|
| consecutive_padawan | 连续铺垫章≤2 |
| small_payoff | 每章有小兑现 |
| expectation_anchor | 有期待锚 |

---

## 交叉终检（继承自 final-reviewer v1.1）

| 终检项 | 说明 |
|--------|------|
| dialogue_consistency | 对话自洽性终检 |
| terminology_consistency | 术语一致性终检 |
| cross_chapter_continuity | 跨章连续性终检 |
| foreshadowing_status | 伏笔状态终检 |

---

## task_config 配置示例

### 传统2步模式（向后兼容）

```json
[
  {
    "id": 4, "name": "Ch{N}质量审核", "agent": "quality-reviewer",
    "depends_on": [3], "parallel_group": null,
    "output_files": ["handoff/chapters/quality_review_ch{N}.json"]
  },
  {
    "id": 5, "name": "Ch{N}终审", "agent": "final-reviewer",
    "depends_on": [4], "parallel_group": null,
    "output_files": ["handoff/chapters/final_review_ch{N}.json"]
  }
]
```

### 统一审核模式（加速）

```json
[
  {
    "id": 4, "name": "Ch{N}统一审稿", "agent": "quality-reviewer",
    "instruction": "以统一审核模式(unified_review)评审第{N}章。读取 auto-runner/unified_review_spec.md 了解12维评分规范。同时执行8维技术评分+4维补充评分+监控检测+交叉终检，一步产出unified_review_ch{N}.json。unified_score=technical_score×0.6+supplementary_score×0.4，≥9.5为approved。",
    "depends_on": [3], "parallel_group": null,
    "input_files": [
      "output/chapter_{NNN}.txt",
      "output/chapter_{NNN-1}.txt",
      "memory/outline.json",
      "memory/characters.json",
      "memory/goal_tracker.json",
      "memory/foreshadowing_tracker.json",
      "config/novel_config.json",
      "handoff/chapters/merged_review_ch{NNN}.json",
      "auto-runner/unified_review_spec.md"
    ],
    "output_files": ["handoff/chapters/unified_review_ch{NNN}.json"],
    "pass_criteria": "输出文件含12维评分+unified_score+verdict，unified_score≥9.5为approved",
    "max_retries": 3
  }
]
```

**步骤节省**：2步→1步（-1步/章）
**文件节省**：2文件→1文件（-1文件/章）
**300章规模节省**：300步 + 300文件 + ~6MB

---

## 质量门禁自动重试规则

| 未通过次数 | 处理方式 |
|-----------|---------|
| 第1次 unified_score < 9.5 | 自动退回 chapter-writer 修订，附上unified_review反馈 |
| 第2次 unified_score < 9.5 | 自动退回 detail-reviewer 精修，附上unified_review反馈 |
| 第3次 unified_score < 9.5 | 停止执行，记录 stop_reason: "质量门禁3次未通过" |

---

## 与并行框架的集成

### 模式7（单章审核内部并行）+ 统一审核

```
detail-reviewer ─┐
                 ├─→ unified_reviewer → memory-manager
de-ai-processor ─┘
```

对比传统流程：
```
detail-reviewer ─┐
                 ├─→ quality-reviewer → final-reviewer → memory-manager
de-ai-processor ─┘
```

**并行组内步骤数**：4步→3步（-1步）
**流水线模式效率提升**：Ch(N)统一审稿 ∥ Ch(N+1)写作 的上下文消耗降低

### 模式8（流水线写作审核）+ 统一审核

```
Ch(N) unified_review ─┐
                      ├─→ Ch(N) memory-manager → Ch(N+1) unified_review ...
Ch(N+1) writing ──────┘
```

统一审核减少了流水线中审核侧的步骤数，使流水线等待时间缩短。
