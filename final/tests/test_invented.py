from conftest import AMAZON_URL
from extractbench.invented import invented_fields, is_supported, page_text
from extractbench.router import via_markdown_llm, via_scraper
from extractbench.schema import FIELDS


def test_llm_invented_price_is_caught(crawl, llm, fixtures):
    markdown = (fixtures / "product_page.md").read_text(encoding="utf-8")
    ext = via_markdown_llm(AMAZON_URL, crawl, llm)
    assert ext.accepted  # the schema alone cannot see the invention
    assert invented_fields(ext.record, markdown, FIELDS) == ["price"]


def test_scraper_values_are_checked_against_the_page_too(crawl, fixtures):
    markdown = (fixtures / "product_page.md").read_text(encoding="utf-8")
    ext = via_scraper(AMAZON_URL, crawl)
    assert invented_fields(ext.record, markdown, FIELDS) == []


def test_number_forms_and_boundaries():
    text = page_text("Price $1,299.99 and (3,773) ratings, 4.0 out of 5 stars")
    assert is_supported("price", 1299.99, text)
    assert not is_supported("price", 299.99, text)
    assert is_supported("reviews_count", 3773, text)
    assert not is_supported("reviews_count", 773, text)
    assert is_supported("rating", 4.0, text)
    assert not is_supported("rating", 4.5, text)


def test_markdown_escapes_do_not_hide_values():
    assert is_supported("title", "Pots & Pans | 10-Piece", page_text(r"# Pots &amp; Pans \| 10\-Piece"))


def test_availability_and_currency_cues():
    text = page_text("Currently unavailable. $49")
    assert is_supported("availability", "out_of_stock", text)
    assert not is_supported("availability", "in_stock", text)
    assert is_supported("currency", "USD", text)
    assert not is_supported("currency", "EUR", text)
