"""Step 7: currency symbols to a code and a number, availability to a two-value enum.

None of the eight shared fields carries a unit, so no unit conversion runs here.
"""
import json
import re

from _common import load, save

FIELDS = ["title", "id", "brand", "price", "currency", "availability", "rating", "reviews_count"]
CURRENCY_SYMBOLS = {"US$": "USD", "C$": "CAD", "A$": "AUD", "$": "USD", "£": "GBP", "€": "EUR", "¥": "JPY", "₹": "INR"}
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
# Placeholders a model writes instead of a real null.
NULLISH = {"null", "none", "n/a", "unknown", "not specified"}


def _text(value) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", str(value).replace("\u200e", "")).strip()
    return None if not value or value.lower() in NULLISH else value


def normalize_currency(value) -> str | None:
    text = _text(value)
    if not text:
        return None
    if re.fullmatch(r"[A-Za-z]{3}", text):
        return text.upper()
    for symbol, code in CURRENCY_SYMBOLS.items():
        if text.startswith(symbol) or text == symbol:
            return code
    return None


def parse_price(value, currency_hint=None) -> tuple[float | None, str | None]:
    currency = normalize_currency(currency_hint)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value), currency
    text = _text(value)
    match = _NUMBER.search(text or "")
    if not match:
        return None, currency
    if currency is None:
        currency = normalize_currency(text[: match.start()].strip() or None)
    number = match.group(0)
    if re.fullmatch(r"\d+,\d{2}", number):  # decimal comma, as in "39,90"
        return float(number.replace(",", ".")), currency
    return float(number.replace(",", "")), currency


def normalize_availability(value) -> str | None:
    if isinstance(value, bool):
        return "in_stock" if value else "out_of_stock"
    text = (_text(value) or "").lower().replace("-", "_").replace(" ", "_")
    if not text:
        return None
    if text in ("in_stock", "out_of_stock"):
        return text
    if any(s in text for s in ("out_of_stock", "unavailable", "sold_out", "not_available")):
        return "out_of_stock"
    if any(s in text for s in ("in_stock", "available", "left_in_stock", "add_to_cart")):
        return "in_stock"
    return None


def parse_rating(value) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", _text(value) or "")
    return float(match.group(0)) if match else None


def parse_count(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*([KM])?", (_text(value) or "").upper())
    if not match:
        return None
    scale = {"K": 1_000, "M": 1_000_000}.get(match.group(2) or "", 1)
    return int(round(float(match.group(1).replace(",", "")) * scale))


def clean_brand(value) -> str | None:
    text = _text(value)
    if not text:
        return None
    match = re.fullmatch(r"(?i)visit the (.+?) store", text)
    if match:
        text = match.group(1)
    return re.sub(r"(?i)^brand:\s*", "", text) or None


def normalize_record(mapped: dict) -> dict:
    price, currency = parse_price(mapped.get("price"), mapped.get("currency"))
    return {
        "title": _text(mapped.get("title")),
        "id": _text(mapped.get("id")),
        "brand": clean_brand(mapped.get("brand")),
        "price": price,
        "currency": currency if price is not None else None,
        "availability": normalize_availability(mapped.get("availability")),
        "rating": parse_rating(mapped.get("rating")),
        "reviews_count": parse_count(mapped.get("reviews_count")),
    }


if __name__ == "__main__":
    mapped = load("01_mapped") or {}
    for site, raw in mapped.items():
        print(f"{site:8s} raw  ", json.dumps(raw, ensure_ascii=False))
        print(f"{site:8s} clean", json.dumps(normalize_record(raw), ensure_ascii=False))
    for sample in ("$1,299.99", "€39,90", "See price in cart"):
        print(f"{sample!r:22s} ->", parse_price(sample))
    if not mapped:
        print("run 01_schema.py first to see the mapped records normalised")
    else:
        print("saved", save("07_normalized", {s: normalize_record(r) for s, r in mapped.items()}))
