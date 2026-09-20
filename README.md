# AI 写作团队 — 番茄小说多智能体协作系统

## 项目简介

基于 TRAE Work 的多智能体小说创作系统，通过 18 个专业化 Agent（Skill）协作，完成从选题预筛、大纲构思、角色设计到章节写作、多层审核、去AI化、平台适配、记忆入库的全流程，面向**番茄小说**平台发布。

> **权威文档**：项目完整上下文见 [AGENTS.md](AGENTS.md)，流程协议见 [auto-runner/master_instruction.md](auto-runner/master_instruction.md)。本 README 只提供入口导航。

## Agent 角色（18 个 Skill）

### 初始化阶段

| Agent | Skill | 职责 |
|-------|-------|------|
| 选题筛子 | topic-screener | 选题6维度预筛（题材耐久度/爽感路径/认知门槛/失败模式匹配等） |
| 大纲师 | plot-architect | 故事大纲、情节线、爽点分布 |
| 书名审核 | title-reviewer | 书名6维 + 简介5维审核 |
| 质疑者 | skeptic | 大纲批判性质疑与迭代优化 |
| 大纲编辑 | outline-editor | 大纲/角色卡6维度评分验收 |
| 设定审核员 | setting-reviewer | 世界观设定6维度评分（地图/图鉴/机制） |
| 角色师 | character-designer | 人物设定、关系网、成长弧线 |
| 命名专家 | keyword-expert | 术语命名与全局巡检 |

### 章节循环

| Agent | Skill | 职责 |
|-------|-------|------|
| 写手 | chapter-writer | 章节正文生成（v4.0，11 条硬约束 H1-H11 + 倾向库） |
| 细节控 | detail-reviewer | 逐句/逐梗/逐伏笔/逐逻辑微观审核（出建议不改文本） |
| 去AI化师 | de-ai-processor | 消除 AI 写作痕迹（分析模式/完整模式） |
| 审稿员 | quality-reviewer | 8维技术分 + 6读者画像评审（含 `unified_score`） |
| 适配师 | fanqie-adapter | 爽点注入、节奏调整、平台合规 |
| 终端裁决 | final-reviewer | 发布前终审（4 补充维度 + 弃书风险扫描） |
| 记忆管家 | memory-manager | 分级存储、摘要、滑动窗口、全局全文重建（**硬门禁**） |
| 长线守护 | longline-guardian | 每 10 章及卷末全局审查 |

### 支撑角色

| Agent | Skill | 职责 |
|-------|-------|------|
| 总编 | chief-editor | 全局编排、任务分发、门禁校验、进度管理（**入口角色**） |
| 人工检查点 | human-checkpoint | 关键节点人工审核（黄金三章/卷宗高潮/伏笔全揭） |

### 文风包

| 资源 | Skill | 说明 |
|------|-------|------|
| 作者文风包 | writer-styles | 8 位作者文风（三件套：style_card + fingerprint + lint_overlay） |

## 目录结构

```
write-assistant/
├── .trae/skills/     # ★ Agent Skill 定义（18 个，系统核心逻辑）
├── config/           # novel_config.json（小说全局配置）、meme_library.json
├── memory/           # ★ 记忆系统（L0-L5 分级存储，唯一事实源）
├── handoff/          # ★ 交接卡（Agent 间通信的唯一信道）
├── output/           # 章节终稿 + 全文合并文件
├── auto-runner/      # 无人值守执行器基建（当前未启用，见 AGENTS.md）
├── logs/             # writing_log.jsonl 写作日志
├── learning/         # 学习子系统：阅文作家专栏 → Skill 优化提案
├── archive/          # 已归档项目
├── review/           # 第三方评审意见（人物形象/情感/故事情节）
├── docs/             # 文风蒸馏方法论文档
└── *.py              # 门禁脚本（见下）
```

## 质量门禁

**提交前置**（写手产出后、进评审前，总编校验，任一不满足直接拒收）：

