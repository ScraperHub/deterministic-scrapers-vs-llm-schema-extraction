"""The step scripts the article quotes must behave exactly like the app in final/."""
import importlib.util
import sys
from pathlib import Path

import pytest

from conftest import AMAZON_URL, LONGTAIL_URL, WALMART_URL
from extractbench import invented as f_invented
from extractbench import normalize as f_normalize
from extractbench import schema as f_schema
from extractbench import validate as f_validate
from extractbench.router import route as final_route

STEPS = Path(__file__).resolve().parents[2] / "steps"
sys.path.insert(0, str(STEPS))


def step(name):
    spec = importlib.util.spec_from_file_location(f"t_{name}", STEPS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema_and_key_maps_match():
    s1 = step("01_schema")
    assert s1.FIELDS == f_schema.FIELDS and s1.SCHEMA_VERSION == f_schema.SCHEMA_VERSION
    raw = {"name": "A", "rawPrice": "1.00", "productInformation": [{"name": "ASIN", "value": "\u200eB0TESTCASE"}],
           "customerReview": "4.5 out of 5 stars", "customerReviewCount": 9, "inStock": False}
    assert s1.map_scraper_output(raw, AMAZON_URL) == f_schema.map_scraper_output(raw, AMAZON_URL)
    raw = {"title": "A", "itemId": "1", "price": "$1.00", "ratings": "4.5", "reviewsCount": "9"}
    assert s1.map_scraper_output(raw, WALMART_URL) == f_schema.map_scraper_output(raw, WALMART_URL)


def test_llm_schema_and_prompt_match():
    s4 = step("04_llm_extract")
    from extractbench import llm as f_llm

    assert s4.LLM_SCHEMA == f_schema.LLM_SCHEMA
    assert s4.SYSTEM_PROMPT == f_llm.SYSTEM_PROMPT
    assert s4.MAX_MARKDOWN_CHARS == f_llm.MAX_MARKDOWN_CHARS


def test_validation_schema_matches():
    assert step("06_validate").PRODUCT_SCHEMA == f_validate.PRODUCT_SCHEMA


@pytest.mark.parametrize("mapped", [
    {"title": " A ", "id": "x1", "brand": "Visit the Meta Quest Store", "price": "$1,299.99", "currency": None,
     "availability": "Currently unavailable.", "rating": "4.0 out of 5 stars", "reviews_count": "3,240"},
    {"title": "B", "id": "y", "brand": None, "price": "€39,90", "currency": None, "availability": True,
     "rating": 4, "reviews_count": "2.5K"},
    {"price": "See price in cart", "currency": "USD"},
])
def test_normalisation_matches(mapped):
    assert step("07_normalize").normalize_record(mapped) == f_normalize.normalize_record(mapped)


@pytest.mark.parametrize("fixture", ["product_page.md", "walmart_page.md", "longtail_page.md"])
def test_invented_check_matches(fixtures, fixture):
    s4 = step("04_llm_extract")
    markdown = (fixtures / fixture).read_text(encoding="utf-8")
    record = {"title": "Steel Kettle 1.7 L", "id": "B0TESTCASE", "brand": "Apple", "price": 49.0, "currency": "USD",
              "availability": "in_stock", "rating": 4.4, "reviews_count": 3240}
    assert s4.invented_fields(record, markdown, f_schema.FIELDS) == f_invented.invented_fields(record, markdown, f_schema.FIELDS)


@pytest.mark.parametrize("url", [AMAZON_URL, WALMART_URL, LONGTAIL_URL])
def test_step_08_route_matches_final_router(url, crawl, llm):
    from extractbench.fakes import FakeCrawlingAPI, FakeOpenAI

    s8 = step("08_route")
    ours = s8.route(url, FakeCrawlingAPI({"token": "t"}), FakeOpenAI(), "gpt-4o-mini-fixture")
    theirs = final_route(url, crawl, llm)
    assert ours["path"] == theirs.path
    assert ours["extractor"] == theirs.extractor
    assert ours["record"] == theirs.record
    assert ours["errors"] == theirs.errors
