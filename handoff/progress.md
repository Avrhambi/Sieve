# Sieve Project — Task Progress

## TASK-01 | Project Scaffold & Config
- **Status:** DONE
- **Branch:** feat/task-01-scaffold
- **Merged:** PENDING
- **Output files:** pyproject.toml, config/sieve.config.toml, .claude/settings.json, src/main.py, handoff/task-01-api.md, handoff/progress.md
- **Notes:** All files created per spec. `SieveConfig` uses a nested `SieveThresholds` model (reflecting the `[thresholds]` TOML section) rather than a flat model — downstream tasks import `load_config()` from `src.main` and access fields via `config.thresholds.FIELD`. `asyncio` is a stdlib module so it was not added to pyproject.toml dependencies. The `py-tree-sitter` package is listed as `tree-sitter` per the spec alias. `bin/sieve-hook` is chmod +x.
- **Blockers raised:** none
