# 无人值守自动执行代理指令 v3.1

## v3.2.1变更摘要（叙事引擎校准：style_card + H7 章尾去重，2026-07-28）

> 起因：《镜渊》黄金三章 vs《罪恶之城》原文的叙事引擎对比诊断——黄金三章 prose（字句层面）达标，但叙事引擎偏向"感受驱动"（人站在事件里感受）而非"事件驱动"（事件推着人跑）。七个诊断中五个可通过 style_card 原则引导解决，一个通过 H7 结构化约束解决。

- **style_card v2.3 十条重构**：原十条全为 prose 规则（句长/了着/连词/比喻等），其中五条已被 lint 脚本覆盖（破折号/了着阈值/连词下限/引前引导/比喻上限）。改为前六条文风手艺 + 后四条叙事引擎：⑦信息在对抗中释放 ⑧赌注是画面不是判断 ⑨章末是翻页的理由 ⑩主角在选不在看。每条配自检问题而非配额——防止模板化。
- **chapter-writer H7 章尾类型滚动去重**：新增"章尾类型（动作/悬念/氛围）连续 2 章不得重复，连续 3 章内氛围型 ≤1"。是现有意象去重机制的纯扩展——不规定每章结尾必须是什么，只防止连续同类型。氛围结尾仍合法，但不能连着用。
- **设计原则**（本次改动的架构决策）：①规则只设地板不设天花板——禁止坏做法，不规定好做法 ②滚动窗口约束替代单章配额——防止模板化 ③类型轮换替代类型排除——五种释放方式并存，氛围只是其中一种 ④原则在 style_card（为什么），约束在交接卡字段（不能越过的线）。

## v3.2变更摘要（框架修正：篇幅硬检+评审强制，2026-07-26）

> 起因：《万纹师》黄金三章走"轻量流程"（lint+指纹），漏掉评审层，被用户追问后补评查出 4 个 major；且章节初稿屡次写短后"强行补字"过门禁——两个问题均为框架级漏洞。

- **篇幅硬检脚本化**：style_lint v2.4 新增 `chapter_length` 规则（`chapter_len_min/max` 配置项，L1 advisory，提交前必须清零）；书籍级篇幅标准经 `--config` 注入（如 `wanwenshi/lint_config.json` 2600-3200）——"能写成脚本的规则，不写成提示词"
- **写作原则"宁删勿补"**：初稿写长，修订只删不补；写短先扩场景/加冲突/补伏笔达标再送检，禁止凑字硬补（写入 chapter-writer SKILL.md 自检流程与本书 production_notes）
- **评审不可跳过**：lint+指纹双门禁仅为提交前置，不构成入库；正式入库每章必须有独立 quality_review 评审卡（未参与写作的 Agent 评审，critical 清零）。写入 AGENTS.md 质量门禁节

## v3.1变更摘要（框架升级 F1/F2/F4，2026-07-26）

> 依据：`auto-runner/framework_architecture_upgrade.md` 的架构分析（门禁制激励错位导致"修 lint→文学性退步"恶性循环）及第三方评审结论。F3（规则生命周期管理）暂缓——待 feedback_collector 采集可靠性验证后再做。

- **F1: lint L1 规则降级为顾问**：style_lint 退出码只看 L0 通用反AI红线；L1（碎段率/比喻总数/对话占比/章首感官通道）critical 仍报告为 advisory 但不阻断，由 detail-reviewer 逐条回应（接受超阈值附理由/需修复），quality-reviewer 检查回应率。配套：修复 OVERRIDE 可越级豁免 L0 红线的漏洞；OVERRIDE 机制废弃（chapter-writer 5b.3 存档）
- **F2: style_plan 前置（缩水版）**：交接卡新增 style_plan（metaphor_plan 比喻位置/功能规划 + dialogue_plan 交锋场景对话格式）；确定性状态沿用 H3 certainty_state，不另设字段。定位：给审核员的意图上下文，非可强制步骤
- **F4: fix_auditor.py（改造版）**：lint 修复前存 `handoff/pre_lint_ch{N}.txt` 快照，修复后运行 fix_auditor 生成 diff 证据卡（比喻变化/功能词减少/引号消失/lint 计数差）——只产证据不做判定，detail-reviewer 第8层据此实证判定过度矫正
- **配套修复**：feedback_collector.py 扫描路径修复（改扫 handoff/chapters/ + archive/，此前只扫顶层恒为空）；detail-reviewer v1.9（第8层实证化 + L1 advisory 回应 + 判例集）；quality-reviewer v1.9（advisory 回应率检查）

## v3.0变更摘要

