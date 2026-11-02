import pytest

from extractbench.validate import RecordRejected, require_valid, stamp, validation_errors

GOOD = {"title": "Steel Kettle", "id": "HL-17", "brand": None, "price": 39.9, "currency": "EUR",
        "availability": "in_stock", "rating": None, "reviews_count": None}


def stamped(record):
    return stamp(record, url="https://shop.example.com/p/1", path="markdown_llm", extractor="openai:gpt-4o-mini")


def test_good_record_passes():
    assert validation_errors(stamped(GOOD)) == []


@pytest.mark.parametrize("change, field", [
    ({"title": None}, "title"),
    ({"price": -1}, "price"),
    ({"currency": "$"}, "currency"),
    ({"currency": None}, "currency"),
    ({"availability": "maybe"}, "availability"),
    ({"rating": 7}, "rating"),
    ({"reviews_count": 12.5}, "reviews_count"),
])
def test_schema_rejects_bad_values(change, field):
    errors = validation_errors(stamped({**GOOD, **change}))
    assert errors and any(field in e or "currency" in e for e in errors)


def test_missing_meta_is_rejected():
    with pytest.raises(RecordRejected):
        require_valid(dict(GOOD))


def test_extra_keys_are_rejected():
    assert validation_errors(stamped({**GOOD, "color": "red"}))
