"""Sieve MCP server — exposes codebase search as Claude-callable tools.

Tools
-----
sieve_find(query, max_results=5)
    Ranked skeleton search across the ledger.  Returns XML with file
    skeletons ordered by keyword/symbol relevance to the query.

sieve_file(path)
    Return the cached skeleton for a single file.  Faster and lower-token
    than a full Read when Claude already knows which file it wants.

Run
---
    python -m src.mcp.server [path/to/ledger.db]

Register in .claude/settings.json:
    {
      "mcpServers": {
        "sieve": {
          "command": "python",
          "args": ["-m", "src.mcp.server", "/path/to/project/ledger.db"]
        }
      }
    }
"""
from __future__ import annotations

import re
import sys
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve repo root so src.* imports work regardless of cwd
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.data.ledger import Ledger, set_db_path  # noqa: E402

try:
    from mcp.server.fastmcp import FastMCP  # noqa: E402
except ImportError as exc:
    sys.exit(f"[sieve-mcp] mcp package not found — run: pip install 'mcp[cli]'\n{exc}")

# ---------------------------------------------------------------------------
# Constants — mirror bin/sieve-hook scoring
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


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "sieve",
    instructions=(
        "Sieve provides ranked, pre-digested codebase search. "
        "Use sieve_find() instead of Grep+Read when you want to understand "
        "which files handle a concept — it returns ranked skeletons (signatures "
        "and docstrings, no bodies) ordered by relevance. "
        "Use sieve_file() when you know which file you want but don't need the "
        "full source — lower token cost than Read."
    ),
)


def _get_ledger() -> Ledger:
    return Ledger()


@mcp.tool()
def sieve_find(query: str, max_results: int = 5) -> str:
    """Search the codebase for files related to a concept or feature.

    Returns ranked file skeletons (class/function signatures + docstrings,
    no bodies) ordered by relevance to the query.  Much cheaper than
    Grep+Read: one call returns structured understanding instead of raw lines.

    Args:
        query: Natural language description of what you're looking for.
               Examples: "authentication logic", "retry on failure",
               "which files write to the database"
        max_results: Maximum number of files to return (default 5).
    """
    keywords = _keywords(query)
    if not keywords:
        return "<sieve_result error='empty query'/>"

    cwd = str(Path.cwd().resolve())
    candidates: list[tuple[float, str, str, str]] = []  # score, path, rel, skeleton

    try:
        with _get_ledger() as ledger:
            rows = ledger.get_files_under(cwd)
            for (path,) in rows:
                if _should_skip(path):
                    continue
                cache = ledger.get_cache(path)
                if not cache or not cache["skeleton"]:
                    continue

                sym_rows = ledger._conn.execute(
                    "SELECT symbol_name FROM symbol_index WHERE source_file = ?",
                    (path.replace("\\", "/"),),
                ).fetchall()
                symbols = [r[0] for r in sym_rows]

                score = _score(path, symbols, keywords)
                if score < 1.0:
                    continue

                try:
                    rel = str(Path(path).relative_to(cwd))
                except ValueError:
                    rel = Path(path).name

                candidates.append((score, path, rel, cache["skeleton"]))

    except Exception as exc:
        return f"<sieve_result error='ledger unavailable: {exc}'/>"

    if not candidates:
        return "<sieve_result query={!r} ranked='true'>\n  <!-- no matches found -->\n</sieve_result>".format(query)

    candidates.sort(key=lambda x: x[0], reverse=True)
    top = candidates[:max_results]

    lines = [f"<sieve_result query={query!r} ranked='true' total_matches='{len(candidates)}'>"]
    for score, path, rel, skeleton in top:
        lines.append(f"  <file path={rel!r} score='{score:.0f}'>")
        for skel_line in skeleton.splitlines():
            lines.append(f"    {skel_line}")
        lines.append("  </file>")
    lines.append("</sieve_result>")

    return "\n".join(lines)


@mcp.tool()
def sieve_file(path: str) -> str:
    """Return the cached skeleton for a specific file.

    Faster and lower token cost than Read when you already know which file
    you want but don't need the full source — returns signatures and
    docstrings only, no function bodies.

    Args:
        path: File path, relative to the project root or absolute.
    """
    cwd = str(Path.cwd().resolve())

    # Resolve relative paths
    if not os.path.isabs(path):
        abs_path = os.path.join(cwd, path)
    else:
        abs_path = path
    abs_path = os.path.normpath(abs_path)

    try:
        with _get_ledger() as ledger:
            cache = ledger.get_cache(abs_path)
            if not cache or not cache["skeleton"]:
                # Try forward-slash normalized path (Windows)
                cache = ledger.get_cache(abs_path.replace("\\", "/"))
            if not cache or not cache["skeleton"]:
                return f"<sieve_file path={path!r} error='not in ledger — daemon may not have processed this file yet'/>"

            try:
                rel = str(Path(abs_path).relative_to(cwd))
            except ValueError:
                rel = Path(abs_path).name

            lines = [f"<sieve_file path={rel!r}>"]
            for skel_line in cache["skeleton"].splitlines():
                lines.append(f"  {skel_line}")
            lines.append("</sieve_file>")
            return "\n".join(lines)

    except Exception as exc:
        return f"<sieve_file path={path!r} error='ledger unavailable: {exc}'/>"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "ledger.db"
    if not db_path.exists():
        sys.exit(f"[sieve-mcp] ledger not found: {db_path}\nRun the daemon first: python src/main.py <project-path>")
    set_db_path(db_path)
    mcp.run()