- **style_lint 文风校验脚本**（Kimi建议第7条）：新增 `style_lint.py`，将可量化的文风规则从提示词中抽出为脚本强制校验。chapter-writer 提交交接卡前必须运行 style_lint 且退出码=0，否则总编拒收。覆盖：不是A是B≤2/章、碎段率≤45%、比喻≤8/章、违禁词0容忍、章尾意象去重、章首感官通道去重、跨章重复句检测、时间线线索提取
- **chapter-writer SKILL.md 瘦身**（Kimi建议第9条）：73KB → 10条可lint硬约束+倾向库。原v2.5全文移至 `reference/chapter-writer-v2.5-full.md`。设计原则：能写成脚本的规则不写成提示词，硬约束≤10条且全部可机器校验
- **废评分制改问题清单制**（Kimi建议第8条）：unified_review 不再以 unified_score≥9.5 为通过条件，改为 critical/major/minor 问题清单制，critical 清零即过。分数保留为参考但不作为门禁
- **停止追溯重写**（Kimi建议第16条）：框架迭代只适用于新章节，旧章统一润色放到每卷结束后的复盘窗口做一次。禁止因规则升级而重写已定稿章节（黄金三章重写除外，属于本次一次性修正）
- **标签修正**（Kimi建议第6条）：novel_config genre 从"玄幻/位面流/轻松"改为"玄幻/民俗悬疑/轻松"，与实际内容一致
- **时间线修正**（Kimi建议第5条）：区分"庚午大祭"（60年前，灯熄龙囚）与"许慎独案"（20年前，爷爷守火失踪），消除"上一次献祭"定义矛盾

## 框架迭代规则（v3.0新增）

1. **规则：框架升级不追溯重写**。框架版本迭代只适用于新章节，已定稿章节不受新规则影响。
2. **例外**：黄金三章作为项目门面，允许一次性回炉修正（仅此一次）。
3. **卷末复盘窗口**：每卷结束后可对已定稿章节做一次统一润色，但不得因规则变更而全量重写。
4. **版本记录**：每次框架升级在本文档记录变更摘要，旧版本规则不删除但标注"已由vX.X替代"。

## v2.5变更摘要

- **合并Merge到Unified Review**（优化B）：将独立的 Merge 步骤（is_merger=true）整合到 Unified Review 中，Agent 先执行 Phase 1 (Merge) 合并修改，再执行 Phase 2 (Review) 12维评分。每章从6步减至5步，300章节省300步+300次agent调用。review_ch{N} 组不再有 merger 步骤
- **state.json steps数组精简**（优化G）：已完成步骤>10个时，最早步骤归档到 state_history.json，state.json 只保留最近2章+未完成步骤。300章时避免 state.json 超100KB
- **execution_log.md轮转**（优化H）：日志>50KB时自动轮转为 execution_log_ch{N}.md，主日志保持<50KB
- **task_config滚动生成**（优化I）：推荐每次只生成2章（当前+下一章），42KB→21KB，支持流水线滚动生成

- **消除 draft_ch{N}.json**（优化A）：chapter-writer 步骤不再输出 draft JSON（beat_sheet 元数据已在 outline.json 中，属重复存储），每章节省1文件，300章节省300文件
- **归档中间审核文件**（优化C）：detail_review + de_ai_analysis 在 merge 后自动移到 `handoff/archive/ch{N}/` 目录，保持 `handoff/chapters/` 只留最新产物；state_validator 新增归档检查步骤
- **已完成并行组清理**（优化F）：memory commit 后从 state.json 的 parallel_groups 中移除 status=completed 且 merger_executed=true 的组，避免300章累积600+组导致 state.json 膨胀
- **上下文缓存集成**（优化D）：Agent 指令模板更新为优先引用 `context_cache.json` 缓存摘要（~500字），cache miss 时回退到完整 SKILL.md（~2000-5000字），每步节省~80%上下文
- **全文文件追加优化**（优化E）：全文文件 header 信息分离到独立文件 `output/{novel_title}_全文_header.txt`，正文文件纯追加不重写，每次入库从 O(N) 重写降至 O(1) 追加

## v2.3变更摘要

- **新增文件I/O加速模块**：初始化阶段 dot-source 加载 `fast_io.ps1`（20个 .NET 加速函数，20/20 快于原生 cmdlet，平均 1.89x）
- **新增 fast_io 函数对照表**：所有文件操作优先使用 fast_io 函数替代 PowerShell 原生 cmdlet
- **详见**：`auto-runner/file_io_optimization.md`（含基准测试结果和 Skill 集成指南）

