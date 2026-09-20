# AGENTS.md — AI 写作团队（write-assistant）

> 本文件面向 AI 编码/写作代理，提供项目的完整上下文。项目全部文档与注释以中文为主，规则文件请沿用中文编写。

## 一、项目概述

这不是一个传统软件项目，而是一套**多智能体网文创作系统**：通过多个专业化 LLM Agent（Skill）协作，完成从选题预筛、大纲构思、角色设计到章节写作、多层审核、去AI化、平台适配、记忆入库的全流程，目标平台为**番茄小说（fanqie）**。**当前在产项目：《第三纪元》**（2026-09-20 重启：旧稿 Ch1-7 已完整归档至 `archive/第三纪元_重启_20260920/`，保留大纲/世界观/角色设定，从序言+Ch1 重写；位面入侵·献祭流·智斗，tiancantudou 文风包，300 章 / 6 卷，详见第九节）。此前《请客》《征诏之界》《镜渊》《万纹师》《有龙则灵》《补天人》《献祭纪元：赊刀人》《临渊》《玩家请就位》均已放弃或归档至 `archive/`。

系统的"代码"主要是三类：

1. **Skill 提示词工程**（`.trae/skills/*/SKILL.md`）——每个 Agent 的角色定义、输入输出契约、工作规则，是系统的核心逻辑；
2. **可执行脚本**——Python（风格校验门禁）与 PowerShell（自动运行器基建）；
3. **状态/数据文件**（JSON/JSONL/Markdown）——Agent 之间不共享对话记忆，全部通过文件交接。

运行环境为 Windows + TRAE IDE（Agent 在 IDE 中被调起），脚本经由 Git Bash 或 PowerShell 执行。仓库无 `package.json`/`pyproject.toml` 等构建配置，Python 脚本仅依赖标准库。

## 二、目录结构与模块划分

