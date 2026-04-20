"""Persists structural snapshots of the symbol_index on every git commit.

Consumes commit hashes from the watcher's ``_commit_queue`` and writes a
point-in-time copy of all current (filepath, symbol_name, signature) rows into
``structural_snapshots``.  ``cs diff --json`` reads the latest snapshot per
file to compute signature-level changes since the last commit.
"""
from __future__ import annotations

import asyncio
import logging
import time

from src.data.ledger import Ledger, LedgerError

logger = logging.getLogger(__name__)


async def start_snapshot_writer(commit_queue: asyncio.Queue[str]) -> None:
    """Consume commit hashes and write a structural snapshot for each."""
    logger.info("Snapshot writer started")
    while True:
        commit_hash = await commit_queue.get()
        try:
            _write_snapshot(commit_hash)
            logger.info("Snapshot written for commit %s", commit_hash)
        except LedgerError as exc:
            logger.warning("Snapshot ledger error for %s: %s", commit_hash, exc)
        except Exception:
            logger.exception("Snapshot write failed for %s", commit_hash)
        finally:
            commit_queue.task_done()


def _write_snapshot(commit_hash: str) -> None:
    snapshot_at = int(time.time())
    with Ledger() as ledger:
        rows = ledger._conn.execute(
            "SELECT symbol_name, source_file, signature FROM symbol_index"
        ).fetchall()
        if not rows:
            logger.debug("symbol_index is empty — skipping snapshot for %s", commit_hash)
            return
        ledger._conn.executemany(
            """
            INSERT OR IGNORE INTO structural_snapshots
                (commit_hash, filepath, symbol_name, signature, snapshot_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (commit_hash, r["source_file"], r["symbol_name"], r["signature"], snapshot_at)
                for r in rows
            ],
        )
        ledger._conn.commit()
