from __future__ import annotations

import re
from typing import Iterable

from scraper.models import VoucherInfo

_PRICE_RE = re.compile(r"(?:S\$|\$|SGD\s*)(\d+(?:,\d{3})*(?:\.\d{1,2})?)", re.IGNORECASE)
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
_MIN_SPEND_RE = re.compile(
    r"(?:min\.?\s*spend|min\.?\s*order|orders?\s*(?:over|above)|spend\s*at\s*least)\s*(?:S\$|\$|SGD\s*)?(\d+(?:,\d{3})*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_CAP_RE = re.compile(
    r"(?:cap(?:ped)?\s*(?:at)?|max\.?\s*(?:discount|off)?)\s*(?:S\$|\$|SGD\s*)?(\d+(?:,\d{3})*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_CODE_RE = re.compile(r"(?:code|promo(?:\s*code)?)\s*[:\-]?\s*([A-Z0-9]{4,20})\b", re.IGNORECASE)


def parse_sgd_price(text: str | None) -> float | None:
    """Extract the first SGD price float from a string."""
    if not text:
        return None
    cleaned = text.replace(",", "")
    m = re.search(r"(?:S\$|\$|SGD\s*)?(\d+(?:\.\d{1,2})?)", cleaned, re.IGNORECASE)
    if not m:
        return None
    try:
        val = float(m.group(1))
        return round(val, 2) if val > 0 else None
    except ValueError:
        return None


def parse_voucher_text(raw_text: str, source: str = "product") -> VoucherInfo:
    """Parse a voucher/coupon text snippet into a structured VoucherInfo object."""
    text = " ".join(raw_text.split())
    min_spend: float | None = None
    max_cap: float | None = None
    code: str | None = None

    m_min = _MIN_SPEND_RE.search(text)
    if m_min:
        min_spend = float(m_min.group(1).replace(",", ""))

    m_cap = _CAP_RE.search(text)
    if m_cap:
        max_cap = float(m_cap.group(1).replace(",", ""))

    m_code = _CODE_RE.search(text)
    if m_code:
        code = m_code.group(1).upper()

    m_pct = _PERCENT_RE.search(text)
    if m_pct:
        pct = float(m_pct.group(1))
        return VoucherInfo(
            description=text,
            discount_type="percent",
            discount_value=pct,
            min_spend=min_spend,
            max_cap=max_cap,
            code=code,
            source=source,
        )

    # Otherwise look for a fixed S$ off amount (before min-spend mention if possible)
    before_min = _MIN_SPEND_RE.split(text)[0] if m_min else text
    m_fixed = _PRICE_RE.search(before_min) or _PRICE_RE.search(text)
    if m_fixed:
        amt = float(m_fixed.group(1).replace(",", ""))
        return VoucherInfo(
            description=text,
            discount_type="fixed",
            discount_value=amt,
            min_spend=min_spend,
            max_cap=max_cap,
            code=code,
            source=source,
        )

    return VoucherInfo(
        description=text,
        discount_type="unknown",
        discount_value=0.0,
        min_spend=min_spend,
        max_cap=max_cap,
        code=code,
        source=source,
    )


def evaluate_vouchers(listed_price: float | None, vouchers: Iterable[VoucherInfo]) -> tuple[float | None, list[VoucherInfo]]:
    """Evaluate voucher eligibility against listed_price and compute net_price.

    Applies the single best eligible voucher per source ('shop'/'product' and 'platform')
    if both exist, or the best single eligible voucher otherwise, keeping calculations
    conservative so discounts are never overstated.
    """
    voucher_list = list(vouchers)
    if listed_price is None or listed_price <= 0:
        return listed_price, voucher_list

    best_by_bucket: dict[str, float] = {}

    for v in voucher_list:
        if v.min_spend is not None and listed_price < v.min_spend:
            v.eligible = False
            v.savings_sgd = 0.0
            continue

        v.eligible = True
        if v.discount_type == "fixed":
            savings = min(v.discount_value, listed_price)
        elif v.discount_type == "percent":
            savings = listed_price * (v.discount_value / 100.0)
            if v.max_cap is not None:
                savings = min(savings, v.max_cap)
            savings = min(savings, listed_price)
        else:
            savings = 0.0

        v.savings_sgd = round(savings, 2)
        bucket = "platform" if v.source == "platform" else "seller"
        if v.savings_sgd > best_by_bucket.get(bucket, 0.0):
            best_by_bucket[bucket] = v.savings_sgd

    total_savings = sum(best_by_bucket.values())
    net_price = round(max(0.0, listed_price - total_savings), 2)
    return net_price, voucher_list
