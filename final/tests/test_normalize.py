import pytest

from extractbench.normalize import (clean_brand, normalize_availability, normalize_record, parse_count, parse_price,
                                    parse_rating)


@pytest.mark.parametrize("raw, hint, expected", [
    ("$1,299.99", None, (1299.99, "USD")),
    ("49.00", "USD", (49.0, "USD")),
    ("€39,90", None, (39.9, "EUR")),
    ("$1,299", None, (1299.0, "USD")),
    ("£12", None, (12.0, "GBP")),
    (19.5, "usd", (19.5, "USD")),
    ("See price in cart", None, (None, None)),
    (None, None, (None, None)),
])
def test_parse_price(raw, hint, expected):
    assert parse_price(raw, hint) == expected


@pytest.mark.parametrize("raw, expected", [
    (True, "in_stock"), (False, "out_of_stock"), ("In Stock", "in_stock"), ("Only 3 left in stock", "in_stock"),
    ("Currently unavailable.", "out_of_stock"), ("Out of stock", "out_of_stock"), ("", None), (None, None),
])
def test_availability_enum(raw, expected):
    assert normalize_availability(raw) == expected


def test_ratings_counts_and_brand():
    assert parse_rating("4.0 out of 5 stars") == 4.0
    assert parse_rating("4.4") == 4.4
    assert parse_count("3,240") == 3240
    assert parse_count("2.5K") == 2500
    assert clean_brand("Visit the Meta Quest Store") == "Meta Quest"
    assert clean_brand("Brand: Lodge") == "Lodge"


def test_no_currency_without_a_price():
    record = normalize_record({"title": "x", "id": "y", "price": None, "currency": "USD"})
    assert record["currency"] is None
