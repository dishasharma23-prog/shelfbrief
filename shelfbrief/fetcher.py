"""A polite HTTP client: obeys robots.txt, rate-limits per host, retries carefully and caches responses."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import httpx

from .robots import Robots

DEFAULT_UA = "ShelfBriefBot/1.0 (+https://github.com/dishasharma23-prog/shelfbrief; portfolio research crawler)"


class Disallowed(Exception):
    """robots.txt does not allow this URL for our user agent."""


class FetchError(Exception):
    """The request failed after all retries."""


@dataclass
class Fetcher:
    user_agent: str = DEFAULT_UA
    delay: float = 1.5                # minimum seconds between requests to the same host
    timeout: float = 20.0
    max_retries: int = 3
    cache_dir: Path | None = None
    cache_ttl: float = 6 * 3600       # seconds a cached response stays fresh
    transport: httpx.BaseTransport | None = None   # injected in tests
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    stats: dict = field(default_factory=lambda: {"requests": 0, "cache_hits": 0, "retries": 0, "disallowed": 0})

    def __post_init__(self):
        self._client = httpx.Client(
            headers={"User-Agent": self.user_agent, "Accept-Language": "en-IN,en;q=0.8"},
            timeout=self.timeout, follow_redirects=True, transport=self.transport,
        )
        self._robots: dict[str, Robots | None] = {}
        self._last_hit: dict[str, float] = {}

    # ---------- robots.txt ----------
    def _robots_for(self, url: str) -> Robots | None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        rp = Robots()
        try:
            self._throttle(parts.netloc)
            r = self._client.get(origin + "/robots.txt")
            self.stats["requests"] += 1
            if r.status_code in (401, 403):
                rp.disallow_all = True          # access-controlled: treat as "keep out"
            elif r.status_code >= 400:
                rp.allow_all = True             # no robots.txt: everything is allowed
            else:
                rp = Robots.parse(r.text, self.user_agent.split("/")[0])
        except httpx.HTTPError:
            rp = None                           # unreachable: we will not crawl it
        self._robots[origin] = rp
        return rp

    def allowed(self, url: str) -> bool:
        rp = self._robots_for(url)
        return rp is not None and rp.can_fetch(url)

    def crawl_delay(self, url: str) -> float:
        rp = self._robots_for(url)
        cd = rp.crawl_delay if rp else None
        return max(self.delay, float(cd or 0))

    # ---------- rate limit ----------
    def _throttle(self, host: str, wait: float | None = None):
        wait = self.delay if wait is None else wait
        last = self._last_hit.get(host)
        if last is not None:
            gap = self.clock() - last
            if gap < wait:
                self.sleep(wait - gap)
        self._last_hit[host] = self.clock()

    # ---------- cache ----------
    def _cache_path(self, url: str) -> Path | None:
        if not self.cache_dir:
            return None
        host = urlsplit(url).netloc.replace(":", "_")
        return Path(self.cache_dir) / host / (hashlib.sha1(url.encode()).hexdigest() + ".json")

    def _cache_get(self, url: str) -> str | None:
        p = self._cache_path(url)
        if p and p.exists():
            entry = json.loads(p.read_text(encoding="utf-8"))
            if time.time() - entry["saved_at"] < self.cache_ttl:
                self.stats["cache_hits"] += 1
                return entry["body"]
        return None

    def _cache_put(self, url: str, body: str):
        p = self._cache_path(url)
        if p:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"url": url, "saved_at": time.time(), "body": body}), encoding="utf-8")

    # ---------- public API ----------
    def get_text(self, url: str) -> str:
        cached = self._cache_get(url)
        if cached is not None:
            return cached
        if not self.allowed(url):
            self.stats["disallowed"] += 1
            raise Disallowed(url)
        host = urlsplit(url).netloc
        wait = self.crawl_delay(url)
        last_error = None
        for attempt in range(self.max_retries + 1):
            self._throttle(host, wait)
            try:
                r = self._client.get(url)
                self.stats["requests"] += 1
            except httpx.HTTPError as e:
                last_error = str(e)
            else:
                if r.status_code == 200:
                    self._cache_put(url, r.text)
                    return r.text
                if r.status_code in (429, 500, 502, 503, 504):
                    last_error = f"HTTP {r.status_code}"
                    retry_after = r.headers.get("Retry-After", "")
                    if retry_after.isdigit():
                        wait = max(wait, min(float(retry_after), 120))
                else:
                    raise FetchError(f"HTTP {r.status_code} for {url}")
            if attempt < self.max_retries:
                self.stats["retries"] += 1
                self.sleep(min(2 ** attempt * wait, 60))
        raise FetchError(f"{last_error} for {url} after {self.max_retries + 1} attempts")

    def get_json(self, url: str):
        return json.loads(self.get_text(url))

    def close(self):
        self._client.close()
