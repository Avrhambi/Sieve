"""Structured JSON producers for the ``cs`` CLI.

Three pure functions read the ledger and return plain dicts. The CLI
serialises them with ``json.dumps``.

* ``get_file_skeleton_json(filepath)`` — per-file: structured symbols + import edges
* ``get_repo_map_json()`` — public-interface map across all indexed files under cwd
* ``get_diff_json(since)`` — signature-level changes vs the latest snapshot
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from src.data.ledger import Ledger


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def _path_to_module(path: str) -> str:
    """Convert a file path to the dotted module form stored in references.

    ``src/daemon/watcher.py`` → ``src.daemon.watcher``
    """
    rel = _norm(path)
    if rel.endswith(".py"):
        rel = rel[:-3]
    return rel.replace("/", ".")


def _module_candidates(path: str) -> list[str]:
    """Yield several module-name forms a file might be imported as.

    Imports may be absolute (``src.daemon.watcher``) or relative-resolved
    (``daemon.watcher``, ``watcher``). Returning all suffixes lets the LIKE
    query catch any of them.
    """
    full = _path_to_module(path)
    parts = full.split(".")
    return [".".join(parts[i:]) for i in range(len(parts))]


def _public(name: str) -> bool:
    return not name.startswith("_")


# ---------------------------------------------------------------------------
# Per-file skeleton
# ---------------------------------------------------------------------------

def get_file_skeleton_json(filepath: str) -> dict[str, Any]:
    """Return structured skeleton + dependency edges for one file."""
    fp = _norm(filepath)
    with Ledger() as ledger:
        file_row = ledger.get_file(fp)
        if file_row is None:
            return {"file": fp, "error": "not indexed"}

        sym_rows = ledger._conn.execute(
            'SELECT symbol_name, signature, "references" FROM symbol_index '
            "WHERE source_file = ? ORDER BY symbol_name",
            (fp,),
        ).fetchall()

        symbols = [
            {"name": r["symbol_name"], "signature": r["signature"]}
            for r in sym_rows
        ]

        # Forward edges: take from the first symbol row (refs are file-level).
        imports_out: list[str] = []
        if sym_rows:
            try:
                imports_out = sorted(set(json.loads(sym_rows[0]["references"])))
            except (TypeError, ValueError):
                imports_out = []

        # Reverse edges: any symbol_index row whose references mention this
        # file (under any of its module-name forms).
        importers: set[str] = set()
        for module in _module_candidates(fp):
            needle = f'"{module}"'
            for row in ledger._conn.execute(
                'SELECT DISTINCT source_file FROM symbol_index '
                'WHERE "references" LIKE ?',
                (f"%{needle}%",),
            ):
                if row["source_file"] != fp:
                    importers.add(row["source_file"])

        cache = ledger.get_cache(fp)
        skeleton_blob = cache["skeleton"] if cache else None

        return {
            "file": fp,
            "indexed_at": file_row["mtime"],
            "skeleton": skeleton_blob,
            "symbols": symbols,
            "dependencies": {
                "imports_out": imports_out,
                "imported_in": sorted(importers),
            },
        }


# ---------------------------------------------------------------------------
# Repo map
# ---------------------------------------------------------------------------

def get_repo_map_json(root: str | None = None) -> dict[str, Any]:
    """Return a public-interface map for every indexed file under *root*.

    Default *root* is the current working directory.
    """
    root_str = _norm(str(Path(root).resolve()) if root else str(Path.cwd().resolve()))
    files: list[dict[str, Any]] = []

    with Ledger() as ledger:
        rows = ledger.get_files_under(root_str)
        for (path,) in rows:
            sym_rows = ledger._conn.execute(
                "SELECT symbol_name, signature FROM symbol_index "
                "WHERE source_file = ? ORDER BY symbol_name",
                (path,),
            ).fetchall()
            public = [
                {"name": r["symbol_name"], "signature": r["signature"]}
                for r in sym_rows
                if _public(r["symbol_name"])
            ]
            if public:
                files.append({"file": path, "public_interface": public})

    return {
        "generated_at": int(time.time()),
        "root": root_str,
        "files": files,
    }


# ---------------------------------------------------------------------------
# Diff vs last snapshot
# ---------------------------------------------------------------------------

def get_diff_json(since: str = "last_commit") -> dict[str, Any]:
    """Return signature-level changes between current symbol_index and a snapshot.

    *since* may be ``"last_commit"`` (default — uses the most recent
    ``snapshot_at``) or an explicit short commit hash.
    """
    with Ledger() as ledger:
        if since == "last_commit":
            row = ledger._conn.execute(
                "SELECT commit_hash FROM structural_snapshots "
                "ORDER BY snapshot_at DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return {"since": since, "commit": None, "changes": [], "error": "no snapshots"}
            commit_hash = row["commit_hash"]
        else:
            commit_hash = since

        snap_rows = ledger._conn.execute(
            "SELECT filepath, symbol_name, signature FROM structural_snapshots "
            "WHERE commit_hash = ?",
            (commit_hash,),
        ).fetchall()

        if not snap_rows:
            return {
                "since": since,
                "commit": commit_hash,
                "changes": [],
                "error": "snapshot not found",
            }

        snapshot: dict[str, dict[str, str | None]] = {}
        for r in snap_rows:
            snapshot.setdefault(r["filepath"], {})[r["symbol_name"]] = r["signature"]

        cur_rows = ledger._conn.execute(
            "SELECT source_file, symbol_name, signature FROM symbol_index"
        ).fetchall()
        current: dict[str, dict[str, str | None]] = {}
        for r in cur_rows:
            current.setdefault(r["source_file"], {})[r["symbol_name"]] = r["signature"]

    changes: list[dict[str, Any]] = []
    for filepath in sorted(set(snapshot) | set(current)):
        snap_syms = snapshot.get(filepath, {})
        cur_syms = current.get(filepath, {})
        added = sorted(set(cur_syms) - set(snap_syms))
        removed = sorted(set(snap_syms) - set(cur_syms))
        modified = [
            {"name": n, "before": snap_syms[n], "after": cur_syms[n]}
            for n in sorted(set(snap_syms) & set(cur_syms))
            if snap_syms[n] != cur_syms[n]
        ]
        if added or removed or modified:
            changes.append({
                "file": filepath,
                "added": [{"name": n, "signature": cur_syms[n]} for n in added],
                "removed": [{"name": n, "signature": snap_syms[n]} for n in removed],
                "modified": modified,
            })

    return {"since": since, "commit": commit_hash, "changes": changes}
