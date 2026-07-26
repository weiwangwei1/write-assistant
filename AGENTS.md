# AGENTS.md — AI 写作团队（write-assistant）

> 本文件面向 AI 编码/写作代理，提供项目的完整上下文。项目全部文档与注释以中文为主，规则文件请沿用中文编写。

## 一、项目概述

这不是一个传统软件项目，而是一套**多智能体网文创作系统**：通过多个专业化 LLM Agent（Skill）协作，完成从大纲构思、角色设计到章节写作、审核、发布的全流程，目标平台为**番茄小说（fanqie）**。当前在产作品为《有龙则灵》（玄幻/民俗悬疑/轻松，规划 330 章 / 6 卷，见 `config/novel_config.json`）。

系统的"代码"主要是三类：

1. **Skill 提示词工程**（`.trae/skills/*/SKILL.md`）——每个 Agent 的角色定义、输入输出契约、工作规则，是系统的核心逻辑；
2. **可执行脚本**——Python（风格校验门禁）与 PowerShell（自动运行器基建）；
3. **状态/数据文件**（JSON/JSONL/Markdown）——Agent 之间不共享对话记忆，全部通过文件交接。

运行环境为 Windows + TRAE IDE（Agent 在 IDE 中被调起），脚本经由 Git Bash 或 PowerShell 执行。仓库无 `package.json`/`pyproject.toml` 等构建配置，Python 脚本仅依赖标准库。

## 二、目录结构与模块划分

```
write-assistant/
├── .trae/skills/          # ★ Agent Skill 定义（18 个，系统核心逻辑所在）
│   ├── chief-editor/          # 总编：全局编排、任务分发、进度管理（入口角色）
│   ├── plot-architect/        # 大纲师：故事大纲、情节线、爽点分布
│   ├── skeptic/               # 质疑者：大纲批判性质疑
│   ├── outline-editor/        # 大纲编辑：6 维度评分验收
│   ├── setting-reviewer/      # 设定审核员：世界观 6 维评分
│   ├── character-designer/    # 角色师：人物设定、关系网、成长弧线
│   ├── chapter-writer/        # 写手：章节正文生成（v3.0 瘦身版，10 条硬约束）
│   ├── detail-reviewer/       # 细节控：逐句/逐伏笔微观打磨
│   ├── quality-reviewer/      # 审稿员：宏观质量评分
│   ├── de-ai-processor/       # 去AI化师：消除 AI 写作痕迹
│   ├── fanqie-adapter/        # 适配师：番茄平台爽点/节奏/合规适配
│   ├── final-reviewer/        # 终审员：发布前终裁
│   ├── memory-manager/        # 记忆管家：分级存储、摘要、滑动窗口（强制步骤）
│   ├── longline-guardian/     # 长线守护：每 10 章及卷末全局审查
│   ├── keyword-expert/        # 命名专家：术语命名与巡检
│   ├── title-reviewer/        # 标题/简介审核
│   ├── topic-screener/        # 选题筛查
│   ├── human-checkpoint/      # 人工检查点
│   └── writer-styles/         # 作者文风包（见下文"文风包"）
├── skills/                # 同名空目录（历史遗留占位，非 Skill 源，勿在此新增内容）
├── auto-runner/           # 无人值守自动执行器（Auto-Runner）
│   ├── master_instruction.md      # 自动执行代理指令 v3.0（运行协议主文档）
│   ├── task_config.json           # 步骤序列与并行组配置（由 generate_task_config.ps1 生成）
│   ├── state.json                 # 运行状态（current_step / parallel_groups / steps[]）
│   ├── execution_log.md           # 追加式执行日志（>50KB 自动轮转）
│   ├── context_preloader.ps1      # Skill 缓存预加载（生成 context_cache.json）
│   ├── fast_io.ps1                # .NET 文件 I/O 加速函数库（dot-source 加载）
│   ├── state_validator.ps1        # 状态一致性校验/归档
│   ├── generate_task_config.ps1   # 任务配置生成（滚动 2 章）
│   ├── unified_review_spec.md     # 统一审核规范 v2.0（12 维评分 + 问题清单制）
│   └── *.md                       # 并行执行/上下文优化/文件 I/O 优化等设计文档
├── config/
│   ├── novel_config.json      # ★ 小说全局配置（书名/卷章规划/核心设定/风格包/生产计划）
│   └── meme_library.json      # 梗库
├── memory/                # ★ 记忆系统（L0-L5 分级存储，memory-manager 维护）
│   ├── session_pointer.json       # 会话指针：当前章节/角色快照/里程碑（开局必读）
│   ├── setting_bible.json         # 设定圣经：时间线/世界观的唯一事实源
│   ├── outline.json               # 章节大纲（含 beat sheet）
│   ├── characters.json            # 角色索引（指针），独立角色卡在 characters/*.json
│   ├── goal_tracker.json          # 目标/悬念窗口/反派梯子追踪
│   ├── foreshadowing_tracker.json # 伏笔追踪
│   ├── chapter_summaries/         # 每章结构化摘要
│   ├── recent_chapters/           # 滑动窗口（按需从 output/ 读取，不维护副本）
│   ├── volume_summaries/ consistency_check/ longline_review/
│   └── decision_log.jsonl         # 决策日志
├── handoff/               # ★ 交接卡（Agent 间通信的唯一信道，JSON 卡片）
│   ├── chapters/                  # 各章审核产物（draft/review/merged/unified）
│   ├── archive/ch{N}/             # 已合并的中间审核文件归档
│   └── setup/                     # 初始化阶段交接卡
├── output/                # 章节终稿（chapter_NNN.txt）+ 全文合并文件
├── logs/writing_log.jsonl # 写作日志
├── learning/              # 学习子系统：持续学习阅文作家专栏，产出 Skill 优化提案
│   └── learning_workflow.md       # 学习工作流说明（选文→提取→对比→提案→用户决策）
├── archive/               # 已完成/废弃的项目批次归档
├── docs/style-distillation/  # 文风自主蒸馏方法论文档（HTML）
├── third/ 作家分享.txt 第三方评价.txt  # 外部评审/资料
├── *.html                 # 各类可视化报告（大纲/读者/执行仪表盘等）
├── style_lint.py          # ★ 文风硬约束校验器（提交前门禁）
└── style_fingerprint.py   # ★ 文体指纹提取与偏差校验（v2.0：章际分布/派生容差/selfcheck）
└── style_pack_check.py    # ★ 风格包入库验收清单（三件套+模板合规）
```

