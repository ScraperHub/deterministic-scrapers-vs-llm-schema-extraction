from conftest import AMAZON_URL, WALMART_URL
from extractbench.benchmark import build_results, run_matrix
from extractbench.metrics import consistency, fill_rate, invented

REC = {"title": "A", "id": "1", "brand": None, "price": 1.0, "currency": "USD", "availability": None,
       "rating": 4.0, "reviews_count": 10}


def obs(url, run, record, inv=(), input_hash=None):
    return {"url": url, "run": run, "record": record, "invented": list(inv), "input_hash": input_hash}


def test_fill_rate_counts_failed_attempts_as_unfilled():
    result = fill_rate([obs("u", 1, REC), obs("u", 2, None)])
    assert result["per_key"]["title"] == 0.5
    assert result["per_key"]["brand"] == 0.0


def test_consistency_needs_identical_normalised_records_in_all_runs():
    drift = {**REC, "price": 1.5}
    data = [obs("a", r, REC) for r in (1, 2, 3)] + [obs("b", 1, REC), obs("b", 2, drift), obs("b", 3, REC)]
    data += [obs("c", 1, REC), obs("c", 2, REC)]  # missing third run
    result = consistency(data, runs=3)
    assert result["urls"] == 3
    assert result["identical_across_runs"] == 1
    assert result["rate"] == round(1 / 3, 4)


def test_consistency_separates_model_drift_from_page_change():
    drift = {**REC, "rating": 4.5}
    data = [obs("a", 1, REC, input_hash="h"), obs("a", 2, drift, input_hash="h"), obs("a", 3, REC, input_hash="h")]
    result = consistency(data, runs=3)
    assert result["identical_input_urls"] == 1
    assert result["identical_input_consistent"] == 0


def test_invented_rate_is_per_non_null_value():
    result = invented([obs("a", 1, REC, inv=["price"]), obs("a", 2, REC)])
    assert result["non_null_values"] == 12
    assert result["invented_values"] == 1
    assert result["per_key"]["price"] == 1


def test_full_matrix_offline(crawl, llm):
    observations = run_matrix([AMAZON_URL, WALMART_URL], 3, crawl, llm, workers=2, log=lambda *_: None)
    results = build_results(observations, 3, "gpt-4o-mini-fixture", {"mode": "test"})
    paths = results["paths"]
    assert paths["scraper"]["all"]["consistency"]["rate"] == 1.0
    assert paths["autoparse"]["walmart"]["error_counts"] == {"no_scraper_match": 3}
    assert paths["markdown_llm"]["amazon"]["invented"]["per_key"]["price"] == 3
    assert paths["markdown_llm"]["all"]["cost_shape"]["llm_calls"] == 6
    assert paths["scraper"]["all"]["cost_shape"]["prompt_tokens"] == 0
    assert "money" not in str(results).lower() and "cost_usd" not in str(results)