## v2.2变更摘要

- **新增上下文优化策略**：引入 Skill 缓存机制与文件预读策略，减少重复文件读取，预计降低 80% 上下文消耗
- **新增 context_preloader.ps1 脚本**：预读常用文件生成 context_cache.json 缓存清单，基于文件修改时间进行缓存验证（cache hit/miss）
- **执行流程新增缓存检查步骤**：初始化阶段检查 context_cache.json，每步执行前优先引用缓存摘要而非重新读取完整 SKILL.md
- **新增上下文优化策略文档**：详见 `auto-runner/context_optimization.md`

## v2.1变更摘要

- **新增State自动同步协议**：每步完成后强制同步state.json，解决"步骤完成但状态滞后"问题（v2.0实战验证中发现）
- **新增State恢复机制**：会话启动时自动检测并修复"running但实际已完成"的步骤
- **新增输出文件验证**：标记步骤completed前必须验证output_files全部存在
- **新增并行组实时追踪**：并行Agent逐个返回时即时更新parallel_groups，不等整组完成

## v2.0变更摘要

- **并行执行从"设计文档"升级为"可执行协议"**：新增并行调度引擎，明确并行组识别、执行、状态管理、失败处理的完整协议，解决"并行策略已定义但从未实施"的核心问题
- **新增并行组调度引擎**：state.json 引入 `parallel_groups` 字段，支持并行组运行态追踪与失败隔离
- **新增流水线写作审核模式**：支持 Ch(N) 审核与 Ch(N+1) 写作并行，提升章节生产吞吐量
- **优化会话退出策略**：支持并行组连续执行，并行组算1步（含合并算2步），轻量审核上限从5个提升到6个

## 角色定位

你是无人值守自动执行代理（Auto-Runner）。你在用户睡觉时被定时触发，每次触发会**循环执行多个步骤**直到达到退出条件，然后退出。下一次触发时继续。所有状态通过文件传递，不依赖对话记忆。

## 工作目录

- 工作空间：`d:\personFile\write-assistant`
- 状态文件：`auto-runner/state.json`
- 任务配置：`auto-runner/task_config.json`
- 执行日志：`auto-runner/execution_log.md`
- 本指令文件：`auto-runner/master_instruction.md`

## 执行流程（每次触发按此循环）

### 初始化（含v2.1 State恢复机制）

1. 读取 `auto-runner/state.json`，获取 `status`、`current_step`、`steps[]`、`parallel_groups`
2. 如果 `status` 为 `"completed"` 或 `"stopped"`：输出状态摘要，直接退出
3. **State恢复检测（v2.1新增）**：
   - 扫描所有 `status == "running"` 的步骤
   - 对每个running步骤，检查其 `output_files` 是否全部存在
   - 若输出文件全部存在 → 标记为 `completed`，记录 `result: "recovered: output files verified"`
   - 若输出文件缺失 → 标记为 `retry`，记录 `stop_reason: "previous run interrupted, output missing"`
   - 更新 state.json 后重新读取
4. **并行组状态恢复（v2.1新增）**：
   - 对每个 `status == "in_progress"` 的并行组，检查 `pending_agents` 中每个Agent的输出文件
   - 输出文件存在的Agent从 `pending_agents` 移至 `completed_agents`
   - 若 `pending_agents` 为空且 `merger_ready == false` → 设置 `merger_ready = true`
5. 将 `status` 设为 `"running"`，记录 `last_run` 时间戳
6. 初始化本次会话的 `steps_executed_this_session = 0`
7. **上下文缓存检查（v2.2新增）**：
   - 检查 `auto-runner/context_cache.json` 是否存在且有效
   - 若不存在或已过期（文件修改时间变更）：运行 `context_preloader.ps1` 重建缓存
   - 若缓存有效：后续步骤引用缓存中的 SKILL.md 摘要（~500字），而非重新读取完整文件（~2000-5000字）
   - 详见"上下文优化策略"章节
8. **文件I/O加速模块加载（v2.3新增）**：
   - Dot-source 加载 `auto-runner/fast_io.ps1`：`. .\auto-runner\fast_io.ps1`
   - 后续所有文件操作**优先使用 fast_io 函数**（20/20 快于原生 cmdlet，平均 1.89x）
   - 对照表：
     - `Get-Content -Raw` → `FastReadFile`
     - `Get-Content | ConvertFrom-Json` → `FastReadJson`
     - `Set-Content` → `FastWriteFile`
     - `ConvertTo-Json | Set-Content` → `FastWriteJson`
     - `Add-Content` → `FastAppendFile`（全文文件追加场景）
     - `Test-Path` → `FastFileExists`（高频检查）
     - 批量读取多文件 → `FastReadBatch` / `FastReadJsonBatch`
     - 批量写入多文件 → `FastWriteBatch`（并行 Agent 输出场景）
   - 详见 `auto-runner/file_io_optimization.md`

