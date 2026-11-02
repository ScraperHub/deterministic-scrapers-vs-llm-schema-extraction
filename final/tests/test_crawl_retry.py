from extractbench.cache import JsonCache
from extractbench.crawl import CrawlClient

URL = "https://www.walmart.com/ip/3551794083"
CHALLENGE = "## Robot or human?\n\nActivate and hold the button to confirm that you're human. Thank You!"


def api_factory(normal_body: str, js_body: str, original_status: str = "200"):
    calls = []

    class Api:
        def __init__(self, options):
            self.token = options["token"]

        def get(self, url, options):
            calls.append(self.token)
            body = normal_body if self.token == "n" else js_body
            return {"status_code": 200, "headers": {"cb_status": "200", "original_status": original_status},
                    "body": body.encode("utf-8")}

    return Api, calls


def test_challenge_page_is_retried_once_on_js_token(tmp_path, fixtures):
    page = (fixtures / "walmart_page.md").read_text(encoding="utf-8")
    api, calls = api_factory(CHALLENGE, page)
    client = CrawlClient("n", "j", JsonCache(tmp_path), api_factory=api)
    result = client.fetch(URL, "markdown", 1)
    assert calls == ["n", "j"]
    assert result.token == "js" and result.js_retried and result.markdown == page

    again = CrawlClient("n", "j", JsonCache(tmp_path), api_factory=api).fetch(URL, "markdown", 1)
    assert calls == ["n", "j"] and again.from_cache and again.token == "js"


def test_challenge_on_both_tokens_is_kept_and_not_retried_again(tmp_path):
    api, calls = api_factory(CHALLENGE, CHALLENGE)
    CrawlClient("n", "j", JsonCache(tmp_path), api_factory=api).fetch(URL, "markdown", 1)
    CrawlClient("n", "j", JsonCache(tmp_path), api_factory=api).fetch(URL, "markdown", 1)
    assert calls == ["n", "j"]


def test_real_404_is_not_retried(tmp_path):
    api, calls = api_factory("Sorry, we couldn't find that page", "x" * 2000, original_status="404")
    result = CrawlClient("n", "j", JsonCache(tmp_path), api_factory=api).fetch(URL, "markdown", 1)
    assert calls == ["n"] and result.token == "normal"
