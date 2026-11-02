"""Step 6: a JSON Schema gate on every record. Reject on failure, stamp the parser or model and schema version."""
import json

from jsonschema import Draft202012Validator

from _common import load, save

SCHEMA_VERSION = "product.v1"
FIELDS = ["title", "id", "brand", "price", "currency", "availability", "rating", "reviews_count"]

PRODUCT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": SCHEMA_VERSION,
    "type": "object",
    "required": FIELDS + ["_meta"],
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 3},
        "id": {"type": "string", "minLength": 3},
        "brand": {"type": ["string", "null"]},
        "price": {"type": ["number", "null"], "minimum": 0},
        "currency": {"type": ["string", "null"], "pattern": "^[A-Z]{3}$"},
        "availability": {"enum": ["in_stock", "out_of_stock", None]},
        "rating": {"type": ["number", "null"], "minimum": 0, "maximum": 5},
        "reviews_count": {"type": ["integer", "null"], "minimum": 0},
        "_meta": {
            "type": "object",
            "required": ["url", "path", "extractor", "schema_version"],
            "properties": {
                "url": {"type": "string"},
                "path": {"enum": ["scraper", "autoparse", "markdown_llm"]},
                "extractor": {"type": "string"},
                "schema_version": {"const": SCHEMA_VERSION},
            },
        },
    },
    "allOf": [
        {"if": {"properties": {"price": {"type": "number"}}, "required": ["price"]},
         "then": {"properties": {"currency": {"type": "string"}}}},
    ],
}
_VALIDATOR = Draft202012Validator(PRODUCT_SCHEMA)


def stamp(record: dict, *, url: str, path: str, extractor: str) -> dict:
    return {**record, "_meta": {"url": url, "path": path, "extractor": extractor, "schema_version": SCHEMA_VERSION}}


def validation_errors(record: dict) -> list[str]:
    return [
        f"{'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
        for err in sorted(_VALIDATOR.iter_errors(record), key=lambda e: list(e.absolute_path))
    ]


if __name__ == "__main__":
    good = load("07_normalized") or {}
    for site, record in good.items():
        stamped = stamp(record, url=f"https://{site}.example/p", path="scraper", extractor=f"crawlbase:{site}-product-details")
        print(f"{site:8s} errors={validation_errors(stamped)}")
    bad = stamp({f: None for f in FIELDS} | {"title": "Kettle", "id": "K1", "price": 12.0, "currency": "$"},
                url="https://shop.example.com/p/1", path="markdown_llm", extractor="openai:gpt-4o-mini")
    errors = validation_errors(bad)
    print("rejected:", json.dumps(errors))
    print("saved", save("06_rejections", {"record": bad, "errors": errors}))
