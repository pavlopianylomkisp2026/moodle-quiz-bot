# Оновлення

## Колектор

1. Скопіюй `test_config.py`, `tests_config.json` у корінь `moodle_quiz_collector`.
2. Замініть `database/db.py`, `main_loop.py`, `main.py`, `parser/import_html.py` файлами з цього пакета.
3. У `tests_config.json` впиши URL Moodle для потрібного тесту.
4. Запускай, наприклад:

```bash
./.venv/bin/python main_loop.py --test 2
```

Питання будуть записуватися з `test_id=2`.

## Telegram

Замініть `bot/bot.py` оновленим файлом.

Видача спроб:

```text
/give 123456789 100
/give @student123 100
/give student123 100
```

Перегляд користувача:

```text
/user 123456789
/user @student123
```

Користувач має спочатку натиснути `/start`, щоб бот знав його Telegram ID/username.
