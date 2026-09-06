# Sieve

**A deterministic, offline code index.** A daemon watches one project, strips every
changed file to a skeleton — signatures and docstrings, no bodies — writes a
one-line deterministic summary and a symbol list into SQLite, and serves ranked
structural search to the `cs` CLI and an MCP server. No model, no network, no
subprocess in the indexing path: the same repository state always produces a
**byte-identical** index (enforced by a test suite, see [Testing](#testing--resilience)).

## Problem

An LLM coding agent exploring an unfamiliar codebase burns tokens on `Grep` →
`Read` round-trips, pulling whole file bodies to recover a handful of signatures
and import edges. The bodies are noise for "what is the shape of this module and
who depends on it" questions.

Sieve pre-digests the tree into that structural layer once, incrementally, on
file save. A query returns ranked skeletons plus the import graph instead of raw
files. Measured on this repo's own source, a skeleton is **58% smaller** than the
file (character count); on body-heavy code it reaches **74.8–88.9%** — see
[`docs/benchmarks.md`](docs/benchmarks.md).


## Architecture

```
                         ┌──────────────────────────────────────────┐
  file save on disk ───▶ │ watcher (watchdog thread)                │
                         │  • extension + .gitignore filter         │
                         │  • call_soon_threadsafe → file queue     │
                         └───────────────┬──────────────────────────┘
                                         │ asyncio.Queue[Path]
                                         ▼
                         ┌──────────────────────────────────────────┐
                         │ processor.process_file                   │
                         │  1. supported ext? exists? not ignored?  │
                         │  2. size ≤ MAX_FILE_SIZE_KB              │
                         │  3. AST-structure hash unchanged ─▶ stop │
                         │  4. skeletonize → summarize → symbols    │
                         └───────────────┬──────────────────────────┘
                                         │ upsert
                                         ▼
                         ┌──────────────────────────────────────────┐
                         │ ledger.db  (SQLite, WAL)                  │
                         │  ledger · context_cache · symbol_index   │
                         │  daemon_heartbeat · structural_snapshots │
                         └───────────────┬──────────────────────────┘
                                         │ concurrent reads
                         ┌───────────────┴───────────────┐
                         ▼                               ▼
                  cs CLI / json_api             MCP: sieve_find / sieve_file

  git commit ─▶ watcher sees .git/logs/HEAD (reflog) ─▶ commit queue
             ─▶ snapshot_writer copies symbol_index → structural_snapshots (keyed by hash)
```

| Module | Responsibility |
|---|---|
| `src/main.py` | Daemon entry point; wires 4 async tasks, points the ledger at `<root>/ledger.db`. |
| `src/config.py` | Loads `config/sieve.config.toml` → pydantic `SieveConfig`. |
| `src/daemon/watcher.py` | `watchdog` observer; extension + `.gitignore` filter; commit detection via the `.git/logs/HEAD` reflog (post-ref-move, so the hash is correct). |
| `src/daemon/processor.py` | Queue consumer; AST-hash gate; `skeletonize → summarize → extract-symbols`; SQLite upserts. |
| `src/daemon/snapshot_writer.py` | On each commit hash, freezes current signatures into `structural_snapshots`. |
| `src/daemon/heartbeat.py` | Liveness timestamp every 10s so hooks can detect a dead daemon. |
| `src/core/skeletonizer.py` | `skeletonize(source: bytes, language) -> str`. Tree-sitter for py/js/ts/go/rust/markdown, line-regex fallback per language. No I/O. |
| `src/core/inference.py` | `summarize(source, language) -> str`. Pure 3-tier heuristic (docstring → symbol names → line count). No LLM. |
| `src/core/registry.py` | Extension → tree-sitter `Language`. |
| `src/data/ledger.py` | `Ledger` over WAL-mode SQLite. All 5 tables + additive migration. |
| `src/layers/json_api.py` | Read-side query layer for `cs` (skeleton, repo-map, diff). |
| `src/mcp/server.py` | MCP tools `sieve_find` (lexical search), `sieve_file` (skeleton by path). |
| `src/mcp/scoring.py` | Keyword/stem extraction and `_score()`. |
| `src/cli.py` | `cs` CLI: `skeleton`, `repo-map`, `diff` (text or `--json`). |

Detailed design: [`docs/architecture/`](docs/architecture/) — `index.md` (map),
`pipeline.md` (the daemon), `data-model.md` (the SQLite schema).

## Design trade-offs

- **Deterministic 3-tier `summarize` vs an LLM.** Lost: a summary that reads
  intent ("retries the reservation with exponential backoff"). Gained: zero cost,
  zero latency, byte-reproducible, no dependency. Tier 1 takes the first sentence
  of the docstring/leading comment; tier 2 lists top-level symbol names; tier 3 is
  `Short {lang} snippet ({n} lines)`.
- **`sieve_find` is lexical with a hard silence gate.** Query keywords (stemmed)
  are matched against file stems (+3) and symbol names (+2); any candidate
  scoring `< 1.0` is dropped. Second-degree importers of a hit are included at
  0.5×. An indirect query ("where do we handle auth") returns *nothing* rather
  than a plausible-looking guess — silence is a safer failure than a wrong file.
- **Forward edges only.** `symbol_index.references` stores the modules a symbol's
  *file* imports, duplicated onto every symbol row of that file. "Who imports me"
  is derived at query time with a `LIKE '%module%'` scan in `json_api` —
  unindexed and approximate, but there is no materialized reverse table to keep
  consistent at side-project scale.
- **Python-only structured signatures.** Python signatures are reconstructed via
  `ast.unparse`. JS/TS get symbol *names* only (regex, `signature = NULL`).
  Go/Rust are skeletonized and summarized (so they appear in `sieve_find` /
  `cs skeleton`) but contribute no `symbol_index` rows — no `cs repo-map` / `cs diff`.
- **Module-global state as IPC.** The shutdown event, the queues, the ledger
  db-path, and the gitignore patterns are process-wide singletons. Keeps the
  wiring tiny; the price is one daemon per process and per-test global resets.
- **No startup backfill.** The daemon indexes only files that *change* while it
  runs. A file never touched is never indexed — there is no initial repo walk.

## Testing & resilience

**`python -m pytest tests/ -q` → `111 passed` in ~1.9s.** (Windows 11, Python 3.14.)

- **Determinism suite** (`tests/test_determinism.py`, 26 tests — 25% of the
  suite). Runs the real pipeline over a multi-file project, dumps
  `context_cache` + `symbol_index`, **wipes the DB, reruns**, and asserts the two
  dumps are row-for-row equal (and stable over 3 repeats). Separately spawns
  subprocesses with `PYTHONHASHSEED=0` vs `1` to prove dict/set ordering never
  leaks into output.
- **AST-hash gate.** `_compute_ast_hash` digests `ast.dump(ast.parse(source))`
  for Python (comments and whitespace dropped) or the skeleton for other
  languages. A comment- or reformat-only edit yields the identical hash and
  `skeletonize` / `summarize` are skipped.
- **SQLite WAL.** Readers (`cs`, `json_api`, MCP) never block the processor and
  are never blocked by it. `busy_timeout=500` + a 0.5s connect timeout; a writer
  stuck longer raises `LedgerError`, which the daemon catches-and-logs (file
  retried on next save) and CLI/MCP surface as an error result.
- **Reduction thresholds are enforced** (`test_benchmark.py`,
  `test_integration.py`): skeleton ≤ 30% of source for 3 languages, and > 70% on
  a synthetic 60-file project.

## Measured numbers

Every figure below is reproducible; full method and raw output in
[`docs/benchmarks.md`](docs/benchmarks.md). **Reduction figures are character
counts** (`len()` on text) — a proxy for token savings, not a tokenizer count.

| Metric | Value | Reproduce |
|---|---|---|
| Test suite | 111 passed, ~1.9s | `python -m pytest tests/ -q` |
| Determinism tests | 26 | `python -m pytest tests/test_determinism.py -q` |
| Skeleton reduction, this repo's `src/` (14 files) | 58.0% (char) | `python docs/bench/bench.py` |
| Skeleton reduction, body-heavy code | 74.8–88.9% (char) | `PYTHONIOENCODING=utf-8 python -m pytest tests/test_benchmark.py::test_reduction_summary -s -o addopts=""` |
| Skeleton reduction, synthetic 60-file project | 86.4% (`len/4` token proxy) | `PYTHONIOENCODING=utf-8 python -m pytest tests/test_integration.py -s -o addopts=""` |
| Index throughput | ~50–60 files/sec (~17–20 ms/file), best of 3 | `python docs/bench/bench.py` |
| Index reproducibility | byte-identical across wipe-and-rerun | `pytest tests/test_determinism.py::TestEndToEndPipelineDeterminism -q` |

## Quick start

```bash
bash install.sh
```

Creates `.venv/`, installs dependencies (tree-sitter grammars, `watchdog`,
`pydantic`, `mcp`), initializes `ledger.db`. No model download, no GPU.

Start the daemon against your project:

```bash
source .venv/bin/activate   # .venv/Scripts/activate on Windows
python src/main.py /path/to/your/project
```

The `cs` CLI is a console script (`pyproject.toml`). After `pip install -e .`:

```bash
cd /path/to/your/project   # cs walks up from here to find the project's ledger.db
cs repo-map --json | jq '.files[].file'
```

From outside the project, pass `cs --db /path/to/your/project/ledger.db ...`
(or set `$SIEVE_DB`). If no ledger is found, `cs` exits non-zero and tells you
to start the daemon.

## CLI

| Command | Output |
|---|---|
| `cs skeleton <file> --json` | Per-file symbols, signatures, import edges (forward + reverse-derived) |
| `cs repo-map --json` | Public-interface map of the indexed project |
| `cs diff --json` | Signature-level changes vs the latest commit snapshot |

Without `--json`, each prints a terse one-line-per-symbol rendering.

```bash
# Who imports this file before I change its interface?
cs skeleton src/daemon/watcher.py --json | jq '.dependencies.imported_in'

# Signature-level changes before pushing
cs diff --json | jq '.changes'
```

## MCP setup

Register in your project's `.claude/settings.json`:

```json
{
  "mcpServers": {
    "sieve": {
      "command": "python3",
      "args": ["-m", "src.mcp.server", "/path/to/project/ledger.db"],
      "cwd": "/path/to/sieve"
    }
  }
}
```

`sieve_find(query)` returns ranked skeletons + second-degree importers (0.5×
score); `sieve_file(path)` returns one cached skeleton. Both read `ledger.db`
directly — no daemon call.

## Configuration

`config/sieve.config.toml`:

| Key | Default | Description |
|---|---|---|
| `MAX_FILE_SIZE_KB` | `100` | Files larger than this are skipped (no ledger row). |

## Known limitations

- **`sieve_find` has a lexical ceiling.** Queries whose words don't appear in
  filenames or symbol names return nothing (by design — see Trade-offs).
- **JS/TS signatures are `NULL`; Go/Rust have no symbols.** `cs repo-map` /
  `cs diff` are Python-only.
- **No startup backfill** — only files changed while the daemon runs get indexed.
- **Commit snapshots need the reflog.** Detection reads `.git/logs/HEAD`,
  which git appends *after* the ref moves — so the snapshot always attaches to
  the new commit (the old `COMMIT_EDITMSG` off-by-one, including on `--amend`,
  is resolved). A repo with `core.logAllRefUpdates=false` has no reflog; the
  watcher falls back to reading `HEAD` directly and the old race reappears.

## Roadmap

- [ ] **JS/TS signature extraction** — replace regex with tree-sitter.
- [ ] **Go/Rust symbol extraction** — so they reach `cs repo-map` / `cs diff`.
- [ ] **Materialized reverse-edge table** — if the `LIKE` scan becomes a
  bottleneck on larger trees.

An embedding-backed semantic search behind `sieve_find` is a *possible* future
direction, but it would trade away the determinism and zero-dependency
properties that are the point of the current design.

## License

MIT
