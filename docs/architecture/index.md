<!-- reviewed-at: ce1da13 -->
<!-- covers: src/ -->

# Sieve architecture

## System overview

Sieve is a daemon-backed, fully offline code index. A `watchdog` observer notices
files that change on disk, an async processor skeletonizes each changed file
(strips function bodies, keeps signatures and docstrings), writes a one-line
deterministic summary and a symbol list into a SQLite ledger, and a git-commit
hook triggers point-in-time structural snapshots. Consumers — the `cs` CLI, the
`json_api` layer, and the MCP server's `sieve_find` / `sieve_file` tools — read
that ledger while the processor keeps writing to it (WAL mode). There is no LLM,
no network, and no subprocess in the indexing path: every stage is a pure
function of the input bytes, so the same repository state always produces a
byte-identical index (enforced by `tests/test_determinism.py`).

## Components

| Module | Responsibility |
| --- | --- |
| `src/main.py` | Daemon entry point; wires the 4 async tasks, points the ledger + heartbeat at `<root>/ledger.db`, owns `_shutdown_event`. |
| `src/config.py` | Loads `config/sieve.config.toml` into a pydantic `SieveConfig` (thresholds like `MAX_FILE_SIZE_KB`). |
| `src/daemon/watcher.py` | `watchdog` observer thread; filters by extension + `.gitignore`; bridges sync events onto the asyncio file queue; detects commits via the `.git/logs/HEAD` reflog (read after the ref moves, so the hash is the new commit) → pushes short hash onto the commit queue. |
| `src/daemon/processor.py` | Consumes the file queue; AST-hash gate; runs skeletonize → summarize → extract-symbols; upserts `ledger` / `context_cache` / `symbol_index`. |
| `src/daemon/snapshot_writer.py` | Consumes the commit queue; copies current `symbol_index` rows into `structural_snapshots` keyed by commit hash. |
| `src/daemon/heartbeat.py` | Writes a liveness timestamp to `daemon_heartbeat` every 10 s; `read_heartbeat()` lets hooks detect a dead daemon. |
| `src/core/skeletonizer.py` | `skeletonize(source: bytes, language: str) -> str`. Tree-sitter for py/js/ts/go/rust/markdown, with a line-regex fallback per language. No I/O. (The `registry.py:22` comment claiming markdown is regex-only is stale.) |
| `src/core/inference.py` | `summarize(source: str, language: str) -> str`. Pure 3-tier heuristic (docstring → symbol names → snippet line count). No LLM. |
| `src/core/registry.py` | Maps file extension → tree-sitter `Language` object. |
| `src/data/ledger.py` | `Ledger` class over a WAL-mode SQLite DB; `set_db_path()` sets a module global. All 5 tables + schema migration live here. |
| `src/layers/json_api.py` | Read-side query layer: `get_file_skeleton_json`, `get_repo_map_json`, `get_diff_json` (signature changes vs the latest snapshot). |
| `src/mcp/server.py` | MCP tools `sieve_find` (lexical search) and `sieve_file` (skeleton by path). |
| `src/mcp/scoring.py` | Keyword/stem extraction and the `_score()` function used by `sieve_find`. |
| `src/cli.py` | `cs` CLI: `skeleton`, `repo-map`, `diff` subcommands (text or `--json`). Resolves the project's `ledger.db` at startup (`--db` flag → `$SIEVE_DB` → walk up from cwd) and calls `set_db_path` before dispatch; exits non-zero if none is found. |

## Data flow

```
                         ┌─────────────────────────────────────────┐
  file save on disk ───▶ │ watcher (watchdog thread)                │
                         │  • ext filter + .gitignore filter       │
                         │  • call_soon_threadsafe → file queue    │
                         └───────────────┬─────────────────────────┘
                                         │ asyncio.Queue[Path]
                                         ▼
                         ┌─────────────────────────────────────────┐
                         │ processor.process_file                  │
                         │  1. ext supported? exists? not ignored? │
                         │  2. size <= MAX_FILE_SIZE_KB            │
                         │  3. _compute_ast_hash(source, ext)      │
                         │     unchanged ─▶ refresh mtime, stop    │
                         │  4. skeletonize → summarize → symbols   │
                         └───────────────┬─────────────────────────┘
                                         │  upsert
                                         ▼
                         ┌─────────────────────────────────────────┐
                         │ ledger.db  (SQLite, WAL)                 │
                         │  ledger · context_cache · symbol_index  │
                         │  daemon_heartbeat · structural_snapshots│
                         └───────────────┬─────────────────────────┘
                                         │ read (concurrent)
                         ┌───────────────┴───────────────┐
                         ▼                               ▼
                  cs CLI / json_api             MCP: sieve_find / sieve_file

  git commit ─▶ watcher sees .git/logs/HEAD (reflog) ─▶ commit queue (asyncio.Queue[str])
             ─▶ snapshot_writer._write_snapshot(hash) ─▶ structural_snapshots
```

## Detail files

- [pipeline.md](pipeline.md) — the daemon: the 4 async tasks, the AST-hash gate,
  the deterministic skeletonize → summarize → extract-symbols flow, gitignore
  filtering, the commit-queue path.
- [data-model.md](data-model.md) — the SQLite WAL schema: every table and column,
  what `symbol_index.references` stores, snapshot keying, WAL concurrency.

## Known trade-offs / rough edges

These are deliberate v1 choices, not bugs — but they are real limits.

- **Module-global mutable state used as IPC.** `src.main._shutdown_event`,
  `heartbeat._DB_PATH`, `processor._gitignore_patterns` / `_repo_root`, and the
  `ledger._DB_PATH` global (set via `set_db_path`) are process-wide singletons.
  This keeps the wiring tiny but means two daemons cannot run in one process and
  tests must reset `set_db_path` per case.
- **No startup backfill.** The daemon only indexes files that *change* while it
  is running. A file that already exists and is never touched is never indexed;
  there is no initial repo walk.
- **`sieve_find` is lexical.** It matches query keywords/stems against file paths
  and symbol names, with a hard silence gate: any candidate scoring `< 1.0` is
  dropped. Indirect / conceptual queries ("where do we handle auth") return
  nothing rather than a guess.
- **JS/TS signatures are `NULL`.** Only Python gets structured signatures
  (reconstructed via `ast.unparse`). JS/TS symbol extraction is regex-based and
  stores `signature = None`; go/rust/markdown extract no symbols at all.
- **Forward edges only.** `symbol_index.references` stores the *imports* of a
  symbol's source file. Reverse edges ("who imports me") are derived at query
  time with a `LIKE '%module%'` scan in `json_api`, which is approximate.
- **Go/Rust index skeletons but not symbols.** The daemon skeletonizes and
  summarizes `.go` / `.rs` files, so they appear in `sieve_find` / `sieve_file`
  and `cs skeleton` output. But `_extract_symbols` is Python/JS-only, so Go and
  Rust contribute no `symbol_index` rows — no signatures, no import edges, and
  they never surface in `cs repo-map` or `cs diff`.
