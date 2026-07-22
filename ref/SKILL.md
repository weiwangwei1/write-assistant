---
name: context-recovery
description: Trae IDE 上下文压缩防跑偏 Skill —— 新对话开局自动恢复任务上下文，避免 AI 因压缩丢失历史而跑偏
version: 1.0.0
author: 路遥 + 阿怪
---

# 上下文压缩防跑偏 Skill

## 目的

Trae IDE 在长对话时会自动压缩历史，导致 AI 丢失：
- 之前讨论过的需求和决策
- 已完成的代码修改
- 正在进行的任务进度
- 用户的偏好和约束

本 Skill 通过"三层记忆 + 开局检查"机制，确保 AI 在新对话或压缩后能正确恢复上下文。

## 三层记忆架构

```
Layer 1: 项目记忆（project_memory.md）     ← 项目级规则、约束、当前指针
   ↓
Layer 2: 日期主题（YYYYmmdd/topics.md）   ← 每日会话摘要、决策记录
   ↓
Layer 3: 会话记忆（session_memory_*.jsonl） ← 消息级细节、TODO、文件路径
```

### Layer 1: project_memory.md
**位置**：`memory/projects/<project-slug>/project_memory.md`

**内容**：
- 项目目标和架构决策
- 关键约束（铁律、防跑偏机制）
- ★ 当前任务指针（每次对话开始时必须更新）
- 完成进度清单
- 教训与注意事项

**示例**：
```markdown
## ★ 当前任务指针（每次对话开始时确认）
- 当前活动子任务：T5 Skill 系统开发
- 当前子任务进度：T1-T4 完成，T5 进行中（50%）
- 上次对话产出：Skill YAML 加载机制完成
- 下一步：Skill 触发词匹配 + 模型路由

## 教训与注意事项
- 2026-07-15：smart-ops-optical 必须有 dependency.yaml，否则构建失败
- 2026-07-15：ci.yaml 的 sed 命令必须用 \\\${ 转义美元符号
```

### Layer 2: topics.md（按日期）
**位置**：`memory/projects/<project-slug>/<YYYYmmdd>/topics.md`

**内容**：
- 当日所有会话的主题摘要
- 每个 session 的关键决策和产出
- session_id 用于追溯细节

**示例**：
```markdown
[session_id: 6a57289d0e4b4efce63b96ad | topic_summary_time: 2026-07-15 15:18:49]
用户启动收费模块抽离迁移任务，要求魔改 smart-ops-optical 为商云收费插件。
关键决策：保留 optical 插件 ID/artifactId/包名，Java 包路径改为 smartopsoptical，
device 禁用方式为不编译（代码保留）。
```

### Layer 3: session_memory_*.jsonl
**位置**：`memory/projects/<project-slug>/<YYYYmmdd>/session_memory_<session_id>.jsonl`

**内容**：
- 消息级细节（JSONL 格式，每行一个 JSON）
- TODO 列表、相关文件路径
- 关键代码片段

## ★ 开局检查清单（每次新对话必须执行）

当用户开启新对话或你感到上下文丢失时，**必须**按以下顺序执行：

### Step 1: 读取 project_memory.md
```
读取 memory/projects/<project-slug>/project_memory.md
```
**重点提取**：
- 当前任务指针（"当前活动子任务"）
- 上次对话产出
- 下一步建议
- 关键约束和铁律

### Step 2: 读取最近 topics.md
```
读取 memory/projects/<project-slug>/<最近日期>/topics.md
```
**重点提取**：
- 最近的 session_id
- 当日关键决策
- 跨会话的连续性线索

### Step 3: 读取 PROGRESS.md（如果存在）
```
读取 <project>/docs/PROGRESS.md
```
**重点提取**：
- 当前活动任务的状态
- 已完成和进行中的步骤

### Step 4: 读取上一个交接卡（如果存在）
```
读取 <project>/docs/handover/T{n-1}_handover.md
```

### Step 5: 向用户汇报当前指针
**必须**用一段话告诉用户：
> "当前任务是 {T{n}}，进行到第 {X} 步，上次产出是 {产出}，下一步计划是 {计划}。是否继续？"

**示例**：
> "当前任务是收费模块抽离迁移，已完成 6 步实施，optical PS4 已 +1，device PS2 已 @WONTFIX。
> 下一步是找同事 +2 merge 两个 change 并部署商云验证。是否继续？"

## ★ 关键规则

### 规则 1：不主动结束对话
- 即使任务看似完成，也必须继续询问用户下一步
- 任务完成后主动提议：进入下一子任务 / Review / 优化文档 / 其他工作

### 规则 2：每次回复必须以 AskUserQuestion 结尾
- 不允许用纯文字结束语
- 给用户明确的选项引导对话继续

### 规则 3：立即更新任务指针
- 每次任务有重大进展时，**立即**更新 project_memory.md 的"当前任务指针"
- 包括：当前活动子任务、当前进度、上次产出、下一步建议

### 规则 4：写入而非依赖对话历史
- 所有重要决策、文件路径、教训都写入记忆文件
- 不要假设下次对话能记住本次的内容

### 规则 5：分层降级恢复
- 如果 project_memory.md 不存在 → 询问用户
- 如果 topics.md 不存在 → 用 project_memory.md 兜底
- 如果都不存在 → 明确告诉用户"我没有找到历史记忆，请告诉我当前任务"

