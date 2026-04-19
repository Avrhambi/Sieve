# Sieve

**Sieve** is a structural context layer for Claude Code — a local daemon that pre-digests your codebase into skeletons (signatures + docstrings, no bodies) and exposes them through two delivery mechanisms: a prompt hook that injects relevant files automatically, and an MCP server that Claude can query on demand.

## How It Works

1. **Daemon watches your project.** `src/main.py` launches a file watcher, a processor, and a heartbeat. The watcher uses `watchdog` to pick up file-save events, filtered by extension (`.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.md`) and `.gitignore` rules.

2. **Each changed file is skeletonized.** The processor computes an AST hash. If the hash matches what is stored, no LLM call is made — a reformatted file is a no-op. If the structure changed, `skeletonizer.py` strips function bodies using `tree-sitter`, keeping only signatures, decorators, and docstrings. Markdown files reduce to headers and links.

3. **A one-sentence summary is generated locally.** `inference.py` selects a tier: instant regex heuristics for short or resource-constrained cases, `Qwen2.5-Coder-1.5B` via Ollama otherwise, silent fallback to heuristics if Ollama is unreachable. No VRAM required.

4. **Results are stored in SQLite WAL mode.** Skeleton and summary go into `ledger.db`. WAL mode lets the hook read while the processor writes — no `SQLITE_BUSY` errors.

5. **The hook selectively injects on every prompt.** `bin/sieve-hook` fires on every `UserPromptSubmit` event. It scores all cached files against the prompt using keyword and symbol overlap, then injects only the top-scoring skeleton (up to 1,500 chars). If the best score is below 1.0, it stays silent. If the daemon is offline, it falls back to a file-tree listing.

## Quick Start

```bash
bash install.sh
```

The script creates a virtual environment, installs dependencies, pulls `qwen2.5-coder:1.5b` via Ollama, and initializes `ledger.db`.

Start the daemon against your project:

```bash
python3 src/main.py /path/to/your/project
```

That's it. The hook fires automatically on every Claude prompt.

## What You Get

| | Without Sieve | With Sieve |
|---|---|---|
| What Claude receives | Nothing, then tool calls | Pre-scored skeleton for the most relevant file |
| Token reduction (skeleton vs raw) | — | ~74% (validated on 386K char codebase) |
| Hook latency (cached) | — | ~15–25ms (native Linux) |
| Tool calls for architecture questions | 2–4 (Search + Read) | 0–2 (hook narrows to right file) |

> **WSL2 note:** Windows filesystem overhead adds ~150ms to hook latency. The 50ms target applies to native Linux.

## Scoring

The hook and MCP server share the same scoring model:

| Signal | Weight |
|---|---|
| Filename or stem matches a query keyword | +3 |
| A symbol in the file matches a query keyword | +2 |
| File is named in the prompt (focal bonus) | +10 |
| Silence gate (best score < 1.0) | inject nothing |

Keywords are stemmed — "watching" matches "watcher.py", "retries" matches "retry".

## Override: inject a full file

```
@full path/to/file.py
```

Prefix any prompt with `@full` followed by a file path to bypass skeletonization for that one prompt. Claude receives the complete file contents with zero tool calls.

## MCP Tools

Register the MCP server in your project's `.claude/settings.json`:

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

Two tools are available:

**`sieve_find(query, max_results=5)`** — Searches the codebase for files related to a concept. Returns ranked skeletons (signatures + docstrings) ordered by relevance. Uses the same keyword/symbol scoring as the hook, plus import graph traversal: files that import a top hit are included at 50% score. Much cheaper than Grep+Read — one call returns structured understanding instead of raw lines.

**`sieve_file(path)`** — Returns the cached skeleton for a specific file. Use this when you already know which file you want but don't need the full source. Lower token cost than Read.

If the daemon is offline or a file hasn't been processed yet, both tools return a clear error rather than silently failing.

## PostCompact Recovery

After `/compact` wipes conversation context, Sieve re-injects an architectural map — a compact one-liner-per-file listing of classes and key functions. This fires automatically via the `PostCompact` hook and fits within Claude Code's inline limit (~1.2KB), so Claude recovers structural awareness with zero tool calls.

## Architecture

```
src/
├── core/
│   ├── skeletonizer.py   # Tree-sitter AST stripping (Python, JS/TS, Markdown)
│   ├── inference.py      # Tiered inference: heuristic → Ollama → fallback
│   └── registry.py       # Extension → tree-sitter grammar mapping
├── daemon/
│   ├── watcher.py        # watchdog file-save events + .gitignore filter
│   ├── processor.py      # Batch processing + RAM/VRAM governors
│   └── heartbeat.py      # Liveness ticking for hook awareness
├── data/
│   └── ledger.py         # SQLite WAL interface (ledger, context_cache, symbol_index)
├── mcp/
│   └── server.py         # sieve_find + sieve_file via FastMCP
└── main.py               # Daemon entry point
bin/
└── sieve-hook            # Claude Code hook (<50ms, fail-fast)
```

## Configuration

Edit `config/sieve.config.toml`:

| Key | Default | Description |
|---|---|---|
| `VRAM_THRESHOLD_MB` | `500` | Min free VRAM before forcing CPU inference |
| `RAM_THRESHOLD_MB` | `1000` | Min free RAM before pausing LLM batches |
| `MAX_FILE_SIZE_KB` | `100` | Files larger than this are skipped |
| `MAX_DEPTH` | `3` | Directory traversal depth for fallback heuristic |
| `OLLAMA_NUM_PARALLEL` | `1` | Max concurrent Ollama requests |

## Tests

```bash
pytest tests/test_skeleton.py -v       # AST stripping unit tests
pytest tests/test_integration.py -v   # Latency + token reduction benchmarks
```

## License

MIT