## 三、技术栈与运行架构

- **语言/工具**：Python 3（仅标准库，实测 3.14 可用）；PowerShell（`powershell -ExecutionPolicy Bypass -File ...`）；无 npm/pip 依赖、无构建步骤。
- **Agent 编排**：Skill 以 Markdown frontmatter（`name`/`version`/`description`）定义，由 TRAE IDE 按描述匹配调起；`chief-editor` 是调度中枢。
- **Agent 间通信**：**交接卡（handoff card）**——JSON 文件，含 `card_type`/`from_agent`/`to_agent`/`status`/`content` 字段。正文永远用 `draft_ref` 引用文件路径，不内嵌 JSON。
- **Auto-Runner 模式**：定时触发的无人值守执行。每次触发读取 `state.json` → 执行 `task_config.json` 中的步骤 → 每步完成立即同步 state（State 同步协议 v2.1）→ 满足退出条件即退。支持并行组（最多 5 个并行 Agent）与流水线模式（Ch(N) 审核与 Ch(N+1) 写作并行）。会话启动时执行 State 恢复（验证 output_files 存在性）与 context 缓存检查。
- **质量门禁（按执行顺序）**：
  1. `style_lint.py` 退出码 0（chapter-writer 提交前置条件；v2.3 起仅 L0 通用反AI红线阻断，L1 降为顾问项由 detail-reviewer 逐条回应）；含 **篇幅硬检**（v2.4 `chapter_length` 规则，书籍级标准经 `--config` 注入，如 `newbook2/lint_config.json`，advisory 提交前必须清零；原则：**宁删勿补**——初稿写长，修订只删不补）；若经历 lint 修复轮次，`fix_auditor.py` 生成修复差异证据卡（只产证据不判定）；
  2. detail-reviewer 微观打磨 + de-ai-processor 去 AI 化（可并行）；
  3. unified_review 统一审核：v3.0 起为**问题清单制**——critical 清零即通过，分数（`unified_score = technical×0.6 + supplementary×0.4`）仅作参考，不再以 ≥9.5 为门禁；
  4. `style_fingerprint.py check`（挂载风格包且基线非 pending 时）；
  5. 质量门禁 3 次未通过则停止执行并记录 `stop_reason`。

  **评审不可跳过（v2.4 新增）**：lint + 指纹双门禁只是**提交前置**，不构成入库。正式入库的每章必须有独立 quality_review 评审卡（由未参与写作的 Agent/子代理按 quality-reviewer rubric 产出，critical 清零）。《万纹师》黄金三章曾因走"轻量流程"漏掉评审，被用户追问后补评并查出 4 个 major——此为本条的数据教训。

