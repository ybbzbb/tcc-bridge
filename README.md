# tcc-bridge

**QQ Claude Code Bridge** — 通过 QQ 远程控制服务器上运行的 Claude Code。

一个 bridge 进程管理多个 Bot，每个 Bot 对应一个项目。

```
手机 QQ App
      ↕ WebSocket
QQ 官方机器人 API
      ↕
tcc-bridge 服务（一个 systemd 进程）
      ├── Bot A ←→ Agent SDK session（projectA）
      └── Bot B ←→ Agent SDK session（projectB）
```

使用 Claude Agent SDK 与 Claude 交互，支持持久多轮会话。

---

## 前置要求

- Ubuntu 22.04（或其他 systemd Linux）
- Python 3.10+
- QQ 机器人 App ID 和 App Secret（从 [q.qq.com](https://q.qq.com) 申请，个人开发者可注册）

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

配置示例：

```toml
[[bots]]
qq_app_id = "your_app_id"
qq_app_secret = "your_app_secret"
allowed_qq_openid = "user_openid"
project_path = "/home/ubuntu/codes/projectA"
project_name = "projectA"
model = "mimo-v2.5-pro"
api_url = "https://your-api-endpoint/v1"
api_key = "your-api-key"
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
make log      # 实时追踪日志
```

或者直接在前台运行：

```bash
python3 src/main.py
```

---

## systemd 部署（生产环境）

```bash
sudo cp deploy/tcc-bridge.service /etc/systemd/system/
sudo nano /etc/systemd/system/tcc-bridge.service  # 修改路径和用户
sudo systemctl daemon-reload
sudo systemctl enable tcc-bridge
sudo systemctl start tcc-bridge
```

查看日志：

```bash
sudo journalctl -u tcc-bridge -f
```

---

## 命令列表

| 命令 | 说明 |
|------|------|
| `/start` | 启动 Claude Code session |
| `/stop` | 关闭 Claude Code session |
| `/restart` | 重启 session（清空上下文） |
| `/cancel` | 取消当前正在处理的消息 |
| `/status` | 查看当前状态 |
| `/help` | 显示帮助 |

**非 `/` 开头的消息**直接透传给 Claude Code，等同于在终端里输入。

---

## 安全说明

- 白名单机制：只有指定用户能控制 bot。
- `bots.toml` 含有密钥，生产环境建议放在 `/etc/tcc-bridge/bots.toml`，不要跟代码放在一起。
- Agent SDK 以 `permission_mode="acceptEdits"` 运行，预授权文件读写和命令执行，请确保服务器安全。

---

## 常见问题

**Bot 没有响应？**
- 检查配置是否正确
- 检查白名单 ID 是否匹配
- 查看日志：`journalctl -u tcc-bridge -f`

**Claude Agent SDK 启动失败？**
- 确认已安装：`pip3 show claude-agent-sdk`
- 确认 API Key 已配置
- 确认 `project_path` 路径存在

---

## License

MIT
