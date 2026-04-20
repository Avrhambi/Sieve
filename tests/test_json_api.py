"""Tests for src.layers.json_api."""
import json

import pytest

from src.data.ledger import Ledger, set_db_path
from src.layers.json_api import (
    get_diff_json,
    get_file_skeleton_json,
    get_repo_map_json,
    _module_candidates,
)


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """Point the module-level ledger at a fresh tmp_path DB."""
    db = tmp_path / "ledger.db"
    set_db_path(db)
    yield db


def _seed_file(path: str, mtime: float, ast_hash: str, skeleton: str) -> None:
    with Ledger() as l:
        l.upsert_file(path, mtime, ast_hash)
        l.upsert_cache(path, skeleton, "summary text")


def _seed_symbol(name: str, file: str, refs: list[str], sig: str | None) -> None:
    with Ledger() as l:
        l.upsert_symbol(name, file, refs, sig)


# ---------------------------------------------------------------------------
# _module_candidates helper
# ---------------------------------------------------------------------------

class TestModuleCandidates:
    def test_emits_all_suffixes(self):
        cands = _module_candidates("src/daemon/watcher.py")
        assert "src.daemon.watcher" in cands
        assert "daemon.watcher" in cands
        assert "watcher" in cands

    def test_handles_backslashes(self):
        cands = _module_candidates("src\\daemon\\watcher.py")
        assert "src.daemon.watcher" in cands


# ---------------------------------------------------------------------------
# get_file_skeleton_json
# ---------------------------------------------------------------------------

class TestFileSkeletonJson:
    def test_unindexed_file_reports_error(self, ledger):
        out = get_file_skeleton_json("missing.py")
        assert out["error"] == "not indexed"

    def test_returns_symbols_and_imports_out(self, ledger):
        _seed_file("src/foo.py", 1.0, "h", "skel")
        _seed_symbol("alpha", "src/foo.py", ["json", "src.bar"], "def alpha()")
        _seed_symbol("Beta", "src/foo.py", ["json", "src.bar"], "class Beta()")

        out = get_file_skeleton_json("src/foo.py")
        names = [s["name"] for s in out["symbols"]]
        assert names == ["Beta", "alpha"]
        sigs = [s["signature"] for s in out["symbols"]]
        assert "class Beta()" in sigs
        assert sorted(out["dependencies"]["imports_out"]) == ["json", "src.bar"]

    def test_imported_in_via_like_query(self, ledger):
        # foo.py defines a thing; bar.py imports foo (via "src.foo").
        _seed_file("src/foo.py", 1.0, "h1", "skel")
        _seed_symbol("alpha", "src/foo.py", [], "def alpha()")

        _seed_file("src/bar.py", 1.0, "h2", "skel")
        _seed_symbol("use_alpha", "src/bar.py", ["src.foo"], "def use_alpha()")

        out = get_file_skeleton_json("src/foo.py")
        assert "src/bar.py" in out["dependencies"]["imported_in"]


# ---------------------------------------------------------------------------
# get_repo_map_json
# ---------------------------------------------------------------------------

class TestRepoMapJson:
    def test_includes_only_public_symbols(self, ledger, tmp_path):
        # Seed two files under tmp_path so they fall under the root prefix.
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        _seed_file(str(f1), 1.0, "h", "skel")
        _seed_symbol("public_fn", str(f1), [], "def public_fn()")
        _seed_symbol("_private", str(f1), [], "def _private()")
        _seed_file(str(f2), 1.0, "h", "skel")
        _seed_symbol("OtherPublic", str(f2), [], "class OtherPublic()")

        out = get_repo_map_json(str(tmp_path))
        assert {entry["file"].split("/")[-1] for entry in out["files"]} == {"a.py", "b.py"}
        a_entry = next(e for e in out["files"] if e["file"].endswith("a.py"))
        names = [s["name"] for s in a_entry["public_interface"]]
        assert names == ["public_fn"]


# ---------------------------------------------------------------------------
# get_diff_json
# ---------------------------------------------------------------------------

class TestDiffJson:
    def test_no_snapshots_returns_error(self, ledger):
        out = get_diff_json("last_commit")
        assert out["error"] == "no snapshots"
        assert out["changes"] == []

    def test_detects_added_removed_modified(self, ledger):
        # Snapshot: foo.py had alpha (old sig), beta (gone in current)
        with Ledger() as l:
            l._conn.execute(
                "INSERT INTO structural_snapshots VALUES (?, ?, ?, ?, ?)",
                ("abc123", "src/foo.py", "alpha", "def alpha()", 1000),
            )
            l._conn.execute(
                "INSERT INTO structural_snapshots VALUES (?, ?, ?, ?, ?)",
                ("abc123", "src/foo.py", "beta", "def beta()", 1000),
            )
            l._conn.commit()

        # Current: alpha has new signature, beta removed, gamma added
        _seed_symbol("alpha", "src/foo.py", [], "def alpha(x)")
        _seed_symbol("gamma", "src/foo.py", [], "def gamma()")

        out = get_diff_json("last_commit")
        assert out["commit"] == "abc123"
        assert len(out["changes"]) == 1
        change = out["changes"][0]
        assert change["file"] == "src/foo.py"
        assert [s["name"] for s in change["added"]] == ["gamma"]
        assert [s["name"] for s in change["removed"]] == ["beta"]
        assert change["modified"][0]["name"] == "alpha"
        assert change["modified"][0]["before"] == "def alpha()"
        assert change["modified"][0]["after"] == "def alpha(x)"
