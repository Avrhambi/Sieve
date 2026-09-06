"""Tests for src.cli — invoked in-process to share the test ledger fixture."""
import io
import json
from contextlib import redirect_stdout

import pytest

from src.cli import main
from src.data.ledger import Ledger, set_db_path


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    set_db_path(tmp_path / "ledger.db")
    monkeypatch.setenv("SIEVE_DB", str(tmp_path / "ledger.db"))
    yield tmp_path


def _seed_basic(root) -> None:
    f = root / "foo.py"
    with Ledger() as l:
        l.upsert_file(str(f), 1.0, "h", is_ignored=False)
        l.upsert_cache(str(f), "skel-blob", "summary")
        l.upsert_symbol("alpha", str(f), ["json"], "def alpha()")
        l.upsert_symbol("_private", str(f), ["json"], "def _private()")


def _capture(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(argv)
    return rc, buf.getvalue()


class TestCli:
    def test_repo_map_json_lists_public_symbols(self, ledger, monkeypatch):
        _seed_basic(ledger)
        monkeypatch.chdir(ledger)
        rc, out = _capture(["repo-map", "--json"])
        assert rc == 0
        payload = json.loads(out)
        assert len(payload["files"]) == 1
        names = [s["name"] for s in payload["files"][0]["public_interface"]]
        assert names == ["alpha"]  # _private excluded

    def test_skeleton_json_for_known_file(self, ledger):
        _seed_basic(ledger)
        f = str(ledger / "foo.py")
        rc, out = _capture(["skeleton", f, "--json"])
        assert rc == 0
        payload = json.loads(out)
        assert payload["file"] == f.replace("\\", "/")
        assert payload["skeleton"] == "skel-blob"
        names = sorted(s["name"] for s in payload["symbols"])
        assert names == ["_private", "alpha"]

    def test_skeleton_unindexed_file_returns_nonzero(self, ledger):
        _seed_basic(ledger)  # ledger exists; missing.py is simply not in it
        rc, _ = _capture(["skeleton", "missing.py", "--json"])
        assert rc == 1

    def test_db_flag_overrides_discovery(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SIEVE_DB", raising=False)
        dbfile = tmp_path / "custom-ledger.db"
        set_db_path(dbfile)
        f = tmp_path / "bar.py"
        with Ledger() as l:
            l.upsert_file(str(f), 1.0, "h", is_ignored=False)
            l.upsert_cache(str(f), "skel", "sum")
            l.upsert_symbol("gamma", str(f), ["json"], "def gamma()")
        monkeypatch.chdir(tmp_path)  # no ledger.db here — discovery would miss
        rc, out = _capture(["--db", str(dbfile), "repo-map", "--json"])
        assert rc == 0
        payload = json.loads(out)
        assert [s["name"] for s in payload["files"][0]["public_interface"]] == ["gamma"]

    def test_cwd_walk_up_discovers_ledger(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SIEVE_DB", raising=False)
        set_db_path(tmp_path / "ledger.db")
        f = tmp_path / "baz.py"
        with Ledger() as l:
            l.upsert_file(str(f), 1.0, "h", is_ignored=False)
            l.upsert_cache(str(f), "skel", "sum")
            l.upsert_symbol("delta", str(f), ["json"], "def delta()")
        nested = tmp_path / "sub" / "dir"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)
        rc, out = _capture(["skeleton", str(f), "--json"])
        assert rc == 0
        assert json.loads(out)["skeleton"] == "skel"

    def test_missing_ledger_exits_nonzero_without_creating_db(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("SIEVE_DB", raising=False)
        monkeypatch.chdir(tmp_path)
        rc = main(["repo-map", "--json"])
        assert rc == 1
        assert "ledger not found" in capsys.readouterr().err
        assert not (tmp_path / "ledger.db").exists()

    def test_diff_no_snapshots_succeeds_with_error_field(self, ledger):
        _seed_basic(ledger)
        rc, out = _capture(["diff", "--json"])
        assert rc == 0
        payload = json.loads(out)
        assert payload["error"] == "no snapshots"

    def test_skeleton_text_renders(self, ledger):
        _seed_basic(ledger)
        f = str(ledger / "foo.py")
        rc, out = _capture(["skeleton", f])
        assert rc == 0
        assert "def alpha()" in out