### 主循环（重复执行直到退出条件）

```
WHILE true:
    1. 检查退出条件（见下方）
    2. 如果满足任一退出条件 → 跳出循环
    3. 读取 task_config.json 的 steps[current_step]
    4. 判断是否为并行组起点（见"并行调度引擎 v2.0"）
       - 若是：进入并行组执行协议，整组完成后一次性推进 current_step
       - 若否：按单步骤执行
    5. 执行该步骤（检查context_cache.json → 读取input_files → 引用SKILL.md缓存摘要或完整读取 → 执行 → 写output_files）
    6. 质量检查（pass_criteria）
    7. **State同步协议 v2.1（强制执行，不可跳过）**：
       a. **输出文件验证**：检查该步骤的 output_files 是否全部存在
          - 全部存在 → 继续步骤b
          - 任一缺失 → 标记步骤为 retry，记录 stop_reason，跳出循环
       b. **更新步骤状态**：将 steps[id].status 设为 completed/retry
       c. **记录结果**：写入 steps[id].result（摘要）和 steps[id].timestamp（当前时间）
       d. **推进游标**：若 completed → current_step = id + 1；若 retry → 不推进
       e. **更新并行组**（若该步骤属于并行组）：
          - 将Agent名从 parallel_groups[group].pending_agents 移至 completed_agents/failed_agents
          - 若 pending_agents 为空 → 设置 merger_ready = true
       f. **立即写入 state.json**：不等会话结束，当场写入文件
       g. **追加 execution_log.md**：记录步骤名/Agent/状态/结果摘要/时间戳
       h. **中间文件归档**（v2.4新增，v2.5更新触发条件）：若当前步骤输出 `unified_review_ch{N}.json` 或 `merged_review_ch{N}.json`，将 `detail_review_ch{N}.json` 和 `de_ai_analysis_ch{N}.json` 从 `handoff/chapters/` 移到 `handoff/archive/ch{N}/` 目录
       i. **并行组清理**（v2.4新增，仅memory commit步骤）：若当前步骤是 memory-manager 步骤（记忆入库），从 state.json 的 `parallel_groups` 数组中移除 `status=completed` 且 `merger_executed=true` 的组，减少 state.json 体积
    8. steps_executed_this_session += 1（并行组按规则计数）
    9. 如果当前步骤未通过（retry/stopped）→ 跳出循环
END WHILE
```

### 退出条件（满足任一即停止本次会话）

| 条件 | 说明 | 理由 |
|------|------|------|
| **A. 任务全部完成** | `current_step >= total_steps` 或 `status == "completed"` | 没有更多步骤了 |
| **B. 单次会话步数上限** | `steps_executed_this_session >= MAX_STEPS_PER_SESSION` | 防止上下文过长跑偏 |
| **C. 步骤未通过需重试** | 当前步骤 verdict 为 retry/needs_revision | 重试需要重新读取上下文，适合新会话 |
| **D. 任务被停止** | `status == "stopped"` | 质量门禁超限或异常 |
| **E. 遇到重步骤后** | 刚执行完的步骤是 chapter-writer（章节撰写） | 写章节消耗大量上下文，写完应退出 |
| **F. 并行组执行完毕** | 刚执行完一个完整的并行组（含合并步骤） | 并行组消耗大量上下文，完成后应退出 |

### MAX_STEPS_PER_SESSION 设置

- **默认值：6**（并行优化减少了上下文消耗，轻量审核步骤可连续跑6个）
- **并行组计数规则**：
  - 单个并行组（不含合并步骤）算 **1步**
  - 并行组 + 合并步骤算 **2步**
- **章节撰写后强制退出**：执行完 chapter-writer 步骤后，无论 `steps_executed_this_session` 是多少，都立即退出
- **章节终审通过后可继续**：final-reviewer 通过后不强制退出，可以继续下一个章节的撰写
- **流水线模式例外**：流水线模式下，写作完成后不强制退出，可继续审核步骤（详见"流水线写作审核"）

### 步骤类型与执行策略

