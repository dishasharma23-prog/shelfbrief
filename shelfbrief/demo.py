"""Serves tests/fixtures/web.json as a fake web, so the full pipeline runs offline on fictional brands."""
from __future__ import annotations

import json
from pathlib import Path

import httpx

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def fake_web_transport(web_path: Path = FIXTURES / "web.json") -> httpx.MockTransport:
    web = json.loads(Path(web_path).read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        page = web.get(str(request.url))
        if page is None:
            return httpx.Response(404, text="not found")
        return httpx.Response(page["status"], text=page["body"], headers={"Content-Type": page["content_type"]})

    return httpx.MockTransport(handler)
