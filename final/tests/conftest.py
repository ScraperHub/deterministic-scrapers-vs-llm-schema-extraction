import sys
from pathlib import Path

import pytest

FINAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FINAL))

from extractbench.cache import JsonCache  # noqa: E402
from extractbench.crawl import CrawlClient  # noqa: E402
from extractbench.fakes import FIXTURES, FakeCrawlingAPI, FakeOpenAI  # noqa: E402
from extractbench.llm import LLMExtractor  # noqa: E402

AMAZON_URL = "https://www.amazon.com/dp/B0TESTCASE"
WALMART_URL = "https://www.walmart.com/ip/3551794083"
LONGTAIL_URL = "https://shop.example.com/p/kettle-17"


@pytest.fixture
def crawl():
    FakeCrawlingAPI.calls = []
    return CrawlClient("normal", "js", JsonCache(None), api_factory=FakeCrawlingAPI)


@pytest.fixture
def llm():
    return LLMExtractor(FakeOpenAI(), "gpt-4o-mini-fixture", JsonCache(None))


@pytest.fixture
def fixtures():
    return FIXTURES
