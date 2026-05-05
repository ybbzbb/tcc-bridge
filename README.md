# tcc-bridge

**Telegram Claude Code Bridge** — 通过 Telegram 远程控制服务器上运行的 Claude Code。

在手机 Telegram 里发消息 → 服务器上的 Claude Code 执行 → 输出实时回传到手机。

---

## 工作原理

```
手机 Telegram App
      ↕ HTTPS
Telegram Bot API
      ↕ polling
tcc-bridge 服务（systemd 常驻）
      ↕ stdin/stdout pipe
Claude Code CLI 子进程
      ↕ 文件系统
目标项目目录
```

**一个 Bot 绑定一个项目**。多个项目时部署多个 Bot 实例，手机上不同聊天窗口对应不同项目。

---

## 前置要求

- Ubuntu 22.04（或其他 systemd Linux）
- Python 3.11+
- [Claude Code CLI](https://github.com/anthropics/claude-code) 已安装并完成登录
- Telegram Bot Token（从 [@BotFather](https://t.me/BotFather) 创建）
- 你的 Telegram User ID（从 [@userinfobot](https://t.me/userinfobot) 查询）

---

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/YOUR_USERNAME/tcc-bridge.git
cd tcc-bridge
```

### 2. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 3. 配置 `.env`

复制示例配置文件并填写：

```bash
cp .env.example .env
nano .env
```

```env
# Telegram
TELEGRAM_BOT_TOKEN=你的_bot_token
TELEGRAM_ALLOWED_USER_ID=你的_user_id   # 只有这个 ID 能控制 bot

# 项目
PROJECT_PATH=/home/ubuntu/codes/myproject   # Claude Code 工作的项目路径
PROJECT_NAME=myproject                       # 显示名称

# Claude Code
CC_MODEL=claude-sonnet-4-6

# 输出
MESSAGE_CHUNK_SIZE=4000
```

---

## 直接运行（测试用）

```bash
python3 src/main.py
```

打开 Telegram，向你的 bot 发送 `/start`，确认能正常收到响应后再配置 systemd。

---

## systemd 部署（生产环境）

### 1. 复制 service 文件

```bash
sudo cp deploy/tcc-bridge.service /etc/systemd/system/
```

### 2. 编辑 service 文件，修改路径

```bash
sudo nano /etc/systemd/system/tcc-bridge.service
```

根据实际情况修改以下字段：

```ini
User=ubuntu                                    # 改为你的用户名
WorkingDirectory=/home/ubuntu/tcc-bridge       # 改为实际路径
ExecStart=/usr/bin/python3 src/main.py         # 确认 python3 路径
EnvironmentFile=/home/ubuntu/tcc-bridge/.env  # 改为 .env 实际路径
```

### 3. 启动服务

```bash
sudo systemctl daemon-reload
sudo systemctl enable tcc-bridge
sudo systemctl start tcc-bridge
```

### 4. 查看日志

```bash
sudo journalctl -u tcc-bridge -f
```

---

## 多项目部署

每个项目独立一套 `.env` 和 service 文件：

```bash
# 项目 A
sudo cp deploy/tcc-bridge.service /etc/systemd/system/tcc-bridge-projecta.service
# 编辑 EnvironmentFile 指向 /home/ubuntu/tcc-bridge-projecta/.env

# 项目 B
sudo cp deploy/tcc-bridge.service /etc/systemd/system/tcc-bridge-projectb.service
# 编辑 EnvironmentFile 指向 /home/ubuntu/tcc-bridge-projectb/.env
```

---

## Telegram 命令

| 命令 | 说明 |
|------|------|
| `/start` | 启动 Claude Code session |
| `/stop` | 关闭 Claude Code session |
| `/restart` | 重启 session（清空上下文） |
| `/status` | 查看当前状态 |
| `/help` | 显示帮助 |

**非 `/` 开头的消息**直接透传给 Claude Code，等同于在终端里输入。

---

## 安全说明

- `TELEGRAM_ALLOWED_USER_ID` 白名单：非白名单用户的消息被静默忽略。
- `.env` 文件已加入 `.gitignore`，不会上传到代码仓库。
- Claude Code 以 `--dangerously-skip-permissions` 模式运行，拥有完整文件系统权限，请确保服务器安全。

---

## 常见问题

**Bot 没有响应？**
- 检查 `TELEGRAM_BOT_TOKEN` 是否正确
- 检查 `TELEGRAM_ALLOWED_USER_ID` 是否是你自己的 ID
- 查看日志：`journalctl -u tcc-bridge -f`

**Claude Code 启动失败？**
- 确认 `claude` 命令在服务器上可用：`which claude`
- 确认 Claude Code 已登录：`claude --version`
- 确认 `PROJECT_PATH` 路径存在

**消息被截断？**
- 调整 `MESSAGE_CHUNK_SIZE`（默认 4000，Telegram 单条上限 4096）

---

## License

MIT
