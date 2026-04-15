# Sieve

**Sieve** reduces LLM context by 90% while preserving meaning — a structural compression layer for Claude Code that runs entirely on local hardware.

Most codebases sent to Claude are padded with implementation noise: function bodies, comments, boilerplate. Sieve strips all of that down to signatures and docstrings before Claude ever sees the file. A background daemon watches your project and keeps a precomputed skeleton cache in SQLite; a Claude Code hook reads from that cache in under 50ms on every prompt. The result is that Claude gets a structurally accurate picture of your codebase at a fraction of the token cost, with no round-trip to any external service.

## How It Works

1. **Daemon starts and watches your project.** `src/main.py` launches three async coroutines: a file watcher, a processor, and a heartbeat. The watcher uses `watchdog` to pick up file-save events and filters them by extension (`.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.md`) and `.gitignore` rules before queuing them for processing.

2. **Each changed file is skeletonized.** The processor computes an AST hash of the file. If the hash matches what is already stored, no LLM call is made — a reformatted file or a comment edit is a no-op. If the structure has changed, `skeletonizer.py` strips function bodies using `tree-sitter`, keeping only signatures, decorators, and docstrings. Markdown files are reduced to headers and links.

3. **A one-sentence summary is generated locally.** After skeletonization, `inference.py` picks a tier: instant regex heuristics for short files or when resources are constrained, `Qwen2.5-Coder-1.5B` via Ollama for everything else, and a silent fallback to heuristics if Ollama is unreachable. No VRAM is required.

4. **Results are stored in SQLite WAL mode.** The skeleton and summary are written to `ledger.db`. WAL mode means the hook can read while the processor writes simultaneously — no `SQLITE_BUSY` errors, no blocking.

5. **The hook injects context on every Claude prompt.** `bin/sieve-hook` fires on every `UserPromptSubmit` event. It reads the skeleton cache for all files under the current working directory and prepends them as context before Claude sees the user's prompt. If the daemon is offline, the hook falls back to a directory tree heuristic and continues without error.

## Quick Start

```bash
bash install.sh
```

The script creates a virtual environment, installs dependencies, pulls `qwen2.5-coder:1.5b` via Ollama, and initializes `ledger.db`.

Start the daemon:

```bash
python3 src/main.py
```

That's it. Sieve injects context automatically on every Claude prompt.

## What You Get

| | Without Sieve | With Sieve |
|---|---|---|
| What Claude receives | Full file contents | Signatures + docstrings only |
| Tokens per file (avg) | ~1,000 | ~70 |
| Token reduction | — | ~93% on a 60-file project |
| Hook latency (cached) | — | ~15–25ms (native Linux) |

> **WSL2 note:** Windows filesystem overhead adds ~150ms to hook latency. The 50ms target applies to native Linux.

## Configuration

Edit `config/sieve.config.toml`:

| Key | Default | Description |
|---|---|---|
| `VRAM_THRESHOLD_MB` | `500` | Min free VRAM before forcing CPU inference |
| `RAM_THRESHOLD_MB` | `1000` | Min free RAM before pausing LLM batches |
| `MAX_FILE_SIZE_KB` | `100` | Files larger than this are skipped |
| `MAX_DEPTH` | `3` | Directory traversal depth for fallback heuristic |
| `OLLAMA_NUM_PARALLEL` | `1` | Max concurrent Ollama requests |

## Override: send a full file

```
!full path/to/file.py
```

Prefix any prompt with `!full` followed by a file path to bypass skeletonization for that one prompt. Claude receives the complete file contents. The hook exits immediately without touching the cache.

## Deep Context: MCP Tools

```bash
python3 -m src.mcp.server
```

Two tools are available via FastMCP over stdio transport.

`get_multi_hop_dependencies(path)` traces the full import graph for a given file, recursing through the `symbol_index` table in `ledger.db`. It detects circular dependencies and annotates them rather than looping. Use this when Claude needs to understand a module's full blast radius before a refactor.

`match_api_route(path_literal)` looks up a URL fragment against the symbol index and returns the handler function and source file that owns that route. Use this to connect a frontend path to its backend implementation without manually searching the codebase.

## Architecture

```
src/
├── core/
│   ├── skeletonizer.py   # Tree-sitter AST stripping (Python, JS/TS, Markdown)
│   ├── inference.py      # Tiered inference: heuristic -> Ollama -> fallback
│   └── registry.py       # Extension -> tree-sitter grammar mapping
├── daemon/
│   ├── watcher.py        # watchdog file-save events + .gitignore filter
│   ├── processor.py      # Batch processing + RAM/VRAM governors
│   └── heartbeat.py      # Liveness ticking for hook awareness
├── data/
│   └── ledger.py         # SQLite WAL interface (ledger, context_cache, symbol_index)
├── visual/
│   ├── ocr_pipeline.py   # RapidOCR image -> structured text
│   └── toaster.py        # Text -> bulleted Structural Toast
├── layers/
│   └── logic_tracing.py  # Static call-graph with circular-dep detection
├── mcp/
│   └── server.py         # MCP tools via FastMCP
└── main.py               # Daemon entry point
bin/
└── sieve-hook            # Claude Code hook (<50ms, fail-fast)
```

## Tests

```bash
pytest tests/test_skeleton.py -v       # AST stripping unit tests
pytest tests/test_ledger.py -v         # SQLite WAL concurrency tests
pytest tests/test_integration.py -v    # Latency + token reduction benchmarks
```

## License

MIT
