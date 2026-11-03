# GitHub 新机推送仓库清单

> 适用场景：在一台新电脑上，把一个本地项目推送到你的 GitHub（账号 `weiwangwei1`）。
> 全程使用 **SSH** 方式（不用 HTTPS + 密码），更稳定且无需每次输凭据。

---

## 一、所需信息汇总（推送前先备齐）

### 1. 一次性准备（每台新电脑只需做一次）

| 所需信息 | 说明 | 来源 |
|---------|------|------|
| GitHub 账号 | 用户名 `weiwangwei1` | GitHub 账户 |
| 本机 SSH 密钥对 | `~/.ssh/id_rsa` + `id_rsa.pub` | 新电脑需用 `ssh-keygen` 重新生成 |
| 公钥已添加到 GitHub | 把 `id_rsa.pub` 内容贴到账户 | GitHub 网页：Settings → SSH and GPG keys |
| Git 身份信息（建议） | `user.name` / `user.email` | 你的姓名 + 邮箱 |

### 2. 每个仓库需要的信息

- **本地仓库路径**（项目文件夹在哪）
- **仓库名**（GitHub 上对应的仓库名）
- **远端地址（SSH 形式）**：`git@github.com:weiwangwei1/<仓库名>.git`
- **默认分支名**：新推一般用 `main`

---

## 二、操作步骤

### 第 1 步：生成 SSH 密钥（新电脑首次）

```powershell
ssh-keygen -t rsa -b 4096 -C "你的github邮箱"
# 一路回车，默认保存到 ~/.ssh/id_rsa
```

### 第 2 步：查看公钥并添加到 GitHub

```powershell
cat ~/.ssh/id_rsa.pub
```

复制整段内容，粘贴到 GitHub → **Settings → SSH and GPG keys → New SSH key**。

### 第 3 步：首次连接信任主机

```powershell
ssh-keyscan -t rsa,ecdsa,ed25519 github.com >> "$env:USERPROFILE\.ssh\known_hosts"
```

### 第 4 步：测试 SSH 连接

```powershell
ssh -T git@github.com
# 看到 "Hi weiwangwei1!" 即连接成功
```

### 第 5 步：配置 git 使用系统 SSH（中文用户名必做）

> Windows 用户名含中文（如 `C:\Users\王伟\`）时，Git 自带的 OpenSSH 会把 UTF-8 当 GBK 解析，导致找不到 `~/.ssh` 密钥。必须强制用系统 SSH：

```powershell
git config core.sshCommand "C:/Windows/System32/OpenSSH/ssh.exe"   # 正斜杠
```

### 第 6 步：在项目目录内初始化并推送

```powershell
cd "你的项目文件夹"
git init
git add -A
git commit -m "first commit"
git branch -M main
git remote add origin git@github.com:weiwangwei1/<仓库名>.git
git push -u origin main
```

> 若 GitHub 上还没有仓库，应先在 GitHub 网页 **New repository** 新建同名空仓库（不要勾选任何初始化选项），或用 `gh repo create` 创建。

---

## 三、常见报错与修复

| 报错 | 原因 | 修复 |
|------|------|------|
| `'git' 不是内部或外部命令` | git 不在 PATH | 用完整路径：`F:\software\git\Git\bin\git.exe` |
| `Host key verification failed` | known_hosts 未信任 | 执行第 3 步 `ssh-keyscan` |
| `Permission denied (publickey)` | 公钥未添加或密钥路径不对 | 检查第 2、4 步 |
| `找不到 ~/.ssh/id_rsa` | 中文用户名编码坑 | 执行第 5 步强制系统 SSH |

---

## 四、一键脚本（把上面命名替换后整段粘贴）

```powershell
# ===== 根据实际修改这三项 =====
$REPO_NAME = "你的仓库名"
$PROJECT_DIR = "你的项目路径"
$GIT_EXE = "$env:ProgramFiles\Git\bin\git.exe"

# ===== 执行 =====
cd $PROJECT_DIR
& $GIT_EXE init
& $GIT_EXE add -A
& $GIT_EXE commit -m "first commit"
& $GIT_EXE branch -M main
& $GIT_EXE remote remove origin 2>$null   # 已有则先移除
& $GIT_EXE remote add origin "git@github.com:weiwangwei1/$REPO_NAME.git"
& $GIT_EXE push -u origin main
```

---

*整理时间：2026-09-09 · 账号 weiwangwei1 · SSH 推送方式*