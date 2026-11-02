"""Shared product record, the JSON Schema gate, and the per-scraper key maps."""
import re
from urllib.parse import urlparse

SCHEMA_VERSION = "product.v1"

FIELDS = ["title", "id", "brand", "price", "currency", "availability", "rating", "reviews_count"]
AVAILABILITY = ["in_stock", "out_of_stock"]

SCRAPERS = {
    "www.amazon.com": "amazon-product-details",
    "amazon.com": "amazon-product-details",
    "www.walmart.com": "walmart-product-details",
    "walmart.com": "walmart-product-details",
}

PRODUCT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": SCHEMA_VERSION,
    "type": "object",
    "required": FIELDS + ["_meta"],
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 3},
        "id": {"type": "string", "minLength": 3},
        "brand": {"type": ["string", "null"]},
        "price": {"type": ["number", "null"], "minimum": 0},
        "currency": {"type": ["string", "null"], "pattern": "^[A-Z]{3}$"},
        "availability": {"enum": AVAILABILITY + [None]},
        "rating": {"type": ["number", "null"], "minimum": 0, "maximum": 5},
        "reviews_count": {"type": ["integer", "null"], "minimum": 0},
        "_meta": {
            "type": "object",
            "required": ["url", "path", "extractor", "schema_version"],
            "properties": {
                "url": {"type": "string"},
                "path": {"enum": ["scraper", "autoparse", "markdown_llm"]},
                "extractor": {"type": "string"},
                "schema_version": {"const": SCHEMA_VERSION},
            },
        },
    },
    "allOf": [
        {"if": {"properties": {"price": {"type": "number"}}, "required": ["price"]},
         "then": {"properties": {"currency": {"type": "string"}}}},
    ],
}

# Strict structured-output schema for the LLM: every key present, every value nullable.
LLM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": FIELDS,
    "properties": {
        "title": {"type": ["string", "null"], "description": "Product title as shown. null if not on the page."},
        "id": {"type": ["string", "null"], "description": "Retailer product id (ASIN or Walmart item id). null if not on the page."},
        "brand": {"type": ["string", "null"], "description": "Brand name. null if not on the page."},
        "price": {"type": ["number", "null"], "description": "Current selling price as a number. null if not on the page."},
        "currency": {"type": ["string", "null"], "description": "ISO 4217 code for the price. null if no price."},
        "availability": {"type": ["string", "null"], "enum": AVAILABILITY + [None],
                         "description": "Stock status. null if the page does not say."},
        "rating": {"type": ["number", "null"], "description": "Average star rating out of 5. null if not on the page."},
        "reviews_count": {"type": ["integer", "null"], "description": "Number of ratings or reviews. null if not on the page."},
    },
}


def scraper_for(url: str) -> str | None:
    return SCRAPERS.get(urlparse(url).hostname or "")


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
    """amazon-product-details: name, rawPrice/price, currency, inStock, customerReview, customerReviewCount."""
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
    """walmart-product-details: title, itemId, price, currency, ratings, reviewsCount. No stock field."""
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
    """Pick the key map from the keys the scraper actually returned."""
    if "customerReviewCount" in raw or "asin" in raw or "name" in raw:
        return map_amazon(raw, url)
    return map_walmart(raw, url)
