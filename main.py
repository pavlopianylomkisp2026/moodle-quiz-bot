from __future__ import annotations

import os
import time
import argparse

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from database.db import count_questions, upsert_question
from moodle.browser import start_browser, open_page
from moodle.quiz import run_one_attempt
from parser.quiz_parser import parse_review_file
from test_config import get_test


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Moodle Quiz Collector")
    parser.add_argument("--test", "--test-id", dest="test_id", type=int, required=True)
    args = parser.parse_args()
    test = get_test(args.test_id)
    test_id = int(test["id"])
    test_name = str(test["name"])
    quiz_url = str(test["url"]).strip()
    max_attempts = int(os.getenv("MAX_ATTEMPTS", "1"))
    pause_seconds = float(os.getenv("PAUSE_BETWEEN_ATTEMPTS", "2"))

    if max_attempts < 1:
        raise RuntimeError("MAX_ATTEMPTS має бути >= 1")

    print("=== Moodle Quiz Collector ===")
    print(f"Тест: {test_name} (test_id={test_id})")
    print(f"URL: {quiz_url}")
    print(f"Заплановано спроб: {max_attempts}")
    print("Якщо Moodle попросить логін — увійди вручну.")
    print()

    with sync_playwright() as playwright:
        context = start_browser(playwright)
        page = open_page(context, quiz_url)

        try:
            for attempt_number in range(1, max_attempts + 1):
                print(f"--- Спроба {attempt_number}/{max_attempts} ---")

                page.goto(quiz_url, wait_until="domcontentloaded")

                html_path = run_one_attempt(page, attempt_number)
                print(f"HTML збережено: {html_path}")

                parsed = parse_review_file(html_path)
                print(f"Знайдено питань: {len(parsed)}")

                for item in parsed:
                    upsert_question(
                        test_id=test_id,
                        question=item.question,
                        answer_letter=item.answer_letter,
                        correct_answer=item.correct_answer,
                        moodle_question_id=item.moodle_question_id,
                    )

                print(f"У базі зараз: {count_questions()} унікальних питань")

                if attempt_number < max_attempts:
                    time.sleep(pause_seconds)

        finally:
            context.close()

    print("Готово.")


if __name__ == "__main__":
    main()
