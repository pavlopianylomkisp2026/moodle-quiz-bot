from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg
from dotenv import load_dotenv

load_dotenv()


def connection_string() -> str:
    return (
        f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB', 'moodle_quiz')} "
        f"user={os.getenv('POSTGRES_USER', 'postgres')} "
        f"password={os.getenv('POSTGRES_PASSWORD', '')}"
    )


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(connection_string())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_question(
    test_id: int,
    question: str,
    answer_letter: str,
    correct_answer: str,
    moodle_question_id: int | None = None,
    quiz_cmid: int | None = None,
    source_attempt_id: int | None = None,
) -> None:
    sql = """
        INSERT INTO questions (
            test_id,
            question,
            answer_letter,
            correct_answer,
            moodle_question_id,
            quiz_cmid,
            source_attempt_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (test_id, question)
        DO UPDATE SET
            answer_letter = EXCLUDED.answer_letter,
            correct_answer = EXCLUDED.correct_answer,
            moodle_question_id = COALESCE(
                EXCLUDED.moodle_question_id,
                questions.moodle_question_id
            ),
            quiz_cmid = COALESCE(
                EXCLUDED.quiz_cmid,
                questions.quiz_cmid
            ),
            source_attempt_id = COALESCE(
                EXCLUDED.source_attempt_id,
                questions.source_attempt_id
            );
    """

    with get_connection() as conn:
        conn.execute(
            sql,
            (
                test_id,
                question,
                answer_letter,
                correct_answer,
                moodle_question_id,
                quiz_cmid,
                source_attempt_id,
            ),
        )


def count_questions(test_id=None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            if test_id is None:
                cur.execute("SELECT COUNT(*) FROM questions")
            else:
                cur.execute(
                    "SELECT COUNT(*) FROM questions WHERE test_id = %s",
                    (test_id,)
                )

            return cur.fetchone()[0]