```
write-assistant/
├── .trae/skills/          # ★ Agent Skill 定义（18 个，系统核心逻辑所在）
│   ├── chief-editor/          # 总编：全局编排、任务分发、门禁校验、进度管理（入口角色）
│   ├── topic-screener/        # 选题筛子：选题6维度预筛
│   ├── plot-architect/        # 大纲师：故事大纲、情节线、爽点分布
│   ├── title-reviewer/        # 书名/简介审核
│   ├── skeptic/               # 质疑者：大纲批判性质疑
│   ├── outline-editor/        # 大纲编辑：6 维度评分验收（兼角色卡审核）
│   ├── setting-reviewer/      # 设定审核员：世界观 6 维评分
│   ├── character-designer/    # 角色师：人物设定、关系网、成长弧线
│   ├── keyword-expert/        # 命名专家：术语命名与巡检
│   ├── chapter-writer/        # 写手：章节正文生成（v4.3，H1-H11 + 倾向库；5.9 技法按 A-E 组 24 条 + 黄金三章开篇量化）
│   ├── detail-reviewer/       # 细节控：逐句/逐伏笔微观审核（v1.21，第11层 18 项 + 黄金三章开篇量化附节，ID 与写手对应）
│   ├── de-ai-processor/       # 去AI化师：消除 AI 写作痕迹（分析/完整模式）
│   ├── quality-reviewer/      # 审稿员：8维技术分 + 6读者画像
│   ├── fanqie-adapter/        # 适配师：番茄平台爽点/节奏/合规适配
│   ├── final-reviewer/        # 终审员：发布前终裁
│   ├── memory-manager/        # 记忆管家：分级存储、摘要、滑动窗口（强制步骤）
│   ├── longline-guardian/     # 长线守护：每 10 章及卷末全局审查
│   ├── human-checkpoint/      # 人工检查点
│   └── writer-styles/         # 作者文风包（见下文"文风包"）
├── auto-runner/           # 无人值守自动执行器（Auto-Runner）基建
│   ├── master_instruction.md      # 自动执行代理指令 v4.0（运行协议主文档）
│   ├── task_config.json           # 步骤序列与并行组配置（由 generate_task_config.ps1 生成）
│   ├── state.json                 # 运行状态（current_step / parallel_groups / steps[]）
│   ├── execution_log.md           # 追加式执行日志（>50KB 自动轮转）
│   ├── context_preloader.ps1      # Skill 缓存预加载（生成 context_cache.json）
│   ├── fast_io.ps1                # .NET 文件 I/O 加速函数库（dot-source 加载）
│   ├── state_validator.ps1        # 状态一致性校验/归档
│   ├── generate_task_config.ps1   # 任务配置生成（滚动 2 章）
│   ├── unified_review_spec.md     # 统一审核规范 v2.1（12 维评分 + 问题清单制）
│   └── *.md                       # 并行执行/上下文优化/文件 I/O 优化等设计文档
│   ⚠️ 当前 state.json / task_config.json / context_cache.json 均不存在 = 未启用。
│      本节其余描述为"启用后"的协议，勿据此以为自动运行已在工作。
├── config/
│   ├── novel_config.json      # ★ 小说全局配置（书名/卷章规划/核心设定/风格包/生产计划）
│   └── meme_library.json      # 梗库
├── memory/                # ★ 记忆系统（L0-L5 分级存储，memory-manager 维护）
│   ├── session_pointer.json       # 会话指针：当前章节/角色快照/里程碑（开局必读）
│   ├── setting_bible.json         # 设定圣经：时间线/世界观的唯一事实源
│   ├── outline.json               # 章节大纲（含 beat sheet）
│   ├── world_setting.json         # 世界设定（地域/势力/关键地点/披露计划）
│   ├── ability_system.json        # 能力体系（分类/等级/获取/限制）
│   ├── conflict_rules.json        # 冲突规则（核心矛盾/势力对抗/隐藏机制）
│   ├── characters.json            # 角色索引（指针），独立角色卡在 characters/*.json
│   ├── goal_tracker.json          # 目标/悬念窗口/反派梯子追踪
│   ├── foreshadowing_tracker.json # 伏笔追踪
│   ├── chapter_summaries/         # 每章结构化摘要
│   ├── recent_chapters/           # 滑动窗口（按需从 output/ 读取，不维护副本）
│   ├── volume_summaries/ consistency_check/ longline_review/
│   ├── style_deviation_log.jsonl  # 指纹偏差日志（style_fingerprint.py check 自动追加）
│   └── decision_log.jsonl         # 决策日志
├── handoff/               # ★ 交接卡（Agent 间通信的唯一信道，JSON 卡片，扁平存放）
│   ├── chapter_draft_{N}.json     # 写手草稿卡（beat_sheet/character_internal/style_plan）
│   ├── detail_review_{N}.json     # 细节控审核
│   ├── de_ai_analysis_{N}.json    # 去AI化分析模式
│   ├── merged_review_{N}.json     # 总编合并清单（含 fingerprint_override 裁定链）
│   ├── quality_review_{N}.json    # 审稿员（含 unified_score / issue_counts / veto_check）
│   ├── final_review_{N}.json      # 终审裁决（含 gate_mode / formula / issue_counts）
│   ├── style_lint_ch{N}.json      # lint 首次运行卡
│   ├── style_lint_ch{N}_final.json # lint 定稿卡（经历修订时才有）
│   ├── fp_check_ch{N}.json        # 指纹校验卡
│   ├── fix_audit_ch{N}.json       # lint 修复差异证据卡（经历修复轮次时才有）
│   ├── pre_lint_ch{N}.txt         # lint 修复前快照（fix_auditor 输入）
│   ├── archive/                    # handoff 占位归档（ch4-7 空目录 + 角色卡/设定首轮审核卡）；Ch1-3 精修证据 golden3_revisions 已随重启移至 archive/第三纪元_重启_20260920/handoff/
│   └── task_plan.json / topic_screening.json / setting_review.json / characters.json 等阶段卡
├── output/                # 章节终稿（chapter_{N:03d}.txt）+ 全文合并文件 + header
├── logs/writing_log.jsonl # 写作日志
├── learning/              # 学习子系统：持续学习阅文作家专栏，产出 Skill 优化提案
│   └── learning_workflow.md       # 学习工作流说明（选文→提取→对比→提案→用户决策）
├── archive/               # 项目批次归档（含 2026-09-20《第三纪元》重启归档：旧稿 Ch1-7 正文与全部过程产物）
├── review/                # 第三方评审意见（人物形象/情感/故事情节 → 驱动了 ch-writer v3.9~v4.0 技法）
├── refSkill/              # 番茄官方写作方法论参考库（精读版 74 篇/13 主题 35 万字 + 5 个合集；2026-09-20 入库，驱动 ch-writer v4.3 等 4 项升级）
├── docs/                  # 文档区
│   ├── style-distillation/        # 文风自主蒸馏方法论（HTML）
│   └── topic-notes/               # 选题过程记录（选题构思/选题推进 AB 细化，2026-08-02，孕育了《第三纪元》）
├── ref/ test/ tmp_golden3/ topic-evaluation/ novel-distillation/
├── style-distillation-summary/ zuiezhicheng-analysis/   # 实验区/参考资料（历史遗留）
├── *.html                 # 各类可视化报告：dashboard.html（进度面板，见第九节）、
│                          #   fusion-style-guide.html / writing-style-analysis.html（文风蒸馏分析）、
│                          #   罪恶之城世界观分析.html（《罪恶之城》文本分析，驱动 style_card v2.3 叙事引擎改造）
├── 作家分享.txt            # 外部资料：阅文作家经验分享（learning 子系统输入）
├── 第三方评价.txt          # 外部资料：第三方评审意见汇总
├── lint_config.json       # ★ 当前书籍的篇幅配置（--config 注入 style_lint）
├── style_lint.py          # ★ 文风硬约束校验器（提交前门禁，v2.5）
├── style_fingerprint.py   # ★ 文体指纹提取与偏差校验（v2.0：章际分布/派生容差/selfcheck）
├── fix_auditor.py         # ★ lint 修复差异证据卡（只产证据不判定）
├── style_pack_check.py    # ★ 风格包入库验收清单（三件套+模板合规）
├── style_signature.py     # 作者签名手法自动提取（N-gram 交叉对比；子命令 extract/compare/vocabulary）
├── style_trend.py         # 风格偏差趋势分析（读 memory/style_deviation_log.jsonl）
└── serve.py               # dashboard 静态服务器（正确声明 UTF-8 Content-Type）
```

> **不存在的旧路径**（若在本文件其他位置看到，属历史遗留）：`skills/`（空占位目录已删）、`handoff/chapters/`、`handoff/setup/`、`third/`——交接卡现为 **handoff/ 下扁平存放**。

### handoff 命名规范（2026-09-20 制定）

**规范形态**（Ch4 起已收敛执行，Ch1-3 为收敛前的多版本形态）：

