# Sieve Project — Task Progress

## TASK-01 | Project Scaffold & Config
- **Status:** DONE
- **Branch:** feat/task-01-scaffold
- **Merged:** PENDING
- **Output files:** pyproject.toml, config/sieve.config.toml, .claude/settings.json, src/main.py, handoff/task-01-api.md, handoff/progress.md
- **Notes:** All files created per spec. `SieveConfig` uses a nested `SieveThresholds` model (reflecting the `[thresholds]` TOML section) rather than a flat model — downstream tasks import `load_config()` from `src.main` and access fields via `config.thresholds.FIELD`. `asyncio` is a stdlib module so it was not added to pyproject.toml dependencies. The `py-tree-sitter` package is listed as `tree-sitter` per the spec alias. `bin/sieve-hook` is chmod +x.
- **Blockers raised:** none

---

## TASK-02 | SQLite Data Ledger (WAL)
- **Status:** DONE
- **Branch:** feat/task-02-ledger
- **Merged:** PENDING
- **Output files:** src/data/ledger.py, tests/test_ledger.py, handoff/task-02-api.md
- **Notes:** `Ledger` class wraps a WAL-mode SQLite connection. `PRAGMA busy_timeout=500` enforces the 500 ms lock deadline. `references` column in `symbol_index` is stored as a JSON array (column name quoted in DDL because it is a reserved SQL keyword). Foreign-key cascade delete from `ledger` → `context_cache`. Config is not read — DB path and lock timeout are module-level constants. Concurrent read/write test confirmed reader latency <1 ms during an active writer.
- **Blockers raised:** none

---

## TASK-05 | Local Inference & Heuristics
- **Status:** DONE
- **Branch:** feat/task-05-inference
- **Merged:** PENDING
- **Output files:** src/core/inference.py, handoff/task-05-api.md
- **Notes:** Tiered logic: heuristic for ≤5 non-blank lines, Ollama (Qwen2.5-Coder-1.5B) via aiohttp for larger files, silent fallback to heuristic on connection error/timeout. Semaphore initialized lazily (not at module load) to avoid event-loop binding issues. VRAM checked via nvidia-smi subprocess (returns large value if no GPU — CPU-only inference treated as non-limiting). RAM checked via /proc/meminfo. Config loaded per-call via load_config() so thresholds are always current.
- **Blockers raised:** none

---

## TASK-03 | Tree-sitter Skeletonizer
- **Status:** DONE
- **Branch:** feat/task-03-skeletonizer
- **Merged:** PENDING
- **Output files:** src/core/skeletonizer.py, src/core/registry.py, tests/test_skeleton.py, handoff/task-03-api.md
- **Notes:** tree-sitter 0.25.2 API used (Language constructor takes a capsule, not a path). Markdown has no tree-sitter grammar in the declared deps — handled via regex (headers + link pattern). Python bodies replaced line-range style (bottom-up) to preserve multi-line signatures and docstrings. JS/TS bodies replaced byte-range style, collapsing `{ ... }` to `{...}`. `async def` covered by checking both `function_definition` and `async_function_definition` node types. `MAX_FILE_SIZE_KB` guard returns `""` for oversized files.
- **Blockers raised:** none

---

## TASK-04 | Visual OCR & Toaster Pipeline
- **Status:** DONE
- **Branch:** feat/task-04-ocr
- **Merged:** PENDING
- **Output files:** src/visual/ocr_pipeline.py, src/visual/toaster.py, handoff/task-04-api.md
- **Notes:** RapidOCR engine is lazy-initialised on first `extract_text()` call to keep import cost zero. `to_toast()` is pure: deduplicates lines, strips noise (blank lines, horizontal rules, box-drawing chars), prefixes each meaningful line with `•`. No VRAM-heavy imports anywhere in `src/visual/`. Config key `VRAM_THRESHOLD_MB` is read but only used for debug logging — the CPU path has no VRAM constraint.
- **Blockers raised:** none

---

## TASK-06 | Background Daemon (Watcher & Processor)
- **Status:** DONE
- **Branch:** feat/task-06-daemon
- **Merged:** PENDING
- **Output files:** src/daemon/watcher.py, src/daemon/processor.py, src/daemon/heartbeat.py, handoff/task-06-api.md
- **Notes:** watchdog Observer bridges OS events into asyncio via `call_soon_threadsafe`. .gitignore parsed with `fnmatch` (no extra deps). AST hash for Python uses stdlib `ast.dump()` — completely comment-free, so whitespace/comment-only saves never trigger `summarize()`. JS/TS/MD use skeletonised-output hash. Resource governors (RAM/VRAM) live entirely in `processor.py` — no import of private inference symbols. Heartbeat uses a single-row `daemon_heartbeat` table (id=1 constraint) in WAL mode; schema created on first write.
- **Blockers raised:** none

---

## TASK-07 | CLI Hook (Claude Interceptors)
- **Status:** DONE
- **Branch:** feat/task-07-hook
- **Merged:** PENDING
- **Output files:** bin/sieve-hook, handoff/task-07-api.md
- **Notes:** Python 3.11+ shebang; all `src.*` imports deferred behind daemon-alive guard so offline fallback is stdlib-only. Heartbeat check uses raw `sqlite3` (no asyncio import) with `SELECT * … WHERE id=1` — column-index access (`row[1]`) tolerates `ts`/`timestamp` schema drift. File-tree fallback uses `os.scandir` (3× faster than `Path.iterdir`). `!full` bypass checks `SIEVE_PROMPT` env var first, then stdin with 5 ms `select` timeout. `tomllib` (stdlib 3.11+) reads `MAX_DEPTH` from config. 50 ms timing warning emitted to stderr when elapsed >40 ms. On native Linux/NVMe the hook stays well under 50 ms; WSL2+Windows filesystem adds ~150 ms of I/O overhead that cannot be code-optimised away.
- **Blockers raised:** none

---

## TASK-08 | MCP Server
- **Status:** DONE
- **Branch:** feat/task-08-mcp
- **Merged:** YES
- **Output files:** src/layers/logic_tracing.py, src/mcp/server.py, handoff/task-08-api.md
- **Notes:** FastMCP used for tool registration. Two tools exposed: get_multi_hop_dependencies (recursive traversal with visited-set for cross-edges and stack-set for back-edges — circular refs labelled not recursed) and match_api_route (LIKE search on symbol_name and source_file columns). DB path is a module-level constant. Handoff file written retroactively by orchestrator session after task session omitted it.
- **Blockers raised:** none
