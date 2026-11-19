from __future__ import annotations

import random
import time
from contextlib import contextmanager
from typing import Any, Generator

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

try:
    from playwright_stealth import Stealth  # type: ignore

    def _apply_stealth(page: Page) -> None:
        Stealth().apply_stealth_sync(page)
except ImportError:
    try:
        from playwright_stealth import stealth_sync  # type: ignore

        def _apply_stealth(page: Page) -> None:
            stealth_sync(page)
    except ImportError:
        def _apply_stealth(page: Page) -> None:
            pass


SG_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


def human_delay(min_s: float = 1.2, max_s: float = 2.8) -> None:
    """Sleep a randomized short interval to mimic human browsing."""
    time.sleep(random.uniform(min_s, max_s))


@contextmanager
def open_sg_context(
    cookies: list[dict[str, Any]] | None = None,
    headless: bool = True,
) -> Generator[tuple[Browser, BrowserContext, Page], None, None]:
    """Create a stealth Playwright Chromium browser context configured for Singapore."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            locale="en-SG",
            timezone_id="Asia/Singapore",
            geolocation={"latitude": 1.3521, "longitude": 103.8198},
            permissions=["geolocation"],
            viewport={"width": 1280, "height": 800},
            user_agent=SG_USER_AGENT,
            extra_http_headers={
                "Accept-Language": "en-SG,en;q=0.9",
            },
        )
        if cookies:
            try:
                context.add_cookies(cookies)
            except Exception as exc:
                print(f"[Playwright] Warning: failed to add some cookies: {exc}")

        page = context.new_page()
        page.set_default_timeout(30000)
        _apply_stealth(page)
        try:
            yield browser, context, page
        finally:
            context.close()
            browser.close()


def is_login_wall(url: str, page_text: str = "") -> bool:
    """Detect common login walls or anti-bot verification redirects."""
    lower_url = url.lower()
    if any(tok in lower_url for tok in ("/buyer/login", "/ap/signin", "member.lazada.sg/user/login", "/verify")):
        return True
    lower_text = page_text.lower()
    if "sign in to continue" in lower_text or "log in to view" in lower_text:
        return True
    return False
