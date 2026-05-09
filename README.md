# tcc-bridge

**Telegram Claude Code Bridge** — 通过 Telegram 远程控制服务器上运行的 Claude Code。

一个 bridge 进程管理多个 Telegram Bot，每个 Bot 对应一个项目。手机上不同聊天窗口对应不同项目。

```
手机 Telegram App
      ↕ HTTPS
Telegram Bot API（或 CF Worker 代理）
      ↕ polling
tcc-bridge 服务（一个 systemd 进程）
      ├── Bot A ←→ Agent SDK session（projectA）
      └── Bot B ←→ Agent SDK session（projectB）
```

使用 Claude Agent SDK 与 Claude 交互，支持持久多轮会话。

---

## 前置要求

- Ubuntu 22.04（或其他 systemd Linux）
- Python 3.11+
- Python 包 `claude-agent-sdk`（通过 `pip install -r requirements.txt` 安装）
- 每个项目对应一个 Telegram Bot Token（从 [@BotFather](https://t.me/BotFather) 创建）
- 你的 Telegram User ID（从 [@userinfobot](https://t.me/userinfobot) 查询）

---

## 第一步：准备 Telegram Bot

### 创建 Bot，获取 Token

1. Telegram 搜索 `@BotFather`，发送 `/newbot`
2. 输入 Bot 显示名称（随意，如 `My Project Bridge`）
3. 输入 Bot 用户名（全局唯一，必须以 `_bot` 结尾，如 `myproject_cc_bot`）
4. 成功后 BotFather 回复 Token，格式如下，复制保存：

```
123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> **安全提示：** Token 等同于密码，不要发给任何人、不要提交到代码仓库。

### 获取你的 Telegram User ID

1. Telegram 搜索 `@userinfobot`
2. 发送任意消息
3. 机器人回复中的 `Id` 字段就是你的 User ID（纯数字）

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

推荐把配置文件放在项目外，例如 `/etc/tcc-bridge/bots.toml`。

复制示例并填写：

```bash
sudo mkdir -p /etc/tcc-bridge
sudo cp bots.toml.example /etc/tcc-bridge/bots.toml
sudo nano /etc/tcc-bridge/bots.toml
```

```toml
[[bots]]
token = "你的_bot_token_A"
allowed_user_id = 123456789        # 只有这个 Telegram ID 能控制该 bot
project_path = "/home/ubuntu/codes/projectA"
project_name = "projectA"
model = "claude-sonnet-4-6"        # 可选，默认 claude-sonnet-4-6
api_url = "https://your-endpoint/v1"  # 可选，自定义 API 地址（ANTHROPIC_BASE_URL）
api_key = "your-api-key"              # 可选，自定义 API Key（ANTHROPIC_API_KEY）

[[bots]]
token = "你的_bot_token_B"
allowed_user_id = 123456789
project_path = "/home/ubuntu/codes/projectB"
project_name = "projectB"
# api_url / api_key 不填则使用系统环境变量或 Claude Code 默认配置
# chunk_size = 4000                 # 可选，Telegram 单条消息最大字符数
```

每个 `[[bots]]` 块对应一个 Bot 和一个项目，数量不限。

程序默认读取项目根目录的 `bots.toml`。如果设置了环境变量 `TCC_BRIDGE_CONFIG`，则优先读取该路径。

---

## 直接运行（测试用）

使用 `make` 命令管理进程：

```bash
make start    # 后台启动
make stop     # 停止服务
make restart  # 重启服务
make status   # 查看是否在运行
make log    # 实时追踪日志，Ctrl+C 退出 
```

或者直接在前台运行（日志实时输出到终端）：

```bash
python3 src/main.py
```

打开 Telegram，向对应的 bot 发送 `/start`，确认正常响应后再配置 systemd。

---

## systemd 部署（生产环境）

如果你是在全新 Ubuntu 22.04 服务器上部署，仓库内已经提供一键脚本：

```bash
chmod +x deploy/install_ubuntu22.sh
./deploy/install_ubuntu22.sh
```

脚本会自动安装 `python3` / `python3-venv`、创建 `.venv`、安装依赖、在 `/etc/tcc-bridge/bots.toml` 生成配置文件、写入 systemd service 并启动服务。

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
Group=ubuntu                                   # 改为你的用户组
WorkingDirectory=/opt/tcc-bridge               # 改为实际路径
Environment=TCC_BRIDGE_CONFIG=/etc/tcc-bridge/bots.toml
EnvironmentFile=-/opt/tcc-bridge/.env
ExecStart=/opt/tcc-bridge/.venv/bin/python /opt/tcc-bridge/src/main.py
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

## 中国服务器：Cloudflare Workers 代理 Telegram API

如果服务器在中国大陆，无法直连 `api.telegram.org`，可部署一个 Cloudflare Worker 作为反向代理。

### 1. 部署 CF Worker

```bash
cd cf-worker
npx wrangler login
npx wrangler deploy
```

部署后获得 URL，格式如：`https://tg-proxy.your-domain.workers.dev`

### 2. （可选）设置鉴权密钥

```bash
npx wrangler secret put TCC_KEY
# 输入一个随机字符串作为密钥
```

### 3. 配置 bots.toml

```toml
[[bots]]
token = "123456:ABC..."
allowed_user_id = 12345678
project_path = "/home/user/project"
project_name = "my-project"
telegram_api_url = "https://tg-proxy.your-domain.workers.dev"
telegram_api_key = "your-tcc-key"  # 与 CF Worker 的 TCC_KEY 一致，未设置 TCC_KEY 则不填
```

重启服务即可：`sudo systemctl restart tcc-bridge`

---

## 添加新项目

1. 在 [@BotFather](https://t.me/BotFather) 创建新 bot，获取 token
2. 在 `/etc/tcc-bridge/bots.toml` 末尾追加一个新的 `[[bots]]` 块
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
- `bots.toml` 含有 bot token，生产环境建议放在 `/etc/tcc-bridge/bots.toml`，不要跟代码放在一起。
- Agent SDK 以 `permission_mode="acceptEdits"` 运行，预授权文件读写和命令执行，请确保服务器安全。

---

## 常见问题

**Bot 没有响应？**
- 检查 `token` 是否正确
- 检查 `allowed_user_id` 是否是你自己的 ID
- 查看日志：`journalctl -u tcc-bridge -f`

**Claude Agent SDK 启动失败？**
- 确认已安装：`pip3 show claude-agent-sdk`
- 确认 `ANTHROPIC_API_KEY` 已配置（环境变量或 `bots.toml` 中的 `api_key`）
- 确认 `project_path` 路径存在

---

## License

MIT
