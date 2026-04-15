"""Daemon heartbeat — writes a liveness timestamp to SQLite every N seconds.

The hook reads ``SELECT ts FROM daemon_heartbeat`` to detect whether the
daemon is alive.  A timestamp older than ``STALE_THRESHOLD`` seconds (or
absent) means the daemon is down.
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from pathlib import Path

from src.data.ledger import Ledger

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent.parent / "ledger.db"
_TICK_INTERVAL: float = 10.0       # seconds between ticks
STALE_THRESHOLD: float = 30.0      # seconds before a tick is considered stale


def _write_tick(db_path: Path) -> None:
    """Write current Unix timestamp into the single-row heartbeat table."""
    with Ledger(db_path) as ledger:
        ledger.write_heartbeat(time.time())


async def start_heartbeat(
    db_path: Path = _DB_PATH,
    interval: float = _TICK_INTERVAL,
) -> None:
    """Coroutine — tick a timestamp into SQLite every *interval* seconds.

    Never raises.  Write failures are logged as warnings so that the daemon
    keeps running even if the DB is temporarily locked.
    """
    logger.info("Heartbeat started (interval=%.0fs)", interval)
    while True:
        try:
            _write_tick(db_path)
            logger.debug("Heartbeat ticked")
        except Exception as exc:
            logger.warning("Heartbeat write failed: %s", exc)
        await asyncio.sleep(interval)


def read_heartbeat(db_path: Path = _DB_PATH) -> float | None:
    """Return the last heartbeat timestamp, or ``None`` if no tick recorded.

    Used by the hook to detect daemon liveness::

        ts = read_heartbeat()
        alive = ts is not None and (time.time() - ts) < STALE_THRESHOLD
    """
    try:
        conn = sqlite3.connect(str(db_path), timeout=0.5)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            row = conn.execute(
                "SELECT ts FROM daemon_heartbeat WHERE id = 1"
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return None
