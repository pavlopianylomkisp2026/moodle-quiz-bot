import logging
import os
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_TELEGRAM_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")
    if value.strip()
}

SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "").strip().lstrip("@")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def database_connection_string() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return database_url

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "moodle_quiz")
    user = os.getenv("POSTGRES_USER", "gifre")
    password = os.getenv("POSTGRES_PASSWORD", "")

    return (
        f"host={host} port={port} dbname={db} "
        f"user={user} password={password}"
    )


@contextmanager
def get_connection():
    conn = psycopg.connect(database_connection_string())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_user(tg_user) -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO users (
                telegram_id, username, first_name, last_name,
                last_seen_at, is_active
            )
            VALUES (%s, %s, %s, %s, NOW(), TRUE)
            ON CONFLICT (telegram_id)
            DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                last_seen_at = NOW(),
                is_active = TRUE
            RETURNING id
            """,
            (
                tg_user.id,
                tg_user.username,
                tg_user.first_name,
                tg_user.last_name,
            ),
        ).fetchone()
        return row[0]


def get_user_balance(telegram_id: int):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT attempts_total, attempts_used,
                   attempts_total - attempts_used AS attempts_left
            FROM users
            WHERE telegram_id = %s
            """,
            (telegram_id,),
        ).fetchone()


def get_tests():
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, name
            FROM tests
            ORDER BY id
            """
        ).fetchall()


def get_test(test_id: int):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, name, description
            FROM tests
            WHERE id = %s
            """,
            (test_id,),
        ).fetchone()


