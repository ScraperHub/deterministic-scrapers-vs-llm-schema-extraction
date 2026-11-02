"""Crawling API calls for the three paths, with latency, cb_status, token type and a disk cache."""
import threading
import time
from dataclasses import asdict, dataclass

from crawlbase import CrawlingAPI

from .cache import JsonCache
from .schema import scraper_for

TIMEOUT_S = 120
RETRY_ON_JS = {"207", "503"}
# A 200 from the API can still carry an interstitial instead of the product page.
CHALLENGE_MARKERS = ("robot or human", "health information consent", "enter the characters you see below")
MIN_MARKDOWN_CHARS = 40


def unusable(result: "CrawlResult") -> bool:
    """Same rule for every path: no product content in an otherwise successful response."""
    if result.cb_status != "200" or result.error:
        return False
    if result.path == "markdown":
        text = (result.markdown or "").lower()
        return len(text) < MIN_MARKDOWN_CHARS or any(m in text for m in CHALLENGE_MARKERS)
    body = result.data.get("body") if isinstance((result.data or {}).get("body"), dict) else result.data
    return not (isinstance(body, dict) and (body.get("name") or body.get("title")))


@dataclass
class CrawlResult:
    url: str
    path: str
    run: int
    status_code: int | None
    cb_status: str | None
    original_status: str | None
    token: str
    latency_s: float
    data: dict | None = None
    markdown: str | None = None
    error: str | None = None
    from_cache: bool = False
    js_retried: bool = False

    @property
    def ok(self) -> bool:
        return self.cb_status == "200" and self.error is None

    def to_dict(self) -> dict:
        return asdict(self)


def path_options(path: str, url: str) -> dict:
    if path == "scraper":
        name = scraper_for(url)
        if not name:
            raise ValueError(f"no built-in scraper for {url}")
        return {"scraper": name}
    if path == "autoparse":
        return {"autoparse": "true"}
    if path == "markdown":
        return {"format": "md"}
    raise ValueError(path)


class CrawlClient:
    def __init__(self, normal_token: str, js_token: str = "", cache: JsonCache | None = None, api_factory=CrawlingAPI):
        self.apis = {"normal": api_factory({"token": normal_token, "timeout": TIMEOUT_S})}
        if js_token:
            self.apis["js"] = api_factory({"token": js_token, "timeout": TIMEOUT_S})
        self.cache = cache or JsonCache(None)
        self.api_calls = 0
        self._lock = threading.Lock()
        self._memo: dict[str, CrawlResult] = {}

    def fetch(self, url: str, path: str, run: int = 1) -> CrawlResult:
        key = f"{path}|{run}|{url}"
        if key in self._memo:
            return self._memo[key]
        cached = self.cache.get("crawl", key)
        first = CrawlResult(**{**cached, "from_cache": True}) if cached else None
        if first is None:
            first = self._call(url, path, run, "normal")
        result = first
        if self._should_retry(first):
            result = self._call(url, path, run, "js")
            result.latency_s = round(result.latency_s + first.latency_s, 3)
            if result.cb_status != "200":
                result = first
            result.js_retried = True
        # Failures are cached too, so a re-run reproduces the measured run instead of retrying it.
        if not (cached and result is first and not result.js_retried):
            self.cache.put("crawl", key, {**result.to_dict(), "from_cache": False})
        self._memo[key] = result
        return result

    def _should_retry(self, first: CrawlResult) -> bool:
        if first.token != "normal" or first.js_retried or "js" not in self.apis:
            return False
        if first.original_status in ("404", "410"):
            return False
        return first.cb_status in RETRY_ON_JS or unusable(first)

    def _call(self, url: str, path: str, run: int, token: str) -> CrawlResult:
        with self._lock:
            self.api_calls += 1
        started = time.monotonic()
        try:
            res = self.apis[token].get(url, dict(path_options(path, url)))
        except Exception as exc:  # network errors, timeouts
            return CrawlResult(url, path, run, None, None, None, token, round(time.monotonic() - started, 3),
                               error=f"{type(exc).__name__}: {exc}")
        latency = round(time.monotonic() - started, 3)
        headers = res.get("headers") or {}
        body = res.get("body") or b""
        if isinstance(body, bytes):
            body = body.decode("utf-8", "replace")
        result = CrawlResult(
            url=url, path=path, run=run,
            status_code=res.get("status_code"),
            cb_status=headers.get("cb_status") or (str(res.get("status_code")) if res.get("status_code") != 200 else None),
            original_status=headers.get("original_status"),
            token=token, latency_s=latency,
        )
        if result.status_code != 200:
            result.error = f"http {result.status_code}"
            return result
        if path == "markdown":
            result.markdown = body
        elif isinstance(res.get("json"), dict):
            result.data = res["json"]
        else:
            result.error = "no_scraper_match"
        return result
