import argparse
import psycopg


PROTECTED_TABLES = ("users", "user_attempts", "admin_actions")


def get_local_data():
    with psycopg.connect(
        "host=localhost port=5432 dbname=moodle_quiz user=gifre"
    ) as conn:
        tests = conn.execute(
            """
            SELECT id, name, description, moodle_quiz_url
            FROM tests
            ORDER BY id
            """
        ).fetchall()

        questions = conn.execute(
            """
            SELECT
                test_id,
                question,
                answer_letter,
                correct_answer,
                moodle_question_id,
                quiz_cmid,
                source_attempt_id,
                collected_at
            FROM questions
            ORDER BY test_id, id
            """
        ).fetchall()

        duplicates = conn.execute(
            """
            SELECT test_id, question, COUNT(*)
            FROM questions
            GROUP BY test_id, question
            HAVING COUNT(*) > 1
            """
        ).fetchall()

        if duplicates:
            raise RuntimeError(
                f"У локальній БД знайдено дублікати питань: {duplicates[:5]}"
            )

        return tests, questions


def get_railway_counts(conn):
    result = {}

    for table in ("tests", "questions", "users", "user_attempts", "admin_actions"):
        result[table] = conn.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]

    return result


def sync(railway_port, dry_run=False):
    tests, questions = get_local_data()

    print(f"Локально тестів: {len(tests)}")
    print(f"Локально питань: {len(questions)}")

    with psycopg.connect(
        host="127.0.0.1",
        port=railway_port,
        dbname="railway",
        user="postgres",
        sslmode="require",
    ) as conn:

        before = get_railway_counts(conn)

        print("\nRailway ДО:")
        for table, count in before.items():
            print(f"  {table}: {count}")

        if dry_run:
            print("\nDRY RUN: змін не внесено.")
            return

        with conn.transaction():

            # ---------------------------------------------------------
            # 1. Оновлюємо / додаємо тести.
            # Існуючі ID не змінюємо.
            # ---------------------------------------------------------
            for test_id, name, description, moodle_url in tests:
                conn.execute(
                    """
                    INSERT INTO tests (
                        id,
                        name,
                        description,
                        moodle_quiz_url
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        moodle_quiz_url = EXCLUDED.moodle_quiz_url
                    """,
                    (test_id, name, description, moodle_url),
                )

            # ---------------------------------------------------------
            # 2. Тимчасова таблиця з локальними питаннями.
            # ---------------------------------------------------------
            conn.execute(
                """
                CREATE TEMP TABLE sync_questions (
                    test_id SMALLINT NOT NULL,
                    question TEXT NOT NULL,
                    answer_letter VARCHAR(20) NOT NULL,
                    correct_answer TEXT NOT NULL,
                    moodle_question_id BIGINT,
                    quiz_cmid BIGINT,
                    source_attempt_id BIGINT,
                    collected_at TIMESTAMPTZ NOT NULL
                ) ON COMMIT DROP
                """
            )

            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO sync_questions (
                        test_id,
                        question,
                        answer_letter,
                        correct_answer,
                        moodle_question_id,
                        quiz_cmid,
                        source_attempt_id,
                        collected_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    questions,
                )

            # ---------------------------------------------------------
            # 3. Оновлюємо існуючі питання.
            # ID питання з Railway зберігається.
            # ---------------------------------------------------------
            conn.execute(
                """
                UPDATE questions AS q
                SET
                    answer_letter = s.answer_letter,
                    correct_answer = s.correct_answer,
                    moodle_question_id = s.moodle_question_id,
                    quiz_cmid = s.quiz_cmid,
                    source_attempt_id = s.source_attempt_id,
                    collected_at = s.collected_at
                FROM sync_questions AS s
                WHERE q.test_id = s.test_id
                  AND q.question = s.question
                """
            )

            # ---------------------------------------------------------
            # 4. Додаємо нові питання.
            # ---------------------------------------------------------
            conn.execute(
                """
                INSERT INTO questions (
                    test_id,
                    question,
                    answer_letter,
                    correct_answer,
                    moodle_question_id,
                    quiz_cmid,
                    source_attempt_id,
                    collected_at
                )
                SELECT
                    s.test_id,
                    s.question,
                    s.answer_letter,
                    s.correct_answer,
                    s.moodle_question_id,
                    s.quiz_cmid,
                    s.source_attempt_id,
                    s.collected_at
                FROM sync_questions AS s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM questions AS q
                    WHERE q.test_id = s.test_id
                      AND q.question = s.question
                )
                """
            )

            # ---------------------------------------------------------
            # 5. Видаляємо старі питання, яких немає локально,
            #    ТІЛЬКИ якщо на них ніхто не посилається.
            #
            #    Якщо user_attempts посилається на question_id,
            #    питання залишаємо для збереження історії.
            # ---------------------------------------------------------
            conn.execute(
                """
                DELETE FROM questions AS q
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM sync_questions AS s
                    WHERE s.test_id = q.test_id
                      AND s.question = q.question
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM user_attempts AS ua
                    WHERE ua.question_id = q.id
                )
                """
            )

            # ---------------------------------------------------------
            # 6. Виправляємо sequence questions.id.
            # ---------------------------------------------------------
            conn.execute(
                """
                SELECT setval(
                    pg_get_serial_sequence('questions', 'id'),
                    COALESCE((SELECT MAX(id) FROM questions), 1),
                    true
                )
                """
            )

            # ---------------------------------------------------------
            # 7. Виправляємо sequence tests.id.
            # ---------------------------------------------------------
            conn.execute(
                """
                SELECT setval(
                    pg_get_serial_sequence('tests', 'id'),
                    COALESCE((SELECT MAX(id) FROM tests), 1),
                    true
                )
                """
            )

            # ---------------------------------------------------------
            # 8. Перевіряємо, що захищені таблиці НЕ змінилися.
            # Якщо змінилися — вся транзакція буде відкотена.
            # ---------------------------------------------------------
            after = get_railway_counts(conn)

            for table in PROTECTED_TABLES:
                if before[table] != after[table]:
                    raise RuntimeError(
                        f"ПОМИЛКА: таблиця {table} змінилася! "
                        f"Було {before[table]}, стало {after[table]}"
                    )

        # Після commit читаємо фінальний стан.
        final_counts = get_railway_counts(conn)

        print("\nRailway ПІСЛЯ:")
        for table, count in final_counts.items():
            print(f"  {table}: {count}")

        print("\nЗахищені таблиці:")
        for table in PROTECTED_TABLES:
            print(
                f"  {table}: {before[table]} -> {final_counts[table]}"
            )

        print("\nСинхронізація завершена успішно.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port",
        type=int,
        required=True,
        help="Порт Railway SSH tunnel",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Тільки перевірка, без змін",
    )

    args = parser.parse_args()

    sync(args.port, args.dry_run)
