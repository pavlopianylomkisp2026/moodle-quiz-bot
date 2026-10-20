from __future__ import annotations

import os
import sys
import threading
import time

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from database.db import count_questions, upsert_question
from moodle.browser import start_browser, open_page, ensure_moodle_login
from moodle.quiz import run_one_attempt
from parser.quiz_parser import parse_review_file
from test_config import get_test
import argparse


pause_event = threading.Event()
stop_event = threading.Event()


def command_listener() -> None:
    """Listen for terminal commands while the collector is running.

    p + Enter = pause/resume between attempts
    q + Enter = stop after the current attempt
    """
    print("Команди керування: [p + Enter] пауза/продовжити | [q + Enter] зупинити")
    print()

    while not stop_event.is_set():
        try:
            command = sys.stdin.readline()
        except (EOFError, KeyboardInterrupt):
            stop_event.set()
            return

        if not command:
            return

        command = command.strip().lower()

        if command == "p":
            if pause_event.is_set():
                pause_event.clear()
                print("\n▶ Продовжуємо. Наступна спроба буде запущена.")
            else:
                pause_event.set()
                print(
                    "\n⏸ ПАУЗА. Поточна спроба буде завершена, "
                    "після чого нові спроби не запускатимуться."
                )
        elif command == "q":
            stop_event.set()
            pause_event.clear()
            print("\n⏹ Отримано команду зупинки. Поточна спроба буде завершена.")
            return
        elif command:
            print("Невідома команда. Використай: p + Enter або q + Enter")


def wait_if_paused() -> None:
    while pause_event.is_set() and not stop_event.is_set():
        time.sleep(0.5)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Moodle Quiz Collector")
    parser.add_argument("--test", "--test-id", dest="test_id", type=int, required=True)
    args = parser.parse_args()
    test = get_test(args.test_id)
    test_id = int(test["id"])
    test_name = str(test["name"])
    quiz_url = str(test["url"]).strip()
    max_attempts = int(os.getenv("MAX_ATTEMPTS", "0"))
    pause_seconds = float(os.getenv("PAUSE_BETWEEN_ATTEMPTS", "2"))

    # MAX_ATTEMPTS=0 means unlimited attempts.
    if max_attempts < 0:
        raise RuntimeError("MAX_ATTEMPTS має бути 0 або більше")

    print(f"Тест: {test_name} (test_id={test_id})")
    print(f"URL: {quiz_url}")
    print(f"Питань у цьому тесті перед стартом: {count_questions(test_id)}")
    print()

    if max_attempts == 0:
        print("Режим: БЕЗКІНЕЧНИЙ ЦИКЛ")
    else:
        print(f"Заплановано спроб: {max_attempts}")

    print("Керування: p + Enter = пауза/продовжити, q + Enter = зупинити.")
    print("Якщо Moodle попросить логін — натисну GoogleVNS і чекатиму ручної авторизації.")
    print()

    listener = threading.Thread(target=command_listener, daemon=True)
    listener.start()

    attempt_number = 0

    with sync_playwright() as playwright:
        context = start_browser(playwright)
        page = open_page(context, quiz_url)

        try:
            while not stop_event.is_set():
                wait_if_paused()

                if stop_event.is_set():
                    break

                attempt_number += 1

                print(f"\n--- Спроба {attempt_number} ---")

                # Re-open the quiz page before every new attempt.
                page.goto(quiz_url, wait_until="domcontentloaded")
                ensure_moodle_login(page, quiz_url)

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

                print(f"У базі для {test_name}: {count_questions(test_id)} унікальних питань")
                print(f"У базі загалом: {count_questions()} унікальних питань")

                if stop_event.is_set():
                    break

                if max_attempts > 0 and attempt_number >= max_attempts:
                    print("\nДосягнуто MAX_ATTEMPTS. Завершуємо.")
                    break

                # If p was pressed during the attempt, pause now.
                if pause_event.is_set():
                    print("⏸ Зараз пауза. Натисни p + Enter для продовження.")

                # Small delay between attempts.
                for _ in range(max(0, int(pause_seconds * 10))):
                    if stop_event.is_set() or pause_event.is_set():
                        break
                    time.sleep(0.1)

        except KeyboardInterrupt:
            print("\n⏹ Зупинка через Ctrl+C.")
        finally:
            stop_event.set()
            context.close()

    print("Готово.")


if __name__ == "__main__":
    main()
