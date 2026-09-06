# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What Sieve is

A deterministic, offline code index. A daemon watches one project; on each file
save it strips the changed file to a skeleton (signatures + docstrings, no
bodies), writes a one-line heuristic summary and a symbol list into SQLite, and
serves ranked structural search to the `cs` CLI and an MCP server. No model, no
network, no subprocess in the indexing path.

## Commands

```bash
bash install.sh                       # create .venv/, install deps, init ledger.db
source .venv/Scripts/activate         # .venv/bin/activate on Linux/Mac
pip install -e .                      # exposes the `cs` console script

python -m pytest tests/ -q            # full suite (~111 tests, ~2s)
python -m pytest tests/test_determinism.py -q          # the determinism guarantee
python -m pytest tests/test_skeleton.py::test_name -q  # single test

# Benchmarks print to stdout, so they disable output capture explicitly:
PYTHONIOENCODING=utf-8 python -m pytest tests/test_benchmark.py::test_reduction_summary -s -o addopts=""
python docs/bench/bench.py            # throughput + reduction on this repo's src/

python src/main.py /path/to/project   # run the daemon against a project
```

No lint or typecheck config is set up in this repo.

Packaging is Poetry (`pyproject.toml`), but `install.sh` installs into a plain
`.venv/` with pip — use it rather than `poetry install`. Python 3.11+.

## Architecture — the big picture

Data flows one direction: **filesystem event → queue → `process_file` → SQLite →
read-side query layers.** `src/main.py` wires four async tasks (watcher,
processor, snapshot_writer, heartbeat) sharing module-global queues.

- `src/daemon/watcher.py` — `watchdog` observer. Extension + `.gitignore` filter.
  Commit detection reads `.git/logs/HEAD` (the reflog), **not** `COMMIT_EDITMSG`
  or `HEAD` — git appends to the reflog *after* moving the ref, so the hash is
  correct (see `docs/lessons.md`).
- `src/daemon/processor.py` — queue consumer. Gate order: supported ext → exists
  → not ignored → size ≤ `MAX_FILE_SIZE_KB` → **AST-structure hash unchanged ⇒
  skip**. Then `skeletonize → summarize → extract-symbols → upsert`.
- `src/core/skeletonizer.py`, `src/core/inference.py` — pure functions, no I/O.
  `summarize` is a 3-tier heuristic (docstring sentence → symbol names → line
  count), never an LLM.
- `src/data/ledger.py` — `Ledger` over WAL-mode SQLite, 5 tables, additive
  migration. Read-side callers (`cs`, MCP) read `ledger.db` directly; no daemon
  call.
- `src/layers/json_api.py`, `src/cli.py` — the `cs` CLI (`skeleton`, `repo-map`,
  `diff`).
- `src/mcp/server.py` — MCP tools `sieve_find` (lexical search), `sieve_file`
  (skeleton by path).

Detailed design: `docs/architecture/` (`index.md`, `pipeline.md`,
`data-model.md`). Post-incident notes: `docs/lessons.md` — read before debugging.

## Invariants that constrain changes

- **Determinism is the product.** The same repository state must produce a
  byte-identical index. Nothing in the indexing path may depend on dict/set
  iteration order, hash randomization, wall-clock time, file mtime, or
  environment. `tests/test_determinism.py` (26 tests) wipes the DB, reruns the
  real pipeline, and asserts row-for-row equality, plus subprocess runs with
  `PYTHONHASHSEED=0` vs `1`. A change that breaks reproducibility is a failed
  test, not a judgement call.
- **The ledger path is module-global.** `Ledger()` with no argument resolves to
  `src/data/ledger.py`'s `_DB_PATH`. `cli.py` and the MCP server call
  `set_db_path()` at startup to point it at the *watched project's* `ledger.db`.
  `Ledger()` / `sqlite3.connect` creates the file on connect, so any "ledger
  missing" error path must check `path.is_file()` *before* constructing a
  `Ledger`.
- **Other module-global singletons** (shutdown event, queues, gitignore
  patterns) mean one daemon per process; tests reset them explicitly.
- **No startup backfill** — only files that change while the daemon runs get
  indexed. This is intentional; don't add a repo walk without discussing it.
- **Language coverage is uneven by design.** Python gets reconstructed
  signatures (`ast.unparse`). JS/TS get symbol *names* only (`signature = NULL`).
  Go/Rust are skeletonized/summarized but contribute no `symbol_index` rows, so
  they don't appear in `cs repo-map` / `cs diff`.
- **`sieve_find` is lexical with a hard silence gate** — candidates scoring
  `< 1.0` are dropped; an indirect query returns nothing rather than a plausible
  wrong file.
