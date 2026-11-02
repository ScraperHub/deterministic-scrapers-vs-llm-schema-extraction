"""Step 1: one product record, two scrapers with different key names.

Live amazon-product-details returns name, rawPrice, currency, inStock, customerReview and
customerReviewCount, with the ASIN inside productInformation. Live walmart-product-details
returns title, itemId, price, currency, ratings and reviewsCount, and no stock field.
"""
import json
import re

from _common import FINAL, save

SCHEMA_VERSION = "product.v1"
FIELDS = ["title", "id", "brand", "price", "currency", "availability", "rating", "reviews_count"]


def _clean(value):
    if isinstance(value, str):
        value = value.replace("\u200e", "").replace("\u200f", "").strip()
        return value or None
    return value


def _asin_from(raw: dict, url: str) -> str | None:
    for row in raw.get("productInformation") or []:
        if isinstance(row, dict) and _clean(row.get("name")) == "ASIN":
            return _clean(row.get("value"))
    match = re.search(r"/dp/([A-Z0-9]{10})", url)
    return match.group(1) if match else None


def map_amazon(raw: dict, url: str) -> dict:
    return {
        "title": _clean(raw.get("name")),
        "id": _asin_from(raw, url),
        "brand": _clean(raw.get("brand")),
        "price": _clean(raw.get("rawPrice")) or _clean(raw.get("price")),
        "currency": _clean(raw.get("currency")),
        "availability": raw.get("inStock"),
        "rating": _clean(raw.get("customerReview")),
        "reviews_count": raw.get("customerReviewCount"),
    }


def map_walmart(raw: dict, url: str) -> dict:
    availability = None
    if "outOfStock" in raw:
        availability = not raw["outOfStock"]
    elif "availability" in raw:
        availability = raw["availability"]
    return {
        "title": _clean(raw.get("title")),
        "id": _clean(raw.get("itemId")) or _clean(raw.get("product_id")),
        "brand": _clean(raw.get("brand")),
        "price": _clean(raw.get("price")),
        "currency": _clean(raw.get("currency")),
        "availability": availability,
        "rating": _clean(raw.get("ratings")) or _clean(raw.get("rating")),
        "reviews_count": _clean(raw.get("reviewsCount")) or _clean(raw.get("reviews_count")),
    }


def map_scraper_output(raw: dict, url: str) -> dict:
    if "customerReviewCount" in raw or "asin" in raw or "name" in raw:
        return map_amazon(raw, url)
    return map_walmart(raw, url)


if __name__ == "__main__":
    fixtures = FINAL / "tests" / "fixtures"
    amazon = json.loads((fixtures / "amazon_scraper.json").read_text(encoding="utf-8"))["body"]
    walmart = json.loads((fixtures / "walmart_scraper.json").read_text(encoding="utf-8"))["body"]
    mapped = {
        "amazon": map_amazon(amazon, "https://www.amazon.com/dp/B0TESTCASE"),
        "walmart": map_walmart(walmart, "https://www.walmart.com/ip/3551794083"),
    }
    for site, record in mapped.items():
        print(f"{site:8s}", json.dumps(record, ensure_ascii=False))
    print(f"schema {SCHEMA_VERSION}: same {len(FIELDS)} keys from both scrapers ->", save("01_mapped", mapped))