| 产物 | 规范文件名 | 说明 |
|------|-----------|------|
| 写手草稿卡 | `chapter_draft_{N}.json` | 每章必有 |
| 细节控审核 | `detail_review_{N}.json` | 每章必有 |
| 去AI化分析 | `de_ai_analysis_{N}.json` | 每章必有 |
| 合并清单 | `merged_review_{N}.json` | 每章必有（含 override 裁定链） |
| 审稿卡 | `quality_review_{N}.json` | 每章必有（入库门禁验证项） |
| 终审卡 | `final_review_{N}.json` | 每章必有 |
| lint 卡 | `style_lint_ch{N}.json` | 首次运行；经历修订则加 `_final` |
| 指纹卡 | `fp_check_ch{N}.json` | 挂包时必有 |
| 修复证据 | `fix_audit_ch{N}.json` | **仅经历 lint 修复轮次时产生** |
| 修复前快照 | `pre_lint_ch{N}.txt` | 同上，与 fix_audit 成对 |

**三条规则**：
1. **禁止 `_v2`/`_v3`/`_v6b` 式版本后缀**——迭代版本应就地覆盖同名文件（`git` 已是版本控制，不需要在文件名里再叠一层）。确需留存某个关键中间态时，写进 `handoff/archive/`。
2. **章号一律用裸数字**（`_7.json` 而非 `_ch7.json`）；历史遗留的 `style_lint_ch{N}` / `fp_check_ch{N}` 保留 `ch` 前缀不再改动（300 章规模迁移成本高于收益，且已是既成约定）。
3. **中间审核产物不长期堆在顶层**——`detail_review` + `de_ai_analysis` 在 merge 完成后可移至 `handoff/archive/ch{N}/`（Auto-Runner 的 state_validator 会自动做；手动流程下由总编在章末整理）。

**已知遗留（2026-09-20 更新）**：`deai_fanqie_{4,5}.json`（早期"去AI化+适配"合并产物）与 Ch1-3 的 44 个多版本 lint/指纹文件均已随《第三纪元》重启归档——前者在 `archive/第三纪元_重启_20260920/handoff/`，后者在 `archive/第三纪元_重启_20260920/handoff/golden3_revisions/`（**保留不删**——黄金三章七轮精修的过程证据，对复盘有价值）。

## 三、技术栈与运行架构

- **语言/工具**：Python 3（仅标准库；本机实测 **3.13.0** 与 3.9.13 均可用，见下「Python 解释器」）；PowerShell（`powershell -ExecutionPolicy Bypass -File ...`）；无 npm/pip 依赖、无构建步骤。
  **Python 解释器**：本机 Python **不在 PATH**（`python` 命令报 CommandNotFound），需用全路径调用：`C:\Users\王伟\AppData\Local\Programs\Python\Python313\python.exe`。文档与 SKILL 中的 `python xxx.py` 命令均需替换为该全路径（或在 PATH 中补入 Python313 目录）。
- **Agent 编排**：Skill 以 Markdown frontmatter（`name`/`version`/`description`）定义，由 TRAE IDE 按描述匹配调起；`chief-editor` 是调度中枢。
- **Agent 间通信**：**交接卡（handoff card）**——JSON 文件，含 `card_type`/`from_agent`/`to_agent`/`status`/`content` 字段。正文永远用 `draft_ref` 引用文件路径，不内嵌 JSON。
- **Auto-Runner 模式（⚠️ 当前未启用）**：定时触发的无人值守执行。每次触发读取 `state.json` → 执行 `task_config.json` 中的步骤 → 每步完成立即同步 state（State 同步协议 v2.1）→ 满足退出条件即退。支持并行组（最多 5 个并行 Agent）与流水线模式（Ch(N) 审核与 Ch(N+1) 写作并行）。会话启动时执行 State 恢复（验证 output_files 存在性）与 context 缓存检查。
  **未启用证据**：`auto-runner/state.json`、`task_config.json`、`context_cache.json` 三个运行态文件在仓库中**均不存在**（`.gitignore` 未忽略它们）。以下关于 Auto-Runner 的描述均为"启用后"的协议说明，不代表当前工作方式；当前章节生产由用户在对话中驱动 chief-editor 完成。启用前需先运行 `generate_task_config.ps1` 生成配置。
