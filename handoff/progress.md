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