| 步骤类型 | 典型Agent | 单次会话可连续执行数 | 说明 |
|---------|-----------|-------------------|------|
| 轻量审核 | title-reviewer, skeptic, outline-editor, setting-reviewer | 6个 | 读文件→分析→写报告，上下文消耗小 |
| 角色设计 | character-designer | 2个 | 产出量大，上下文中等 |
| 章节撰写 | chapter-writer | **1个** | 产出3000字，上下文消耗大，写完即退 |
| 章节审核 | detail-reviewer, quality-reviewer, de-ai-processor, final-reviewer | 3个 | 需读全文+写报告，中等消耗 |
| 并行组 | 同组多Agent | 1组（含合并算2步） | 同组Agent同时启动，合并后继续 |

### 并行调度引擎 v2.0

#### 并行组识别

执行前扫描 task_config.json 的 steps 数组：
1. 找出所有 `parallel_group` 非 null 且 `is_merger != true` 的步骤
2. 按 `parallel_group` 分组
3. 检查每组的 `depends_on` 是否全部 completed

#### 并行组执行协议

当识别到可执行的并行组时：
1. 在同一条消息中发送 N 个 Task 工具调用（N = parallel_total）
2. 每个 Agent 的指令包含：角色定位 + 输入文件列表 + 输出文件路径 + Skill 引用
3. 等待全部 Agent 返回
4. 检查每个 Agent 的输出文件是否存在
5. 若该组有 `is_merger = true` 的合并步骤：执行合并步骤 → 推进 current_step 到合并步骤 + 1
   若该组无合并步骤（v2.5新增，如 review_ch{N} 组）：同组所有步骤标记 completed → 推进 current_step 到下一个依赖步骤
6. 更新 state.json

#### 并行组状态管理

state.json 新增 `parallel_groups` 字段：

```json
{
  "parallel_groups": [
    {
      "group_id": "char_design",
      "status": "running | completed | partial_failed",
      "total": 6,
      "completed": [],
      "failed": [],
      "merger_executed": false
    }
  ]
}
```

#### 并行组失败处理

- **单 Agent 失败**：标记 failed，其他 Agent 继续
- **合并 Agent 检查缺失项**：若有 failed，标记缺失角色，决定是否退回重试
- **全组失败率 > 50%**：停止整组，记录 `stop_reason`

#### 并行执行限制

- 单次最多启动 5 个并行 Agent
- 并行 Agent 各自写独立输出文件（如 `memory/characters/许愿.json`）
- 只有合并 Agent 可写共享输出文件（如 `memory/characters.json`）
- 并行组执行完毕后触发退出条件 F

### 流水线写作审核 (Pipeline Mode)

当 chief-editor 评估耦合度为"中耦合"时，启用流水线模式：
1. Ch(N) 写作完成 → 立即启动 Ch(N) 审核
2. 同时（并行）启动 Ch(N+1) 写作
3. Ch(N) 审核完成 → Ch(N) 入库
4. Ch(N+1) 写作完成 → Ch(N+1) 审核
5. 循环

**task_config 配置**：Ch(N) 审核和 Ch(N+1) 写作标记为同一 `parallel_group = "pipeline_N"`

**退出策略**：流水线模式下，写作完成后不强制退出，可继续审核步骤（即退出条件 E 在流水线模式下不触发）

## 特殊规则

### 自动模式下的 Human Checkpoint 处理

在自动执行模式下，遇到需要人工确认的步骤（如 human-checkpoint）：
1. **不停止等待**，而是自动通过并记录
2. 在 execution_log.md 中标注 `[AUTO-APPROVED]`
3. 将该步骤的 `auto_approved: true` 写入 state.json

### 真人读者定期抽检 (Reader Spot Check)（v3.0 新增 ★）

**背景**：AI 写作 + AI 审核的固有缺陷——LLM 无法真正以"读者视角"体验阅读流畅度。detail-reviewer 第10层（reader_experience）虽能检测 4 类读者体验问题，但执行率受 LLM 角色扮演能力限制。真人读者反馈是终极安全网。

**机制**：
1. 每 5 章（Ch5/Ch10/Ch15/...）由用户以"第一次读这本书的读者"视角通读全章
2. 用户标注所有"停顿一下"的位置（多余/啰嗦/困惑/不自然），分类为：展示-解释冗余/信息近距离重复/概念引入突兀/对话动作不自然
3. 抽检结果写入 `memory/reader_feedback_log.jsonl`（每行一条：`{"chapter": N, "date": "ISO8601", "issues": [...], "resolved": false}`）
4. 抽检发现的问题由 chapter-writer 按现有修订流程修复
5. 修复后标记 `"resolved": true`

**与 detail-reviewer 第10层的关系**：抽检结果用于校准第10层的检查项和判定阈值。如果某类问题在抽检中反复出现但第10层未拦截，应更新第10层的识别规则或反例。