- **质量门禁（按执行顺序）**：
  1. **提交前置门禁**（chapter-writer 产出后、进评审前，chief-editor 校验，任一不满足直接拒收）：
     - `style_lint.py` 退出码 0（v2.3 起仅 L0 通用反AI红线阻断，L1 降为顾问项由 detail-reviewer 逐条回应）
     - 含 **篇幅硬检**（v2.4 `chapter_length` 规则，书籍级标准经 `--config` 注入，当前书用根目录 `lint_config.json`；advisory 提交前必须清零；原则：**宁删勿补**——初稿写长，修订只删不补）
     - `style_fingerprint.py check` 通过（挂载风格包且基线非 pending 时）
     - 若经历 lint 修复轮次：`handoff/pre_lint_ch{N}.txt` 快照 + `fix_auditor.py` 产出的证据卡（只产证据不判定）
     - 交接卡结构字段齐备（`beat_sheet` / `cross_chapter_facts` / `shuang_type` / `suspense_budget_check` / `character_internal` / `style_plan`）
  2. detail-reviewer 微观审核 ∥ de-ai-processor 去 AI 化分析（并行，各出建议清单不改文本）→ chief-editor 合并为 `merged_review_{N}.json`；
  3. quality-reviewer 宏观评审（8维技术分 + 6读者画像），产出 `quality_review_{N}.json`；
  4. de-ai-processor 完整模式 + fanqie-adapter 平台适配；
  5. final-reviewer 终审裁决，产出 `final_review_{N}.json`；
  6. **入库门禁**（final-reviewer 返回 approved 后，chief-editor 校验）：`issue_counts.critical == 0` + `high_abandonment_risk == 0` + `veto_dimensions_below_8 == 0` + `quality_review_{N}.json` 存在。任一不满足不得调用 memory-manager；
  7. 质量门禁 3 次未通过则停止执行并记录 `stop_reason`。

  **通过门槛 = 问题清单制（v3.0，唯一口径）**：critical 清零即通过，分数（`unified_score = technical×0.6 + supplementary×0.4`）仅作参考趋势数据，**不再以 ≥9.5 为门禁**（LLM 自评分数通胀无区分度，实测 Ch4-7 落在 9.11–9.44）。例外：**初始化阶段的 setting-reviewer（设定）/ outline-editor（大纲）仍保留 ≥9.5 分数门槛**——一次性产物，高门槛边际成本低，属有意差异，两个 SKILL 内已注明理由。

  **评审不可跳过（v2.4 新增）**：lint + 指纹双门禁只是**提交前置**，不构成入库。正式入库的每章必须有独立 quality_review 评审卡（由未参与写作的 Agent/子代理按 quality-reviewer rubric 产出，critical 清零）。《万纹师》黄金三章曾因走"轻量流程"漏掉评审，被用户追问后补评（`wanwenshi/quality_review_golden3.json` 2026-07-26 17:30）查出 4 个 major——verdict="需修改"尚未清零，待修 major：①Ch3 第14行沈拓误称老铁匠"爹"（角色死穴专属称呼）②Ch3 章末"温到了天明"余韵收尾违反 chapter_end_hook_rule ③雷横角色卡"指针疯转"与正文"锈死"矛盾 ④Ch3"登记册六十年"无信息来源。此为本条的数据教训。

## 四、常用命令

```bash
# 文风硬约束校验（写手提交前必须退出码 0；1=存在 critical，2=用法/文件错误）
python style_lint.py output/chapter_001.txt --style tiancantudou --config lint_config.json --json handoff/style_lint_ch1.json
python style_lint.py output/ --style tiancantudou        # 目录模式含跨章检查，加载风格包覆盖层

# 修复差异证据（lint 修复后、detail 审核前；只产证据不判定，退出码恒 0）
python fix_auditor.py handoff/pre_lint_ch7.txt output/chapter_007.txt --json handoff/fix_audit_ch7.json

# 文体指纹：从原作建基线 / 校验章节偏差（退出码 0=通过 1=超阈 2=基线不可用）
# 原作语料已移出仓库，存放在 d:\personFile\corpus\writer-styles\<作者名>\原作[_utf8]\
python style_fingerprint.py build "d:\personFile\corpus\writer-styles\作者名\原作_utf8\原作1.txt" "d:\personFile\corpus\writer-styles\作者名\原作_utf8\原作2.txt" --author 作者名 --exclude-names 主角名 --out fingerprint.json
python style_fingerprint.py check output/chapter_007.txt --baseline .trae/skills/writer-styles/tiancantudou/fingerprint.json --json handoff/fp_check_ch7.json
python style_fingerprint.py selfcheck --baseline fingerprint.json   # 容差健康度：原作章节应高比例通过
python style_pack_check.py --all                                    # 风格包入库验收清单（FAIL 禁止入库）

# 文风分析辅助脚本
python style_signature.py --help        # 作者签名手法提取（N-gram 交叉对比）
python style_trend.py                   # 偏差趋势分析（读 memory/style_deviation_log.jsonl）

# 进度面板
python serve.py 8000                    # 访问 http://localhost:8000/dashboard.html

# Auto-Runner 基建（PowerShell，当前未启用）
powershell -ExecutionPolicy Bypass -File auto-runner/context_preloader.ps1   # 重建 Skill 缓存
powershell -ExecutionPolicy Bypass -File auto-runner/generate_task_config.ps1 # 滚动生成任务配置
```

**--config 注入约定**：当前书篇幅标准在仓库根目录 `lint_config.json`（《第三纪元》2400-2600）；历史书籍曾用 `<项目名>/lint_config.json`（如 `wanwenshi/lint_config.json`，已随项目归档）。新书立项时同步更新根目录 `lint_config.json`。

触发写作流程的方式：在对话中输入"开始写第 N 章"，或等待定时任务（日更 09:00 / 进度检查 08:00 / 周复盘 周日 10:00——**需先启用 Auto-Runner**）。

## 五、测试与验证策略

项目无单元测试框架。"测试"即**校验脚本 + 门禁退出码 + 评审交接卡**：

- **修改 `style_lint.py` / `style_fingerprint.py` 后**：对 `output/` 现有章节运行，确认退出码与报告符合预期（注意：对已定稿旧章报 critical 属预期——框架升级不追溯，见下）；**改动字数/口径统计函数时须额外自检**：`chapter_length` 与 `ch*_per_1000` 家族共用同一个字符计数分母，改动会同时影响 8 个风格包的千字率阈值校准（详见第九节「已知缺陷」）；
- **修改 Skill 或流程后**：运行 `auto-runner/state_validator.ps1` 检查状态一致性（⚠️ 需先启用 Auto-Runner）；变更需在 `master_instruction.md` 记录版本变更摘要；
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

