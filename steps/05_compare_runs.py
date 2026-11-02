"""Step 5: three runs per URL per path, then fill rate, consistency, invented values and token counts.

This is the measurement on two URLs. final/run_benchmark.py runs the same definitions on 50
and writes final/output/results.json. No money fields: requests and tokens only.
"""
from _common import crawling_api, load_step, openai_client, save, urls

RUNS = 3


def fill_rate(records: list[dict | None], fields: list[str]) -> dict:
    return {f: round(sum(1 for r in records if r and r.get(f) is not None) / len(records), 4) for f in fields}


def identical_across_runs(runs: list[dict | None]) -> bool:
    return all(r is not None for r in runs) and all(r == runs[0] for r in runs)


if __name__ == "__main__":
    schema, scraper, autoparse = load_step("01_schema"), load_step("02_builtin_scraper"), load_step("03_autoparse")
    llm_step, normalize = load_step("04_llm_extract"), load_step("07_normalize")
    api = crawling_api()
    client, model = openai_client()
    by_path = {"scraper": {}, "autoparse": {}, "markdown_llm": {}}
    invented = {p: 0 for p in by_path}
    values = {p: 0 for p in by_path}
    tokens = 0
    for url in urls():
        for p in by_path:
            by_path[p][url] = []
        for _ in range(RUNS):
            page = llm_step.fetch_markdown(api, url)
            md = page["markdown"]
            a = scraper.fetch_builtin(api, url)
            b = autoparse.fetch_autoparse(api, url)
            c = llm_step.extract_with_llm(client, model, url, md)
            tokens += c["prompt_tokens"] + c["completion_tokens"]
            records = {
                "scraper": normalize.normalize_record(schema.map_scraper_output(a["data"], url)) if a["data"] else None,
                "autoparse": normalize.normalize_record(schema.map_scraper_output(b["data"], url)) if b["matched"] else None,
                "markdown_llm": normalize.normalize_record(c["data"]) if c["data"] else None,
            }
            for p, record in records.items():
                by_path[p][url].append(record)
                if record:
                    values[p] += sum(v is not None for v in record.values())
                    invented[p] += len(llm_step.invented_fields(record, md, schema.FIELDS))

    summary = {}
    for p, per_url in by_path.items():
        flat = [r for runs in per_url.values() for r in runs]
        summary[p] = {
            "fill_rate": fill_rate(flat, schema.FIELDS),
            "consistent_urls": sum(identical_across_runs(r) for r in per_url.values()),
            "urls": len(per_url),
            "invented_values": invented[p],
            "non_null_values": values[p],
            "requests": len(flat),
            "tokens": tokens if p == "markdown_llm" else 0,
        }
        mean = sum(summary[p]["fill_rate"].values()) / len(schema.FIELDS)
        print(f"{p:13s} fill={mean:.2f} consistent={summary[p]['consistent_urls']}/{summary[p]['urls']} "
              f"invented={invented[p]}/{values[p]} requests={summary[p]['requests']} tokens={summary[p]['tokens']}")
    print("saved", save("05_compare", summary))
