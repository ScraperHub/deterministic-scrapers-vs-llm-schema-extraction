# Built-in scrapers vs LLM schema extraction

This program turns product URLs into one JSON record with eight fields (`title`, `id`, `brand`, `price`, `currency`, `availability`, `rating`, `reviews_count`) and measures three ways of doing it:

1. Crawlbase Crawling API with a built-in scraper (`scraper=amazon-product-details`, `scraper=walmart-product-details`).
2. The same API with `autoparse=true`.
3. The same API with `format=md`, then one OpenAI structured-output call with a JSON Schema.

`final/` holds the router (scraper, then `autoparse`, then Markdown plus LLM), the normaliser, the JSON Schema gate, and the benchmark that writes `final/output/results.json`. It reports fill rate, three-run consistency, invented values (checked against the page text), latency, and request and token counts. `steps/01_schema.py` to `steps/09_async_batch.py` are the same logic in small slices. A test keeps them in step with `final/`.

## Install

Python 3.11 or newer. One `requirements.txt`, at `code/`.

Windows (PowerShell):

```powershell
cd code
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux and macOS:

```bash
cd code
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows, if activation is blocked, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or call `.\.venv\Scripts\python.exe` directly.

## Configure

Copy `final/.env.example` to `final/.env` and fill in your Crawlbase normal token, JavaScript token, OpenAI key and model. Steps and final both read that one file. `.env` is gitignored.

## Run

Testing mode needs no network and no keys:

```
cd final
python -m pytest -q
python run_benchmark.py --mode test
```

Production mode calls the Crawling API and OpenAI, caches every response under `final/.cache/`, and writes `final/output/results.json`. Re-runs read the cache.

```
python run_benchmark.py --mode live --runs 3
python make_results_svg.py
```

`--no-llm` runs the two Crawlbase paths only. The same commands work in PowerShell, bash and zsh.

The step scripts run offline from fixtures by default. Add `--live` to call the APIs for two sample URLs:

```
cd steps
python 01_schema.py
python 08_route.py
python 09_async_batch.py --live
```

---

Copyright (c) 2026 Crawlbase
