from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import BrowserContext, Page, Playwright, TimeoutError as PlaywrightTimeoutError

load_dotenv()

PROFILE_DIR = Path("browser_profile")


def start_browser(playwright: Playwright) -> BrowserContext:
    headless = os.getenv("HEADLESS", "false").lower() == "true"

    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=headless,
        viewport={"width": 1440, "height": 900},
    )


def open_page(context: BrowserContext, url: str):
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(url, wait_until="domcontentloaded")
    return page


def ensure_moodle_login(page: Page, quiz_url: str, timeout: int = 120_000) -> None:
    """Ensure the browser is authenticated in Moodle.

    If Moodle shows its login page, click the GoogleVNS identity-provider button
    and give the user up to `timeout` milliseconds to finish Google authentication.
    Passwords are never handled by this script.
    """
    login_button = page.locator("a.login-identityprovider-btn").filter(has_text="GoogleVNS").first
    on_login_page = "/login/" in page.url or login_button.count() > 0

    if not on_login_page:
        return

    login_button.wait_for(state="visible", timeout=15_000)
    print("Moodle просить авторизацію. Натискаю GoogleVNS...")
    login_button.click()

    try:
        page.wait_for_url(
            lambda url: "vns.lpnu.ua" in url and "/login/" not in url,
            timeout=timeout,
        )
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            "Не вдалося завершити Google/Moodle авторизацію за 120 секунд. "
            "У браузері потрібно завершити вхід вручну."
        ) from exc

    page.goto(quiz_url, wait_until="domcontentloaded")

    if page.locator("a.login-identityprovider-btn").filter(has_text="GoogleVNS").count() > 0:
        raise RuntimeError(
            "Moodle все ще показує сторінку входу після GoogleVNS. "
            "Перевір авторизацію у відкритому браузері."
        )

    print("Авторизація Moodle успішна.")