## 四、常用命令

```bash
# 文风硬约束校验（写手提交前必须退出码 0；1=存在 critical，2=用法/文件错误）
python style_lint.py output/chapter_001.txt --json handoff/style_lint_ch1.json
python style_lint.py output/ --style yanyujiangnan        # 目录模式含跨章检查，加载风格包覆盖层

# 修复差异证据（lint 修复后、detail 审核前；只产证据不判定，退出码恒 0）
python fix_auditor.py handoff/pre_lint_ch15.txt output/chapter_015.txt --json handoff/fix_audit_ch15.json

# 文体指纹：从原作建基线 / 校验章节偏差（退出码 0=通过 1=超阈 2=基线不可用）
python style_fingerprint.py build 原作1.txt 原作2.txt --author 作者名 --exclude-names 主角名 --out fingerprint.json
python style_fingerprint.py check chapter_013.txt --baseline fingerprint.json --json check.json
python style_fingerprint.py selfcheck --baseline fingerprint.json   # 容差健康度：原作章节应高比例通过
python style_pack_check.py --all                                    # 风格包入库验收清单（FAIL 禁止入库）

# Auto-Runner 基建（PowerShell）
powershell -ExecutionPolicy Bypass -File auto-runner/context_preloader.ps1   # 重建 Skill 缓存
powershell -ExecutionPolicy Bypass -File auto-runner/generate_task_config.ps1 # 滚动生成任务配置
```

触发写作流程的方式：在对话中输入"开始写第 N 章"，或等待定时任务（日更 09:00 / 进度检查 08:00 / 周复盘 周日 10:00）。

## 五、测试与验证策略

项目无单元测试框架。"测试"即**校验脚本 + 门禁退出码 + 评审交接卡**：

- **修改 `style_lint.py` / `style_fingerprint.py` 后**：对 `output/` 现有章节运行，确认退出码与报告符合预期（注意：对已定稿旧章报 critical 属预期——框架升级不追溯，见下）；
- **修改 Skill 或流程后**：运行 `auto-runner/state_validator.ps1` 检查状态一致性；变更需在 `master_instruction.md` 记录版本变更摘要；
- **E2E 验证记录**见 `auto-runner/e2e_test_report.md` 与 `handoff/process_record_ch1-10.md`（历史实战记录，可作为回归参照）。

## 六、开发约定（重要）

1. **能写成脚本的规则，不写成提示词**。提示词规则执行率不可靠；硬约束必须可机器校验且 ≤10 条。chapter-writer v3.0 即按此原则从 73KB 全文瘦身为 10 条硬约束 + 倾向库（旧全文在 `reference/chapter-writer-v2.5-full.md`）。
2. **框架升级不追溯重写**。新规则只适用于新章节；已定稿章节仅在卷末复盘窗口统一润色（黄金三章一次性回炉属例外）。因此 lint 对旧章报错**不等于**需要改旧章。
3. **版本与变更记录**：每次框架/Skill 升级，在 `auto-runner/master_instruction.md` 或对应 SKILL.md 的 frontmatter `description` 中记录变更摘要；旧规则标注"已由 vX.X 替代"而非删除。
4. **交接卡契约**：Agent 产出必须包含约定字段（如 chapter_draft 卡的 `beat_sheet.cross_chapter_facts`/`shuang_type`/`suspense_budget_check`）；缺字段总编直接拒收，不进评审。
5. **memory-manager 是硬门禁**：终审通过后必须先完成记忆入库（更新 session_pointer/chapter_summaries/goal_tracker 等），才允许开写下一章。Ch4–10 曾因跳账导致跨章事实硬伤，此为数据教训。
6. **设定圣经唯一事实源**：年份/干支/时长/专名必须与 `memory/setting_bible.json` 逐条一致；lint 输出的 `timeline_clues` 须逐条确认。注意区分"庚午大祭"（60 年前）与"许慎独案"（20 年前）。
7. **优先级仲裁**：lint 硬约束 > 风格覆盖层 > 决策卡倾向；爽点需求不得以牺牲文风红线为代价。
8. **文件 I/O 约定**（Auto-Runner 内）：优先使用 `fast_io.ps1` 的加速函数替代原生 cmdlet；`characters.json` 只存索引指针；`recent_chapters` 按需从 `output/` 读取；全文文件 header 与正文分离、正文纯追加。
9. **状态安全**：state.json 每步完成立即写入；标记 completed 前必须验证 output_files 全部存在且非空。
10. **语言与编码**：交接卡、记忆文件、报告用中文，JSON 一律 `ensure_ascii=False` + UTF-8；章节正文不得使用 Markdown 标记。

