"""Run the three-path benchmark.

  python run_benchmark.py --mode test          offline, fixtures only, writes output/results.test.json
  python run_benchmark.py --mode live --runs 3 Crawling API + OpenAI, cached, writes output/results.json
"""
import argparse
import json
import sys

from extractbench.benchmark import build_results, run_matrix, select_urls, write_results
from extractbench.cache import JsonCache
from extractbench.config import CACHE_DIR, OUTPUT_DIR, URLS_PATH, load_settings
from extractbench.crawl import CrawlClient
from extractbench.llm import LLMExtractor


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["test", "live"], default="test")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--per-site", type=int, default=25)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--no-llm", action="store_true", help="crawl only; the LLM path is reported as not run")
    parser.add_argument("--cache-only", action="store_true", help="live mode from .cache only; any uncached call fails")
    args = parser.parse_args(argv)

    if args.mode == "test":
        from extractbench.fakes import FakeCrawlingAPI, FakeOpenAI

        crawl = CrawlClient("test-token", "test-js-token", JsonCache(None), api_factory=FakeCrawlingAPI)
        llm = None if args.no_llm else LLMExtractor(FakeOpenAI(), "gpt-4o-mini-fixture", JsonCache(None))
        urls = ["https://www.amazon.com/dp/B0TESTCASE", "https://www.walmart.com/ip/3551794083"]
        meta = {"mode": "test", "urls": {"amazon": 1, "walmart": 1}, "url_swaps": []}
        out_path = OUTPUT_DIR / "results.test.json"
    else:
        settings = load_settings()
        cache = JsonCache(CACHE_DIR, read_only=args.cache_only)
        if args.cache_only:
            from extractbench.fakes import Offline

            crawl = CrawlClient("cache-only", "cache-only-js", cache, api_factory=Offline)
        else:
            crawl = CrawlClient(settings.crawlbase_token, settings.crawlbase_js_token, cache)
        llm = None
        if not args.no_llm:
            from openai import OpenAI

            client = Offline() if args.cache_only else OpenAI(api_key=settings.openai_api_key)
            llm = LLMExtractor(client, settings.openai_model, cache)
        candidates = json.loads(URLS_PATH.read_text(encoding="utf-8"))
        urls, swaps = select_urls(candidates, crawl, args.per_site)
        print(f"selected {len(urls)} urls, {len(swaps)} swapped out")
        meta = {
            "mode": "live",
            "urls": {"amazon": sum("amazon." in u for u in urls), "walmart": sum("walmart." in u for u in urls)},
            "url_swaps": swaps,
            "selected_urls": urls,
            "recomputed_from_cache": args.cache_only,
        }
        out_path = OUTPUT_DIR / "results.json"

    observations = run_matrix(urls, args.runs, crawl, llm, workers=args.workers)
    meta["crawl_api_calls_this_invocation"] = crawl.api_calls
    meta["llm_api_calls_this_invocation"] = llm.api_calls if llm else 0
    meta["llm_path"] = "not run" if llm is None else "run"
    results = build_results(observations, args.runs, llm.model if llm else None, meta)
    write_results(results, out_path)

    for path, block in results["paths"].items():
        s = block["all"]
        print(f"{path:13s} fill={s['fill_rate']['mean']} consistent={s['consistency']['rate']} "
              f"invented={s['invented']['rate']} accepted={s['schema_accept_rate']} "
              f"tokens={s['cost_shape']['prompt_tokens'] + s['cost_shape']['completion_tokens']}")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
