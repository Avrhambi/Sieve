# TASK-05 Public API

## Module path: `src.core.inference`

---

### `async summarize(source: str, language: str) -> str`

Returns a one-sentence summary of the given source code. Never raises an exception — falls back to heuristic if Ollama is unreachable.

**Parameters:**
- `source` — raw source code as a string
- `language` — language hint string (e.g. `"python"`, `"javascript"`, `"typescript"`)

**Tier selection (evaluated in order):**

| Tier | Condition | Behaviour |
|---|---|---|
| 1 — Heuristic | `source` has ≤ 5 non-blank lines | Regex extraction of top-level names; no LLM call |
| 1 — Resource guard | Available VRAM < `VRAM_THRESHOLD_MB` OR available RAM < `RAM_THRESHOLD_MB` | Same regex heuristic; Ollama skipped |
| 2 — Ollama | All other cases | Async HTTP POST to `http://localhost:11434/api/generate` with model `qwen2.5-coder:1.5b`, bounded by semaphore |
| 3 — Fallback | Ollama unreachable / timeout | Silently falls back to heuristic; no exception raised |

**Invariants for callers:**
- Always returns a non-empty string.
- Never raises — Ollama failure is caught internally.
- At most one concurrent Ollama request (semaphore = `OLLAMA_NUM_PARALLEL`).

---

### Config keys read

| Key | Purpose |
|---|---|
| `config.thresholds.VRAM_THRESHOLD_MB` | Skip Ollama if free VRAM is below this value |
| `config.thresholds.RAM_THRESHOLD_MB` | Skip Ollama if available RAM is below this value |
| `config.thresholds.OLLAMA_NUM_PARALLEL` | Semaphore limit on concurrent Ollama calls (always 1) |

---

### Internal helpers (not part of public API)

- `_heuristic_summary(source, language) -> str` — regex extraction, pure, no I/O
- `_ollama_summarize(source, language) -> Optional[str]` — async, semaphore-gated, returns `None` on failure
- `_available_ram_mb() -> int` — reads `/proc/meminfo`; returns large value on error
- `_available_vram_mb() -> int` — reads `nvidia-smi`; returns large value if no GPU
