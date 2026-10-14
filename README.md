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

## 🧪 Testing

```bash
python -m pytest tests/ -v
```

## 📝 License

MIT License