`.trae/skills/writer-styles/` 收录蒸馏的作者文风，每包三件套：`style_card.md`（决策卡，每章注入写手）+ `fingerprint.json`（指纹基线）+ `lint_overlay.json`（lint 阈值覆盖/签名手法豁免/专属违禁词）。已收录 **8 位作者**：`tiancantudou`（天蚕土豆，**当前挂载**，《第三纪元》在用）、`yanyujiangnan`（烟雨江南）、`chendong`（辰东）、`jiangnan`、`jinhezai`、`maibao`、`wuzei`、`wochixihongshi`（我吃西红柿）。指纹基线均为 v2.0 口径 ready。挂载方式：`config/novel_config.json` 设 `"style_pack": "<名称>"`，一本书只挂一个包。覆盖层只能调阈值与豁免签名手法，**不能关闭通用反 AI 红线**。蒸馏新作者的四阶段流程、style_card 模板与入库验收见该目录 `README.md` 与 `docs/style-distillation/`。**原作语料（226MB+ txt）已移出仓库，存放在 `d:\personFile\corpus\writer-styles\<作者名>\原作[_utf8]\`，fingerprint.json 的 `source` 字段已更新为绝对路径**。指纹口径 v2.0（2026-07-26 重建）：分句只按句末标点、破折号去重计数（数值约为 v1 的 1/3）、对话占比按引号内字数（低于 v1 口径）、容差由章际波动推导；校验判读：1-2 个轻微超阈≈正常章际波动，≥3 个超阈才需修。

> **千字率阈值的口径绑定**：`lint_overlay.json` 里的 `*_per_1000` 系列阈值是用 `style_lint.han_len()`（仅汉字+数字）作分母、从原作语料实测推导出来的。**改这个计数函数会同时移动 8 个风格包的全部千字率阈值基线**——改之前必须重跑 `style_pack_check.py --all` 并复核各包 `fingerprint_ref.key_metrics`。

## 八、安全与合规注意事项

- **平台合规**：终稿须经 fanqie-adapter 敏感词过滤与审核合规处理后方可发布；`config/novel_config.json` 的 `topic_screening.core_commitments` 是内容红线（如势力仅三家、前 30 章新造专名 ≤5 个等），不可擅自突破。
- **无密钥/无外发**：仓库不含凭证；系统所有状态为本地文件。脚本不联网（learning 子系统的 WebFetch 由 Agent 在对话中执行，非脚本行为）。
- **指纹基线必须用原作**：`style_fingerprint.py build` 禁止用蒸馏产物或 AI 文本充当原作样本，否则基线失真。
- **自动模式的人工检查点**：Auto-Runner 遇 human-checkpoint 步骤自动通过并标注 `[AUTO-APPROVED]`，需人工复核日志。
- 修改记忆文件（`memory/`）前注意它们是多个 Agent 的共享事实源——保持 schema 与既有字段命名一致，勿随意重构结构。

## 九、当前进度快照

**当前状态**：在产项目《第三纪元》**已于 2026-09-20 重启**——旧稿 Ch1-7 正文与全部章级过程产物（含黄金三章精修证据）完整归档至 `archive/第三纪元_重启_20260920/`（output 9 / handoff 48 / golden3_revisions 43 / memory 10）；**保留**大纲（`memory/outline.json`）、世界观（`setting_bible`/`world_setting`/`ability_system`/`conflict_rules`）、角色设定（8 张角色卡 + `characters.json`）、立项与审核卡（topic_screening / 大纲与设定审核卡）。指针已归零（`session_pointer.current_chapter=0`，`handoff/task_plan.json` phase=init），8 张角色卡 `current_state` 已回退 Ch1 基线，**下一步从序言+Ch1 按现有大纲重写**（适用 chapter-writer v4.3 / detail-reviewer v1.21）。全书规划 300 章 / 6 卷，tiancantudou（天蚕土豆）文风包，2500 字/章（区间 2400-2600，见根目录 `lint_config.json`）。**初始化欠账仍在**（角色卡复审未跑；设定三件套 3 项登记项源自旧稿、暂缓）——见下方「初始化欠账」小节。

**质量趋势**：旧稿 Ch1-7 记录（Ch1-3 走用户直评通道；Ch4 unified 9.11；Ch5 9.28；Ch6 overall 9.44；Ch7 overall 9.43，全部终审 approved）已随重启归档（`archive/第三纪元_重启_20260920/`）；新稿自 Ch1 起重新累积。

**当前待决**（session_pointer.open_decisions）：①书名与简介待 final（忌俗套重生流书名）②指纹基线终裁——新稿位面篇（Ch15 归城）结束后由用户裁决（旧稿证据已随重启归档，届时重新裁决）③番茄「多书名实验」测试时机（20-50 万/100 万字后，发布后执行）。

### 初始化欠账（2026-09-20 核实修正）

《第三纪元》的初始化流程未走完即已进入章节循环。**经逐项取证，四项欠账的真实性质与初判不同**——不是"没做"，而是**"已做/已整改，但复审未执行"**：

| 里程碑 | 真实状态（取证结论） | 是否阻塞重写 |
|--------|---------------------|:---:|
| topic-screener 预筛 | ✅ **已完成**（2026-08-06，verdict=pass_with_note，6 维全评）。此前标 pending 系归档错名所致，已更正 | 否 |
| plot-architect 完整大纲 | ✅ **第一卷已覆盖**：`memory/outline.json` 含 `volumes`（6 卷总纲）+ `volume_1_chapters`（第一卷逐章 beat）+ `naming_budget`/`suspense_window_plan`/`shuang_point_distribution`。卷 2+ 逐章 beat 未生成，但**这是设计意图**（滚动生成），非欠账 | 否 |
| character-designer 角色卡 | ⚠️ **已审核 8.45（revise）→ 已整改 → 未复审**。`handoff/character_review.json` 的 C1（齿轮刻痕断代三方冲突）+ M1（关系⑤证据误植）+ M2（沈.json 断代接口）**整改均已落地**：`沈.json` 内有显式标注「【断代注记（M2修复）】」「【M2修复新增：刻痕断代表，与C1'新痕'仲裁咬合】」，C1 按审核推荐方案 (a) 裁定（齿轮左钩=近期新痕，作者=收刀的传人）；M1 的「还息」段已在 `characters.json` | **否**（C1 已按 (a) 落定，与 Ch5「搭痕第2次递进」不冲突） |
| 设定三件套 + setting-reviewer | ⚠️ **已审核 9.08（revise）→ 整改已全部落地 → 未复审**。7 项 recommended_fix 经逐项复核**均已应用**（详见下方验证表），含 P1-3 术语级 disclosure（落在 `ability_system.武器装备分级`，非被点名的 `world_setting`） | 否 |

**取证方法说明**（可复现）：三件套、角色卡、两张审核卡**全部提交于同一个 commit**（`d60cfc9`），故无法用文件时间或 git 历史判断"整改是否在审核之后发生"。判定依据是**文件内的显式修复标注**（如「【M2修复】」字样）与整改项的关键词落地情况——这是间接证据，**最终确认须以重跑复审为准**。

**补账方案（按优先级，均不阻塞 Ch8）**：

| # | 动作 | 依据 | 成本 |
|---|------|------|------|
| 1 | 重跑 **setting-reviewer** 复审三件套，确认 ≥9.5 并冲线（原 9.08，note 称"底子已达9.5水准，配合 minor 清零后可复审冲线"） | 7 项 recommended_fix **已全部验证落地**（见下） | 中 |
| 2 | 重跑 **outline-editor（角色卡审核）**，确认 C1/M1/M2 整改后 verdict（原 8.45 revise） | C1/M1/M2 已落地 | 中 |
| 3 | 卷 2 逐章 beat 按滚动方式生成（当前最新章节 +2 章即够） | 设计意图 | 随生产进行 |

**7 项 recommended_fix 的逐项验证结果（2026-09-20 复核，全部已应用）**：

| 项 | 要求 | 落地位置与证据 |
|---|------|--------------|
| P0-1 | 拆开深祭/命祭；命祭=四阶临时仅限燃命者；补四阶临时光色规则；跨阶挑战注明起算基准 | `ability_system`：`跨阶挑战规则.statement` 含"起算基准：命祭=深度献祭命格，自二阶临时越至三阶临时；本纪元献祭封顶三阶临时，四阶级威力仅前纪元遗物可达——**无光只有灰**"（即光色规则） |
| P0-2 | 裁定铁壁城/第二纪元计数口径；更正昭关首现为 Ch1；同步 setting_bible 与 outline | `world_setting.专名纪律`：含「铁壁城（Ch1:36，传闻中的内陆大城，一次性提及）」「计数口径」「昭关（Ch1:20/146首现）」；`setting_bible`/`outline.naming_budget` 均已同步 |
| P1-3 | 术语级 disclosure 批量更正（凡器/遗器/祭器/位面裂隙/四阶流动纹） | **在 `ability_system.武器装备分级`（非 world_setting）**：凡器「概念已披露（Ch1 长矛/箭画面），术语名未点破」；遗器「概念已披露（Ch2-3 残骸/芯子），术语名未点破」；祭器「已披露（Ch1:18 术语首现'得武师或者祭器才杀得动'）」；四阶「卷1计划（**Ch1-3 遗器流动纹画面已展示（Ch1:158首现）**）」 |
| P1-4 | 锈关守军.定位补注；昭关条目补"已被纹兽所破（Ch1）" | `world_setting`：含「老周头」卷1计划注记与「纹兽所破」 |
| P2-5 | tier_1 补头目去向；补 Ch14/Ch33 区分条；新增后期真相时间轴跨文件索引 | `conflict_rules`：含「头目去向」与「后期真相时间轴」 |
| P2-6 | 补"上一座城两夜即破（Ch1:20）"；补核市经济与工分经济接口原则 | `world_setting` 含「两夜」；`conflict_rules` 含核市/工分经济表述 |
| P2-7 | 祭器加阶位浮动注；跨阶规则交叉引用位面环境对冲；御兽师分级加封存注记 | `ability_system`：祭器「对应阶位：二-三阶（**随献祭档位浮动**：浅祭=二阶临时/深祭=三阶临时）」；跨阶规则含"卷1实例详见「位面环境对冲」Ch10"；御兽师条目含封存注记 |

**正文交叉验证（关键三项，以旧稿 `output/chapter_*.txt` 为准；旧稿已随重启归档至 `archive/第三纪元_重启_20260920/output/`）**：
- 祭器 Ch1:18 —— 实测 Ch1 第 18 行「得武师或者祭器才杀得动」，**与设定一致** ✓
- 位面裂隙 Ch1→Ch2→Ch4 —— 实测 Ch1:14「从位面裂隙里涌出来」→ Ch2:127「裂隙那边的兽体内有活核」→ Ch4:105「裂隙卧在乱石滩深处」，**与设定一致** ✓
- 四阶流动纹 Ch1-3 —— 实测 Ch1:158-160「纹路在动，像水在金属表面慢慢流」「这截金属上的纹路是活的，在流」、Ch2:107/135、Ch3:97/103，**画面确已展示**（正文按"术语未点破"原则从未出现"流动纹"三字，验算一致）✓

> **取证方法论警告（本次会话踩坑 3 次，务必注意）**：判断"某要求是否已落实"时，**不要只用关键词匹配**。
> 本文件的心脏教训：①"术语未点破"意味着**正文刻意不出现该术语**，用术语字面搜索必然误判为"未落实" ②整改可能落在**与被审文件不同的另一个文件**里（如 P1-3 落在 `ability_system` 而非被点名的 `world_setting`） ③正则的方向性错误会假报 False（"祭器…Ch1:18" 与 "Ch1:18…祭器" 是两种顺序）。
> 本次因此先后误判两次：把"已整改未复审"说成"未审核"，把"已应用的 P1-3"说成"唯一未应用项"。**结论须以重跑复审为准，关键词匹配只能作线索。**

**关键判断（2026-09-20 重启后口径）**：四项欠账**均不阻塞从 Ch1 重写**；C1 已按方案 (a) 落定（刻痕线裁定仍有效）。建议**新稿开写的同时并行执行 1-2 项补账（重跑复审）**，3 项随生产进行。

### 已知缺陷（2026-09-20 巡检发现）

**缺陷 #1：`chapter_length` 篇幅硬检字数口径不一致 —— ✅ 已修复（style_lint v2.5）**

- **现象**：`style_lint.py` 的 `chapter_length` 规则原用 `han_len()` 计数字数，该函数**只统计汉字与数字，排除全部中文标点**；而 `lint_config.json` 的 `chapter_len_min/max`（2400-2600）、`novel_config.chapter_word_count`（2500）、以及写手与终审员核对的"字数"，用的都是**去空白字符数（含标点）**。两者系统性相差约 15%（≈360-450 字）。
- **实测数据**（Ch1-7，两种口径对比）：

  | 章节 | 旧口径（汉字+数字） | 新口径（去空白） | 旧判定 | 新判定 |
  |------|-------------------|----------------|--------|--------|
  | Ch1 | 3482 | 3937 | 超上限 | 超上限（黄金三章，豁免） |
  | Ch2 | 3206 | 3685 | 超上限 | 超上限（黄金三章，豁免） |
  | Ch3 | 2980 | 3400 | 超上限 | 超上限（黄金三章，豁免） |
  | Ch4 | 2449 | 2897 | 区间内 ✓ | **超上限 ✗**（待决） |
  | Ch5 | 2228 | 2547 | **低于下限 ✗** | 区间内 ✓ |
  | Ch6 | 2128 | 2586 | **低于下限 ✗** | 区间内 ✓ |
  | Ch7 | 2192 | 2557 | **低于下限 ✗** | 区间内 ✓ |

- **后果（修复前）**：Ch5-7 三章的 `chapter_length` advisory **从未清零**，但 L1 规则不阻断退出码（lint 仍报 PASS），所以"advisory 提交前必须清零"这条要求在实践中**从未被满足且无人发现**——写手看到"2557字达标"，lint 看到"2192字不达标"，双方都没错，是分母不统一。
- **修复方式（v2.5 已实施）**：新增独立函数 `word_count()`（去空白字符数口径），`chapter_length` 规则改用它；**未改动 `han_len()`**——它与 `dash_max_per_1000` / `ellipsis_max_per_1000` / `le_max_per_1000` / `zhe_max_per_1000` / `conjunction_min_per_1000` 等共用分母，而这些阈值是从原作语料实测校准的（见第七节「千字率阈值的口径绑定」）。
- **回归验证**：对 Ch1-7 逐一比对修复前/后完整 lint 输出，**差异仅 `chapter_length` 一条规则**，其余全部规则（含千字率家族）逐条一致；`style_pack_check.py --all` 中 8 个真实风格包全 PASS（仅 `writer-styles/test/` 草稿目录 FAIL，属扫描含测试目录的既有噪音）。新口径结果与终审员人工核对数（2547/2586/2557）**完全一致**。
- **待决已裁定（2026-09-20）**：Ch4 按真实口径 2897 字超上限 2600 字约 297 字——**按「框架升级不追溯重写」原则豁免，不回溯修改**；如后续认为影响阅读节奏，纳入该卷卷末复盘窗口统一润色。（同批：Ch1-3 黄金三章 3937/3685/3400 字亦超上限，同属定稿时 lint_config 尚未生效，一并豁免。）

**缺陷 #2：`topic_screening.json` 曾被已归档项目《请客》的数据占用 —— ✅ 已处理**

- `handoff/topic_screening.json` 是框架**契约文件名**（topic-screener 写入、chief-editor/skeptic 读取、`parallel_task_config_template.json` 引用）。该槽位此前被**已归档《请客》**的预筛卡占用（`ref.book_title` 实测为《请客》，2026-08-02），而《第三纪元》的预筛卡被存成了非标准名 `topic_screening_disanjiyuan.json`（2026-08-06）——调度器按固定名读取会拿到**错项目**的数据。
- **已处理（2026-09-20）**：①删除被《请客》占用的 `handoff/topic_screening.json`；②将《第三纪元》的预筛卡由非标准名 `topic_screening_disanjiyuan.json` **改名为契约名 `handoff/topic_screening.json`**（实测 `ref.book_title=《第三纪元》`，timestamp 2026-08-06）；③同步把 session_pointer 中该里程碑由 `pending` 更正为 `done`。
- **连带发现**：《第三纪元》的正式预筛**实际已完成**（6 维全部评分：题材耐久度/爽感路径/认知门槛/失败模式匹配 4 项 pass、暗基调补偿与平台基调 2 项 pass_with_note，verdict=pass_with_note，并附 3 条 adjustment_suggestions）——此前 session_pointer 标为 `pending` 属**误标**，根因是归档在错的文件名下，而非真的没做。

**缺陷 #3：`output/chapter_001~003.txt`（黄金三章）当前 lint 报 L0 阻断 2 项**

- 实测 Ch1-3 各有 `not_a_is_b`（"不是…是…"）2 处，超过 tiancantudou 覆盖层的 `not_a_is_b_max_per_chapter: 1` → L0 critical 2。
- **已核实为预先存在，与 style_lint v2.5 修复无关**（用 HEAD 原版脚本对照，阻断数一致）。
- **属文档记载的预期行为**：`handoff/style_lint_ch1_tiancantudou_final.json` 等历史卡记录 `blocking=0`，即黄金三章定稿时该覆盖层阈值尚未生效或未按当前配置运行；按「框架升级不追溯重写」原则，**旧章报 critical 不等于需要改旧章**（AGENTS.md 第六节第 2 条）。

**项目进度面板**：`dashboard.html`（位于 `write-assistant/` 根目录，作为通用工具不绑定具体项目，避免项目归档时被删除）提供实时可视化监控（进度/质量趋势/角色状态/伏笔追踪/悬念窗口/反派梯队/下一步动作/目录信息/章节目录）。支持项目选择器（URL 参数 `?project=<项目名>`）、模块展开/折叠、章节目录按卷分组。启动方式：在 `write-assistant/` 目录下运行 `python serve.py [port]`（或 `python -m http.server 8000`），访问 `http://localhost:8000/dashboard.html`。数据源为各项目 `memory/*.json`。当前 `KNOWN_PROJECTS = ['.']`（《第三纪元》memory 文件直接在根目录 `memory/` 下，用 `.` 表示当前目录），`PROJECT_DISPLAY_NAMES` 映射为「第三纪元」；新项目立项后须在 `dashboard.html` 的 `KNOWN_PROJECTS` 数组中追加项目名。

