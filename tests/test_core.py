from __future__ import annotations

from datetime import date, datetime, timedelta

from scraper.cookies import normalize_cookies_for_playwright
from scraper.models import SGT, VoucherInfo, is_item_expired
from scraper.notifier import can_send_cookie_warning, format_item_alert, should_send_item_alert
from scraper.voucher_calc import evaluate_vouchers, parse_sgd_price, parse_voucher_text


def test_parse_sgd_price():
    assert parse_sgd_price("S$129.90") == 129.90
    assert parse_sgd_price("$1,299.00") == 1299.00
    assert parse_sgd_price("SGD 45.5") == 45.50
    assert parse_sgd_price("Out of stock") is None


def test_voucher_parsing_and_evaluation():
    v1 = parse_voucher_text("10% off min spend S$100 capped at S$15", source="shop")
    v2 = parse_voucher_text("S$8 off min spend S$80", source="platform")
    v3 = parse_voucher_text("S$30 off min spend S$500", source="shop")

    net, evaluated = evaluate_vouchers(120.0, [v1, v2, v3])
    # v1: 10% of 120 = S$12 (eligible, shop bucket)
    # v2: S$8 off (eligible, platform bucket)
    # v3: min spend 500 not met (ineligible)
    assert evaluated[0].eligible is True
    assert evaluated[0].savings_sgd == 12.0
    assert evaluated[1].eligible is True
    assert evaluated[1].savings_sgd == 8.0
    assert evaluated[2].eligible is False
    assert net == 100.0


def test_cookie_normalization():
    raw = [
        {
            "name": "SPC_EC",
            "value": "abc123",
            "domain": ".shopee.sg",
            "path": "/",
            "sameSite": "no_restriction",
            "secure": False,
            "httpOnly": True,
            "expirationDate": 1800000000.5,
        }
    ]
    norm = normalize_cookies_for_playwright(raw)
    assert len(norm) == 1
    assert norm[0]["sameSite"] == "None"
    assert norm[0]["secure"] is True
    assert norm[0]["expires"] == 1800000000


def test_item_expiration_sgt():
    ref = date(2026, 11, 19)
    assert is_item_expired({"end_date": "2026-11-18"}, reference_date=ref) is True
    assert is_item_expired({"end_date": "2026-11-19"}, reference_date=ref) is False
    assert is_item_expired({"end_date": "2026-11-25"}, reference_date=ref) is False


def test_alert_deduplication_and_formatting():
    item = {
        "name": "Sony WH-1000XM5",
        "platform": "shopee_sg",
        "target_price": 400.0,
        "alert_on_new_voucher": True,
        "url": "https://shopee.sg/product/1/2",
    }
    latest = {
        "listed_price": 410.0,
        "net_price": 395.0,
        "seller_name": "Sony Official Store",
        "vouchers": [VoucherInfo(description="S$15 off", discount_type="fixed", discount_value=15.0).to_dict()],
    }

    should_send, reason = should_send_item_alert(item, latest)
    assert should_send is True
    assert reason == "target_met"

    msg = format_item_alert(item, latest, reason)
    assert "Sony WH-1000XM5" in msg
    assert "S$395.00" in msg
    assert "Shopee SG" in msg

    # Simulate already alerted with exact same state
    from scraper.models import compute_voucher_hash
    item["last_alerted_state"] = {
        "listed_price": 410.0,
        "net_price": 395.0,
        "voucher_hash": compute_voucher_hash(latest["vouchers"]),
    }
    should_send_again, _ = should_send_item_alert(item, latest)
    assert should_send_again is False


def test_cookie_warning_24h_throttle():
    now = datetime(2026, 11, 19, 12, 0, tzinfo=SGT)
    assert can_send_cookie_warning({}, now=now) is True
    recent = {"last_warned_at": (now - timedelta(hours=5)).isoformat()}
    assert can_send_cookie_warning(recent, now=now) is False
    old = {"last_warned_at": (now - timedelta(hours=25)).isoformat()}
    assert can_send_cookie_warning(old, now=now) is True