## 七、文风包（writer-styles）

`.trae/skills/writer-styles/` 收录蒸馏的作者文风，每包三件套：`style_card.md`（决策卡，每章注入写手）+ `fingerprint.json`（指纹基线）+ `lint_overlay.json`（lint 阈值覆盖/签名手法豁免/专属违禁词）。已收录 6 位作者：`yanyujiangnan`（烟雨江南，当前挂载）、`chendong`、`jiangnan`、`jinhezai`、`maibao`、`wuzei`，指纹基线均为 v2.0 口径 ready。挂载方式：`config/novel_config.json` 设 `"style_pack": "<名称>"`，一本书只挂一个包。覆盖层只能调阈值与豁免签名手法，**不能关闭通用反 AI 红线**。蒸馏新作者的四阶段流程、style_card 模板与入库验收见该目录 `README.md` 与 `docs/style-distillation/`。指纹口径 v2.0（2026-07-26 重建）：分句只按句末标点、破折号去重计数（数值约为 v1 的 1/3）、对话占比按引号内字数（低于 v1 口径）、容差由章际波动推导；校验判读：1-2 个轻微超阈≈正常章际波动，≥3 个超阈才需修。

## 八、安全与合规注意事项

- **平台合规**：终稿须经 fanqie-adapter 敏感词过滤与审核合规处理后方可发布；`config/novel_config.json` 的 `topic_screening.core_commitments` 是内容红线（如势力仅三家、前 30 章新造专名 ≤5 个等），不可擅自突破。
- **无密钥/无外发**：仓库不含凭证；系统所有状态为本地文件。脚本不联网（learning 子系统的 WebFetch 由 Agent 在对话中执行，非脚本行为）。
- **指纹基线必须用原作**：`style_fingerprint.py build` 禁止用蒸馏产物或 AI 文本充当原作样本，否则基线失真。
- **自动模式的人工检查点**：Auto-Runner 遇 human-checkpoint 步骤自动通过并标注 `[AUTO-APPROVED]`，需人工复核日志。
- 修改记忆文件（`memory/`）前注意它们是多个 Agent 的共享事实源——保持 schema 与既有字段命名一致，勿随意重构结构。

## 九、当前进度快照

以 `memory/session_pointer.json` 为准（开局必读）：截至最近更新，《有龙则灵》处于 chapter_loop 阶段，卷一，已完成 14 章，下一章为第 15 章。注意 `novel_config.json`（total_chapters=330、outline_version=v4.1）与 session_pointer（total_chapters=300、outline_version=v4.3 定稿）存在口径差异——**session_pointer 为运行时事实源，config 为立项配置**；涉及总数/版本判断时以 session_pointer 为准并可向用户确认。

**其他项目状态**：《献祭纪元：赊刀人》已放弃归档（`archive/newbook_献祭纪元_放弃_20260726/`）；《万纹师》为当前在产新书（`newbook2/`，天赋流铸纹师、无系统金手指、热血+悬念、chendong 文风包，420 章 6 卷大纲，9 张角色卡，黄金三章已入库且经 quality_review 复评修复），篇幅标准 2600-3200 字/章（lint 命令须带 `--config newbook2/lint_config.json`），下一章为第 4 章（糖葫芦单元 2：修复断纹罗盘）。