## ★ 常见跑偏场景与对策

### 场景 1：AI 忘记之前的决策
**症状**：用户说"按我们之前讨论的方案做"，AI 问"什么方案？"

**对策**：
1. 立即读取 project_memory.md 和最近 topics.md
2. 如果还找不到，问用户"能否提示一下大概是哪个方面的决策？"
3. 恢复后，立即把决策写入 project_memory.md

### 场景 2：AI 重复已完成的工作
**症状**：AI 又开始做已经完成的步骤

**对策**：
1. 开局检查时必须读取 PROGRESS.md 或当前任务指针
2. 汇报指针时明确"已完成 X 步，下一步是 Y"
3. 用户纠正后，更新指针并写入记忆

### 场景 3：AI 丢失用户的偏好
**症状**：用户说"按我喜欢的方式做"，AI 用了不同的方式

**对策**：
1. 读取 user_profile.md（用户级偏好）
2. 读取 project_memory.md 的"关键约束"
3. 恢复后，把新发现的偏好立即写入 user_profile.md

### 场景 4：AI 在长对话中段丢失前文
**症状**：对话进行中，AI 突然说"我不记得我们之前讨论过什么"

**对策**：
1. 这是上下文压缩的典型症状
2. 立即触发开局检查清单
3. 向用户说明："我感觉上下文被压缩了，让我重新读取记忆恢复..."
4. 恢复后继续任务

## ★ 记忆文件写入时机

### 立即写入的情况
- 用户明确说"记住这个"或"写入长期记忆"
- 完成一个子任务或重要里程碑
- 发现一个重要的教训或约束
- 用户表达了新的偏好或习惯

### 写入位置选择
- **用户偏好** → `memory/user_profile.md`（跨项目）
- **项目规则** → `memory/projects/<slug>/project_memory.md`
- **当日进展** → `memory/projects/<slug>/<YYYYmmdd>/topics.md`
- **细节决策** → 同时更新 project_memory.md 和 topics.md

### 写入格式
- 用 Markdown，结构清晰
- 包含日期（YYYY-MM-DD）
- 包含 session_id（用于追溯）
- 用 ★ 标记关键规则

## ★ 示例：完整的开局恢复流程

```
用户: "继续"

AI 内部流程:
1. 读取 memory/projects/-d-...-ai-assistant/project_memory.md
   → 提取：当前任务是收费模块抽离迁移，6 步全部完成
   → 提取：optical PS4 +1，device PS2 @WONTFIX
   → 提取：下一步是找同事 merge

2. 读取 memory/projects/-d-...-ai-assistant/20260715/topics.md
   → 提取：最近 session 讨论了 SonarQube 违规修复

3. 读取 d:\...\ai-assistant\docs\PROGRESS.md
   → 提取：6 步进度标记为 ✅

4. 读取 docs/handover/charge-module-migration_handover.md
   → 提取：详细的实施记录

5. 向用户汇报：
   "当前任务是收费模块抽离迁移，6 步已完成，optical PS4 已 +1，
    device PS2 已 @WONTFIX。下一步是找同事 +2 merge 并部署商云。
    是否继续？"
```

## ★ 与其他 Skill 的协作

- **luyao_identity**：身份注入（路遥），负责"你是谁"
- **context-recovery**（本 Skill）：记忆恢复，负责"我们在哪"
- 两者配合：路遥身份 + 当前任务指针 = 完整上下文

## ★ 故障排查

### 问题：记忆文件路径找不到
**排查**：
1. 确认项目 slug：`memory/projects/` 下的目录名是项目路径的转义（如 `-d-UserData----desktop---job-ai-assistant`）
2. 确认日期格式：`YYYYmmdd`（如 `20260715`）
3. 用 LS 工具列出 `memory/projects/` 查看实际存在的项目

### 问题：读取的记忆内容过时
**排查**：
1. 检查文件修改时间（LS 工具会显示）
2. 读取最近日期的 topics.md（可能跨天）
3. 如果内容冲突，以最新文件为准

### 问题：用户说"你不记得了"但记忆里有
**排查**：
1. 可能是压缩导致当前对话没有加载记忆
2. 立即执行开局检查清单
3. 向用户确认："我读取到...（复述记忆内容），是这个吗？"

## ★ 维护建议

- **每日清理**：定期清理过期的 session_memory_*.jsonl（保留最近 7 天）
- **每周归档**：把 topics.md 中的关键决策合并到 project_memory.md
- **每月审查**：检查 project_memory.md 的"当前任务指针"是否准确
- **及时更新**：任务状态变化时立即更新，不要攒到最后

## ★ 快速参考卡

```
新对话开局 5 步：
1. Read project_memory.md → 提取当前任务指针
2. Read topics.md (最近日期) → 提取当日进展
3. Read PROGRESS.md → 确认任务状态
4. Read handover (如果存在) → 接续上下文
5. 向用户汇报："当前任务是 X，进度 Y，下一步 Z"

立即写入记忆的情况：
- 用户说"记住" → 立即写
- 完成任务 → 立即更新指针
- 发现教训 → 立即记录
- 用户偏好 → 立即写入 user_profile.md

分层降级：
- project_memory.md 不存在 → 问用户
- topics.md 不存在 → 用 project_memory 兜底
- 都没有 → 明确告诉用户"没有历史记忆"
```
