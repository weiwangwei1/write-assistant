# 项目共享规则（来自 AGENTS.md，跨工具统一）
@AGENTS.md

# 以下是仅给 Claude Code 的专属补充
- 本项目无构建步骤、无包管理器：不要引入 npm/pip 依赖，不要创建 `package.json` / `pyproject.toml`
- Python 脚本只依赖标准库；当前解释器为 `C:\Users\王伟\AppData\Local\Programs\Python\Python313\python.exe`（未加入 PATH，`python` 命令可能不可用）
- "测试"= 门禁脚本退出码 + 评审交接卡，没有单元测试框架，不要写 `test/` 下的 pytest 用例
- 提交信息遵循 Conventional Commits