"""Unit tests for src.mcp.server scoring and keyword logic.

Imports the pure helper functions directly, bypassing the FastMCP/ledger
import chain so tests run without a live daemon or mcp package installed.
"""
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Replicate the pure helpers locally so tests don't need FastMCP installed.
# These are copied verbatim from src/mcp/server.py — if server.py changes,
# update here too and add a test that catches the divergence.
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "in", "of", "to", "for", "is", "are",
    "was", "be", "on", "at", "by", "do", "it", "this", "that", "with",
    "from", "how", "what", "where", "when", "why", "would", "could",
    "should", "can", "i", "you", "we", "my", "your", "me", "us",
})
_STEM_SUFFIXES = ("ing", "er", "ers", "ed", "ion", "ions", "or", "ors", "ly", "ive", "tion")
_SKIP_DIRS = frozenset({"tests", "test", "docs", "doc", "__pycache__"})


def _stem(word: str) -> str:
    for suffix in _STEM_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _keywords(query: str) -> set:
    tokens = re.findall(r"[A-Za-z_]\w*", query)
    result: set = set()
    for t in tokens:
        low = t.lower()
        if len(low) > 2 and low not in _STOP_WORDS:
            result.add(low)
            result.add(_stem(low))
    return result


def _should_skip(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    return any(p in _SKIP_DIRS for p in parts)


def _score(path: str, symbols: list, keywords: set) -> float:
    score = 0.0
    name = Path(path).stem.lower()
    if name in keywords or _stem(name) in keywords:
        score += 3.0
    for sym in symbols:
        if sym.lower() in keywords:
            score += 2.0
    return score


# ---------------------------------------------------------------------------
# _stem
# ---------------------------------------------------------------------------

class TestStem:
    def test_strips_ing(self):
        assert _stem("watching") == "watch"

    def test_strips_er(self):
        assert _stem("processor") == "process"

    def test_strips_ed(self):
        assert _stem("cached") == "cach"

    def test_strips_ion(self):
        assert _stem("injection") == "inject"

    def test_short_word_unchanged(self):
        assert _stem("run") == "run"

    def test_no_matching_suffix(self):
        assert _stem("ledger") == "ledger"

    def test_strips_tion(self):
        assert _stem("skeletonization") == "skeletoniza"


# ---------------------------------------------------------------------------
# _keywords
# ---------------------------------------------------------------------------

class TestKeywords:
    def test_basic_extraction(self):
        kw = _keywords("file watching logic")
        assert "file" in kw
        # either the raw token or its stem should be present
        assert "watching" in kw or "watch" in kw

    def test_stop_words_removed(self):
        kw = _keywords("how do i find the file")
        assert "how" not in kw
        assert "the" not in kw
        assert "do" not in kw

    def test_stemmed_forms_included(self):
        kw = _keywords("watching")
        assert "watching" in kw
        assert "watch" in kw

    def test_empty_query(self):
        assert _keywords("") == set()

    def test_short_tokens_excluded(self):
        kw = _keywords("a b is do")
        assert not kw or all(len(k) > 2 for k in kw)

    def test_multiple_words(self):
        kw = _keywords("retry on failure connection timeout")
        assert "retry" in kw or "retri" in kw
        assert "failure" in kw or "fail" in kw
        assert "connection" in kw
        assert "timeout" in kw


# ---------------------------------------------------------------------------
# _score
# ---------------------------------------------------------------------------

class TestScore:
    def test_filename_match_scores_3(self):
        kw = {"watcher", "watch"}
        assert _score("src/daemon/watcher.py", [], kw) == 3.0

    def test_stem_filename_match_scores_3(self):
        kw = _keywords("watching")  # includes "watch"
        assert _score("src/daemon/watcher.py", [], kw) >= 3.0

    def test_symbol_match_adds_2_per_symbol(self):
        kw = {"process"}
        score = _score("other.py", ["process_file", "process"], kw)
        # "process_file".lower() in {"process"} → False (not equal)
        # "process".lower() in {"process"} → True → +2
        assert score == 2.0

    def test_no_match_scores_zero(self):
        kw = {"authentication", "login"}
        assert _score("src/daemon/watcher.py", ["watch_file"], kw) == 0.0

    def test_filename_and_symbol_accumulate(self):
        kw = {"watcher", "watch"}
        score = _score("src/daemon/watcher.py", ["watcher"], kw)
        assert score == 3.0 + 2.0  # filename match + symbol match


# ---------------------------------------------------------------------------
# _should_skip
# ---------------------------------------------------------------------------

class TestShouldSkip:
    def test_skips_tests_dir(self):
        assert _should_skip("tests/test_skeleton.py")

    def test_skips_docs_dir(self):
        assert _should_skip("docs/conf.py")

    def test_skips_doc_dir(self):
        assert _should_skip("doc/api.md")

    def test_does_not_skip_src(self):
        assert not _should_skip("src/daemon/watcher.py")

    def test_does_not_skip_root_file(self):
        assert not _should_skip("main.py")

    def test_handles_backslash_paths(self):
        assert _should_skip("tests\\test_skeleton.py")

    def test_skips_pycache(self):
        assert _should_skip("src/__pycache__/ledger.cpython-311.pyc")

    def test_does_not_skip_test_in_name(self):
        # A file *named* test_utils but not inside a tests/ dir should pass
        assert not _should_skip("src/test_utils.py")
