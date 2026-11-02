"""Offline stand-ins for the Crawling API and the OpenAI client, built from tests/fixtures."""
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def _load(name: str):
    path = FIXTURES / name
    return json.loads(path.read_text(encoding="utf-8")) if name.endswith(".json") else path.read_text(encoding="utf-8")


def _site(url: str) -> str:
    host = urlparse(url).hostname or ""
    if "amazon." in host:
        return "amazon"
    if "walmart." in host:
        return "walmart"
    return "longtail"


def _sdk_json_response(envelope: dict) -> dict:
    return {
        "status_code": 200,
        "headers": {"original_status": str(envelope["original_status"]), "cb_status": str(envelope["cb_status"]), "url": envelope["url"]},
        "body": json.dumps(envelope).encode("utf-8"),
        "json": envelope["body"],
    }


class FakeCrawlingAPI:
    """Mimics crawlbase.CrawlingAPI.get(): scraper JSON, an autoparse miss, and Markdown bodies."""

    calls: list = []

    def __init__(self, options: dict):
        self.token = options["token"]

    def get(self, url: str, options: dict) -> dict:
        FakeCrawlingAPI.calls.append((url, dict(options)))
        site = _site(url)
        if options.get("format") == "md":
            body = _load({"amazon": "product_page.md", "walmart": "walmart_page.md", "longtail": "longtail_page.md"}[site])
            return {"status_code": 200, "headers": {"original_status": "200", "cb_status": "200", "url": url}, "body": body.encode("utf-8")}
        if options.get("scraper") or (options.get("autoparse") and site == "amazon"):
            return _sdk_json_response(_load(f"{site}_scraper.json"))
        miss = _load("autoparse_miss.json")
        return {**miss, "body": miss["body"].encode("utf-8")}


class Offline:
    """Stands in for both clients when re-computing from cache. Any call is a bug and fails loudly."""

    def __init__(self, *args, **kwargs):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._refuse))

    def get(self, *args, **kwargs):
        raise RuntimeError("cache-only: uncached crawl")

    def _refuse(self, **kwargs):
        raise RuntimeError("cache-only: uncached LLM call")


class FakeOpenAI:
    """Mimics client.chat.completions.create() with structured output and token usage."""

    def __init__(self, model: str = "gpt-4o-mini-fixture"):
        self.model = model
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        prompt = kwargs["messages"][-1]["content"]
        url = prompt.split("\n", 1)[0].removeprefix("URL: ").strip()
        data = _load("llm_invented_price.json")[_site(url)]
        message = SimpleNamespace(content=json.dumps(data))
        usage = SimpleNamespace(prompt_tokens=len(prompt) // 4, completion_tokens=60)
        return SimpleNamespace(model=self.model, choices=[SimpleNamespace(message=message)], usage=usage)
