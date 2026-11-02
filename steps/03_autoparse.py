"""Step 3: the same URLs with autoparse=true. A miss comes back as a page body, not scraper JSON."""
import time

from _common import crawling_api, load_step, save, urls


def fetch_autoparse(api, url: str) -> dict:
    started = time.monotonic()
    res = api.get(url, {"autoparse": "true"})
    data = res.get("json")
    return {
        "url": url,
        "cb_status": (res.get("headers") or {}).get("cb_status"),
        "latency_s": round(time.monotonic() - started, 2),
        "matched": isinstance(data, dict),
        "data": data if isinstance(data, dict) else None,
    }


if __name__ == "__main__":
    schema = load_step("01_schema")
    api = crawling_api()
    results = []
    for url in urls():
        out = fetch_autoparse(api, url)
        mapped = schema.map_scraper_output(out["data"], url) if out["matched"] else None
        print(f"{url:44s} matched={out['matched']} cb_status={out['cb_status']}")
        results.append({**out, "mapped": mapped})
    print("saved", save("03_autoparse", results))
