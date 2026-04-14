# 🤖 AdForwarder Bot

Forward a Telegram post to all your joined groups automatically.

---

## 📁 Project Structure

```
adbot/
├── bot.py           # Entry point
├── config.py        # API keys & defaults
├── handlers.py      # All bot command/button handlers
├── userbot.py       # Telethon (ads account) wrapper
├── worker.py        # Background forwarding task
├── db.py            # SQLite persistence
├── states.py        # Conversation-handler states
├── requirements.txt
└── README.md
```

---

## ⚙️ Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the bot
python bot.py
```

---

## 🚀 Usage

### 1 — Login your ads account
Send `/login` to the bot and follow the prompts.  
Your session is saved locally as `aduser.session` — you only need to do this once.

### 2 — Scan your groups
```
/refresh
```

### 3 — Set the post to forward
```
/setpost https://t.me/yourchannel/123
```

### 4 — Start forwarding
```
/startads
```

---

## 📋 All Commands

| Command | Description |
|---|---|
| `/login` | Login your ads account (interactive) |
| `/logout` | Log out |
| `/setpost <link>` | Set the post to forward |
| `/startads` | Start forwarding to all groups |
| `/stopads` | Stop forwarding |
| `/status` | Show current status & counters |
| `/groups` | List & toggle individual groups |
| `/refresh` | Re-scan groups from account |
| `/delay <seconds>` | Delay between groups (default 60s) |
| `/rounds <n>` | Max rounds, 0 = unlimited |
| `/stats` | Forwarding statistics |

---

## ⚙️ Settings

Edit `config.py` to change defaults:

```python
DEFAULT_DELAY_SECONDS = 60   # gap between each group forward
DEFAULT_ROUNDS        = 0    # 0 = loop forever
```

Or change at runtime:
```
/delay 30      ← 30 seconds between groups
/rounds 5      ← stop after 5 full rounds
```

---

## 🔒 Security

- Only the `OWNER_ID` in `config.py` can use the bot.
- Session is stored locally in `aduser.session`.
- Never share `aduser.session` — it gives full account access.
