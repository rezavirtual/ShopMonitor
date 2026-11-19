"""Platform-specific Playwright scrapers for Singapore e-commerce sites."""

from scraper.platforms.amazon import scrape_amazon_item
from scraper.platforms.lazada import scrape_lazada_item
from scraper.platforms.shopee import scrape_shopee_item

SCRAPER_DISPATCH = {
    "shopee_sg": scrape_shopee_item,
    "lazada_sg": scrape_lazada_item,
    "amazon_sg": scrape_amazon_item,
}

__all__ = [
    "SCRAPER_DISPATCH",
    "scrape_shopee_item",
    "scrape_lazada_item",
    "scrape_amazon_item",
]
