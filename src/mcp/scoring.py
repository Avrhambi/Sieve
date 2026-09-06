"""Pure keyword / scoring helpers for the Sieve MCP server.

Extracted from ``src.mcp.server`` so they can be imported and unit-tested
without pulling in FastMCP or a live ledger.
"""
from __future__ import annotations

import re
from pathlib import Path

_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "in", "of", "to", "for", "is", "are",
    "was", "be", "on", "at", "by", "do", "it", "this", "that", "with",
    "from", "how", "what", "where", "when", "why", "would", "could",
    "should", "can", "i", "you", "we", "my", "your", "me", "us",
})

# Ordered longest-first so a longer suffix wins over a shorter tail of it.
_STEM_SUFFIXES = ("tion", "ions", "ers", "ing", "ion", "ors", "ive", "ed", "er", "or", "ly")

# Minimum remaining-stem length per suffix. The agent-noun suffixes "er"/"or"
# and "tion" need a longer stem to avoid mangling short roots
# (e.g. "ledger" -> "ledg", "injection" -> "injec").
_STEM_MIN_STEM = {"tion": 6, "er": 5, "ers": 5, "or": 5, "ors": 5}

_SKIP_DIRS = frozenset({"tests", "test", "docs", "doc", "__pycache__"})


def _stem(word: str) -> str:
    for suffix in _STEM_SUFFIXES:
        min_stem = _STEM_MIN_STEM.get(suffix, 3)
        if word.endswith(suffix) and len(word) - len(suffix) >= min_stem:
            return word[: -len(suffix)]
    return word


def _keywords(query: str) -> set[str]:
    tokens = re.findall(r"[A-Za-z_]\w*", query)
    result: set[str] = set()
    for t in tokens:
        low = t.lower()
        if len(low) > 2 and low not in _STOP_WORDS:
            result.add(low)
            result.add(_stem(low))
    return result


def _should_skip(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    return any(p in _SKIP_DIRS for p in parts)


def _score(path: str, symbols: list[str], keywords: set[str]) -> float:
    score = 0.0
    name = Path(path).stem.lower()
    if name in keywords or _stem(name) in keywords:
        score += 3.0
    for sym in symbols:
        if sym.lower() in keywords:
            score += 2.0
    return score
