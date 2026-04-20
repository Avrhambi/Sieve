"""Tests for src.daemon.snapshot_writer."""
import asyncio

import pytest

from src.daemon.snapshot_writer import _write_snapshot, start_snapshot_writer
from src.data.ledger import Ledger, set_db_path


@pytest.fixture
def ledger(tmp_path):
    set_db_path(tmp_path / "ledger.db")
    yield


def _seed_symbols() -> None:
    with Ledger() as l:
        l.upsert_symbol("alpha", "src/foo.py", ["json"], "def alpha()")
        l.upsert_symbol("Beta", "src/foo.py", ["json"], "class Beta()")


def _snapshot_rows(commit_hash: str) -> list[tuple]:
    with Ledger() as l:
        return l._conn.execute(
            "SELECT filepath, symbol_name, signature FROM structural_snapshots "
            "WHERE commit_hash = ? ORDER BY symbol_name",
            (commit_hash,),
        ).fetchall()


class TestWriteSnapshot:
    def test_writes_one_row_per_symbol(self, ledger):
        _seed_symbols()
        _write_snapshot("commit01")
        rows = _snapshot_rows("commit01")
        assert len(rows) == 2
        names = sorted(r["symbol_name"] for r in rows)
        assert names == ["Beta", "alpha"]

    def test_empty_symbol_index_writes_nothing(self, ledger):
        _write_snapshot("commitXX")
        assert _snapshot_rows("commitXX") == []

    def test_idempotent_for_same_commit(self, ledger):
        _seed_symbols()
        _write_snapshot("commit02")
        _write_snapshot("commit02")  # second call must not duplicate
        rows = _snapshot_rows("commit02")
        assert len(rows) == 2


class TestStartSnapshotWriter:
    def test_consumes_one_commit(self, ledger):
        _seed_symbols()
        queue: asyncio.Queue[str] = asyncio.Queue()

        async def run():
            queue.put_nowait("commit03")
            task = asyncio.create_task(start_snapshot_writer(queue))
            await queue.join()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run())
        rows = _snapshot_rows("commit03")
        assert len(rows) == 2
