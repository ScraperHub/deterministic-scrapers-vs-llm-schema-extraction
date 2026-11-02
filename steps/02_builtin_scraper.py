"""Step 2: call the Crawling API with scraper=amazon-product-details or walmart-product-details.

Run offline:  python 02_builtin_scraper.py
Run live:     python 02_builtin_scraper.py --live   (2 crawls)
"""
import time
from urllib.parse import urlparse

from _common import crawling_api, load_step, save, urls

SCRAPERS = {"www.amazon.com": "amazon-product-details", "www.walmart.com": "walmart-product-details"}


def fetch_builtin(api, url: str) -> dict:
    name = SCRAPERS[urlparse(url).hostname]
    started = time.monotonic()
    res = api.get(url, {"scraper": name})
    headers = res.get("headers") or {}
    return {
        "url": url,
        "scraper": name,
        "status_code": res.get("status_code"),
        "cb_status": headers.get("cb_status"),
        "latency_s": round(time.monotonic() - started, 2),
        "data": res.get("json"),  # the SDK parses the scraper JSON into res["json"]
    }


if __name__ == "__main__":
    schema = load_step("01_schema")
    api = crawling_api()
    results = []
    for url in urls():
        out = fetch_builtin(api, url)
        mapped = schema.map_scraper_output(out["data"], url) if isinstance(out["data"], dict) else None
        print(f"{out['scraper']:24s} cb_status={out['cb_status']} {out['latency_s']}s title={mapped and mapped['title']!r}")
        results.append({**out, "mapped": mapped})
    print("saved", save("02_scraper", results))
