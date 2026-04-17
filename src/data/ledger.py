"""SQLite WAL-mode data ledger for Sieve."""
import json
import sqlite3
from pathlib import Path
from typing import Optional

from src.main import load_config

_DB_PATH = Path(__file__).parent.parent.parent / "ledger.db"
_LOCK_TIMEOUT_MS = 500


def set_db_path(path: Path) -> None:
    """Override the default ledger.db location (called by main before startup)."""
    global _DB_PATH
    _DB_PATH = path


def _get_db_path() -> Path:
    return _DB_PATH


class LedgerError(RuntimeError):
    """Raised when the ledger is locked beyond the timeout threshold."""


def _connect(db_path: Path = _DB_PATH) -> sqlite3.Connection:
    """Open a WAL-mode connection.  Raises LedgerError if the DB is locked
    for longer than 500 ms."""
    conn = sqlite3.connect(str(db_path), timeout=_LOCK_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=500")
        conn.execute("PRAGMA foreign_keys=ON")
    except sqlite3.OperationalError as exc:
        conn.close()
        raise LedgerError(f"DB locked or unavailable: {exc}") from exc
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ledger (
            path       TEXT PRIMARY KEY,
            mtime      REAL NOT NULL,
            ast_hash   TEXT NOT NULL,
            is_ignored INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS context_cache (
            file_id  TEXT NOT NULL REFERENCES ledger(path) ON DELETE CASCADE,
            skeleton TEXT,
            summary  TEXT,
            PRIMARY KEY (file_id)
        );

        CREATE TABLE IF NOT EXISTS symbol_index (
            symbol_name TEXT NOT NULL,
            source_file TEXT NOT NULL,
            "references" TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (symbol_name, source_file)
        );

        CREATE TABLE IF NOT EXISTS daemon_heartbeat (
            id  INTEGER PRIMARY KEY,
            ts  REAL    NOT NULL
        );
        """
    )
    conn.commit()


class Ledger:
    """Persistent storage for file hashes, skeletons, and symbol references.

    All writes use WAL mode so readers are never blocked by an ongoing write.
    Raises LedgerError if the database is locked for >500 ms.

    Config keys read:
        (none — storage path and lock timeout are fixed constants)
    """

    def __init__(self, db_path: Path = None) -> None:
        if db_path is None:
            db_path = _DB_PATH
        self._db_path = db_path
        self._conn = _connect(db_path)
        _init_schema(self._conn)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # ledger table
    # ------------------------------------------------------------------

    def upsert_file(
        self,
        path: str,
        mtime: float,
        ast_hash: str,
        is_ignored: bool = False,
    ) -> None:
        """Insert or replace a file record in the ledger table."""
        self._conn.execute(
            """
            INSERT INTO ledger (path, mtime, ast_hash, is_ignored)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                mtime      = excluded.mtime,
                ast_hash   = excluded.ast_hash,
                is_ignored = excluded.is_ignored
            """,
            (path, mtime, ast_hash, int(is_ignored)),
        )
        self._conn.commit()

    def get_file(self, path: str) -> Optional[sqlite3.Row]:
        """Return the ledger row for *path*, or None if not present."""
        return self._conn.execute(
            "SELECT * FROM ledger WHERE path = ?", (path,)
        ).fetchone()

    def delete_file(self, path: str) -> None:
        """Remove a file record (cascades to context_cache)."""
        self._conn.execute("DELETE FROM ledger WHERE path = ?", (path,))
        self._conn.commit()

    # ------------------------------------------------------------------
    # context_cache table
    # ------------------------------------------------------------------

    def upsert_cache(
        self,
        file_id: str,
        skeleton: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> None:
        """Store or update the skeleton/summary for a file."""
        self._conn.execute(
            """
            INSERT INTO context_cache (file_id, skeleton, summary)
            VALUES (?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
                skeleton = excluded.skeleton,
                summary  = excluded.summary
            """,
            (file_id, skeleton, summary),
        )
        self._conn.commit()

    def get_cache(self, file_id: str) -> Optional[sqlite3.Row]:
        """Return the context_cache row for *file_id*, or None."""
        return self._conn.execute(
            "SELECT * FROM context_cache WHERE file_id = ?", (file_id,)
        ).fetchone()

    # ------------------------------------------------------------------
    # symbol_index table
    # ------------------------------------------------------------------

    def upsert_symbol(
        self,
        symbol_name: str,
        source_file: str,
        references: list[str],
    ) -> None:
        """Store or update a symbol and the files that reference it.

        *references* is a list of file paths and is serialised as JSON.
        """
        self._conn.execute(
            """
            INSERT INTO symbol_index (symbol_name, source_file, "references")
            VALUES (?, ?, ?)
            ON CONFLICT(symbol_name, source_file) DO UPDATE SET
                "references" = excluded."references"
            """,
            (symbol_name, source_file, json.dumps(references)),
        )
        self._conn.commit()

    def get_symbol(
        self, symbol_name: str, source_file: str
    ) -> Optional[sqlite3.Row]:
        """Return the symbol_index row, or None."""
        return self._conn.execute(
            "SELECT * FROM symbol_index WHERE symbol_name = ? AND source_file = ?",
            (symbol_name, source_file),
        ).fetchone()

    def get_references(self, symbol_name: str, source_file: str) -> list[str]:
        """Return the deserialized references list for a symbol."""
        row = self.get_symbol(symbol_name, source_file)
        if row is None:
            return []
        return json.loads(row["references"])  # noqa: RUF100

    def write_heartbeat(self, ts: float) -> None:
        """Upsert the daemon liveness timestamp."""
        self._conn.execute(
            "INSERT INTO daemon_heartbeat (id, ts) VALUES (1, ?)"
            " ON CONFLICT(id) DO UPDATE SET ts=excluded.ts",
            (ts,),
        )
        self._conn.commit()

    def get_files_under(self, path_prefix: str) -> list[sqlite3.Row]:
        """Return all non-ignored ledger rows whose path starts with path_prefix."""
        prefix = path_prefix.rstrip("/") + "/"
        return self._conn.execute(
            "SELECT path FROM ledger WHERE path LIKE ? AND is_ignored = 0 ORDER BY path",
            (prefix + "%",),
        ).fetchall()
