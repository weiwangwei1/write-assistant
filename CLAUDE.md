# 项目共享规则（来自 AGENTS.md，跨工具统一）
@AGENTS.md

# Claude Code 专属补充

> 本节仅收录 Claude Code 专属的补充与快速索引；共享规则全部以 AGENTS.md 为准（上方导入），冲突时按 AGENTS.md 执行。

## 快速索引（会话入口）
- 会话开始先读 `memory/session_pointer.json`（当前进度 / 下一步 / 待决项），汇报后再继续
- 系统总纲 `AGENTS.md` ｜ 18 个角色规则 `.trae/skills/*/SKILL.md` ｜ 门禁脚本（根目录）：`style_lint.py` / `fix_auditor.py` / `style_fingerprint.py` / `emotion_curve.py` 等
- 在产项目《第三纪元》：正文 `output/` ｜ 过程卡与证据 `handoff/` ｜ 记忆 `memory/`

## 运行环境
- Windows + PowerShell；无构建步骤、无包管理器——不要引入 npm/pip 依赖，不要创建 `package.json` / `pyproject.toml`
- Python 脚本只依赖标准库；解释器未加入 PATH，须全路径调用：`C:\Users\王伟\AppData\Local\Programs\Python\Python313\python.exe`
- 中文路径与 PowerShell 引号易踩坑：复杂命令先写成临时脚本文件再执行，避免长引号拼接

## “测试”的定义（无测试框架）
- “测试” = 门禁脚本退出码 + 评审交接卡（本项目没有单元测试框架）
- 不要在 `test/` 下写 pytest 用例（该目录为实验与原则库区域）

## 提交规范
- 提交信息遵循 Conventional Commits（中文、简洁）
- git 远程操作一律使用 SSH（不使用 HTTPS + 密码）；不提交密钥 / 凭据类文件

## 写作与文件易错点
- 规则、文档、交接卡一律用中文；JSON 统一 `ensure_ascii=False` + UTF-8
- 章节正文不得使用 Markdown 标记（分段排版，单段 ≤200 字）
- `memory/`、`handoff/` 是多个 Agent 的共享事实源：改动时保持既有 schema 与字段命名，不随意重构