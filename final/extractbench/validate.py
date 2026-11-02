"""The JSON Schema gate every record passes through, whichever path produced it."""
from jsonschema import Draft202012Validator

from .schema import PRODUCT_SCHEMA, SCHEMA_VERSION

_VALIDATOR = Draft202012Validator(PRODUCT_SCHEMA)


def stamp(record: dict, *, url: str, path: str, extractor: str) -> dict:
    return {**record, "_meta": {"url": url, "path": path, "extractor": extractor, "schema_version": SCHEMA_VERSION}}


def validation_errors(record: dict) -> list[str]:
    return [
        f"{'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
        for err in sorted(_VALIDATOR.iter_errors(record), key=lambda e: list(e.absolute_path))
    ]


class RecordRejected(Exception):
    def __init__(self, record: dict, errors: list[str]):
        super().__init__("; ".join(errors))
        self.record = record
        self.errors = errors


def require_valid(record: dict) -> dict:
    errors = validation_errors(record)
    if errors:
        raise RecordRejected(record, errors)
    return record
