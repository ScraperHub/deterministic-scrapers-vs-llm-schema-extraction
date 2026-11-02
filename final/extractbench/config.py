import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

FINAL_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = FINAL_DIR / ".env"
CACHE_DIR = FINAL_DIR / ".cache"
OUTPUT_DIR = FINAL_DIR / "output"
URLS_PATH = FINAL_DIR / "urls.json"


@dataclass(frozen=True)
class Settings:
    crawlbase_token: str
    crawlbase_js_token: str
    openai_api_key: str
    openai_model: str


def load_settings(env_path: Path = ENV_PATH) -> Settings:
    load_dotenv(env_path, override=False)
    missing = [k for k in ("CRAWLBASE_TOKEN", "OPENAI_API_KEY") if not os.getenv(k)]
    if missing:
        raise SystemExit(f"Missing {', '.join(missing)} in {env_path}. Copy .env.example to .env.")
    return Settings(
        crawlbase_token=os.environ["CRAWLBASE_TOKEN"],
        crawlbase_js_token=os.getenv("CRAWLBASE_JS_TOKEN", ""),
        openai_api_key=os.environ["OPENAI_API_KEY"],
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    )
