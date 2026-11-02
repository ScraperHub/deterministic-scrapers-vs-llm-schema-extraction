"""One structured-output LLM call per page, on the Markdown the Crawling API returned."""
import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass

from .cache import JsonCache
from .schema import LLM_SCHEMA

MAX_MARKDOWN_CHARS = 60_000

SYSTEM_PROMPT = (
    "You extract one product record from a retail product page converted to Markdown. "
    "Use only values printed on the page. If a value is not on the page, return null. "
    "Do not guess, convert, or fill in values from general knowledge."
)


@dataclass
class LLMResult:
    data: dict | None
    model: str | None
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    truncated: bool
    error: str | None = None
    from_cache: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and isinstance(self.data, dict)

    def to_dict(self) -> dict:
        return asdict(self)


class LLMExtractor:
    def __init__(self, client, model: str, cache: JsonCache | None = None):
        self.client = client
        self.model = model
        self.cache = cache or JsonCache(None)
        self.api_calls = 0
        self._lock = threading.Lock()

    def extract(self, url: str, markdown: str, run: int = 1) -> LLMResult:
        digest = hashlib.sha1(markdown.encode("utf-8")).hexdigest()
        key = f"{self.model}|{run}|{url}|{digest}"
        cached = self.cache.get("llm", key)
        if cached:
            return LLMResult(**{**cached, "from_cache": True})

        truncated = len(markdown) > MAX_MARKDOWN_CHARS
        page = markdown[:MAX_MARKDOWN_CHARS]
        with self._lock:
            self.api_calls += 1
        started = time.monotonic()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"URL: {url}\n\n{page}"},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "product_v1", "strict": True, "schema": LLM_SCHEMA},
                },
            )
        except Exception as exc:
            return LLMResult(None, self.model, 0, 0, round(time.monotonic() - started, 3), truncated,
                             error=f"{type(exc).__name__}: {str(exc)[:200]}")

        latency = round(time.monotonic() - started, 3)
        usage = response.usage
        content = response.choices[0].message.content or ""
        try:
            data, error = json.loads(content), None
        except json.JSONDecodeError as exc:
            data, error = None, f"json_parse_error: {exc}"
        result = LLMResult(data, response.model, usage.prompt_tokens, usage.completion_tokens, latency, truncated, error)
        self.cache.put("llm", key, result.to_dict())
        return result