```bash
python style_lint.py output/chapter_001.txt --style tiancantudou --config lint_config.json
python style_fingerprint.py check output/chapter_001.txt --baseline .trae/skills/writer-styles/tiancantudou/fingerprint.json
```

**入库门禁**：问题清单制 —— `issue_counts.critical == 0` 且无一票否决，即放行；分数仅作趋势数据。

> 历史口径提示：v3.0 起已废止「八维均分≥9.5」门禁（LLM 自评分数通胀无区分度）。设定/大纲审核仍保留分数门槛，属有意差异，见对应 SKILL。

配套脚本：

| 脚本 | 用途 |
|------|------|
| `style_lint.py` | 文风硬约束校验（L0 反AI红线阻断 / L1 顾问项 + 篇幅硬检） |
| `style_fingerprint.py` | 文体指纹基线构建（build）与偏差校验（check / selfcheck） |
| `fix_auditor.py` | lint 修复差异证据卡（只产证据不判定） |
| `style_pack_check.py` | 风格包入库验收清单 |
| `style_signature.py` | 作者签名手法自动提取（N-gram 交叉对比） |
| `style_trend.py` | 风格偏差趋势分析（读 style_deviation_log.jsonl） |
| `serve.py` | dashboard 静态服务器（正确声明 UTF-8 Content-Type） |

## 作者文风包（writer-styles）

已收录 8 位作者：`yanyujiangnan`（烟雨江南）、`chendong`（辰东）、`jiangnan`、`jinhezai`、`maibao`、`wuzei`、`tiancantudou`（天蚕土豆）、`wochixihongshi`（我吃西红柿）。

每包三件套：`style_card.md`（决策卡，每章注入）+ `fingerprint.json`（文体指纹基线）+ `lint_overlay.json`（lint 覆盖层）。

挂载方式：`config/novel_config.json` 设 `"style_pack": "<名称>"`，一本书只挂一个包。详见 [.trae/skills/writer-styles/README.md](.trae/skills/writer-styles/README.md)。

**原作语料**（226MB+）不在仓库内，存放于 `d:\personFile\corpus\writer-styles\<作者名>\原作[_utf8]\`。

## 工作流程

**初始化**（16 步，详见 chief-editor SKILL）：

```
读配置 → topic-screener → plot-architect → title-reviewer → skeptic（多轮）
→ outline-editor → human-checkpoint → character-designer → outline-editor（角色卡）
→ human-checkpoint → 设定三件套 → setting-reviewer（循环至≥9.5）→ human-checkpoint → chapter_loop
```

**章节循环**（每章闭环）：

```
并行写作评估 → chapter-writer
→ 【提交前置门禁】lint L0 退出码0 + 篇幅 advisory 清零 + 指纹通过 + 字段齐备
→ 审核并行：detail-reviewer ∥ de-ai分析模式 → 合并（merged_review）
→ quality-reviewer → critical 清零?
→ de-ai完整模式 → fanqie-adapter → final-reviewer（终审裁决）
→ 【入库门禁】critical=0 + 无high风险 + 无一票否决 + quality_review 卡存在
→ memory-manager（先完成记忆入库，才可开写下一章）
→ 真人读者随口反馈（沉默 = [AUTO-APPROVED]）→ 命中检查点则 human-checkpoint
```

## 使用方式

1. 编辑 `config/novel_config.json` 设置小说参数（书名/类型/卷章规划/日更目标/风格包）
2. 对话中输入"开始写第 N 章"触发写作流程，或说"继续/接着写"恢复上下文
3. 查看进度面板：`python serve.py 8000` → 访问 `http://localhost:8000/dashboard.html`

## 定时任务（Auto-Runner，当前未启用）

- 日更写作 09:00 / 进度检查 08:00 / 周度复盘 周日 10:00

> 该子系统依赖 `auto-runner/state.json` 与 `task_config.json`，当前仓库中这两个文件不存在，表示**未启用**。启用前需先跑 `generate_task_config.ps1`。