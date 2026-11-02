"""Catalogue-sized runs: queue with async=true&store=true, then read results from Cloud Storage by rid."""
import json
import time

from crawlbase import CrawlingAPI, StorageAPI

from .schema import scraper_for


def submit(api: CrawlingAPI, url: str, callback: str | None = None) -> str | None:
    options = {"async": "true", "store": "true"}
    name = scraper_for(url)
    options.update({"scraper": name} if name else {"autoparse": "true"})
    if callback:
        options["callback"] = callback
    res = api.get(url, options)
    payload = res.get("json")
    if not isinstance(payload, dict):
        try:
            payload = json.loads(res.get("body") or b"{}")
        except ValueError:
            payload = {}
    return payload.get("rid")


def fetch_stored(storage: StorageAPI, rid: str, attempts: int = 12, wait_s: float = 10.0) -> dict | None:
    """Poll storage until the queued crawl lands. Retrieval is not billed."""
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
    """Stored scraper results arrive as an envelope or as the scraper JSON itself."""
    body = stored.get("body", stored)
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return None
    if isinstance(body, dict) and isinstance(body.get("body"), dict):
        body = body["body"]
    return body if isinstance(body, dict) else None
