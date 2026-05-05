# tcc-bridge

**Telegram Claude Code Bridge** — 通过 Telegram 远程控制服务器上运行的 Claude Code。

一个 bridge 进程管理多个 Telegram Bot，每个 Bot 对应一个项目。手机上不同聊天窗口对应不同项目。

```
手机 Telegram App
      ↕ HTTPS
Telegram Bot API
      ↕ polling
tcc-bridge 服务（一个 systemd 进程）
      ├── Bot A ←→ CC 子进程（projectA）
      └── Bot B ←→ CC 子进程（projectB）
```

---

## 前置要求

- Ubuntu 22.04（或其他 systemd Linux）
- Python 3.11+
- [Claude Code CLI](https://github.com/anthropics/claude-code) 已安装并完成登录
- 每个项目对应一个 Telegram Bot Token（从 [@BotFather](https://t.me/BotFather) 创建）
- 你的 Telegram User ID（从 [@userinfobot](https://t.me/userinfobot) 查询）

---

## 安装

### 1. 克隆仓库

```bash
git clone git@github.com:ybbzbb/tcc-bridge.git
cd tcc-bridge
```

### 2. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 3. 配置 `bots.toml`

复制示例并填写：

```bash
cp bots.toml.example bots.toml
nano bots.toml
```

```toml
[[bots]]
token = "你的_bot_token_A"
allowed_user_id = 123456789        # 只有这个 Telegram ID 能控制该 bot
project_path = "/home/ubuntu/codes/projectA"
project_name = "projectA"

[[bots]]
token = "你的_bot_token_B"
allowed_user_id = 123456789
project_path = "/home/ubuntu/codes/projectB"
project_name = "projectB"
# model = "claude-sonnet-4-6"      # 可选，默认 claude-sonnet-4-6
# chunk_size = 4000                 # 可选，Telegram 单条消息最大字符数
```

每个 `[[bots]]` 块对应一个 Bot 和一个项目，数量不限。

---

## 直接运行（测试用）

```bash
python3 src/main.py
```

打开 Telegram，向对应的 bot 发送 `/start`，确认正常响应后再配置 systemd。

---

## systemd 部署（生产环境）

### 1. 复制 service 文件

```bash
sudo cp deploy/tcc-bridge.service /etc/systemd/system/
```

### 2. 编辑 service 文件

```bash
sudo nano /etc/systemd/system/tcc-bridge.service
```

修改以下字段：

```ini
User=ubuntu                                    # 改为你的用户名
WorkingDirectory=/home/ubuntu/tcc-bridge       # 改为实际路径
ExecStart=/usr/bin/python3 src/main.py         # 确认 python3 路径
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

## 添加新项目

1. 在 [@BotFather](https://t.me/BotFather) 创建新 bot，获取 token
2. 在 `bots.toml` 末尾追加一个新的 `[[bots]]` 块
3. 重启服务：`sudo systemctl restart tcc-bridge`

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

- `allowed_user_id` 白名单：非白名单用户的消息被静默忽略。
- `bots.toml` 含有 bot token，已加入 `.gitignore`，不会上传到代码仓库。
- Claude Code 以 `--dangerously-skip-permissions` 模式运行，拥有完整文件系统权限，请确保服务器安全。

---

## 常见问题

**Bot 没有响应？**
- 检查 `token` 是否正确
- 检查 `allowed_user_id` 是否是你自己的 ID
- 查看日志：`journalctl -u tcc-bridge -f`

**Claude Code 启动失败？**
- 确认 `claude` 命令可用：`which claude`
- 确认已登录：`claude --version`
- 确认 `project_path` 路径存在

---

## License

MIT
