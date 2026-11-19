from __future__ import annotations

import urllib.parse
from typing import Any

from scraper.models import ScrapeResult, VoucherInfo, now_sgt_iso
from scraper.platforms.base import human_delay, is_login_wall, open_sg_context
from scraper.voucher_calc import evaluate_vouchers, parse_sgd_price, parse_voucher_text


def _build_lazada_search_url(item: dict[str, Any]) -> str:
    store = (item.get("store_name") or "").strip()
    keyword = (item.get("keyword") or item.get("name") or "").strip()
    query = f"{store} {keyword}".strip()
    return f"https://www.lazada.sg/catalog/?q={urllib.parse.quote_plus(query)}"


def _extract_lazada_vouchers(page: Any) -> list[VoucherInfo]:
    vouchers: list[VoucherInfo] = []
    seen: set[str] = set()
    selectors = [
        ".voucher-item",
        "[class*='pdp-voucher'] [class*='tag']",
        "[class*='voucher-tag']",
        "[data-spm='voucher'] span",
        "span:has-text('% Off')",
        "span:has-text('Off Min')",
    ]
    for sel in selectors:
        try:
            for el in page.locator(sel).all()[:10]:
                txt = (el.inner_text() or "").strip()
                if not txt or len(txt) > 120:
                    continue
                if ("off" in txt.lower() or "%" in txt or "s$" in txt.lower()) and txt not in seen:
                    seen.add(txt)
                    vouchers.append(parse_voucher_text(txt, source="shop"))
        except Exception:
            continue
    return vouchers


def _scrape_lazada_once(item: dict[str, Any], cookies: list[dict[str, Any]] | None) -> ScrapeResult:
    result = ScrapeResult(last_checked=now_sgt_iso())
    target_url = (item.get("url") or "").strip() if item.get("mode", "url") == "url" else ""
    if not target_url:
        target_url = _build_lazada_search_url(item)

    with open_sg_context(cookies=cookies) as (_, _, page):
        page.goto(target_url, wait_until="domcontentloaded", timeout=35000)
        human_delay(2.0, 3.5)

        if is_login_wall(page.url, page.content()[:4000]):
            result.login_wall_detected = True
            result.error = "Lazada login wall detected"
            return result

        if item.get("mode") == "search" or "/catalog/" in page.url:
            first_card = page.locator("[data-qa-locator='product-item'] a").first
            if first_card.count() > 0:
                href = first_card.get_attribute("href")
                if href:
                    full_url = urllib.parse.urljoin("https://www.lazada.sg", href)
                    page.goto(full_url, wait_until="domcontentloaded", timeout=35000)
                    human_delay(2.0, 3.2)

        result.resolved_url = page.url

        for sel in [".pdp-price_type_normal", ".pdp-product-price span", "[class*='pdp-price']"]:
            loc = page.locator(sel).first
            if loc.count() > 0:
                parsed = parse_sgd_price(loc.inner_text())
                if parsed:
                    result.listed_price = parsed
                    break

        for sel in [".pdp-price_type_deleted", "del.pdp-price", "[class*='origin-block'] del"]:
            loc = page.locator(sel).first
            if loc.count() > 0:
                parsed = parse_sgd_price(loc.inner_text())
                if parsed:
                    result.original_price = parsed
                    break

        for sel in [".seller-name__detail-name", "[class*='seller-name'] a"]:
            loc = page.locator(sel).first
            if loc.count() > 0:
                txt = (loc.inner_text() or "").strip()
                if txt:
                    result.seller_name = txt
                    break

        body_text = (page.locator("body").inner_text() or "").lower()
        if "out of stock" in body_text or "sold out" in body_text:
            result.stock_status = "out_of_stock"
        elif result.listed_price is not None:
            result.stock_status = "in_stock"

        result.vouchers = _extract_lazada_vouchers(page)
        result.net_price, result.vouchers = evaluate_vouchers(result.listed_price, result.vouchers)
        return result


def scrape_lazada_item(item: dict[str, Any], cookies: list[dict[str, Any]] | None = None) -> ScrapeResult:
    """Scrape a Lazada SG product, falling back to public mode if cookies hit a login wall."""
    try:
        res = _scrape_lazada_once(item, cookies)
        if res.login_wall_detected and cookies:
            fallback = _scrape_lazada_once(item, None)
            fallback.login_wall_detected = True
            return fallback
        return res
    except Exception as exc:
        return ScrapeResult(
            last_checked=now_sgt_iso(),
            resolved_url=item.get("url"),
            error=f"Lazada scrape error: {exc}",
        )
