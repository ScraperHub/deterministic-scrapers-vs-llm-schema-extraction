"""Route a URL: built-in scraper, then autoparse, then Markdown plus one LLM call. Reject what fails the schema."""
import json
from dataclasses import dataclass, field
from pathlib import Path

from .crawl import CrawlClient, unusable
from .llm import LLMExtractor
from .normalize import normalize_record
from .schema import map_scraper_output, scraper_for
from .validate import stamp, validation_errors


@dataclass
class Extraction:
    url: str
    path: str
    extractor: str
    record: dict | None
    errors: list[str] = field(default_factory=list)
    crawl: dict | None = None
    llm: dict | None = None

    @property
    def accepted(self) -> bool:
        return self.record is not None and not self.errors


def _finish(url, path, extractor, mapped, crawl, llm=None) -> Extraction:
    record = stamp(normalize_record(mapped), url=url, path=path, extractor=extractor)
    return Extraction(url, path, extractor, record, validation_errors(record), crawl, llm)


def via_scraper(url: str, crawl: CrawlClient, run: int = 1) -> Extraction:
    name = scraper_for(url)
    res = crawl.fetch(url, "scraper", run)
    if not res.ok:
        return Extraction(url, "scraper", f"crawlbase:{name}", None, [res.error or f"cb_status {res.cb_status}"], res.to_dict())
    return _finish(url, "scraper", f"crawlbase:{name}", map_scraper_output(res.data, url), res.to_dict())


def via_autoparse(url: str, crawl: CrawlClient, run: int = 1) -> Extraction:
    res = crawl.fetch(url, "autoparse", run)
    if not res.ok:
        return Extraction(url, "autoparse", "crawlbase:autoparse", None, [res.error or f"cb_status {res.cb_status}"], res.to_dict())
    return _finish(url, "autoparse", "crawlbase:autoparse", map_scraper_output(res.data, url), res.to_dict())


def via_markdown_llm(url: str, crawl: CrawlClient, llm: LLMExtractor, run: int = 1, gate: bool = True) -> Extraction:
    res = crawl.fetch(url, "markdown", run)
    extractor = f"openai:{llm.model}"
    if not res.ok:
        return Extraction(url, "markdown_llm", extractor, None, [res.error or f"cb_status {res.cb_status}"], res.to_dict())
    if gate and unusable(res):
        # A 200 that carries a challenge or an empty body never reaches the model.
        return Extraction(url, "markdown_llm", extractor, None, ["not_a_product_page"], res.to_dict())
    out = llm.extract(url, res.markdown, run)
    if not out.ok:
        return Extraction(url, "markdown_llm", extractor, None, [out.error], res.to_dict(), out.to_dict())
    return _finish(url, "markdown_llm", f"openai:{out.model or llm.model}", out.data, res.to_dict(), out.to_dict())


def route(url: str, crawl: CrawlClient, llm: LLMExtractor, run: int = 1) -> Extraction:
    """First accepted record wins. A rejected record falls through to the next path."""
    attempts = []
    if scraper_for(url):
        attempts.append(lambda: via_scraper(url, crawl, run))
    attempts.append(lambda: via_autoparse(url, crawl, run))
    attempts.append(lambda: via_markdown_llm(url, crawl, llm, run))
    result = None
    for attempt in attempts:
        result = attempt()
        if result.accepted:
            return result
    return result


def write_record(extraction: Extraction, out_path: Path) -> bool:
    if not extraction.accepted:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(extraction.record, ensure_ascii=False) + "\n")
    return True
