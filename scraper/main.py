from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from scraper.cookies import load_platform_cookies
from scraper.models import is_item_expired, is_item_not_started, now_sgt_iso
from scraper.notifier import notify_cookie_expired_if_needed, notify_item_if_needed
from scraper.platforms import SCRAPER_DISPATCH

DEFAULT_WATCHLIST_PATH = Path("data/watchlist.json")
MAX_HISTORY_LEN = 50


def load_watchlist(path: Path = DEFAULT_WATCHLIST_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "updated_at": None, "cookie_status": {}, "items": []}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_watchlist(data: dict[str, Any], path: Path = DEFAULT_WATCHLIST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = now_sgt_iso()
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def run_monitor(watchlist_path: Path = DEFAULT_WATCHLIST_PATH, target_item_id: str | None = None) -> dict[str, Any]:
    data = load_watchlist(watchlist_path)
    items: list[dict[str, Any]] = data.setdefault("items", [])
    cookie_status: dict[str, Any] = data.setdefault("cookie_status", {})

    platform_cookies_cache: dict[str, tuple[list[dict[str, Any]], str]] = {}

    for item in items:
        item_id = str(item.get("id") or "")
        if target_item_id and item_id != target_item_id:
            continue

        if is_item_expired(item):
            item["active"] = False
            continue

        if not item.get("active", True) or is_item_not_started(item):
            continue

        platform = str(item.get("platform") or "")
        scraper_fn = SCRAPER_DISPATCH.get(platform)
        if not scraper_fn:
            print(f"[Monitor] Unsupported platform '{platform}' for item '{item.get('name')}'.")
            continue

        if platform not in platform_cookies_cache:
            platform_cookies_cache[platform] = load_platform_cookies(platform)

        cookies, cookie_load_status = platform_cookies_cache[platform]
        cookie_entry = cookie_status.setdefault(platform, {})
        cookie_entry["last_checked"] = now_sgt_iso()

        if cookie_load_status == "unconfigured":
            cookie_entry["status"] = "unconfigured"
            cookie_entry["message"] = "No cookies configured; running public checks."
        elif cookie_load_status == "invalid":
            cookie_entry["status"] = "invalid"
            cookie_entry["message"] = "Cookie JSON secret is invalid; running public checks."
        else:
            cookie_entry["status"] = "ok"
            cookie_entry["message"] = "Cookies loaded."

        print(f"[Monitor] Checking '{item.get('name')}' on {platform}...")
        result = scraper_fn(item, cookies if cookies else None)
        latest_dict = result.to_dict()

        if result.login_wall_detected and cookies:
            cookie_entry["status"] = "expired"
            cookie_entry["message"] = "Login wall detected; cookies may be expired."
            notify_cookie_expired_if_needed(platform, cookie_status)

        item["latest"] = latest_dict
        item["updated_at"] = now_sgt_iso()

        if result.listed_price is not None:
            history = item.setdefault("price_history", [])
            history.append(
                {
                    "timestamp": latest_dict["last_checked"],
                    "listed_price": result.listed_price,
                    "net_price": result.net_price,
                    "voucher_count": len(result.vouchers),
                }
            )
            if len(history) > MAX_HISTORY_LEN:
                item["price_history"] = history[-MAX_HISTORY_LEN:]

        notify_item_if_needed(item, latest_dict)

    save_watchlist(data, watchlist_path)
    return data


def main() -> None:
    target_id = os.environ.get("ITEM_ID", "").strip() or None
    watchlist_file = Path(os.environ.get("WATCHLIST_PATH", str(DEFAULT_WATCHLIST_PATH)))
    run_monitor(watchlist_path=watchlist_file, target_item_id=target_id)


if __name__ == "__main__":
    main()