**其他项目状态**（均已归档）：
- 《请客》：已放弃归档（`archive/请客_放弃_20260804/`，2026-08-04 归档；无限流/系统流·民俗悬念·黑色幽默智斗，yanyujiangnan 文风包，300 章 / 6 卷，2500 字/章；Ch1-3 多轮修订完成 lint 全绿 + Ch4-5 完成，共 5 章约 12000 字；归档原因：文本质量极高（三份评审文学质感均评 9.0+），但与番茄"无限流/系统流"标签严重错配——黄金三章沉浸于"送客宴"副本氛围，未展示核心类型要素。关键教训：类型小说黄金三章必须前 3 章展示核心类型钩子，文学质感在番茄是门槛而非优势）
- 《征诏之界》：已放弃归档（`archive/征诏之界_放弃_20260801/`，2026-08-01 归档；征调/副本流/无限流变体，yanyujiangnan 文风包，400 章 / 6 卷，2400-2600 字/章；Ch1-4 全部 published（终审 9.05/9.06/9.04/9.40，Ch4 用户终评"可以定稿"），实验区 test/ 一并归档（12 维韵味蒸馏工具链/重写稿/盲测归档/读者判别知识）；归档原因：用户决定放弃，开启新项目。潜在复活点：Ch5 beat sheet 已就绪（明晚掌眼兑现/铜钱规则差异清账/苏眠身份第一层解释/赵阙登名））
- 《镜渊》：已放弃归档（`archive/镜渊_20260728/`，2026-07-28 归档；赛博朋克×智性幻想，yanyujiangnan 文风包，505 章 / 8 卷；黄金三章 Ch1-3 重写完成 + Ch4《问锤》完成，共 4 章约 10000 字；归档原因：用户决定放弃）
- 《万纹师》：已归档（`archive/wanwenshi_20260727/`，2026-07-27 归档；玄幻/职业流/热血正剧，规划 420 章 / 6 卷，chendong 文风包；黄金三章已写 Ch1-3 共 9100 字，quality_review verdict=需修改 4 个 major 待修，Ch4 任务分配已就绪但未开写；归档原因：用户决定开启新项目。潜在复活点：Ch3 三项 major 修复 + Ch4「喂纹」开写）
- 《有龙则灵》：已归档（`archive/有龙则灵_20260726/`，2026-07-26 归档；旧版 Ch1-14 删除，重写版 Ch1-4 入库后整体归档）
- 《补天人》：已归档（`archive/补天人_20260726/`，写了 5 章后归档）
- 《献祭纪元：赊刀人》：已放弃归档（`archive/newbook_献祭纪元_放弃_20260726/`）
- 《临渊》《玩家请就位》：早期归档项目（`archive/临渊_20260719/`、`archive/玩家请就位_20260720/`）
