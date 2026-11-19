from __future__ import annotations

import html
import os
from datetime import datetime, timedelta
from typing import Any

import requests

from scraper.models import PLATFORM_LABELS, SGT, compute_voucher_hash, now_sgt, now_sgt_iso


def _get_telegram_creds() -> tuple[str | None, str | None]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or None
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip() or None
    return token, chat_id


def send_telegram_message(text: str) -> bool:
    """Send an HTML-formatted message via the Telegram Bot API."""
    token, chat_id = _get_telegram_creds()
    if not token or not chat_id:
        print("[Telegram] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured; skipping notification.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code != 200:
            print(f"[Telegram] Failed ({resp.status_code}): {resp.text[:300]}")
            return False
        return True
    except requests.RequestException as exc:
        print(f"[Telegram] Request error: {exc}")
        return False


def should_send_item_alert(item: dict[str, Any], latest: dict[str, Any]) -> tuple[bool, str]:
    """Determine whether an alert should be sent for an item and why.

    Returns (should_send, reason) where reason is e.g. 'target_met', 'new_voucher', or ''.
    """
    listed_price = latest.get("listed_price")
    net_price = latest.get("net_price")
    vouchers = latest.get("vouchers") or []
    target_price = item.get("target_price")
    alert_on_new_voucher = bool(item.get("alert_on_new_voucher", False))

    if listed_price is None and net_price is None:
        return False, ""

    effective_price = net_price if net_price is not None else listed_price
    current_voucher_hash = compute_voucher_hash(vouchers)

    prev_state = item.get("last_alerted_state") or {}
    prev_listed = prev_state.get("listed_price")
    prev_net = prev_state.get("net_price")
    prev_vhash = prev_state.get("voucher_hash")

    target_hit = False
    if target_price is not None:
        if (listed_price is not None and listed_price <= float(target_price)) or (
            effective_price is not None and effective_price <= float(target_price)
        ):
            target_hit = True

    new_voucher_hit = bool(alert_on_new_voucher and vouchers and current_voucher_hash != prev_vhash)

    if not target_hit and not new_voucher_hit:
        return False, ""

    # Deduplicate exact same price + voucher state
    same_listed = prev_listed == listed_price
    same_net = prev_net == net_price
    same_vouchers = prev_vhash == current_voucher_hash

    if same_listed and same_net and same_vouchers:
        return False, ""

    # If target hit, check if price dropped or vouchers changed since last alert
    if target_hit:
        return True, "target_met"

    return True, "new_voucher"


def format_item_alert(item: dict[str, Any], latest: dict[str, Any], reason: str) -> str:
    """Format a rich HTML Telegram alert for a monitored product."""
    platform_key = item.get("platform", "")
    platform_label = PLATFORM_LABELS.get(platform_key, platform_key)
    item_name = html.escape(str(item.get("name") or "Monitored Item"))
    store_name = html.escape(str(latest.get("seller_name") or item.get("store_name") or "Unknown Store"))
    listed_price = latest.get("listed_price")
    net_price = latest.get("net_price")
    target_price = item.get("target_price")
    vouchers = latest.get("vouchers") or []
    product_url = latest.get("resolved_url") or item.get("url") or ""

    header = "🎯 <b>Target Price Hit!</b>" if reason == "target_met" else "🎟️ <b>New Voucher / Promo Detected!</b>"

    listed_str = f"S${listed_price:.2f}" if listed_price is not None else "N/A"
    net_str = f"S${net_price:.2f}" if net_price is not None else listed_str
    target_str = f"S${float(target_price):.2f}" if target_price is not None else "N/A"

    lines = [
        header,
        "",
        f"<b>Item:</b> {item_name}",
        f"<b>Platform:</b> {html.escape(platform_label)}",
        f"<b>Store:</b> {store_name}",
        f"<b>Listed Price:</b> {listed_str}",
        f"<b>Net Price (after vouchers):</b> <b>{net_str}</b>",
        f"<b>Target Price:</b> {target_str}",
    ]

    if vouchers:
        lines.append("")
        lines.append("<b>Available Vouchers:</b>")
        for v in vouchers[:5]:
            desc = html.escape(str(v.get("description", "")))
            elig = "✅" if v.get("eligible", True) else "⚠️ (min spend not met)"
            code_part = f" [Code: <code>{html.escape(str(v['code']))}</code>]" if v.get("code") else ""
            lines.append(f"• {elig} {desc}{code_part}")

    if product_url:
        lines.append("")
        lines.append(f'🔗 <a href="{html.escape(product_url, quote=True)}">Open Product Page</a>')

    return "\n".join(lines)


def notify_item_if_needed(item: dict[str, Any], latest: dict[str, Any]) -> bool:
    """Evaluate alert rules, send Telegram message if triggered, and update last_alerted_state."""
    should_send, reason = should_send_item_alert(item, latest)
    if not should_send:
        return False

    msg = format_item_alert(item, latest, reason)
    sent = send_telegram_message(msg)
    if sent:
        item["last_alerted_state"] = {
            "listed_price": latest.get("listed_price"),
            "net_price": latest.get("net_price"),
            "voucher_hash": compute_voucher_hash(latest.get("vouchers") or []),
            "alerted_at": now_sgt_iso(),
        }
    return sent


def can_send_cookie_warning(cookie_entry: dict[str, Any], now: datetime | None = None) -> bool:
    """Return True if at least 24 hours have passed since last_warned_at (or never warned)."""
    last_warned = cookie_entry.get("last_warned_at")
    if not last_warned:
        return True
    try:
        warned_dt = datetime.fromisoformat(str(last_warned))
        if warned_dt.tzinfo is None:
            warned_dt = warned_dt.replace(tzinfo=SGT)
        ref = now or now_sgt()
        return (ref - warned_dt) >= timedelta(hours=24)
    except ValueError:
        return True


def notify_cookie_expired_if_needed(platform: str, cookie_status_map: dict[str, Any]) -> bool:
    """Send a Telegram warning (max once every 24h) when a platform's cookies expire."""
    entry = cookie_status_map.setdefault(platform, {})
    if not can_send_cookie_warning(entry):
        return False

    platform_label = PLATFORM_LABELS.get(platform, platform)
    msg = (
        f"⚠️ <b>Session Cookies Expired ({html.escape(platform_label)})</b>\n\n"
        f"The scraper detected a login wall or expired session cookies for <b>{html.escape(platform_label)}</b>.\n"
        "Falling back to public unauthenticated price checks (logged-in vouchers may not be visible).\n\n"
        "Please re-export your cookies using Cookie-Editor and update the GitHub Secret."
    )
    sent = send_telegram_message(msg)
    if sent:
        entry["last_warned_at"] = now_sgt_iso()
    return sent
