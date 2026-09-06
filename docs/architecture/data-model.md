<!-- reviewed-at: ce1da13 -->
<!-- covers: src/data/ledger.py, src/daemon/snapshot_writer.py -->

# Data model

One SQLite file per watched repo: `<root>/ledger.db` (plus `-wal` / `-shm`
sidecars). `src/data/ledger.py` owns the schema, the connection, and every
write. `src/daemon/snapshot_writer.py` owns writes to `structural_snapshots`.

## Connection & pragmas

`_connect(db_path)` opens with `sqlite3.connect(..., timeout=0.5)` and sets, on
every connection:

- `PRAGMA journal_mode=WAL` — readers never block the writer and vice versa.
- `PRAGMA busy_timeout=500` — plus the 0.5 s connect timeout; a lock held longer
  raises `LedgerError` (`class LedgerError(RuntimeError)`).
- `PRAGMA foreign_keys=ON` — makes the `context_cache` cascade real.

`row_factory = sqlite3.Row`. `_init_schema` runs `CREATE TABLE IF NOT EXISTS`
for all five tables on every `Ledger()` construction, then an idempotent
additive migration: if `symbol_index` lacks a `signature` column (checked via
`PRAGMA table_info`), `ALTER TABLE ... ADD COLUMN signature TEXT`.

### The db-path global

Module global `_DB_PATH` defaults to `<repo>/ledger.db`. `set_db_path(path)`
rebinds it; `src/main.py` calls this at startup with `<root>/ledger.db`, and
also sets `heartbeat._DB_PATH` separately (the two globals are independent).
`src/cli.py` also calls it before dispatch, resolving the path via `--db` →
`$SIEVE_DB` → walking up from the cwd for a `ledger.db` (the daemon writes it
into the watched project, not the Sieve checkout).
`Ledger(db_path=None)` falls back to the current `_DB_PATH`. Tests must call
`set_db_path(tmp_path / "ledger.db")` per case. `_connect`'s own
`db_path=_DB_PATH` default arg is bound at import and is effectively dead —
`Ledger.__init__` always passes an explicit path.

## Tables

### `ledger` — one row per known file

| Column | Type | Notes |
| --- | --- | --- |
| `path` | TEXT PK | Normalized to forward slashes (`_norm`). Absolute on disk. |
| `mtime` | REAL NOT NULL | `path.stat().st_mtime` at last processing. Refreshed even when the AST hash is unchanged. |
| `ast_hash` | TEXT NOT NULL | 16-hex-char structural digest (see pipeline.md). The gate that decides whether to re-run skeletonize/summarize. |
| `is_ignored` | INTEGER NOT NULL DEFAULT 0 | `1` for files matched by `.gitignore`; content tables are not populated for them. |

`upsert_file` is `INSERT ... ON CONFLICT(path) DO UPDATE`. `delete_file`
cascades to `context_cache`.

### `context_cache` — skeleton + summary per file

| Column | Type | Notes |
| --- | --- | --- |
| `file_id` | TEXT PK | `REFERENCES ledger(path) ON DELETE CASCADE`. |
| `skeleton` | TEXT | Body-stripped source from `skeletonize`. |
| `summary` | TEXT | One-line deterministic summary from `summarize`. |

`upsert_cache` upserts on `file_id`. Written only on the full-pipeline branch
(new file or changed `ast_hash`).

### `symbol_index` — one row per (symbol, file)

| Column | Type | Notes |
| --- | --- | --- |
| `symbol_name` | TEXT NOT NULL | Part of composite PK. Bare function/class/method name — not dotted or qualified. Two symbols with the same name in the **same file** (e.g. two classes that each define `add`) collapse to one row, last-write-wins; different files keep distinct rows. |
| `source_file` | TEXT NOT NULL | Normalized path; part of composite PK. |
| `"references"` | TEXT NOT NULL DEFAULT '[]' | JSON array — reserved word, always quoted in SQL. **File-level import list**, duplicated onto every symbol row of that file. See below. |
| `signature` | TEXT (added by migration) | Python: reconstructed via `ast.unparse` (`def f(x: int) -> str`, `class C(Base)`). **JS/TS: always `NULL`.** go/rust/markdown: no rows at all. |

PK `(symbol_name, source_file)`. `upsert_symbol` upserts both `"references"` and
`signature`. `get_references` deserializes the JSON.

#### What `references` actually stores

It is the set of **modules the symbol's *file* imports** — forward edges, and
file-scoped, not symbol-scoped. For Python it is `ast` `Import` /
`ImportFrom.module` names (dotted, e.g. `src.core.skeletonizer`, `json`,
`collections`). For JS/TS it is the string literals from
`import ... from "..."`. Every symbol in the same file gets the identical list.

**Reverse edges are not stored.** `json_api.get_file_skeleton_json` derives
"who imports this file" at query time: it generates every dotted suffix of the
target file's module path (`src.daemon.watcher`, `daemon.watcher`, `watcher`)
via `_module_candidates`, then runs
`SELECT DISTINCT source_file FROM symbol_index WHERE "references" LIKE '%"<module>"%'`
for each. This is a substring scan — approximate, unindexed, and can false-match
on a coincidental name.

### `daemon_heartbeat` — single-row liveness

| Column | Type | Notes |
| --- | --- | --- |
| `id` | INTEGER PK | Always `1`. |
| `ts` | REAL NOT NULL | `time.time()` of the last tick (every 10 s). |

`write_heartbeat` upserts on `id=1`. `heartbeat.read_heartbeat()` reads it on a
throwaway connection; `alive = ts is not None and time.time() - ts < 30.0`.

### `structural_snapshots` — signatures frozen at a commit

| Column | Type | Notes |
| --- | --- | --- |
| `commit_hash` | TEXT NOT NULL | First 12 chars of the commit hash. Part of PK. |
| `filepath` | TEXT NOT NULL | = `symbol_index.source_file` at snapshot time. Part of PK. |
| `symbol_name` | TEXT NOT NULL | Part of PK. |
| `signature` | TEXT | Copied verbatim from `symbol_index.signature` (so `NULL` for JS/TS). |
| `snapshot_at` | INTEGER NOT NULL | `int(time.time())` when the snapshot was written. |

PK `(commit_hash, filepath, symbol_name)`. `_write_snapshot` does
`INSERT OR IGNORE ... executemany(...)` over a full `SELECT ... FROM symbol_index`,
so re-processing the same commit hash is a no-op. `get_diff_json` picks the
snapshot by `ORDER BY snapshot_at DESC LIMIT 1` (or an explicit hash) and diffs
its `{filepath: {symbol: signature}}` map against the live `symbol_index`,
emitting `added` / `removed` / `changed` per symbol.

## WAL concurrency in practice

The processor holds short-lived write transactions (each `upsert_*` calls
`commit()` immediately). The heartbeat writes every 10 s. Readers — the `cs`
CLI, `json_api`, and the MCP server — open their own connections and read
committed rows without blocking the writer; WAL means they also are not blocked
*by* the writer. The only failure mode is a writer stuck > 500 ms behind another
writer, which surfaces as `LedgerError` and is caught-and-logged in the daemon
(the file is retried on its next save) and surfaces to CLI/MCP callers as an
error result. There is no cross-process coordination beyond SQLite's own
locking; a stale `-wal` file from a hard-killed daemon is recovered by SQLite on
the next open.