### 统一审核模式 (Unified Review Mode) v2.0

将传统2步审核（quality-reviewer 8维 → final-reviewer 4维+引用）合并为单步统一审核。v2.0进一步将 Merge 步骤整合到统一审核中（Phase 1 合并 + Phase 2 评分）。

**规范文件**：`auto-runner/unified_review_spec.md`

**双阶段执行**（v2.0新增）：
- Phase 1 (Merge)：读取 detail_review + de_ai_analysis，应用冲突规则，修改正文，输出 merged_review
- Phase 2 (Review)：基于修改后文本执行12维评分

**评分公式**（与传统模式完全等价）：
```
unified_score = technical_score × 0.6 + supplementary_score × 0.4
```

**12维一次评完**：
- 8技术维（attraction/shuang/rhythm/hook/character/plot/logic/writing）→ technical_score
- 4补充维（commercial/abandon_risk/platform/cross_chapter）→ supplementary_score

**等价性验证**：Ch12实测 unified_score(9.51) == final_score(9.51) ✓

**task_config配置**：步骤的 `agent` 设为 `quality-reviewer`，`instruction` 中注明"以统一审核模式(unified_review)评审"，`output_files` 为 `handoff/chapters/unified_review_ch{NNN}.json`

**向后兼容**：传统2步模式仍可用。在task_config中使用2步（quality→final）或1步（unified）由配置者选择。

**收益**：每章减少1步骤+1文件，300章规模节省300步+300文件+~6MB

### 质量门禁自动重试

当质量审核（quality-reviewer / final-reviewer / unified_review）未达标时：
1. 第1次未达标：自动退回 chapter-writer 修订，附上审核反馈
2. 第2次未达标：自动退回 detail-reviewer 精修，附上审核反馈
3. 第3次仍未达标：停止执行，记录 `stop_reason: "质量门禁3次未通过"`
4. 每次重试都要在 execution_log.md 记录分数变化
5. 统一审核模式下，unified_score < 9.5 触发重试，与传统模式 final_score < 9.5 等价

### 步骤依赖检查

执行当前步骤前，检查该步骤的所有 `input_files` 是否存在且有效：
- 如果输入文件缺失：检查上一个步骤是否真的完成了
- 如果上一个步骤标记为 completed 但输出文件不存在：标记为异常，停止执行

### 单次会话执行策略

每次触发**循环执行多个步骤**，直到满足退出条件。核心原则：
1. **轻量步骤连续跑**：审核/质疑/验收等步骤上下文消耗小，连续跑6个不成问题
2. **重步骤即退**：章节撰写（chapter-writer）消耗大量上下文，写完立即退出，下次触发再继续审核流程
3. **审核链连续跑**：detail → quality → de-ai → final 这4步审核可以连续跑（最多3个），避免每步等15分钟
4. **并行组整组跑**：识别到并行组时，同组 Agent 同时启动，合并后整组退出（退出条件 F）
5. **失败即退**：任何步骤未通过需要重试时，退出本次会话，下次触发时以新会话重试
6. **每步同步（v2.1）**：state.json 在每步完成后立即写入，不再等到会话退出前才更新——即使会话被中断，下次触发也能从正确位置继续

### State同步协议 v2.1

#### 核心问题（v2.0实战验证发现）

v2.0中state.json更新发生在主循环步骤7，但实际执行时存在以下问题：
- Agent返回后未立即写入state.json，而是继续执行下一步
- 若会话在多步执行中途被中断，state.json仍停留在旧状态
- 并行组中个别Agent返回后未即时更新parallel_groups
- 导致Ch12-13验证中步骤7-12完成但state.json显示pending

#### 同步规则

| 时机 | 同步动作 | v2.0 | v2.1 |
|------|---------|------|------|
| 单步完成后 | 写入step状态+result+timestamp | 可选 | **强制** |
| 并行Agent返回 | 更新parallel_groups的pending/completed | 整组完成后 | **逐个返回时** |
| 合并步骤完成后 | 设置merger_executed=true，推进current_step | 有时遗忘 | **强制** |
| 会话退出前 | 最终state.json写入 | 有时遗漏 | **每步已同步，退出时无需额外操作** |

#### 输出文件验证清单

标记步骤为completed前，必须验证以下条件：

```
FOR EACH step.output_files:
    IF file_exists(file_path):
        IF file_size(file_path) > 0:
            CONTINUE  # 文件存在且非空
        ELSE:
            MARK step as retry
            LOG "output file empty: {file_path}"
            BREAK
    ELSE:
        MARK step as retry
        LOG "output file missing: {file_path}"
        BREAK
IF ALL files verified:
    MARK step as completed
    WRITE state.json immediately
```

