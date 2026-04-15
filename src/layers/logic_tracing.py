"""Static call-graph traversal with circular-dependency detection.

Reads from the symbol_index table in ledger.db.  Each row stores the set of
files that a symbol's source file imports/calls (the `references` JSON column).
Tracing multi-hop dependencies means following those edges recursively while
keeping a visited set to stop on back-edges (circular imports).
"""
import json
import sqlite3
from pathlib import Path
from typing import Optional

_DB_PATH = Path(__file__).parent.parent.parent / "ledger.db"


def _file_refs(conn: sqlite3.Connection, path: str) -> list[str]:
    """Return deduplicated referenced files for every symbol in *path*."""
    rows = conn.execute(
        'SELECT "references" FROM symbol_index WHERE source_file = ?',
        (path,),
    ).fetchall()
    seen: set[str] = set()
    out: list[str] = []
    for (raw,) in rows:
        for ref in json.loads(raw):
            if ref not in seen:
                seen.add(ref)
                out.append(ref)
    return out


def trace_dependencies(
    path: str,
    *,
    db_path: Path = _DB_PATH,
    _visited: Optional[set[str]] = None,
    _stack: Optional[set[str]] = None,
) -> dict:
    """Recursively trace file dependencies from the symbol_index.

    Args:
        path:     Absolute or repo-relative file path to start from.
        db_path:  Override the ledger DB location (for testing).

    Returns a nested structure::

        {
            "path": "a.py",
            "dependencies": [
                {"path": "b.py", "dependencies": [...]},
                {"path": "c.py", "circular": "[Circular: a.py ↔ c.py]"},
            ]
        }

    Circular references are labeled ``[Circular: X ↔ Y]`` and not recursed.
    Nodes already fully expanded in another branch are returned as
    ``{"path": ..., "cached": True, "dependencies": []}`` to avoid
    re-expanding the same subtree.
    """
    if _visited is None:
        _visited = set()
    if _stack is None:
        _stack = set()

    if path in _stack:  # pragma: no cover
        return {"path": path, "circular": f"[Circular: {path} ↔ {path}]"}

    if path in _visited:
        return {"path": path, "cached": True, "dependencies": []}

    _visited.add(path)
    _stack.add(path)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=500")
    try:
        conn.row_factory = sqlite3.Row
        refs = _file_refs(conn, path)
    finally:
        conn.close()

    children: list[dict] = []
    for dep in refs:
        if dep in _stack:
            children.append(
                {"path": dep, "circular": f"[Circular: {path} ↔ {dep}]"}
            )
        else:
            children.append(
                trace_dependencies(dep, db_path=db_path, _visited=_visited, _stack=_stack)
            )

    _stack.discard(path)
    return {"path": path, "dependencies": children}


def match_route(
    path_literal: str,
    *,
    db_path: Path = _DB_PATH,
) -> Optional[dict]:
    """Search symbol_index for a backend symbol whose name contains *path_literal*.

    Used by the MCP server to map a frontend URL string (e.g. ``"/api/user"``)
    to a backend route handler.

    Returns the first matching row as a dict with keys ``symbol_name`` and
    ``source_file``, or ``None`` if nothing is found.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=500")
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT symbol_name, source_file FROM symbol_index "
            "WHERE symbol_name LIKE ? OR source_file LIKE ? "
            "LIMIT 1",
            (f"%{path_literal}%", f"%{path_literal}%"),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    return {"symbol_name": row["symbol_name"], "source_file": row["source_file"]}
