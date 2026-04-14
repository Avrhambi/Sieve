# TASK-01 Public API

## Pydantic Config Model

**Module path:** `src.main`

### `SieveThresholds(BaseModel)`
| Field | Type |
|---|---|
| `VRAM_THRESHOLD_MB` | `int` |
| `RAM_THRESHOLD_MB` | `int` |
| `MAX_FILE_SIZE_KB` | `int` |
| `MAX_DEPTH` | `int` |
| `OLLAMA_NUM_PARALLEL` | `int` |

### `SieveConfig(BaseModel)`
| Field | Type |
|---|---|
| `thresholds` | `SieveThresholds` |

### `load_config(path: Path = CONFIG_PATH) -> SieveConfig`
Loads and validates `config/sieve.config.toml`. Import and call this to access thresholds.

---

## config/sieve.config.toml Keys

```toml
[thresholds]
VRAM_THRESHOLD_MB    # int — MB of VRAM before skipping inference
RAM_THRESHOLD_MB     # int — MB of RAM before skipping inference
MAX_FILE_SIZE_KB     # int — max file size to process
MAX_DEPTH            # int — max AST/directory depth
OLLAMA_NUM_PARALLEL  # int — parallel Ollama requests allowed
```

---

## Folder Structure

```
sieve/                          ← /workspace/repo
├── .claude/
│   └── settings.json
├── bin/
│   └── sieve-hook              ← empty stub, chmod +x
├── config/
│   └── sieve.config.toml
├── src/
│   ├── core/
│   │   ├── skeletonizer.py     ← empty stub
│   │   ├── inference.py        ← empty stub
│   │   └── registry.py         ← empty stub
│   ├── daemon/
│   │   ├── watcher.py          ← empty stub
│   │   ├── processor.py        ← empty stub
│   │   └── heartbeat.py        ← empty stub
│   ├── data/
│   │   └── ledger.py           ← empty stub
│   ├── visual/
│   │   ├── ocr_pipeline.py     ← empty stub
│   │   └── toaster.py          ← empty stub
│   ├── layers/
│   │   ├── library.py          ← empty stub
│   │   └── logic_tracing.py    ← empty stub
│   ├── mcp/
│   │   └── server.py           ← empty stub
│   └── main.py                 ← daemon entry point
├── tests/
│   ├── test_skeleton.py        ← empty stub
│   └── test_integration.py     ← empty stub
└── handoff/
    ├── progress.md
    └── task-01-api.md
```
