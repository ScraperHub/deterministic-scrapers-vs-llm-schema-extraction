"""Step 4: format=md on the same URLs, one structured-output LLM call, and the invented-value check.

A value is invented when no normalised form of it appears in that page's stored Markdown.
The check runs on every path, so the built-in scraper is never its own ground truth.
"""
import html
import json
import re
import time

from _common import crawling_api, load_step, openai_client, save, urls

MAX_MARKDOWN_CHARS = 60_000
SYSTEM_PROMPT = (
    "You extract one product record from a retail product page converted to Markdown. "
    "Use only values printed on the page. If a value is not on the page, return null. "
    "Do not guess, convert, or fill in values from general knowledge."
)


FIELDS = ["title", "id", "brand", "price", "currency", "availability", "rating", "reviews_count"]

# Strict structured output: every key present, every value nullable, "null if not on the page" per field.
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
        "availability": {"type": ["string", "null"], "enum": ["in_stock", "out_of_stock", None],
                         "description": "Stock status. null if the page does not say."},
        "rating": {"type": ["number", "null"], "description": "Average star rating out of 5. null if not on the page."},
        "reviews_count": {"type": ["integer", "null"], "description": "Number of ratings or reviews. null if not on the page."},
    },
}


def fetch_markdown(api, url: str) -> dict:
    started = time.monotonic()
    res = api.get(url, {"format": "md"})
    body = res.get("body") or b""
    return {
        "url": url,
        "cb_status": (res.get("headers") or {}).get("cb_status"),
        "latency_s": round(time.monotonic() - started, 2),
        "markdown": body.decode("utf-8", "replace") if isinstance(body, bytes) else body,
    }


def extract_with_llm(client, model: str, url: str, markdown: str) -> dict:
    started = time.monotonic()
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": f"URL: {url}\n\n{markdown[:MAX_MARKDOWN_CHARS]}"}],
        response_format={"type": "json_schema",
                         "json_schema": {"name": "product_v1", "strict": True, "schema": LLM_SCHEMA}},
    )
    try:
        data, error = json.loads(response.choices[0].message.content or ""), None
    except json.JSONDecodeError as exc:
        data, error = None, f"json_parse_error: {exc}"
    return {"data": data, "error": error, "model": response.model, "latency_s": round(time.monotonic() - started, 2),
            "prompt_tokens": response.usage.prompt_tokens, "completion_tokens": response.usage.completion_tokens}


# The invented-value check.
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
    return any(re.search(rf"(?<![\d.,]){re.escape(f)}(?![\d]|[.,]\d)", text) for f in _number_forms(value))


def _has_abbreviated(text: str, value: float) -> bool:
    """27406 is on the page if the page prints 27.4K; compare at the precision shown."""
    for m in re.finditer(r"(?<![\d.,])(\d+(?:\.(\d+))?)\s*([km])\b", text):
        scale = 1_000 if m.group(3) == "k" else 1_000_000
        if round(value / scale, len(m.group(2) or "")) == float(m.group(1)):
            return True
    return False


def _has_rating(text: str, value: float) -> bool:
    forms = {f"{value:.1f}"} | ({str(int(value))} if float(value).is_integer() else set())
    return any(re.search(rf"(?<![\d.]){re.escape(f)}(?:\s*out of 5|\s*stars|\))", text) for f in forms) or any(
        re.search(rf"\(\s*{re.escape(f)}\s*\)", text) for f in forms
    )


def _has_text(text: str, value: str) -> bool:
    needle = re.sub(r"\s+", " ", html.unescape(value)).strip().lower()[:60]
    return not needle or needle in text or needle.replace(" ", "") in text.replace(" ", "")


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
        return any(cue in text for cue in (IN_STOCK_CUES if value == "in_stock" else OUT_OF_STOCK_CUES))
    return True


def invented_fields(record: dict, markdown: str, fields: list[str], url: str = "") -> list[str]:
    """The URL counts as input: an id taken from it is not invented."""
    text = page_text(markdown) + " " + url.lower()
    return [f for f in fields if record.get(f) is not None and not is_supported(f, record[f], text)]


if __name__ == "__main__":
    normalize = load_step("07_normalize")
    api = crawling_api()
    client, model = openai_client()
    results = []
    for url in urls():
        page = fetch_markdown(api, url)
        if page["cb_status"] != "200":
            print(f"{url:44s} cb_status={page['cb_status']}: no LLM call for a failed crawl")
            continue
        out = extract_with_llm(client, model, url, page["markdown"])
        record = normalize.normalize_record(out["data"] or {})
        invented = invented_fields(record, page["markdown"], FIELDS)
        print(f"{url:44s} tokens={out['prompt_tokens']}+{out['completion_tokens']} invented={invented}")
        results.append({"url": url, "model": out["model"], "record": record, "invented": invented,
                        "prompt_tokens": out["prompt_tokens"], "completion_tokens": out["completion_tokens"]})
    print("saved", save("04_llm", results))
