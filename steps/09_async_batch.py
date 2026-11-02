"""Step 9: a catalogue-sized run. Queue with async=true&store=true, keep the rid, read the result from storage later.

Without a callback the result lands in Cloud Storage, so no public webhook is needed.
Run live:  python 09_async_batch.py --live   (2 queued crawls, storage reads are free)
"""
import json
import time

from _common import is_live, load_step, save, urls

SCRAPERS = {"www.amazon.com": "amazon-product-details", "www.walmart.com": "walmart-product-details"}

CALLBACK_EXAMPLE = """\
# With a webhook instead of polling (not executed here):
res = api.get(url, {"async": "true", "store": "true", "scraper": "amazon-product-details",
                    "callback": "https://your-app.example/crawlbase-webhook"})
rid = res["json"]["rid"]   # Crawlbase POSTs the result to the callback; storage keeps a copy by rid
"""


def submit(api, url: str) -> str | None:
    from urllib.parse import urlparse

    options = {"async": "true", "store": "true"}
    name = SCRAPERS.get(urlparse(url).hostname or "")
    options.update({"scraper": name} if name else {"autoparse": "true"})
    res = api.get(url, options)
    payload = res.get("json")
    if not isinstance(payload, dict):
        try:
            payload = json.loads(res.get("body") or b"{}")
        except ValueError:
            payload = {}
    return payload.get("rid")  # the SDK puts the async rid in res["json"], not res["rid"]


def fetch_stored(storage, rid: str, attempts: int = 12, wait_s: float = 10.0) -> dict | None:
    for _ in range(attempts):
        try:
            res = storage.get(rid, {"format": "json"})
        except KeyError:  # crawlbase 1.1.0 raises this while the rid is not stored yet
            res = {}
        if res.get("status_code") == 200:
            stored = res.get("json_body")
            if isinstance(stored, dict) and stored:
                return stored
            body = res.get("body") or b""
            if body:
                return {"body": body.decode("utf-8", "replace") if isinstance(body, bytes) else body}
        time.sleep(wait_s)
    return None


def scraper_payload(stored: dict) -> dict | None:
    body = stored.get("body", stored)
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return None
    if isinstance(body, dict) and isinstance(body.get("body"), dict):
        body = body["body"]
    return body if isinstance(body, dict) else None


if __name__ == "__main__":
    print(CALLBACK_EXAMPLE)
    if not is_live():
        print("offline: pass --live to queue", len(urls()), "URLs with async=true&store=true and read them back by rid")
        raise SystemExit(0)

    from crawlbase import CrawlingAPI, StorageAPI

    from _common import env

    schema, normalize = load_step("01_schema"), load_step("07_normalize")
    token = env()["CRAWLBASE_TOKEN"]
    api, storage = CrawlingAPI({"token": token, "timeout": 120}), StorageAPI({"token": token, "timeout": 120})
    rids = {url: submit(api, url) for url in urls()}
    print("queued:", json.dumps(rids))
    results = {}
    for url, rid in rids.items():
        stored = fetch_stored(storage, rid) if rid else None
        payload = scraper_payload(stored) if stored else None
        record = normalize.normalize_record(schema.map_scraper_output(payload, url)) if payload else None
        results[url] = {"rid": rid, "stored": stored is not None, "record": record}
        print(f"{url:44s} rid={rid} stored={stored is not None} title={record and record['title']!r}")
    print("saved", save("09_async", results))