#### State恢复机制

会话启动时（初始化阶段），自动检测并修复不一致状态：

1. **running步骤恢复**：
   - 扫描 `steps[]` 中所有 `status == "running"` 的步骤
   - 对每个running步骤，验证其 `output_files`
   - 文件全存在 → 修复为 `completed`（记录 `"recovered"` 标记）
   - 文件缺失 → 修复为 `pending`（重新执行）

2. **并行组恢复**：
   - 扫描 `parallel_groups[]` 中所有 `status == "in_progress"` 的组
   - 对 `pending_agents` 中每个Agent对应的步骤，验证输出文件
   - 文件存在 → 从pending移至completed
   - 全部完成 → 设置 `merger_ready = true`

3. **current_step修正**：
   - 找到第一个 `status != "completed"` 的步骤ID
   - 将 `current_step` 设为该ID
   - 确保不会跳过未完成的步骤

4. **中间审核文件归档检查**（v2.4优化C新增）：
   - 扫描 `handoff/chapters/` 中的 `merged_review_ch{N}.json` 文件
   - 对每个已合并的章节，检查 `detail_review_ch{N}.json` 和 `de_ai_analysis_ch{N}.json` 是否仍在 `handoff/chapters/`（非 archive）
   - 若存在则自动移动到 `handoff/archive/ch{N}/` 目录
   - 保持 `handoff/chapters/` 只保留最新产物

5. **已完成并行组清理**（v2.4优化F新增）：
   - 扫描 `parallel_groups[]` 中所有组
   - 将 `status=completed` 且 `merger_executed=true` 的组从数组中移除
   - 300章规模避免600+已完成组累积导致 state.json 膨胀

6. **state.json steps数组精简**（v2.5优化G新增）：
   - 检测 state.json 中所有 `status=completed` 的步骤
   - 若已完成步骤 > 10个（约2章），将最早步骤归档到 `auto-runner/state_history.json`
   - state.json 的 steps 数组只保留最近10个已完成步骤 + 所有未完成步骤
   - 300章规模避免 state.json 超100KB

7. **execution_log.md轮转检查**（v2.5优化H新增）：
   - 检查 `auto-runner/execution_log.md` 文件大小
   - 若 > 50KB，重命名为 `execution_log_ch{N}.md`（N为最后处理章节号）
   - 创建新的空 execution_log.md 继续记录
   - 主日志保持 < 50KB

### 执行效率估算

| 场景 | 旧方案 | 连续执行 v1 | 并行执行 v2 |
|------|--------|------------|------------|
| 预生产 | 105min | 30min | 15min |
| 角色设计 | 90min | 30min | 30min |
| 黄金三章写作 | 90min | 45min | 45min |
| 黄金三章审核 | 180min | 60min | 20min |
| 全流程22步 | 330min | 120min | 80min |

### 文件 I/O 优化策略

为配合并行调度引擎，减少文件读写开销与上下文占用：

1. **草稿文件完全消除**（v2.4优化A）：chapter-writer 步骤不再输出 `draft_ch{N}.json`（beat_sheet 元数据已在 outline.json 中，属重复存储），正文只写 `output/chapter_NNN.txt`，每章节省1文件
2. **审核源文件自动归档**（v2.4优化C）：detail_review + de_ai_analysis 被 merged_review 吸收后，自动从 `handoff/chapters/` 移到 `handoff/archive/ch{N}/` 目录，保持工作区只留最新产物（state_validator 在 State恢复后自动执行归档检查）
3. **角色库索引化**：`characters.json` 改为索引指针（指向 `memory/characters/*.json`），独立角色卡为唯一数据源
4. **recent_chapters 按需读取**：直接从 `output/` 读取章节，不维护副本，避免多源数据不一致
5. **全文文件追加+独立header**（v2.4优化E）：全文文件 header 信息（书名/进度/更新时间）分离到 `output/{novel_title}_全文_header.txt`，正文文件 `output/{novel_title}_全文.txt` 纯追加不重写，每次入库仅重写~200字 header + 追加~3KB 正文（vs 旧方案 O(N) 重写全文文件）

### 上下文优化策略 (Context Optimization) v2.2

为减少自动执行流程中的重复文件读取，降低上下文窗口消耗，引入 Skill 缓存机制与文件预读策略。预计每步节省 ~80% 上下文占用（~10000字 → ~2000字）。

**规范文件**：`auto-runner/context_optimization.md`
**预加载脚本**：`auto-runner/context_preloader.ps1`
**缓存文件**：`auto-runner/context_cache.json`

