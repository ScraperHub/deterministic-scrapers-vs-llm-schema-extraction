"""Three paths, the same URLs, three runs. Every value is checked against that run's stored Markdown."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse

from .crawl import CrawlClient
from .invented import invented_fields, page_text
from .llm import MAX_MARKDOWN_CHARS, LLMExtractor
from .metrics import summarize
from .router import Extraction, via_autoparse, via_markdown_llm, via_scraper
from .schema import FIELDS, SCHEMA_VERSION

PATHS = ("scraper", "autoparse", "markdown_llm")


def site_of(url: str) -> str:
    host = urlparse(url).hostname or ""
    return "amazon" if "amazon." in host else "walmart" if "walmart." in host else "other"


def product_id_of(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def is_product_page(markdown: str | None, url: str) -> bool:
    """Path-neutral check used to swap dead URLs: the page text names the product id."""
    return bool(markdown) and len(markdown) > 1500 and product_id_of(url).lower() in page_text(markdown)


def select_urls(candidates: dict, crawl: CrawlClient, per_site: int, workers: int = 6) -> tuple[list[str], list[dict]]:
    """Walk each site's list in order and swap in reserves for pages that are not product pages."""
    selected, swaps = [], []
    for site in ("amazon", "walmart"):
        queue = candidates[site][:per_site] + candidates.get("reserves", {}).get(site, [])
        chosen = []
        while queue and len(chosen) < per_site:
            batch, queue = queue[:per_site - len(chosen)], queue[per_site - len(chosen):]
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(lambda u: crawl.fetch(u, "markdown", 1), batch))
            for url, res in zip(batch, results):
                if res.ok and is_product_page(res.markdown, url):
                    chosen.append(url)
                else:
                    reason = (res.error or f"cb_status {res.cb_status}") if not res.ok else "not a product page"
                    swaps.append({"url": url, "reason": reason, "original_status": res.original_status,
                                  "token": res.token, "markdown_head": (res.markdown or "")[:60]})
        selected += chosen
    return selected, swaps


UNCHECKABLE = {"walmart": {"rating"}}  # Walmart Markdown does not print the item's own rating


def checked_fields(site: str) -> list[str]:
    return [f for f in FIELDS if f not in UNCHECKABLE.get(site, set())]


def _invented(ext: Extraction, record: dict | None, markdown: str | None, product_page: bool) -> list[str] | None:
    """The LLM is checked against the exact text it read. The parsers are checked against
    the same run's Markdown crawl, and only when that crawl was a product page."""
    if record is None or markdown is None:
        return None
    if ext.path == "markdown_llm":
        markdown = markdown[:MAX_MARKDOWN_CHARS]
    elif not product_page:
        return None
    return invented_fields(record, markdown, checked_fields(site_of(ext.url)), ext.url)


def _observation(ext: Extraction, run: int, markdown: str | None, md_hash: str | None, product_page: bool) -> dict:
    crawl = ext.crawl or {}
    llm = ext.llm or {}
    record = {k: ext.record.get(k) for k in FIELDS} if ext.record else None
    latency = (crawl.get("latency_s") or 0) + (llm.get("latency_s") or 0)
    return {
        "url": ext.url,
        "site": site_of(ext.url),
        "path": ext.path,
        "run": run,
        "extractor": ext.extractor,
        "record": record,
        "accepted": ext.accepted,
        "errors": ext.errors,
        "md_product_page": product_page,
        "invented": _invented(ext, record, markdown, product_page),
        "crawl_ok": crawl.get("cb_status") == "200",
        "cb_status": crawl.get("cb_status"),
        "token": crawl.get("token"),
        "latency_s": round(latency, 3) if crawl.get("latency_s") is not None else None,
        "crawl_requests": 1,
        "llm_calls": 1 if ext.path == "markdown_llm" and llm else 0,
        "prompt_tokens": llm.get("prompt_tokens", 0),
        "completion_tokens": llm.get("completion_tokens", 0),
        "llm_truncated": llm.get("truncated"),
        "input_hash": md_hash if ext.path == "markdown_llm" else None,
    }


def observe(url: str, run: int, crawl: CrawlClient, llm: LLMExtractor | None) -> list[dict]:
    md = crawl.fetch(url, "markdown", run)
    markdown = md.markdown if md.ok else None
    md_hash = hashlib.sha1(markdown.encode("utf-8")).hexdigest() if markdown is not None else None
    product_page = is_product_page(markdown, url)
    out = [
        _observation(via_scraper(url, crawl, run), run, markdown, None, product_page),
        _observation(via_autoparse(url, crawl, run), run, markdown, None, product_page),
    ]
    if llm is not None:
        # Ungated on purpose: this measures what Markdown + LLM does with whatever the crawl returned.
        llm_ext = via_markdown_llm(url, crawl, llm, run, gate=False)
        out.append(_observation(llm_ext, run, markdown, md_hash, product_page))
    return out


def run_matrix(urls: list[str], runs: int, crawl: CrawlClient, llm: LLMExtractor | None, workers: int = 6,
               log=print) -> list[dict]:
    observations = []
    for run in range(1, runs + 1):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for i, obs in enumerate(pool.map(lambda u: observe(u, run, crawl, llm), urls), 1):
                observations += obs
                if i % 10 == 0 or i == len(urls):
                    log(f"run {run}: {i}/{len(urls)} urls")
    return observations


def build_results(observations: list[dict], runs: int, model: str | None, meta: dict) -> dict:
    paths = {}
    for path in PATHS:
        subset = [o for o in observations if o["path"] == path]
        if not subset:
            continue
        paths[path] = {"all": summarize(subset, runs)}
        for site in ("amazon", "walmart"):
            site_obs = [o for o in subset if o["site"] == site]
            if site_obs:
                paths[path][site] = summarize(site_obs, runs)
    tokens = {}
    for o in observations:
        if o.get("token"):
            tokens[o["token"]] = tokens.get(o["token"], 0) + 1
    per_record = [
        {k: o[k] for k in ("url", "path", "run", "accepted", "errors", "invented", "md_product_page", "cb_status", "token",
                           "latency_s", "prompt_tokens", "completion_tokens", "input_hash")}
        | {"filled": [k for k in FIELDS if o["record"] and o["record"].get(k) is not None]}
        for o in observations
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "schema_version": SCHEMA_VERSION,
        "llm_model_requested": model,
        "llm_models_returned": sorted({o["extractor"] for o in observations if o["path"] == "markdown_llm"}),
        "runs": runs,
        **meta,
        "crawl_token_counts": tokens,
        "paths": paths,
        "per_record": per_record,
    }


def write_results(results: dict, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
