# Telegram bot

This package is designed for the existing `moodle_quiz` PostgreSQL database.

## 1. Migration

Run from the project root:

```bash
./.venv/bin/python -m pip install -r telegram_bot/requirements.txt
psql -d moodle_quiz -f telegram_bot/database/bot_schema.sql
```

The migration:
- creates 22 placeholder tests;
- adds `test_id` to existing questions;
- assigns existing questions to Test 1;
- creates users;
- creates one global attempt balance per user;
- records every successful question lookup;
- records admin actions.

## 2. Environment

Copy `.env.example` values into the project's `.env`:

```env
BOT_TOKEN=...
ADMIN_TELEGRAM_IDS=123456789
SUPPORT_USERNAME=manager_username
```

Do NOT send the bot token in chat.

## 3. Run

```bash
./.venv/bin/python telegram_bot/bot.py
```

## User commands

- `/start`

## Admin commands

- `/admin`
- `/give <telegram_id> <amount>`
- `/user <telegram_id>`
- `/stats`
- `/broadcast <text>`

Only IDs listed in `ADMIN_TELEGRAM_IDS` can use admin commands.

## Important

A successful exact question lookup consumes one attempt.
A question that is not found does not consume an attempt.
