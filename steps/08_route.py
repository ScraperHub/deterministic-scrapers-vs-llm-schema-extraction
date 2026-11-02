"""Step 8: the hybrid. Built-in scraper if the host has one, else autoparse, else Markdown plus one LLM call.

Normalise, then reject the record that fails the schema. A rejected record falls through to the
next path. Only accepted records are written. final/extractbench/router.py is the same rule.
"""
import json
from urllib.parse import urlparse

from _common import CACHE, crawling_api, load_step, openai_client

SCRAPERS = {"www.amazon.com": "amazon-product-details", "amazon.com": "amazon-product-details",
            "www.walmart.com": "walmart-product-details", "walmart.com": "walmart-product-details"}

schema = load_step("01_schema")
llm_step = load_step("04_llm_extract")
validate = load_step("06_validate")
normalize = load_step("07_normalize")


CHALLENGE_MARKERS = ("robot or human", "health information consent", "enter the characters you see below")


def not_a_product_page(markdown: str | None) -> bool:
    text = (markdown or "").lower()
    return len(text) < 40 or any(m in text for m in CHALLENGE_MARKERS)


def _accept(url: str, path: str, extractor: str, mapped: dict) -> dict:
    record = validate.stamp(normalize.normalize_record(mapped), url=url, path=path, extractor=extractor)
    return {"path": path, "extractor": extractor, "record": record, "errors": validate.validation_errors(record)}


def route(url: str, api, client, model: str) -> dict:
    result = None
    name = SCRAPERS.get(urlparse(url).hostname or "")
    if name:
        res = api.get(url, {"scraper": name})
        if (res.get("headers") or {}).get("cb_status") == "200" and isinstance(res.get("json"), dict):
            result = _accept(url, "scraper", f"crawlbase:{name}", schema.map_scraper_output(res["json"], url))
            if not result["errors"]:
                return result

    res = api.get(url, {"autoparse": "true"})
    if (res.get("headers") or {}).get("cb_status") == "200" and isinstance(res.get("json"), dict):
        result = _accept(url, "autoparse", "crawlbase:autoparse", schema.map_scraper_output(res["json"], url))
        if not result["errors"]:
            return result

    page = llm_step.fetch_markdown(api, url)
    if page["cb_status"] != "200":
        return {"path": "markdown_llm", "extractor": f"openai:{model}", "record": None,
                "errors": [f"cb_status {page['cb_status']}"]}
    if not_a_product_page(page["markdown"]):
        # A 200 that carries a challenge or an empty body never reaches the model.
        return {"path": "markdown_llm", "extractor": f"openai:{model}", "record": None, "errors": ["not_a_product_page"]}
    out = llm_step.extract_with_llm(client, model, url, page["markdown"])
    if out["error"]:
        return {"path": "markdown_llm", "extractor": f"openai:{model}", "record": None, "errors": [out["error"]]}
    return _accept(url, "markdown_llm", f"openai:{out['model']}", out["data"])


def write(result: dict, path) -> bool:
    if result["record"] is None or result["errors"]:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(result["record"], ensure_ascii=False) + "\n")
    return True


if __name__ == "__main__":
    import sys

    api = crawling_api()
    client, model = openai_client()
    targets = [a for a in sys.argv[1:] if a.startswith("http")] or [
        "https://www.amazon.com/dp/B0TESTCASE", "https://www.walmart.com/ip/3551794083", "https://shop.example.com/p/kettle-17"]
    out_path = CACHE / "08_records.jsonl"
    out_path.unlink(missing_ok=True)
    for url in targets:
        result = route(url, api, client, model)
        written = write(result, out_path)
        print(f"{url:44s} -> {result['path']:13s} {result['extractor']:34s} written={written} errors={result['errors']}")
    print("records in", out_path)