def get_question_answer(test_id: int, question_text: str):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, answer_letter, correct_answer
            FROM questions
            WHERE test_id = %s
              AND BTRIM(question) = BTRIM(%s)
            LIMIT 1
            """,
            (test_id, question_text),
        ).fetchone()


def consume_attempt(telegram_id: int, test_id: int, question_id: int):
    """
    Atomically consumes one global user attempt.
    Returns remaining attempts, or None if there are no attempts left.
    """
    with get_connection() as conn:
        user_row = conn.execute(
            """
            UPDATE users
            SET attempts_used = attempts_used + 1,
                last_seen_at = NOW()
            WHERE telegram_id = %s
              AND attempts_used < attempts_total
              AND is_active = TRUE
            RETURNING id, attempts_total - attempts_used AS attempts_left
            """,
            (telegram_id,),
        ).fetchone()

        if user_row is None:
            return None

        conn.execute(
            """
            INSERT INTO user_attempts (user_id, test_id, question_id)
            VALUES (%s, %s, %s)
            """,
            (user_row[0], test_id, question_id),
        )

        return user_row[1]


def is_admin(telegram_id: int) -> bool:
    return telegram_id in ADMIN_TELEGRAM_IDS


def admin_required(update: Update) -> bool:
    user = update.effective_user
    return bool(user and is_admin(user.id))


def tests_keyboard():
    tests = get_tests()
    rows = []
    row = []

    for test_id, name in tests:
        row.append(
            InlineKeyboardButton(
                name,
                callback_data=f"test:{test_id}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    if SUPPORT_USERNAME:
        rows.append(
            [
                InlineKeyboardButton(
                    "🆘 Підтримка",
                    url=f"https://t.me/{SUPPORT_USERNAME}",
                )
            ]
        )

    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return

    upsert_user(user)
    balance = get_user_balance(user.id)
    attempts_left = balance[2] if balance else 0

    context.user_data.pop("test_id", None)

    text = (
        "👋 Вітаю!\n\n"
        "Це бот для роботи з тестами.\n\n"
        "Оберіть тест, після чого надішліть "
        "точний текст питання. Бот знайде правильну "
        "відповідь у базі.\n\n" \
        "Всі питання і за спробами сюди: @bomzhkk\n\n"
        f"🎟 Ваші спроби: {attempts_left}\n\n"
        "📚 Оберіть тест:"
    )

    await update.message.reply_text(
        text,
        reply_markup=tests_keyboard(),
    )


async def test_selected(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user = update.effective_user

    if query is None or user is None:
        return

    await query.answer()
    upsert_user(user)

    try:
        test_id = int(query.data.split(":", 1)[1])
    except (AttributeError, ValueError):
        await query.edit_message_text("❌ Некоректний вибір тесту.")
        return

    test = get_test(test_id)
    balance = get_user_balance(user.id)

    if test is None or balance is None:
        await query.edit_message_text("❌ Не вдалося завантажити тест.")
        return

    context.user_data["test_id"] = test_id
    attempts_left = balance[2]

    description = test[2] or ""

    text = (
        f"📚 {test[1]}\n\n"
        f"{description}\n\n" if description else
        f"📚 {test[1]}\n\n"
    )
    text += (
        f"🎟 Залишилось спроб: {attempts_left}\n\n"
        "Надішліть точний текст питання."
    )

    await query.edit_message_text(text)


async def handle_question(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user
    message = update.message

    if user is None or message is None or not message.text:
        return

    upsert_user(user)

    test_id = context.user_data.get("test_id")
    if test_id is None:
        await message.reply_text(
            "Спочатку оберіть тест через /start."
        )
        return

    question = get_question_answer(test_id, message.text)

    if question is None:
        balance = get_user_balance(user.id)
        attempts_left = balance[2] if balance else 0

        await message.reply_text(
            "❌ Питання не знайдено.\n\n"
            "Спроба не списана.\n"
            f"🎟 Залишилось: {attempts_left}"
        )
        return

    question_id, answer_letter, correct_answer = question

    remaining = consume_attempt(
        user.id,
        test_id,
        question_id,
    )

    if remaining is None:
        await message.reply_text(
            "❌ У вас закінчилися спроби.\n\n"
            "Зверніться до адміністратора для отримання "
            "додаткових спроб."
        )
        return

    await message.reply_text(
        "✅ Правильна відповідь:\n\n"
        f"{correct_answer}\n\n"
        f"🎟 Залишилось спроб: {remaining}"
    )


async def admin_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.effective_user is None or update.message is None:
        return

    if not admin_required(update):
        await update.message.reply_text("⛔ Доступ заборонено.")
        return

    await update.message.reply_text(
        "🔧 Адмін-команди:\n\n"
        "/give <telegram_id> <кількість>\n"
        "/user <telegram_id>\n"
        "/stats\n"
        "/broadcast <текст>\n\n"
        "Приклад:\n"
        "/give 123456789 50"
    )


async def give_attempts(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.effective_user is None or update.message is None:
        return

    if not admin_required(update):
        await update.message.reply_text("⛔ Доступ заборонено.")
        return

    if len(context.args) != 2:
        await update.message.reply_text(
            "Формат:\n"
            "/give <telegram_id або @username> <кількість>\n\n"
            "Приклади:\n"
            "/give 123456789 50\n"
            "/give @student123 50\n"
            "/give student123 50"
        )
        return

    identifier = context.args[0].strip()
    
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text(
            "❌ Кількість спроб має бути числом."
        )
        return

    if amount <= 0:
        await update.message.reply_text(
            "❌ Кількість спроб має бути більшою за 0."
        )
        return

    with get_connection() as conn:
        # Якщо введено Telegram ID
        if identifier.isdigit():
            target_id = int(identifier)

            row = conn.execute(
                """
                UPDATE users
                SET attempts_total = attempts_total + %s,
                    last_seen_at = NOW()
                WHERE telegram_id = %s
                RETURNING telegram_id, username,
                          attempts_total, attempts_used,
                          attempts_total - attempts_used AS attempts_left
                """,
                (amount, target_id),
            ).fetchone()

        else:
            # Якщо введено username
            username = identifier.lstrip("@")

            row = conn.execute(
                """
                UPDATE users
                SET attempts_total = attempts_total + %s,
                    last_seen_at = NOW()
                WHERE LOWER(username) = LOWER(%s)
                RETURNING telegram_id, username,
                          attempts_total, attempts_used,
                          attempts_total - attempts_used AS attempts_left
                """,
                (amount, username),
            ).fetchone()

        if row is None:
            await update.message.reply_text(
                "❌ Користувача не знайдено.\n\n"
                "Перевір Telegram ID або @username.\n"
                "Користувач повинен хоча б один раз "
                "натиснути /start у боті."
            )
            return

        conn.execute(
            """
            INSERT INTO admin_actions (
                admin_telegram_id,
                action,
                target_telegram_id,
                amount,
                details
            )
            VALUES (%s, 'give_attempts', %s, %s, %s)
            """,
            (
                update.effective_user.id,
                row[0],
                amount,
                f"identifier={identifier}",
            ),
        )

    display_username = (
        f"@{row[1]}" if row[1] else str(row[0])
    )

    await update.message.reply_text(
        "✅ Готово.\n\n"
        f"Користувач: {display_username}\n"
        f"Telegram ID: {row[0]}\n"
        f"Додано спроб: +{amount}\n\n"
        f"Всього: {row[2]}\n"
        f"Використано: {row[3]}\n"
        f"Залишилось: {row[4]}"
    )


async def user_info(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.effective_user is None or update.message is None:
        return

    if not admin_required(update):
        await update.message.reply_text("⛔ Доступ заборонено.")
        return

    if len(context.args) != 1:
        await update.message.reply_text(
            "Формат:\n/user <telegram_id>"
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Некоректний Telegram ID.")
        return

    with get_connection() as conn:
        user = conn.execute(
            """
            SELECT id, telegram_id, username, first_name, last_name,
                   attempts_total, attempts_used,
                   created_at, last_seen_at, is_active
            FROM users
            WHERE telegram_id = %s
            """,
            (target_id,),
        ).fetchone()

        usage = conn.execute(
            """
            SELECT t.name, COUNT(*)
            FROM user_attempts ua
            JOIN tests t ON t.id = ua.test_id
            WHERE ua.user_id = (SELECT id FROM users WHERE telegram_id = %s)
            GROUP BY t.id, t.name
            ORDER BY t.id
            """,
            (target_id,),
        ).fetchall()

    if user is None:
        await update.message.reply_text("❌ Користувача не знайдено.")
        return

    username = f"@{user[2]}" if user[2] else "—"
    usage_text = "\n".join(
        f"• {name}: {count}" for name, count in usage
    ) or "• ще немає використаних спроб"

    await update.message.reply_text(
        "👤 Користувач\n\n"
        f"ID: {user[1]}\n"
        f"Username: {username}\n"
        f"Ім'я: {user[3] or '—'}\n\n"
        f"🎟 Всього видано: {user[5]}\n"
        f"🎟 Використано: {user[6]}\n"
        f"🎟 Залишилось: {user[5] - user[6]}\n\n"
        "📚 Використання:\n"
        f"{usage_text}"
    )


async def stats(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.effective_user is None or update.message is None:
        return

    if not admin_required(update):
        await update.message.reply_text("⛔ Доступ заборонено.")
        return

    with get_connection() as conn:
        users_count = conn.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        active_count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE is_active"
        ).fetchone()[0]

        tests_count = conn.execute(
            "SELECT COUNT(*) FROM tests"
        ).fetchone()[0]

        questions_count = conn.execute(
            "SELECT COUNT(*) FROM questions"
        ).fetchone()[0]

        attempts_count = conn.execute(
            "SELECT COUNT(*) FROM user_attempts"
        ).fetchone()[0]

    await update.message.reply_text(
        "📊 Статистика\n\n"
        f"👥 Користувачів: {users_count}\n"
        f"🟢 Активних: {active_count}\n"
        f"📚 Тестів: {tests_count}\n"
        f"❓ Питань: {questions_count}\n"
        f"🎟 Використано спроб: {attempts_count}"
    )


async def broadcast(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.effective_user is None or update.message is None:
        return

    if not admin_required(update):
        await update.message.reply_text("⛔ Доступ заборонено.")
        return

    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text(
            "Формат:\n/broadcast <текст>\n\n"
            "Наприклад:\n"
            "/broadcast 🆕 Додано новий тест!"
        )
        return

    with get_connection() as conn:
        users = conn.execute(
            """
            SELECT telegram_id
            FROM users
            WHERE is_active = TRUE
            ORDER BY id
            """
        ).fetchall()

    sent = 0
    failed = 0

    for (telegram_id,) in users:
        try:
            await context.bot.send_message(
                chat_id=telegram_id,
                text=text,
            )
            sent += 1
        except Exception as exc:
            failed += 1
            logger.warning(
                "Broadcast failed for %s: %s",
                telegram_id,
                exc,
            )

    await update.message.reply_text(
        "📢 Розсилку завершено.\n\n"
        f"✅ Надіслано: {sent}\n"
        f"❌ Не доставлено: {failed}"
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Telegram update error", exc_info=context.error)


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "Не задано BOT_TOKEN у .env"
        )

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("give", give_attempts))
    application.add_handler(CommandHandler("user", user_info))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("broadcast", broadcast))

    application.add_handler(
        CallbackQueryHandler(test_selected, pattern=r"^test:\d+$")
    )

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question)
    )

    application.add_error_handler(error_handler)

    logger.info("Telegram bot started")
    application.run_polling()


if __name__ == "__main__":
    main()
