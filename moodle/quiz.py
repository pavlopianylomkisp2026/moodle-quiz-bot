from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

ARCHIVE_DIR = Path("html/archive")
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def save_html(page: Page, attempt_number: int) -> Path:
    path = ARCHIVE_DIR / f"attempt_{attempt_number:06d}.html"
    path.write_text(page.content(), encoding="utf-8")
    return path


def click_exact_text(page: Page, text: str, timeout: int = 15_000) -> None:
    locator = page.get_by_text(text, exact=True)
    locator.last.click(timeout=timeout)


def start_new_attempt(page: Page) -> None:
    click_exact_text(page, "Зробити наступну спробу")

    submit = page.locator("#id_submitbutton")
    submit.wait_for(state="visible", timeout=15_000)
    submit.click()

    page.wait_for_load_state("domcontentloaded")


def finish_attempt(page: Page) -> None:
    button = page.locator("#mod_quiz-next-nav")
    button.wait_for(state="visible", timeout=15_000)
    button.click()

    page.wait_for_load_state("domcontentloaded")


def submit_and_confirm(page: Page) -> None:
    # First click: opens Moodle's confirmation modal.
    page.get_by_role(
        "button",
        name="Відправити все та завершити",
        exact=True,
    ).last.click(timeout=15_000)

    # Second click: the real confirmation button inside the modal.
    modal = page.locator(".modal-content").filter(
        has_text="Надіслати всі свої відповіді та закінчити?"
    ).last
    modal.wait_for(state="visible", timeout=15_000)

    dialog_button = modal.locator('button[data-action="save"]')
    dialog_button.wait_for(state="visible", timeout=15_000)
    dialog_button.click()

    page.wait_for_load_state("domcontentloaded")


def wait_for_review_page(page: Page) -> None:
    page.locator("div.que .rightanswer").first.wait_for(
        state="visible",
        timeout=30_000,
    )


def run_one_attempt(page: Page, attempt_number: int) -> Path:
    start_new_attempt(page)
    finish_attempt(page)
    submit_and_confirm(page)
    wait_for_review_page(page)
    return save_html(page, attempt_number)


def pause(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)
