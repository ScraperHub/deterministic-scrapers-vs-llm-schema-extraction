"""Cases taken from the live run's hand-check."""
from extractbench.cache import JsonCache
from extractbench.crawl import CHALLENGE_MARKERS, CrawlClient
from extractbench.invented import invented_fields, is_supported, page_text
from extractbench.llm import LLMExtractor
from extractbench.normalize import normalize_record
from extractbench.router import via_markdown_llm
from extractbench.schema import FIELDS
from extractbench.validate import stamp, validation_errors

ROBOT = "## Robot or human?\n\nActivate and hold the button to confirm that you're human. Thank You!"


def test_string_null_title_is_rejected_by_the_schema():
    record = normalize_record({"title": "null", "id": "3551794083", "brand": "null", "availability": "in_stock"})
    assert record["title"] is None and record["brand"] is None
    errors = validation_errors(stamp(record, url="https://www.walmart.com/ip/3551794083", path="markdown_llm", extractor="x"))
    assert any(e.startswith("title") for e in errors)


def test_abbreviated_counts_match_at_shown_precision():
    text = page_text("4.3 (27.4K) | [14K ratings](#)")
    assert is_supported("reviews_count", 27406, text)
    assert is_supported("reviews_count", 27400, text)
    assert is_supported("reviews_count", 14084, text)
    assert not is_supported("reviews_count", 27600, text)


def test_brand_spacing_does_not_count_as_invented():
    assert is_supported("brand", "HeroCosmetics", page_text("Mighty Patch Hero Cosmetics Original"))


def test_id_from_the_url_is_input_not_invention():
    url = "https://www.walmart.com/ip/3551794083"
    assert invented_fields({"id": "3551794083", "availability": "in_stock"}, ROBOT, FIELDS, url) == ["availability"]


def test_gate_keeps_a_challenge_page_away_from_the_model(tmp_path):
    class Api:
        def __init__(self, options):
            pass

        def get(self, url, options):
            return {"status_code": 200, "headers": {"cb_status": "200", "original_status": "200"}, "body": ROBOT.encode()}

    class NoModel:
        def __getattr__(self, name):
            raise AssertionError("the model must not be called")

    crawl = CrawlClient("n", "", JsonCache(None), api_factory=Api)
    ext = via_markdown_llm("https://www.walmart.com/ip/3551794083", crawl, LLMExtractor(NoModel(), "m", JsonCache(None)))
    assert ext.record is None and ext.errors == ["not_a_product_page"]


def test_step_08_uses_the_same_challenge_markers():
    import importlib.util
    from pathlib import Path
    import sys

    steps = Path(__file__).resolve().parents[2] / "steps"
    sys.path.insert(0, str(steps))
    spec = importlib.util.spec_from_file_location("s08", steps / "08_route.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.CHALLENGE_MARKERS == CHALLENGE_MARKERS
    assert module.not_a_product_page(ROBOT) and module.not_a_product_page("")
