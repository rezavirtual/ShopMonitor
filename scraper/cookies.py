from __future__ import annotations

import json
import os
from typing import Any

COOKIE_ENV_VARS: dict[str, str] = {
    "shopee_sg": "SHOPEE_COOKIES_JSON",
    "lazada_sg": "LAZADA_COOKIES_JSON",
    "amazon_sg": "AMAZON_COOKIES_JSON",
}

_SAME_SITE_MAP: dict[str, str] = {
    "strict": "Strict",
    "lax": "Lax",
    "none": "None",
    "no_restriction": "None",
    "unspecified": "Lax",
}


def normalize_cookies_for_playwright(raw_cookies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Cookie-Editor / browser-exported cookies into Playwright add_cookies() format."""
    normalized: list[dict[str, Any]] = []
    for c in raw_cookies:
        if not isinstance(c, dict):
            continue
        name = c.get("name")
        value = c.get("value")
        domain = c.get("domain")
        if not name or value is None or not domain:
            continue

        cookie: dict[str, Any] = {
            "name": str(name),
            "value": str(value),
            "domain": str(domain),
            "path": str(c.get("path") or "/"),
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": bool(c.get("secure", False)),
        }

        same_site_raw = str(c.get("sameSite") or "").strip().lower()
        if same_site_raw in _SAME_SITE_MAP:
            mapped = _SAME_SITE_MAP[same_site_raw]
            # Playwright requires secure=True when sameSite is None
            if mapped == "None" and not cookie["secure"]:
                cookie["secure"] = True
            cookie["sameSite"] = mapped

        expires = c.get("expirationDate") or c.get("expires")
        if isinstance(expires, (int, float)) and expires > 0:
            cookie["expires"] = int(expires)

        normalized.append(cookie)
    return normalized


def load_platform_cookies(platform: str) -> tuple[list[dict[str, Any]], str]:
    """Load and normalize cookies for a platform from environment variables.

    Returns (cookies_list, status_string) where status_string is one of:
    'loaded', 'unconfigured', 'invalid'.
    """
    env_var = COOKIE_ENV_VARS.get(platform)
    if not env_var:
        return [], "unconfigured"

    raw = os.environ.get(env_var, "").strip()
    if not raw:
        return [], "unconfigured"

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "cookies" in parsed:
            parsed = parsed["cookies"]
        if not isinstance(parsed, list):
            return [], "invalid"
        cookies = normalize_cookies_for_playwright(parsed)
        if not cookies:
            return [], "invalid"
        return cookies, "loaded"
    except json.JSONDecodeError:
        return [], "invalid"
