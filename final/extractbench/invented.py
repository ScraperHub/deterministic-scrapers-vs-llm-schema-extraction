"""A value is invented when no normalised form of it appears in the page text stored for that run."""
import html
import re

_ESCAPES = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|>~])")

IN_STOCK_CUES = ("in stock", "add to cart", "left in stock", "pickup as soon as", "pickup today", "delivery as soon as")
OUT_OF_STOCK_CUES = ("out of stock", "currently unavailable", "sold out", "not available", "unavailable")
CURRENCY_CUES = {"USD": ("$", "usd"), "GBP": ("£", "gbp"), "EUR": ("€", "eur"), "CAD": ("c$", "cad"), "JPY": ("¥", "jpy")}


def page_text(markdown: str) -> str:
    text = html.unescape(_ESCAPES.sub(r"\1", markdown or ""))
    text = text.replace("\u200e", "").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).lower()


def _number_forms(value: float) -> list[str]:
    forms = {f"{value:,.2f}", f"{value:.2f}"}
    if float(value).is_integer():
        forms |= {f"{int(value):,}", str(int(value))}
    return sorted(forms, key=len, reverse=True)


def _has_number(text: str, value: float) -> bool:
    for form in _number_forms(value):
        if re.search(rf"(?<![\d.,]){re.escape(form)}(?![\d]|[.,]\d)", text):
            return True
    return False


def _has_abbreviated(text: str, value: float) -> bool:
    """27406 is on the page if the page prints 27.4K; compare at the precision shown."""
    for match in re.finditer(r"(?<![\d.,])(\d+(?:\.(\d+))?)\s*([km])\b", text):
        shown, decimals = float(match.group(1)), len(match.group(2) or "")
        scale = 1_000 if match.group(3) == "k" else 1_000_000
        if round(value / scale, decimals) == shown:
            return True
    return False


def _has_rating(text: str, value: float) -> bool:
    forms = {f"{value:.1f}"} | ({str(int(value))} if float(value).is_integer() else set())
    return any(re.search(rf"(?<![\d.]){re.escape(f)}(?:\s*out of 5|\s*stars|\))", text) for f in forms) or any(
        re.search(rf"\(\s*{re.escape(f)}\s*\)", text) for f in forms
    )


def _has_text(text: str, value: str) -> bool:
    needle = re.sub(r"\s+", " ", html.unescape(value)).strip().lower()
    if not needle:
        return True
    return needle[:60] in text or needle[:60].replace(" ", "") in text.replace(" ", "")


def is_supported(field: str, value, text: str) -> bool:
    if value is None:
        return True
    if field in ("title", "brand", "id"):
        return _has_text(text, str(value))
    if field == "price":
        return _has_number(text, float(value))
    if field == "reviews_count":
        return _has_number(text, float(value)) or _has_abbreviated(text, float(value))
    if field == "rating":
        return _has_rating(text, float(value))
    if field == "currency":
        return any(cue in text for cue in CURRENCY_CUES.get(value, (value.lower(),)))
    if field == "availability":
        cues = IN_STOCK_CUES if value == "in_stock" else OUT_OF_STOCK_CUES
        return any(cue in text for cue in cues)
    return True


def invented_fields(record: dict, markdown: str, fields: list[str], url: str = "") -> list[str]:
    """The URL counts as input: an id taken from it is not invented."""
    text = page_text(markdown) + " " + url.lower()
    return [f for f in fields if record.get(f) is not None and not is_supported(f, record[f], text)]
