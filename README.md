# AI 写作团队 — 番茄小说多智能体协作系统

## 项目简介

基于 TRAE Work 的多智能体小说创作系统，通过 7 个专业化 Agent 协作完成从大纲构思到章节写作的全流程，面向番茄小说平台发布。

## Agent 角色

| Agent | Skill 名称 | 职责 |
|-------|-----------|------|
| 总编 | chief-editor | 全局编排、任务分发、进度管理 |
| 大纲师 | plot-architect | 故事大纲、情节线、爽点分布 |
| 质疑者 | skeptic | 大纲批判性质疑与迭代优化 |
| 大纲编辑 | outline-editor | 大纲6维度评分验收、角色卡审核 |
| 设定审核员 | setting-reviewer | 世界观设定6维度评分（地图/图鉴/机制），循环至9.5 |
| 角色师 | character-designer | 人物设定、关系网、成长弧线 |
| 写手 | chapter-writer | 章节内容生成 |
| 细节控 | detail-reviewer | 逐句/逐梗/逐伏笔/逐逻辑微观打磨 |
| 审稿员 | quality-reviewer | 一致性检查、质量评分、反馈，循环至9.5 |
| 去AI化师 | de-ai-processor | 消除AI写作痕迹、人性化语言 |
| 适配师 | fanqie-adapter | 爽点注入、节奏调整、审核合规 |
| 记忆管家 | memory-manager | 上下文管理、摘要生成、滑动窗口 |
| 人工检查点 | human-checkpoint | 关键节点人工审核与反馈 |

## 目录结构

```
d:\write-assistant\
├── config/           # 小说配置
├── handoff/          # 交接卡（Agent 间通信）
├── memory/           # 记忆系统（分级存储）
├── output/           # 终稿输出
├── .trae/skills/     # 7 个 Agent Skill
├── logs/             # 写作日志
└── README.md
```

## 作者文风包（writer-styles）

`.trae/skills/writer-styles/` 收录蒸馏的作者文风（原 writeStyle 仓库，已并入本仓库维护）。
每包三件套：`style_card.md`（决策卡，每章注入）+ `fingerprint.json`（文体指纹基线）+ `lint_overlay.json`（lint覆盖层）。
已收录：辰东（chendong）、烟雨江南（yanyujiangnan）。

在 `config/novel_config.json` 设 `"style_pack": "yanyujiangnan"` 即可挂载，详见 `.trae/skills/writer-styles/README.md`。

配套脚本：
- `style_lint.py`：文风硬约束校验（提交前门禁，`--style` 加载覆盖层）
- `style_fingerprint.py`：文体指纹提取（build）与偏差校验（check）

## 工作流程

1. **初始化**: 用户配置 → 总编解析 → 大纲师生成大纲 → 质疑者迭代 → 大纲编辑评分 → 人工检查点 → 角色师创建角色卡 → 角色卡审核 → 人工检查点 → 创建世界观设定文件（地图/图鉴/机制）→ 设定审核员评分（循环至9.5）→ 人工检查点 → 进入章节循环
2. **章节循环**: 写手生成初稿（先分镜后正文）→ 细节控微观打磨 → 审稿员宏观评分（循环至9.5）→ 去AI化师处理 → 适配师处理 → 记忆管家更新
3. **发布**: 终稿存入 output/ → 番茄发布

## 定时任务

- 日更写作: 每日 09:00 自动生成章节
- 进度检查: 每日 08:00 扫描交接卡状态
- 周度复盘: 每周日 10:00 质量分析与 Skill 优化

## 使用方式

1. 编辑 `config/novel_config.json` 设置小说参数
2. 对话中输入"开始写第N章"触发写作流程
3. 或等待定时任务自动执行
