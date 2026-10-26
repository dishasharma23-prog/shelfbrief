"""robots.txt rules per RFC 9309: user-agent groups, Allow/Disallow with `*` and `$`, longest match wins.

Python's urllib.robotparser treats `*` literally, and Shopify's default robots.txt is full of wildcard rules
(`/collections/*sort_by*`, `/*/products/*-remote`), so we parse it ourselves.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit


def _pattern(path: str) -> re.Pattern:
    anchored = path.endswith("$")
    body = re.escape(path[:-1] if anchored else path).replace(r"\*", ".*")
    return re.compile(body + ("$" if anchored else ""))


@dataclass
class Robots:
    rules: list[tuple[bool, str, re.Pattern]] = field(default_factory=list)  # (allow, raw path, regex)
    crawl_delay: float | None = None
    allow_all: bool = False
    disallow_all: bool = False

    @classmethod
    def parse(cls, text: str, agent: str) -> "Robots":
        agent = agent.lower()
        groups: list[tuple[list[str], list[tuple[str, str]]]] = []
        agents: list[str] = []
        lines: list[tuple[str, str]] = []
        in_rules = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (s.strip() for s in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if in_rules:                       # a new group starts
                    groups.append((agents, lines))
                    agents, lines, in_rules = [], [], False
                agents.append(value.lower())
            elif key in ("allow", "disallow", "crawl-delay"):
                in_rules = True
                lines.append((key, value))
        if agents:
            groups.append((agents, lines))

        # The most specific group naming us wins; otherwise the "*" group(s).
        mine = [l for a, l in groups if any(x != "*" and x in agent for x in a)]
        chosen = mine or [l for a, l in groups if "*" in a]
        r = cls()
        for group in chosen:
            for key, value in group:
                if key == "crawl-delay":
                    try:
                        r.crawl_delay = float(value)
                    except ValueError:
                        pass
                elif value:                         # an empty Disallow means "allow everything"
                    r.rules.append((key == "allow", value, _pattern(value)))
        return r

    def can_fetch(self, url: str) -> bool:
        if self.disallow_all:
            return False
        if self.allow_all:
            return True
        parts = urlsplit(url)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        if path == "/robots.txt":
            return True
        best: tuple[int, bool] | None = None
        for allow, raw, rx in self.rules:
            if rx.match(path):
                key = (len(raw), allow)                # longer rule wins; on a tie, Allow wins
                if best is None or key > best:
                    best = key
        return True if best is None else best[1]
