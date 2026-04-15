# Sieve

Intelligent context-filtering and multimodal hook system for [Claude Code](https://claude.ai/code). Reduces token usage by 70–90% via AST skeletonization, OCR-to-text conversion, and local LLM inference — all running on local hardware with no cloud dependencies.

## How It Works

Sieve sits between your files and Claude's context window:

1. **Background daemon** watches for file saves and pre-computes AST skeletons using `py-tree-sitter`
2. **CLI hook** intercepts every `UserPromptSubmit` event, fetches cached skeletons from SQLite, and injects them as context — in under 50ms
3. **OCR pipeline** converts screenshots in `~/.claude/image-cache/` into compact bulleted "Toasts" via RapidOCR (no VRAM required)
4. **Local inference** summarizes files using Ollama / Qwen2.5-Coder-1.5B, with automatic fallback to regex heuristics when resources are low
5. **MCP server** exposes on-demand deep queries: multi-hop dependency graphs and frontend-to-backend route matching

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com) installed and running
- Hardware tested on: i5 / 16GB RAM / MX350 2GB VRAM (WSL2 supported)

## Installation

```bash
bash install.sh
```

The script will:
- Create a Python virtual environment (`.venv/`)
- Install all dependencies via pip
- Pull `qwen2.5-coder:1.5b` via Ollama
- Initialize the SQLite WAL database (`ledger.db`)

## Usage

**Start the daemon:**
```bash
python3 src/main.py
```

The daemon watches your project, keeps the skeleton cache warm, and ticks a heartbeat every 10 seconds. The Claude Code hooks fire automatically on every prompt.

**Manual override — bypass Sieve for one prompt:**
```
!full path/to/file.py
```

**Deep context via MCP:**
```bash
python3 -m src.mcp.server
```
Exposes `get_multi_hop_dependencies(path)` and `match_api_route(path_literal)` as MCP tools.

## Configuration

Edit `config/sieve.config.toml`:

| Key | Default | Description |
|---|---|---|
| `VRAM_THRESHOLD_MB` | `500` | Min free VRAM before forcing CPU inference |
| `RAM_THRESHOLD_MB` | `1000` | Min free RAM before pausing LLM batches |
| `MAX_FILE_SIZE_KB` | `100` | Files larger than this are skipped |
| `MAX_DEPTH` | `3` | Directory traversal depth for fallback heuristic |
| `OLLAMA_NUM_PARALLEL` | `1` | Max concurrent Ollama requests |

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
├── visual/
│   ├── ocr_pipeline.py   # RapidOCR image → structured text
│   └── toaster.py        # Text → bulleted Structural Toast
├── layers/
│   └── logic_tracing.py  # Static call-graph with circular-dep detection
├── mcp/
│   └── server.py         # MCP tools via FastMCP
└── main.py               # Daemon entry point
bin/
└── sieve-hook            # Claude Code hook (<50ms, fail-fast)
```

## Performance

| Metric | Target | Measured |
|---|---|---|
| Hook latency (cached) | < 50ms | ~15–25ms (native Linux) |
| Token reduction | > 70% | ~93% on 60-file synthetic project |
| Concurrent DB access | 0 SQLITE_BUSY errors | ✓ WAL mode |

> **WSL2 note:** Windows filesystem overhead adds ~150ms to hook latency. The 50ms target applies to native Linux.

## Tests

```bash
pytest tests/test_skeleton.py -v       # AST stripping unit tests
pytest tests/test_ledger.py -v         # SQLite WAL concurrency tests
pytest tests/test_integration.py -v    # Latency + token reduction benchmarks
```

## License

MIT
