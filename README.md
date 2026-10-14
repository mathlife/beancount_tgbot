# TG_bot - Telegram Beancount 记账机器人

智能的个人记账 Telegram Bot，支持自然语言输入，自动生成 Beancount 格式的交易记录。

## ✨ 特性

- 🗣️ **自然语言输入**：`晚饭 稻禾风 32.55 citic`
- 🤖 **AI 智能分类**：基于 Gemini API 自动匹配支出类别
- 💱 **多币种支持**：支持 `@@` 语法的货币转换
- 🎟️ **优惠拆分**：自动处理折扣和返现
- ⚡ **别名系统**：支持 Beancount 元数据和 YAML 双源别名
- 🛡️ **稳定可靠**：自动备份、错误恢复、交易日志

## 📁 项目结构

```
TG_bot/
├── main.py                 # 入口文件
├── config/
│   ├── .env                # 环境变量
│   └── settings.yaml       # 配置文件
├── data/
│   ├── main.bean           # Beancount 主文件
│   ├── logs/               # 交易日志
│   └── backups/            # 自动备份
├── tools/
└── src/
    ├── bot/                # Telegram Bot 模块
    ├── core/               # 核心逻辑模块
    ├── models/             # 数据模型
    └── utils/              # 工具模块
```

## 🚀 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置

```bash
cp config/.env.example config/.env
# 编辑 .env 填入你的 Token 和 API Key
```

### 3. 运行

```bash
python main.py
```

## 📖 输入格式

| 格式 | 示例 |
|------|------|
| 基础 | `午饭 32 wx` |
| 带商户 | `稻禾风 晚饭 32.55 citic` |
| 带优惠 | `打车 优惠 3 15 za` |
| 多币种 | `打车 11.40 HKD @@ 13.77 CNY za` |

## 🤖 Bot 命令

| 命令 | 说明 |
|------|------|
| `/start` | 显示欢迎信息 |
| `/reload` | 重新加载账户数据 |
| `/reload config` | 热更新配置文件 |
| `/undo` | 撤销最后一笔交易 |
| `/today` | 查看今日交易汇总 |

## 📚 文档

- [项目上下文](contexts/context.md) - 完整项目说明
- [解析规范](specs/parsing-spec.md) - 技术规范

## 🛠️ 技术栈

- Python 3.10-3.11
- python-telegram-bot
- Beancount
- Google Gemini API

## 🧪 测试

```bash
python -m pytest tests/ -v
```

## 📝 许可证

MIT License
