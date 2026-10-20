from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from database.db import count_questions, upsert_question
from parser.quiz_parser import parse_review_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Імпортувати Moodle review HTML у PostgreSQL"
    )
    parser.add_argument("html_file", help="Шлях до HTML сторінки перегляду")
    args = parser.parse_args()

    questions = parse_review_file(args.html_file)

    for item in questions:
        upsert_question(
            question=item.question,
            answer_letter=item.answer_letter,
            correct_answer=item.correct_answer,
            moodle_question_id=item.moodle_question_id,
        )

    print(f"Розпізнано питань: {len(questions)}")
    print(f"Питань у базі зараз: {count_questions()}")

    for item in questions:
        print(
            f"[{item.answer_letter}] {item.correct_answer} | "
            f"{item.question}"
        )


if __name__ == "__main__":
    main()
