from __future__ import annotations

import urllib.parse
from typing import Any

from scraper.models import ScrapeResult, VoucherInfo, now_sgt_iso
from scraper.platforms.base import human_delay, is_login_wall, open_sg_context
from scraper.voucher_calc import evaluate_vouchers, parse_sgd_price, parse_voucher_text


def _build_shopee_search_url(item: dict[str, Any]) -> str:
    store = (item.get("store_name") or "").strip()
    keyword = (item.get("keyword") or item.get("name") or "").strip()
    query = f"{store} {keyword}".strip()
    return f"https://shopee.sg/search?keyword={urllib.parse.quote_plus(query)}"


def _extract_shopee_vouchers_from_dom(page: Any) -> list[VoucherInfo]:
    vouchers: list[VoucherInfo] = []
    seen: set[str] = set()
    selectors = [
        "[class*='voucher-ticket']",
        "[class*='mini-vouchers'] [class*='voucher']",
        "[data-testid='pdp-voucher-item']",
        "button:has-text('% off')",
        "button:has-text('S$')",
        "div:has-text('Shop Vouchers') ~ div span",
    ]
    for sel in selectors:
        try:
            elements = page.locator(sel).all()[:10]
            for el in elements:
                txt = (el.inner_text() or "").strip()
                if not txt or len(txt) > 120:
                    continue
                if ("off" in txt.lower() or "%" in txt or "s$" in txt.lower()) and txt not in seen:
                    seen.add(txt)
                    vouchers.append(parse_voucher_text(txt, source="shop"))
        except Exception:
            continue
    return vouchers


def _scrape_shopee_once(item: dict[str, Any], cookies: list[dict[str, Any]] | None) -> ScrapeResult:
    result = ScrapeResult(last_checked=now_sgt_iso())
    target_url = (item.get("url") or "").strip() if item.get("mode", "url") == "url" else ""
    if not target_url:
        target_url = _build_shopee_search_url(item)

    captured_pdp: dict[str, Any] = {}

    with open_sg_context(cookies=cookies) as (_, _, page):
        def _on_response(resp: Any) -> None:
            try:
                url = resp.url
                if resp.status == 200 and ("/api/v4/pdp/get_pc" in url or "/api/v4/item/get" in url):
                    data = resp.json()
                    if isinstance(data, dict) and data.get("data"):
                        captured_pdp["payload"] = data["data"]
            except Exception:
                pass

        page.on("response", _on_response)
        page.goto(target_url, wait_until="domcontentloaded", timeout=35000)
        human_delay(2.0, 3.5)

        if is_login_wall(page.url, page.content()[:4000]):
            result.login_wall_detected = True
            result.error = "Shopee login wall detected"
            return result

        # If search mode, click the first matching product card
        if item.get("mode") == "search" or "/search?" in page.url:
            first_card = page.locator("a[data-sqe='link']").first
            if first_card.count() > 0:
                href = first_card.get_attribute("href")
                if href:
                    full_url = urllib.parse.urljoin("https://shopee.sg", href)
                    page.goto(full_url, wait_until="domcontentloaded", timeout=35000)
                    human_delay(2.0, 3.2)

        result.resolved_url = page.url
        if is_login_wall(page.url, page.content()[:4000]):
            result.login_wall_detected = True
            result.error = "Shopee anti-bot / login wall detected. Add SHOPEE_COOKIES_JSON secret for logged-in checks."
            return result

        # Prefer intercepted PDP API payload if available
        pdp = captured_pdp.get("payload") or {}
        item_data = pdp.get("item") if isinstance(pdp.get("item"), dict) else pdp
        if isinstance(item_data, dict) and item_data.get("price"):
            raw_price = item_data.get("price", 0)
            result.listed_price = round(raw_price / 100000.0, 2) if raw_price > 10000 else float(raw_price)
            raw_orig = item_data.get("price_before_discount") or 0
            if raw_orig:
                result.original_price = round(raw_orig / 100000.0, 2) if raw_orig > 10000 else float(raw_orig)
            stock = item_data.get("stock")
            if isinstance(stock, int):
                result.stock_status = "in_stock" if stock > 0 else "out_of_stock"

        shop_info = pdp.get("shop_detailed") or {}
        if isinstance(shop_info, dict) and shop_info.get("name"):
            result.seller_name = str(shop_info["name"])

        # Fallback / supplement from DOM
        if result.listed_price is None:
            for sel in ["[class*='pqTWkA']", "[data-testid='pdp-product-price']", "div.flex.items-center > div:has-text('S$')"]:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    parsed = parse_sgd_price(loc.inner_text())
                    if parsed:
                        result.listed_price = parsed
                        break

        if result.original_price is None:
            for sel in ["[class*='Y3DvsN']", "del:has-text('S$')"]:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    parsed = parse_sgd_price(loc.inner_text())
                    if parsed:
                        result.original_price = parsed
                        break

        if not result.seller_name:
            for sel in ["[class*='VlDReK']", "[data-testid='pdp-shop-name']"]:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    txt = (loc.inner_text() or "").strip()
                    if txt:
                        result.seller_name = txt
                        break

        if result.stock_status == "unknown":
            body_text = (page.locator("body").inner_text() or "").lower()
            if "sold out" in body_text or "out of stock" in body_text:
                result.stock_status = "out_of_stock"
            elif result.listed_price is not None:
                result.stock_status = "in_stock"

        result.vouchers = _extract_shopee_vouchers_from_dom(page)
        result.net_price, result.vouchers = evaluate_vouchers(result.listed_price, result.vouchers)
        return result


def scrape_shopee_item(item: dict[str, Any], cookies: list[dict[str, Any]] | None = None) -> ScrapeResult:
    """Scrape a Shopee SG product, falling back to public mode if cookies hit a login wall."""
    try:
        res = _scrape_shopee_once(item, cookies)
        if res.login_wall_detected and cookies:
            fallback = _scrape_shopee_once(item, None)
            fallback.login_wall_detected = True
            return fallback
        return res
    except Exception as exc:
        return ScrapeResult(
            last_checked=now_sgt_iso(),
            resolved_url=item.get("url"),
            error=f"Shopee scrape error: {exc}",
        )
