from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

SGT = timezone(timedelta(hours=8), name="SGT")

PLATFORM_LABELS: dict[str, str] = {
    "shopee_sg": "Shopee SG",
    "lazada_sg": "Lazada SG",
    "amazon_sg": "Amazon SG",
}

PLATFORM_DOMAINS: dict[str, str] = {
    "shopee_sg": "shopee.sg",
    "lazada_sg": "lazada.sg",
    "amazon_sg": "amazon.sg",
}


def now_sgt() -> datetime:
    """Return current timezone-aware datetime in Singapore Time (UTC+8)."""
    return datetime.now(SGT)


def now_sgt_iso() -> str:
    """Return current SGT timestamp in ISO-8601 format."""
    return now_sgt().isoformat(timespec="seconds")


def today_sgt() -> date:
    """Return current date in Singapore Time (UTC+8)."""
    return now_sgt().date()


def is_item_expired(item: dict[str, Any], reference_date: date | None = None) -> bool:
    """Check whether an item's monitoring duration has ended in SGT."""
    ref = reference_date or today_sgt()
    end_date_str = item.get("end_date")
    if not end_date_str:
        return False
    try:
        end_d = date.fromisoformat(str(end_date_str)[:10])
        return ref > end_d
    except ValueError:
        return False


def is_item_not_started(item: dict[str, Any], reference_date: date | None = None) -> bool:
    """Check whether an item's monitoring start_date is still in the future."""
    ref = reference_date or today_sgt()
    start_date_str = item.get("start_date")
    if not start_date_str:
        return False
    try:
        start_d = date.fromisoformat(str(start_date_str)[:10])
        return ref < start_d
    except ValueError:
        return False


@dataclass
class VoucherInfo:
    description: str
    discount_type: str = "unknown"  # "fixed" | "percent" | "unknown"
    discount_value: float = 0.0
    min_spend: float | None = None
    max_cap: float | None = None
    code: str | None = None
    source: str = "product"  # "shop" | "platform" | "product"
    eligible: bool = True
    savings_sgd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScrapeResult:
    listed_price: float | None = None
    original_price: float | None = None
    net_price: float | None = None
    vouchers: list[VoucherInfo] = field(default_factory=list)
    stock_status: str = "unknown"  # "in_stock" | "out_of_stock" | "unknown"
    seller_name: str | None = None
    resolved_url: str | None = None
    last_checked: str = field(default_factory=now_sgt_iso)
    error: str | None = None
    login_wall_detected: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["vouchers"] = [v.to_dict() for v in self.vouchers]
        return data


def compute_voucher_hash(vouchers: list[dict[str, Any]]) -> str:
    """Produce a stable hash of detected vouchers for alert deduplication."""
    normalized = sorted(
        {
            (
                str(v.get("description", "")).strip().lower(),
                str(v.get("code") or "").strip().lower(),
                float(v.get("discount_value") or 0.0),
                v.get("discount_type", ""),
            )
            for v in vouchers
        }
    )
    payload = json.dumps(normalized, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
