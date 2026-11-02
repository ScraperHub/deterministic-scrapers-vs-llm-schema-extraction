"""Plumbing shared by the step scripts: .env, the step cache, fixtures, and loading an earlier step."""
import importlib.util
import json
import os
import sys
from pathlib import Path

STEPS = Path(__file__).resolve().parent
FINAL = STEPS.parent / "final"
CACHE = STEPS / ".cache"
sys.path.insert(0, str(FINAL))

SAMPLE_URLS = ["https://www.amazon.com/dp/B0CHX2XFLN", "https://www.walmart.com/ip/3551794083"]
FIXTURE_URLS = ["https://www.amazon.com/dp/B0TESTCASE", "https://www.walmart.com/ip/3551794083"]


def is_live() -> bool:
    return "--live" in sys.argv


def urls() -> list[str]:
    return SAMPLE_URLS if is_live() else FIXTURE_URLS


def env() -> dict:
    from dotenv import load_dotenv

    load_dotenv(FINAL / ".env")
    return {k: os.getenv(k, "") for k in ("CRAWLBASE_TOKEN", "CRAWLBASE_JS_TOKEN", "OPENAI_API_KEY", "OPENAI_MODEL")}


def crawling_api(token_kind: str = "normal"):
    """The real SDK with --live, the offline fixture stand-in otherwise."""
    if is_live():
        from crawlbase import CrawlingAPI

        token = env()["CRAWLBASE_JS_TOKEN" if token_kind == "js" else "CRAWLBASE_TOKEN"]
        return CrawlingAPI({"token": token, "timeout": 120})
    from extractbench.fakes import FakeCrawlingAPI

    return FakeCrawlingAPI({"token": "offline"})


def openai_client():
    if is_live():
        from openai import OpenAI

        return OpenAI(api_key=env()["OPENAI_API_KEY"]), env()["OPENAI_MODEL"] or "gpt-4o-mini"
    from extractbench.fakes import FakeOpenAI

    return FakeOpenAI(), "gpt-4o-mini-fixture"


def save(name: str, value) -> Path:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{name}.json"
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load(name: str):
    path = CACHE / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def load_step(name: str):
    spec = importlib.util.spec_from_file_location(f"step_{name}", STEPS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
