# Beancount TG Bot - Telegram Accounting Bot for Beancount

**A Telegram bot bringing mobile natural-language transaction capture to the Beancount plain-text accounting community.**

## ✨ Features

- 🗣️ **Natural Language Input**: `Lunch 32.55 wx` → auto generates Beancount entries
- 🤖 **AI Smart Categorization**: Gemini-powered automatic account matching
- 💱 **Multi-currency Support**: `@@` syntax for currency conversion
- 🎟️ **Discount Splitting**: Automatic handling of rebates & cashback
- ⚡ **Alias System**: YAML + Beancount metadata dual-source aliases
- 🛡️ **Reliable & Stable**: Auto backup, error recovery, transaction logging

## 🔒 Privacy

- Messages you send to the bot go through Telegram's Bot API (as with any Telegram bot).
- Transaction text is sent to the Google Gemini API for AI-powered categorization.
- Your ledger files stay on the machine where you run the bot.

## 🚀 Quick Start

### Prerequisites

- **Telegram Bot Token**: Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
- **Gemini API Key**: Get one from [Google AI Studio](https://aistudio.google.com/apikey).
- **Python 3.10+** installed on the machine running the bot.

### 1. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configuration

```bash
cp config/.env.example config/.env
# Edit .env to add your Telegram token and Gemini API key
```

### 3. Run the Bot

```bash
python main.py
```

## 📖 Input Formats

| Format              | Example                     |
|---------------------|-----------------------------|
| Basic               | `Lunch 32.55 wx`            |
| With Merchant       | `Rice 晚饭 32.55 citic`     |
| With Discount       | `Ride 优惠 3 15 za`         |
| Multi-currency      | `Ride 11.40 HKD @@ 13.77 CNY za` |

## 🤖 Bot Commands

| Command              | Description                     |
|----------------------|---------------------------------|
| `/start`             | Show welcome message            |
| `/reload`            | Reload ledger & accounts        |
| `/reload config`     | Hot reload configuration        |
| `/undo`              | Undo last transaction           |
| `/today`             | Show today's summary            |

## 📚 Documentation

- [Project Context](contexts/context.md) - Full project explanation
- [Parsing Spec](specs/parsing-spec.md) - Technical specification

## 🛠️ Technology Stack

- Python 3.10+
- python-telegram-bot
- Beancount
- Google Gemini API

## 📁 Project Structure

```
beancount_tgbot/
├── main.py                 # Entry point
├── config/
│   ├── .env                # Environment variables
│   └── settings.yaml       # Configuration
├── data/
│   ├── main.bean           # Beancount ledger file
│   ├── logs/               # Transaction log
│   └── backups/            # Auto backups
├── src/
│   ├── bot/                # Telegram Bot module
│   ├── core/               # Core logic
│   ├── utils/              # Utility modules
│   └── models/             # Data models
```

## 🧪 Testing

```bash
python -m pytest tests/ -v
```

## 📝 License

MIT License
