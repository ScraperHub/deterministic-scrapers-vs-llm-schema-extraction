from conftest import AMAZON_URL, LONGTAIL_URL, WALMART_URL
from extractbench.fakes import FakeCrawlingAPI
from extractbench.router import route, via_autoparse, write_record
from extractbench.schema import map_amazon, map_walmart


def test_amazon_routes_to_builtin_scraper(crawl, llm):
    ext = route(AMAZON_URL, crawl, llm)
    assert ext.accepted
    assert ext.path == "scraper"
    assert ext.extractor == "crawlbase:amazon-product-details"
    assert ext.record["id"] == "B0TESTCASE"
    assert ext.record["_meta"]["schema_version"] == "product.v1"
    assert [opts for _, opts in FakeCrawlingAPI.calls] == [{"scraper": "amazon-product-details"}]


def test_walmart_keys_map_into_the_same_record(crawl, llm):
    ext = route(WALMART_URL, crawl, llm)
    assert ext.accepted and ext.path == "scraper"
    assert ext.record["title"] == "Meta Quest 3 512GB VR Headset"
    assert ext.record["id"] == "3551794083"
    assert ext.record["brand"] == "Meta Quest"
    assert ext.record["reviews_count"] == 3240
    assert ext.record["availability"] is None  # the Walmart scraper exposes no stock field


def test_long_tail_falls_through_autoparse_to_markdown_llm(crawl, llm):
    ext = route(LONGTAIL_URL, crawl, llm)
    assert ext.accepted
    assert ext.path == "markdown_llm"
    assert ext.record["currency"] == "EUR"
    assert [opts for _, opts in FakeCrawlingAPI.calls] == [{"autoparse": "true"}, {"format": "md"}]


def test_autoparse_miss_is_reported_not_filled(crawl):
    ext = via_autoparse(WALMART_URL, crawl)
    assert ext.record is None
    assert ext.errors == ["no_scraper_match"]


def test_key_maps_disagree_on_names_but_agree_on_meaning():
    amazon = map_amazon({"name": "A", "rawPrice": "1.00", "customerReview": "4.5 out of 5 stars", "customerReviewCount": 9}, AMAZON_URL)
    walmart = map_walmart({"title": "A", "itemId": "1", "price": "$1.00", "ratings": "4.5", "reviewsCount": "9"}, WALMART_URL)
    assert set(amazon) == set(walmart)
    assert amazon["id"] == "B0TESTCASE"


def test_only_accepted_records_are_written(crawl, llm, tmp_path):
    out = tmp_path / "records.jsonl"
    assert write_record(route(AMAZON_URL, crawl, llm), out)
    assert not write_record(via_autoparse(WALMART_URL, crawl), out)
    assert len(out.read_text(encoding="utf-8").splitlines()) == 1
