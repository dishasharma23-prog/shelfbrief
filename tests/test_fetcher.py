import httpx
import pytest

from shelfbrief.fetcher import Disallowed, FetchError, Fetcher


class Clock:
    def __init__(self):
        self.t = 0.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(round(s, 2))
        self.t += s


def make(handler, **kw):
    clock = Clock()
    f = Fetcher(transport=httpx.MockTransport(handler), sleep=clock.sleep, clock=clock.now, **kw)
    return f, clock


def test_obeys_robots_disallow():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
        return httpx.Response(200, text="ok")
    f, _ = make(handler)
    assert f.get_text("https://shop.test/public") == "ok"
    with pytest.raises(Disallowed):
        f.get_text("https://shop.test/private/page")
    assert f.stats["disallowed"] == 1


def test_missing_robots_allows_but_forbidden_robots_blocks():
    f, _ = make(lambda req: httpx.Response(404 if req.url.path == "/robots.txt" else 200, text="x"))
    assert f.allowed("https://a.test/anything")
    f2, _ = make(lambda req: httpx.Response(403, text="no"))
    assert not f2.allowed("https://b.test/anything")


def test_respects_crawl_delay_between_requests():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nCrawl-delay: 3\n")
        return httpx.Response(200, text="ok")
    f, clock = make(handler, delay=1.0)
    f.get_text("https://slow.test/a")
    f.get_text("https://slow.test/b")
    assert clock.slept and max(clock.slept) == pytest.approx(3.0)


def test_retries_on_429_then_succeeds():
    calls = {"n": 0}

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        calls["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "2"}) if calls["n"] < 3 else httpx.Response(200, text="done")
    f, _ = make(handler, delay=0.1)
    assert f.get_text("https://busy.test/x") == "done"
    assert f.stats["retries"] == 2


def test_gives_up_after_max_retries_and_does_not_retry_404():
    f, _ = make(lambda req: httpx.Response(404 if req.url.path == "/robots.txt" else 503), max_retries=2)
    with pytest.raises(FetchError):
        f.get_text("https://down.test/x")
    assert f.stats["retries"] == 2
    f2, _ = make(lambda req: httpx.Response(404))
    with pytest.raises(FetchError):
        f2.get_text("https://gone.test/x")
    assert f2.stats["retries"] == 0


def test_cache_avoids_second_request(tmp_path):
    hits = {"n": 0}

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        hits["n"] += 1
        return httpx.Response(200, text="cached body")
    f, _ = make(handler, cache_dir=tmp_path)
    assert f.get_text("https://c.test/p") == "cached body"
    assert f.get_text("https://c.test/p") == "cached body"
    assert hits["n"] == 1 and f.stats["cache_hits"] == 1


def test_identifies_itself():
    seen = {}

    def handler(req):
        seen["ua"] = req.headers["User-Agent"]
        return httpx.Response(404)
    f, _ = make(handler)
    f.allowed("https://ua.test/")
    assert seen["ua"].startswith("ShelfBriefBot/")


SHOPIFY_STYLE = """
User-agent: *
Disallow: /cart
Disallow: /collections/*sort_by*
Disallow: /*/products/*-remote
Disallow: /search
Allow: /search/ok$

User-agent: ShelfBriefBot
Disallow: /private
Crawl-delay: 4

User-agent: AhrefsBot
Disallow: /
"""


def test_robots_wildcards_specific_group_and_longest_match():
    from shelfbrief.robots import Robots
    star = Robots.parse(SHOPIFY_STYLE, "SomeOtherBot")
    assert not star.can_fetch("https://s.test/collections/all?sort_by=price")
    assert star.can_fetch("https://s.test/collections/all")
    assert not star.can_fetch("https://s.test/en/products/x-remote")
    assert not star.can_fetch("https://s.test/search?q=x")
    assert star.can_fetch("https://s.test/search/ok") and not star.can_fetch("https://s.test/search/ok/more")
    assert star.can_fetch("https://s.test/products.json?limit=250&page=1")
    mine = Robots.parse(SHOPIFY_STYLE, "ShelfBriefBot")      # our own group replaces the * group
    assert mine.crawl_delay == 4 and not mine.can_fetch("https://s.test/private/x")
    assert mine.can_fetch("https://s.test/cart")
