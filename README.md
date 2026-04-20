# Sieve

**Sieve** is a daemon-backed code index for a single project. It watches your source tree, strips every changed file to a skeleton (signatures + docstrings, no bodies), and exposes that index through two surfaces:

- **`cs` CLI** — structured JSON output for machine consumers (scripts, prompts, diff reviews)
- **MCP server** — ranked skeleton search callable from Claude Code


## What you get

| Surface | Use for |
|---|---|
| `cs skeleton <file> --json` | Per-file structured symbols + import edges (forward and reverse) |
| `cs repo-map --json` | Public-interface map of the whole indexed project |
| `cs diff --json` | Signature-level changes since the last commit — structural diff, no body noise |
| MCP `sieve_find(query)` | Ranked skeletons for a natural-language query, with second-degree import graph |
| MCP `sieve_file(path)` | Cached skeleton for a specific file — cheaper than `Read` |

## How it works

1. **Daemon watches your project.** `src/main.py` launches four async tasks: a `watchdog` file watcher, a processor, a snapshot writer, and a heartbeat. The watcher filters by extension (`.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.md`, `.go`, `.rs`) and `.gitignore` rules. It also routes `.git/COMMIT_EDITMSG` events to a separate commit queue.

2. **Each changed file is skeletonized.** The processor computes an AST hash. If the hash is unchanged (whitespace, comment, body edits), no LLM call is made. If structure changed, `skeletonizer.py` strips function bodies via `tree-sitter`, keeping signatures, decorators, and docstrings. Markdown files reduce to headers and links.

3. **Symbols and signatures are extracted.** For Python, `ast.unparse` rebuilds a one-line signature per def/class. Import edges are captured as forward references. JS/TS use regex (signatures punted for v1).

4. **A one-sentence summary is generated locally.** `inference.py` calls `qwen2.5-coder:1.5b` via Ollama if available, falls back to a regex heuristic otherwise.

5. **Every commit triggers a structural snapshot.** When `.git/COMMIT_EDITMSG` changes, the snapshot writer copies the current `symbol_index` into `structural_snapshots` keyed by commit hash. `cs diff` reads from this.

6. **All results land in a single SQLite WAL file.** `ledger.db` at the watched project root. CLI and MCP read from it concurrently without blocking the processor.

## Quick start

```bash
bash install.sh
```

Creates `.venv/`, installs dependencies, pulls `qwen2.5-coder:1.5b` via Ollama if present.

Start the daemon against your project:

```bash
source .venv/bin/activate
python src/main.py /path/to/your/project
```

The `cs` CLI is registered as a console script via `pyproject.toml`. After `pip install -e .` (or `poetry install`) it's on your PATH:

```bash
cd /path/to/your/project
cs repo-map --json | jq '.files[] | .path'
```

## CLI examples

**Before removing a symbol, see who imports the file:**
```bash
cs skeleton src/daemon/watcher.py --json | jq '.dependencies.imported_in'
```

**Audit the project's public surface in one shot:**
```bash
cs repo-map --json | jq '.files[] | {path, symbols: [.symbols[].name]}'
```

**Review signature-level changes before pushing:**
```bash
cs diff --json | jq '.changes'
```

Without `--json`, each subcommand prints a terse human-readable rendering — one line per symbol.

## MCP setup

Register the server in your project's `.claude/settings.json`:

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

Then in Claude Code, ask structural questions:

> Which files handle the file-watching logic?

Claude calls `sieve_find`, receives ranked skeletons + second-degree importers at 50% score, and answers without `Grep`/`Read` round-trips.

## Scoring

`sieve_find` uses the same lexical model as the original hook:

| Signal | Weight |
|---|---|
| Filename or stem matches a query keyword | +3 |
| A symbol in the file matches a query keyword | +2 |
| File is named in the prompt (focal bonus) | +10 |
| Silence gate (best score < 1.0) | return no matches |

Keywords are stemmed: "watching" matches "watcher.py", "retries" matches "retry".

## Architecture

```
src/
├── core/
│   ├── skeletonizer.py       # tree-sitter AST stripping (Python, JS, TS, Markdown, Go, Rust)
│   ├── inference.py          # Ollama → heuristic fallback
│   └── registry.py           # extension → tree-sitter grammar
├── daemon/
│   ├── watcher.py            # watchdog events + .gitignore filter + commit detection
│   ├── processor.py          # AST-hash gate, skeletonize, extract signatures
│   ├── snapshot_writer.py    # on commit, copy symbol_index → structural_snapshots
│   └── heartbeat.py          # liveness timestamp
├── data/
│   └── ledger.py             # SQLite WAL: ledger, context_cache, symbol_index, structural_snapshots
├── layers/
│   └── json_api.py           # pure JSON producers for cs
├── mcp/
│   └── server.py             # sieve_find + sieve_file via FastMCP
├── cli.py                    # cs dispatcher
└── main.py                   # daemon entry point
```

## Schema notes

- `symbol_index.references` stores **forward edges** (modules the source file imports), despite the name. Reverse direction is derived on-demand via JSON `LIKE` in `json_api.py` — no materialized `imported_in` table at side-project scale.
- `symbol_index.signature` — Python signatures via `ast.unparse`; `NULL` for JS/TS.
- `structural_snapshots` — point-in-time signatures keyed by `commit_hash`.

## Configuration

Edit `config/sieve.config.toml`:

| Key | Default | Description |
|---|---|---|
| `VRAM_THRESHOLD_MB` | `0` | Pause inference if free VRAM drops below this |
| `RAM_THRESHOLD_MB` | `0` | Pause inference if available RAM drops below this |
| `MAX_FILE_SIZE_KB` | `100` | Skip files larger than this |
| `OLLAMA_NUM_PARALLEL` | `1` | Max concurrent Ollama requests |

## Tests

```bash
pytest tests/ -v --tb=short
```

| File | What it covers |
|---|---|
| `test_skeleton.py` | AST stripping — Python, JS, TS, Markdown |
| `test_integration.py` | Token reduction >70% on a 60-file synthetic project |
| `test_benchmark.py` | Reduction + semantic preservation, 3 languages |
| `test_mcp.py` | MCP scoring, keyword extraction, stemming |
| `test_json_api.py` | `cs` JSON output shape |
| `test_snapshot_writer.py` | Commit-queue consumer |
| `test_cli.py` | `cs` dispatcher and JSON round-trip |

For manual smoke tests and the fresh-Claude validation, see [`tests/testing-guide.md`](tests/testing-guide.md).

## Known limitations

- **JS/TS signatures are `NULL`.** Python only for v1. `cs diff` and `cs repo-map` carry signatures for Python files; others get names only.
- **`git commit --amend` race.** `COMMIT_EDITMSG` fires before `HEAD` updates, so a snapshot taken during an amend may lag by one commit.
- **Lexical ceiling on `sieve_find`.** Indirect queries ("which file handles rate limiting?") miss when filenames and symbols don't contain query words.

## Roadmap

- [ ] **Embedding index** — semantic search behind `sieve_find` via `nomic-embed-text`. Same interface, no lexical ceiling.
- [ ] **JS/TS signature extraction** — replace regex with tree-sitter.
- [ ] **MCP wrappers for `cs`** — once the JSON schema is validated end-to-end.

## License

MIT
