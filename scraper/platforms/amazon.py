from __future__ import annotations

import urllib.parse
from typing import Any

from scraper.models import ScrapeResult, VoucherInfo, now_sgt_iso
from scraper.platforms.base import human_delay, is_login_wall, open_sg_context
from scraper.voucher_calc import evaluate_vouchers, parse_sgd_price, parse_voucher_text


def _build_amazon_search_url(item: dict[str, Any]) -> str:
    store = (item.get("store_name") or "").strip()
    keyword = (item.get("keyword") or item.get("name") or "").strip()
    query = f"{store} {keyword}".strip()
    return f"https://www.amazon.sg/s?k={urllib.parse.quote_plus(query)}"


def _extract_amazon_vouchers(page: Any) -> list[VoucherInfo]:
    vouchers: list[VoucherInfo] = []
    seen: set[str] = set()
    selectors = [
        "#couponBadgeRegularVpc",
        "[id^='couponText']",
        ".promoPriceBlockMessage",
        "#applicablePromotionList_feature_div span",
        "label[id^='coupon'] span",
        "span:has-text('Apply')",
    ]
    for sel in selectors:
        try:
            for el in page.locator(sel).all()[:8]:
                txt = (el.inner_text() or "").strip()
                if not txt or len(txt) > 140:
                    continue
                lower = txt.lower()
                if ("voucher" in lower or "coupon" in lower or "save" in lower or "% off" in lower) and txt not in seen:
                    seen.add(txt)
                    vouchers.append(parse_voucher_text(txt, source="product"))
        except Exception:
            continue
    return vouchers


def _scrape_amazon_once(item: dict[str, Any], cookies: list[dict[str, Any]] | None) -> ScrapeResult:
    result = ScrapeResult(last_checked=now_sgt_iso())
    target_url = (item.get("url") or "").strip() if item.get("mode", "url") == "url" else ""
    if not target_url:
        target_url = _build_amazon_search_url(item)

    with open_sg_context(cookies=cookies) as (_, _, page):
        page.goto(target_url, wait_until="domcontentloaded", timeout=35000)
        human_delay(1.8, 3.0)

        if is_login_wall(page.url, page.content()[:4000]):
            result.login_wall_detected = True
            result.error = "Amazon SG login wall detected"
            return result

        if item.get("mode") == "search" or "/s?" in page.url:
            for link_sel in [
                "div[data-component-type='s-search-result'] h2 a",
                "div[data-component-type='s-search-result'] a:has(h2)",
                "div[data-component-type='s-search-result'] a.a-link-normal[href*='/dp/']",
            ]:
                first_link = page.locator(link_sel).first
                if first_link.count() > 0:
                    href = first_link.get_attribute("href")
                    if href:
                        full_url = urllib.parse.urljoin("https://www.amazon.sg", href)
                        page.goto(full_url, wait_until="domcontentloaded", timeout=35000)
                        human_delay(1.8, 3.0)
                        break

        result.resolved_url = page.url

        body_sample = (page.content() or "")[:6000].lower()
        if "validatecaptcha" in page.url.lower() or "type the characters you see" in body_sample:
            result.error = "Amazon SG bot/CAPTCHA check triggered; will retry next cycle."
            return result

        for sel in [
            "#corePrice_feature_div .a-price .a-offscreen",
            "#corePriceDisplay_desktop_feature_div .priceToPay .a-offscreen",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            ".a-price .a-offscreen",
        ]:
            loc = page.locator(sel).first
            if loc.count() > 0:
                parsed = parse_sgd_price(loc.inner_text())
                if parsed:
                    result.listed_price = parsed
                    break

        for sel in [
            "#corePriceDisplay_desktop_feature_div .basisPrice .a-offscreen",
            ".a-text-price .a-offscreen",
        ]:
            loc = page.locator(sel).first
            if loc.count() > 0:
                parsed = parse_sgd_price(loc.inner_text())
                if parsed and (result.listed_price is None or parsed > result.listed_price):
                    result.original_price = parsed
                    break

        for sel in ["#sellerProfileTriggerId", "#merchant-info a", "#bylineInfo"]:
            loc = page.locator(sel).first
            if loc.count() > 0:
                txt = (loc.inner_text() or "").strip()
                if txt:
                    result.seller_name = txt
                    break

        avail_loc = page.locator("#availability").first
        if avail_loc.count() > 0:
            avail_txt = (avail_loc.inner_text() or "").lower()
            if "currently unavailable" in avail_txt or "out of stock" in avail_txt:
                result.stock_status = "out_of_stock"
            elif "in stock" in avail_txt:
                result.stock_status = "in_stock"
        elif result.listed_price is not None:
            result.stock_status = "in_stock"

        result.vouchers = _extract_amazon_vouchers(page)
        result.net_price, result.vouchers = evaluate_vouchers(result.listed_price, result.vouchers)
        return result


def scrape_amazon_item(item: dict[str, Any], cookies: list[dict[str, Any]] | None = None) -> ScrapeResult:
    """Scrape an Amazon SG product, falling back to public mode if cookies hit a login wall."""
    try:
        res = _scrape_amazon_once(item, cookies)
        if res.login_wall_detected and cookies:
            fallback = _scrape_amazon_once(item, None)
            fallback.login_wall_detected = True
            return fallback
        return res
    except Exception as exc:
        return ScrapeResult(
            last_checked=now_sgt_iso(),
            resolved_url=item.get("url"),
            error=f"Amazon SG scrape error: {exc}",
        )