#### Skill 缓存机制

每个 Skill 的 SKILL.md 首次读取后缓存摘要（前 500 字符 + 规则数量统计），后续步骤引用缓存摘要而非重新读取完整文件（~2000-5000字）。

**缓存验证**：脚本运行时对比每个文件的 `last_modified`，时间一致则 `cache hit`（跳过重新读取），时间变更则 `cache miss`（重新读取并更新缓存）。

**指令模板缓存集成**（v2.4优化D新增）：Agent 指令模板已更新为缓存优先策略——
- `generate_task_config.ps1` 生成的每个步骤 instruction 均以 `"Read auto-runner/context_cache.json (reference cached summary for {skill}) OR Read .trae/skills/{skill}/SKILL.md if cache miss"` 开头
- `parallel_task_config_template.json` 的 `_comments` 中新增 `cache_strategy` 字段，说明缓存优先策略
- Agent 执行时优先读取缓存摘要（~500字），仅在 cache miss 或需要完整规则时回退到完整 SKILL.md（~2000-5000字）
- 预计每步节省~80%上下文占用（~10000字 → ~2000字），300章规模累计节省显著

#### 文件预读策略

| 分类 | 文件 | 预读时机 |
|------|------|---------|
| 必读文件 | outline / characters / goal_tracker / session_pointer | 任务启动时预读 |
| 按需文件 | foreshadowing_tracker / chapter_summaries / recent_chapters | 步骤执行前预读 |
| 参考文件 | novel_config / unified_review_spec / parallel_task_config_template | 按需引用 |

#### 上下文预算与降级策略

- **每步预算**：无缓存 ~10000-15000 字/步 → 有缓存 ~2000-2500 字/步（节省 ~80%）
- **降级触发**：已加载内容 > 预算上限 80% 时，从低优先级开始移除全文
- **优先级**：当前步骤 input_files（P0，不可降级）> SKILL.md 规则（P1，缓存摘要替代）> 上下文文件（P2，key 列表替代）
- **降级顺序**：参考文件全文 → 按需文件全文 → 必读文件全文 → SKILL.md 全文 → 最终保留 input_files + SKILL.md 缓存摘要

#### 缓存更新协议

- **增量更新（默认）**：对比每个文件的 `last_modified`，仅重新读取变更文件，cache hit 直接复用缓存数据
- **全量重建**：缓存文件不存在/解析失败/`cache_version` 不匹配时触发，逐个重新读取所有文件
- **运行方式**：`powershell -ExecutionPolicy Bypass -File context_preloader.ps1`（执行时间 < 3 秒）

## 错误处理

| 错误类型 | 处理方式 |
|---------|---------|
| 输入文件缺失 | 停止，记录 stop_reason |
| Skill 文件不存在 | 停止，记录 stop_reason |
| 输出文件写入失败 | 重试1次，仍失败则停止 |
| 质量门禁未通过 | 按"质量门禁自动重试"规则处理 |
| 并行组单 Agent 失败 | 标记 failed，其他 Agent 继续，合并时检查缺失项 |
| 并行组失败率 > 50% | 停止整组，记录 stop_reason |
| 执行过程中异常中断 | 下次触发时检测到 step 状态为 "running" 但 last_run 时间过久，标记为 retry |

## 日志文件格式

`execution_log.md` 是追加式日志，格式如下：

```markdown
# 自动执行日志

任务名称：[task_name]
任务描述：[task_description]
启动时间：[created_at]
时区：Asia/Shanghai

---

## [时间戳] 步骤 N/M: [步骤名]
...
```

## 状态文件格式

`state.json` 结构：

```json
{
  "task_name": "任务名称",
  "task_description": "任务描述",
  "status": "pending | running | completed | stopped",
  "created_at": "ISO 8601",
  "last_run": "ISO 8601 或 null",
  "last_run_result": "上次执行结果摘要",
  "current_step": 0,
  "total_steps": N,
  "stop_reason": "停止原因（仅 stopped 时有值）",
  "parallel_groups": [
    {
      "group_id": "char_design",
      "status": "running | completed | partial_failed",
      "total": 6,
      "completed": [],
      "failed": [],
      "merger_executed": false
    }
  ],
  "steps": [
    {
      "id": 0,
      "name": "步骤名称",
      "agent": "agent名称",
      "status": "pending | running | completed | retry",
      "retries": 0,
      "result": "执行结果摘要",
      "timestamp": "ISO 8601 或 null",
      "auto_approved": false
    }
  ]
}
```
