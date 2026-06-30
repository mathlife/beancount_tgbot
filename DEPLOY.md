# TG_bot 部署指南 (更新版)

本指南适用于 Armbian/Debian 系统部署，已更新至包含最新的稳定性增强功能。

---

## 1. 系统要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Debian/Ubuntu/Armbian |
| Python | 3.10 - 3.11 (推荐 3.11) |
| 内存 | ≥ 512MB |
| 磁盘 | ≥ 500MB |

### 安装系统依赖

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-dev build-essential git
```

> [!WARNING]
> **Python 版本警告**：如果系统自带 Python 3.12+，beancount 可能编译失败。
> 请安装 Python 3.11：
> ```bash
> sudo apt install python3.11 python3.11-venv python3.11-dev
> ```

---

## 2. 获取代码

```bash
cd /opt
sudo git clone <your-repo-url> tg_bot
sudo chown -R $USER:$USER /opt/tg_bot
cd /opt/tg_bot
```

---

## 3. Python 环境配置

```bash
# 使用 Python 3.11 创建虚拟环境
python3.11 -m venv .venv
source .venv/bin/activate

# 升级 pip 并安装依赖
pip install --upgrade pip
pip install -r requirements.txt

# 安装测试框架（可选）
pip install pytest
```

---

## 4. 配置文件

### 4.1 环境变量

```bash
cp config/.env.example config/.env
nano config/.env
```

填写以下变量：
```ini
TELEGRAM_BOT_TOKEN=your_bot_token_here
ALLOWED_USER_ID=your_telegram_user_id
GEMINI_API_KEY=your_gemini_api_key
```

### 4.2 应用配置

编辑 `config/settings.yaml`：
```yaml
aliases:
  "饭": "Expenses:Food"
  "咖啡": "Expenses:Drink"
  # ... 其他别名

system:
  currency: "CNY"
  bean_file: "data/main.bean"
  append_file: "data/2026.bean"
```

### 4.3 数据目录

```bash
mkdir -p data/logs data/backups
touch data/main.bean data/2026.bean
```

> [!NOTE]
> **新增目录说明**：
> - `data/logs/` - 交易日志存储位置
> - `data/backups/` - 自动备份存储位置

---

## 5. 目录结构

```
/opt/tg_bot/
├── main.py                 # 入口脚本
├── config/
│   ├── .env                # 环境变量
│   └── settings.yaml       # 应用配置
├── data/
│   ├── main.bean           # Beancount 主文件
│   ├── 2026.bean           # 当年交易文件
│   ├── logs/               # [NEW] 交易日志
│   └── backups/            # [NEW] 自动备份
├── src/
│   ├── bot/                # Bot 模块
│   ├── core/               # 核心逻辑
│   ├── models/             # 数据模型
│   └── utils/              # 工具模块
└── tests/                  # 单元测试
```

---

## 6. Systemd 服务配置

创建服务文件：
```bash
sudo nano /etc/systemd/system/tg_bot.service
```

```ini
[Unit]
Description=Telegram Beancount Bot
After=network.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/opt/tg_bot
ExecStart=/opt/tg_bot/.venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# 环境变量（可选，如果不使用 .env 文件）
# Environment=TELEGRAM_BOT_TOKEN=xxx

[Install]
WantedBy=multi-user.target
```

> [!IMPORTANT]
> 将 `User=pi` 和 `WorkingDirectory` 替换为实际路径。
> 确保该用户对 `data/` 目录有读写权限。

---

## 7. 启动与管理

```bash
# 重新加载 systemd
sudo systemctl daemon-reload

# 启用开机自启
sudo systemctl enable tg_bot

# 启动服务
sudo systemctl start tg_bot

# 查看状态
sudo systemctl status tg_bot
```

### 常用管理命令

| 命令 | 说明 |
|------|------|
| `sudo systemctl restart tg_bot` | 重启服务 |
| `sudo systemctl stop tg_bot` | 停止服务 |
| `sudo journalctl -u tg_bot -f` | 实时查看日志 |
| `sudo journalctl -u tg_bot --since today` | 查看今日日志 |

---

## 8. 验证部署

### 8.1 运行测试

```bash
cd /opt/tg_bot
source .venv/bin/activate
python -m pytest tests/ -v
```

### 8.2 检查 Bot 启动消息

启动后，Bot 会向配置的用户发送：
```
🚀 Beancount Bot 已启动！
```

### 8.3 测试命令

| 命令 | 预期结果 |
|------|----------|
| `/start` | 显示欢迎信息 |
| `/reload` | 重新加载账户数据 |
| `/today` | 显示今日交易汇总 |
| `午饭 32 wx` | 创建交易并显示确认卡片 |

---

## 9. 故障排查

### 问题：Bot 无响应

```bash
# 检查服务状态
sudo systemctl status tg_bot

# 查看错误日志
sudo journalctl -u tg_bot -n 50 --no-pager
```

### 问题：写入失败

```bash
# 检查文件权限
ls -la /opt/tg_bot/data/

# 确保目录可写
chmod 755 /opt/tg_bot/data
chmod 644 /opt/tg_bot/data/*.bean
```

### 问题：依赖安装失败

```bash
# 确保使用正确的 Python 版本
python3.11 --version

# 重新创建虚拟环境
rm -rf .venv
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 10. 更新部署

当代码更新后：

```bash
cd /opt/tg_bot
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart tg_bot
```

---

## 附录：新功能说明

### A. 新增 Bot 命令

| 命令 | 说明 |
|------|------|
| `/undo` | 撤销最后一笔交易 |
| `/today` | 查看今日交易汇总 |
| `/reload config` | 热更新配置文件 |
| `/reload all` | 重新加载所有数据 |

### B. 自动备份机制

- 每次写入前自动备份到 `data/backups/`
- 保留最近 10 个备份
- 写入失败时自动回滚

### C. 交易日志

- 日志存储在 `data/logs/transactions_YYYY_MM.jsonl`
- 记录所有交易状态变更
- 支持按日期查询
