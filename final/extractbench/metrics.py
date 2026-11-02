"""Fill rate, three-run consistency, invented-value rate, latency, and request/token counts."""
from collections import defaultdict
from statistics import median

from .schema import FIELDS


def _core(record: dict | None) -> dict | None:
    return None if record is None else {k: record.get(k) for k in FIELDS}


def fill_rate(observations: list[dict]) -> dict:
    attempts = len(observations)
    per_key = {}
    for key in FIELDS:
        filled = sum(1 for o in observations if o.get("record") and o["record"].get(key) is not None)
        per_key[key] = round(filled / attempts, 4) if attempts else None
    values = [v for v in per_key.values() if v is not None]
    return {"per_key": per_key, "mean": round(sum(values) / len(values), 4) if values else None}


def consistency(observations: list[dict], runs: int) -> dict:
    by_url = defaultdict(list)
    for o in observations:
        by_url[o["url"]].append(o)
    consistent = 0
    same_input = same_input_consistent = 0
    complete = 0
    for obs in by_url.values():
        records = [_core(o.get("record")) for o in sorted(obs, key=lambda o: o["run"])]
        if len(records) < runs or any(r is None for r in records):
            continue
        complete += 1
        identical = all(r == records[0] for r in records)
        consistent += identical
        hashes = {o.get("input_hash") for o in obs}
        if None not in hashes and len(hashes) == 1:
            same_input += 1
            same_input_consistent += identical
    urls = len(by_url)
    return {
        "urls": urls,
        "urls_with_all_runs": complete,
        "identical_across_runs": consistent,
        "rate": round(consistent / urls, 4) if urls else None,
        "identical_input_urls": same_input,
        "identical_input_consistent": same_input_consistent,
    }


def drift_by_key(observations: list[dict]) -> dict:
    """How many URLs changed each key at least once across runs (URLs with a record in every run)."""
    by_url = defaultdict(list)
    for o in observations:
        by_url[o["url"]].append(o)
    counts = {k: 0 for k in FIELDS}
    for obs in by_url.values():
        records = [_core(o.get("record")) for o in obs]
        if any(r is None for r in records):
            continue
        for k in FIELDS:
            counts[k] += len({repr(r[k]) for r in records}) > 1
    return counts


def clean_page_consistency(observations: list[dict], runs: int) -> dict:
    """Consistency over URLs whose Markdown was a product page in every run."""
    by_url = defaultdict(list)
    for o in observations:
        by_url[o["url"]].append(o)
    keep = [o for obs in by_url.values() if len(obs) >= runs and all(x.get("md_product_page") for x in obs) for o in obs]
    return consistency(keep, runs)


def non_product_pages(observations: list[dict]) -> dict:
    hit = [o for o in observations if o.get("md_product_page") is False]
    return {
        "attempts": len(hit),
        "records_accepted": sum(1 for o in hit if o.get("accepted")),
        "llm_tokens": sum(o.get("prompt_tokens", 0) + o.get("completion_tokens", 0) for o in hit),
    }


def invented(observations: list[dict]) -> dict:
    checked = [o for o in observations if o.get("record") and o.get("invented") is not None]
    unchecked = sum(1 for o in observations if o.get("record") and o.get("invented") is None)
    values = sum(sum(1 for k in FIELDS if o["record"].get(k) is not None) for o in checked)
    flagged = [(o, f) for o in checked for f in o["invented"]]
    per_key = {k: sum(1 for _, f in flagged if f == k) for k in FIELDS}
    pages = len({(o["url"], o["run"]) for o, _ in flagged})
    return {
        "records_checked": len(checked),
        "records_unchecked": unchecked,
        "non_null_values": values,
        "invented_values": len(flagged),
        "rate": round(len(flagged) / values, 4) if values else None,
        "records_with_invented_value": pages,
        "per_key": per_key,
    }


def latency(observations: list[dict]) -> dict:
    values = sorted(o["latency_s"] for o in observations if o.get("latency_s") is not None)
    if not values:
        return {"median_s": None, "p90_s": None}
    return {"median_s": round(median(values), 2), "p90_s": round(values[min(len(values) - 1, int(0.9 * len(values)))], 2)}


def cost_shape(observations: list[dict]) -> dict:
    return {
        "crawl_requests": sum(o.get("crawl_requests", 0) for o in observations),
        "llm_calls": sum(o.get("llm_calls", 0) for o in observations),
        "prompt_tokens": sum(o.get("prompt_tokens", 0) for o in observations),
        "completion_tokens": sum(o.get("completion_tokens", 0) for o in observations),
    }


def summarize(observations: list[dict], runs: int) -> dict:
    attempts = len(observations)
    crawl_ok = sum(1 for o in observations if o.get("crawl_ok"))
    produced = sum(1 for o in observations if o.get("record"))
    accepted = sum(1 for o in observations if o.get("accepted"))
    errors = defaultdict(int)
    for o in observations:
        for e in o.get("errors", []):
            errors[e.split(":")[0]] += 1
    cost = cost_shape(observations)
    return {
        "attempts": attempts,
        "crawl_ok": crawl_ok,
        "records_produced": produced,
        "schema_accepted": accepted,
        "schema_accept_rate": round(accepted / attempts, 4) if attempts else None,
        "error_counts": dict(errors),
        "fill_rate": fill_rate(observations),
        "consistency": consistency(observations, runs),
        "consistency_clean_pages": clean_page_consistency(observations, runs),
        "drift_by_key": drift_by_key(observations),
        "markdown_not_product_page": non_product_pages(observations),
        "invented": invented(observations),
        "latency": latency(observations),
        "cost_shape": {
            **cost,
            "tokens_per_page": round((cost["prompt_tokens"] + cost["completion_tokens"]) / attempts, 1) if attempts else None,
        },
    }
