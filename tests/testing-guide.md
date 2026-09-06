# Sieve — Testing Guide

Last updated: 2026-09-06

---

## Surfaces to test

| Surface | How to test |
|---|---|
| Daemon (watcher + processor + snapshot_writer + heartbeat) | Start it against a project, verify cache populates, commit, verify snapshot |
| `cs` CLI (`skeleton`, `repo-map`, `diff`) | Run each subcommand with `--json` and inspect output |
| MCP server (`sieve_find`, `sieve_file`) | Configure in `.claude/settings.json`, ask Claude a structural question |

---

## Path reference

```bash
SIEVE=/path/to/sieve
PROJECT=/path/to/your/project   # the codebase you want to index
```

---

## Quick start

### 1. Install

```bash
cd $SIEVE
bash install.sh
```

Creates `.venv/`, installs dependencies (tree-sitter grammars, `watchdog`, `pydantic`, `mcp`), initializes `ledger.db`. No model download, no GPU.

### 2. Start the daemon

```bash
source .venv/bin/activate  # or .venv/Scripts/activate on Windows
python src/main.py $PROJECT
```

Expected log lines:
```
Sieve daemon starting — watching /path/to/project
Watcher active
Processor started — root: ..., N gitignore pattern(s)
Snapshot writer started
```

### 3. Trigger initial cache build

Save any supported file (`.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.md`, `.go`, `.rs`) under `$PROJECT`, or touch an existing one. Wait a few seconds.

Verify the cache:
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('$PROJECT/ledger.db')
cc = conn.execute('SELECT COUNT(*) FROM context_cache').fetchone()[0]
si = conn.execute('SELECT COUNT(*) FROM symbol_index').fetchone()[0]
print(f'context_cache: {cc}  |  symbol_index: {si}')
"
```

---

## Automated tests

```bash
cd $SIEVE
python3 -m pytest tests/ -v --tb=short
```

| File | What it covers |
|---|---|
| `test_skeleton.py` | AST stripping — Python, JS, TS, Markdown, Go, Rust (27) |
| `test_determinism.py` | Byte-identical index across reruns; `PYTHONHASHSEED` cross-process; AST-hash gate (26) |
| `test_mcp.py` | MCP scoring logic, keyword extraction, stemming (26) |
| `test_json_api.py` | `cs` JSON output shape — skeleton, repo-map, diff (8) |
| `test_benchmark.py` | Reduction + semantic preservation, 3 languages (7) |
| `test_cli.py` | `cs` subcommand dispatch, JSON round-trip, ledger discovery (8) |
| `test_snapshot_writer.py` | Commit-queue consumer writes structural snapshots (4) |
| `test_watcher_commit.py` | Reflog-based commit detection; non-commit events ignored (4) |
| `test_integration.py` | Token reduction >70% on a 60-file synthetic project (1) |

Total: 111. Benchmark method and measured numbers: [`../docs/benchmarks.md`](../docs/benchmarks.md).

---

## CLI smoke tests

Run these with the daemon online and the cache populated. `cs` finds the
project's `ledger.db` by walking up from the current directory, so run these
from inside `$PROJECT` (or pass `cs --db $PROJECT/ledger.db ...`).

### `cs repo-map`

```bash
cd $PROJECT
cs repo-map --json | jq '.files | length'
```

Expected: a positive integer matching your non-ignored, non-test source file count.

### `cs skeleton`

```bash
cs skeleton src/some/file.py --json | jq '.dependencies'
```

Expected: `{ "imports": [...], "imported_in": [...] }`. `imported_in` lists files whose `references` column points at this file's dotted module name.

### `cs diff`

```bash
# Make a trivial signature change to any tracked file, then commit.
git commit -am "test: signature change"
cs diff --json | jq '.changes'
```

Expected: non-empty `changes` array with `added` / `removed` / `modified` keys per affected file.

---

## MCP smoke test

1. Register the server in `$PROJECT/.claude/settings.json`:
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

2. Open Claude Code in `$PROJECT`.

3. Ask a structural question:
   > Which files handle the file-watching logic in this codebase?

**Expected:** Claude calls `sieve_find` and names the correct files (e.g. `watcher.py`, `processor.py`) from the returned XML — zero additional `Grep`/`Read` calls.

Verify the server starts standalone:
```bash
cd $SIEVE
python3 -m src.mcp.server $PROJECT/ledger.db
```

---

## Fresh-Claude validation (the Step-4 goal)

This is the end-to-end test for whether the JSON payload is information-complete.

```bash
cd $PROJECT
cs repo-map --json > /tmp/repo_map.json
cs skeleton src/daemon/watcher.py --json > /tmp/watcher.json
```

Open a fresh Claude session (no prior context). Paste both files. Ask:

> Based only on this structural payload, tell me what would break across the codebase if I removed `start_watcher` from `src/daemon/watcher.py`.

**Pass:** Claude names the importers using only `dependencies.imported_in` data, without asking for raw file contents.

**Fail:** Claude hedges or asks for source. If so, inspect the JSON for missing edges and trace back through `src/layers/json_api.py` and the reverse-edge `LIKE` query.

---

## Edge cases

| Edge case | How to trigger | Expected result |
|---|---|---|
| File > `MAX_FILE_SIZE_KB` | Write a file larger than the configured limit | Daemon skips it silently |
| Syntax error in `.py` | Save `def foo(:` | Falls back to SHA-256 hash; no crash |
| Rapid saves (10× in 2s) | Loop `touch file.py` | AST-hash gate fires; skeletonize/summarize run once |
| File deleted while watching | `rm file.py` while daemon runs | No crash |
| Gitignored file | Add to `.gitignore`, save it | Indexed as `is_ignored=1`, not processed |
| `git commit` / `--amend` | Commit or amend | Snapshot attaches to the new commit hash (reflog is read post-ref-move) |
| `git checkout` / `reset` | Switch or move HEAD | No snapshot — only `commit` reflog entries trigger the writer |

---

## Daemon log messages

| Message | Meaning |
|---|---|
| `AST unchanged — no re-summary` | Comment/whitespace edit — skeletonize/summarize skipped |
| `Cache updated` | Structural change processed |
| `Snapshot written for commit <hash>` | snapshot_writer consumed a commit event |
| `Shutdown signal received — processor exiting` | Clean Ctrl+C shutdown |

---

## Graceful shutdown

```bash
# Start the daemon, save several files rapidly, then:
Ctrl+C
```

Expected: `Shutdown signal received — daemon stopped`. Verify DB integrity:
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('$PROJECT/ledger.db')
print(conn.execute('PRAGMA integrity_check').fetchone()[0])
"
```

Expected: `ok`.
