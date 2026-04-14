# TASK-07 API — bin/sieve-hook

## Invocation

```sh
bin/sieve-hook [--mode=prompt|compact]
```

| Flag | Description |
|---|---|
| `--mode=prompt` | **UserPromptSubmit** — injects skeleton context before the user's prompt (default) |
| `--mode=compact` | **PostCompact** — re-injects full architectural skeleton after context compaction |

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success, fail-fast fallback, or `!full` bypass — always safe to continue |
| non-zero | Unrecoverable error (abnormal process failure only; never raised intentionally) |

## Stdout Format

### When daemon is alive (prompt mode)
```
### src/foo/bar.py
<skeleton text>

### src/baz/qux.py
<skeleton text>
```
Each file section is a `### <relative-path>` header followed by the cached skeleton from `context_cache`.

### When daemon is alive (compact mode)
```
[sieve] architectural skeleton re-injection (post-compact)

### src/foo/bar.py
<skeleton text>
...
```

### When daemon is offline (both modes)
```
[sieve] daemon offline — file-tree heuristic

  src/foo/bar.py
  src/baz/qux.ts
  ...
```
Source files (`.py`, `.js`, `.ts`, `.tsx`, `.jsx`) up to `MAX_DEPTH` directories deep.

### When images are present in `~/.claude/image-cache/`
Image toast blocks are appended after skeleton/heuristic output:
```
[image: screenshot.png]
• detected text line one
• detected text line two
```

### Empty ledger
```
[sieve] no cached skeletons in ledger
```

## Inputs

### Command-line flags
- `--mode=prompt` (default) or `--mode=compact`

### Environment variables
| Variable | Purpose |
|---|---|
| `SIEVE_PROMPT` | If value starts with `!full `, hook exits 0 immediately (bypass) |

### Stdin
If stdin is a pipe (not TTY), the hook reads a JSON payload looking for `{"prompt": "..."}`.
If the prompt starts with `!full `, hook exits 0 immediately.
Read has a 5 ms timeout via `select.select` — never blocks.

### Filesystem
| Path | Read |
|---|---|
| `ledger.db` | SQLite WAL-mode DB: `daemon_heartbeat`, `ledger`, `context_cache` tables |
| `config/sieve.config.toml` | `thresholds.MAX_DEPTH` (fallback depth; read via `tomllib`) |
| `~/.claude/image-cache/` | PNG/JPG/BMP/TIFF images for OCR processing |

## STALE_THRESHOLD

The daemon-liveness threshold is `30.0` seconds, matching `src.daemon.heartbeat.STALE_THRESHOLD`.
The hook reads it inline via a raw `sqlite3` query (`SELECT * FROM daemon_heartbeat WHERE id=1`)
without importing the `src.daemon.heartbeat` module, to avoid asyncio import overhead on the fast path.

## Fail-Fast Guarantees

- **DB locked**: `Ledger` raises `LedgerError` (500 ms busy_timeout) → hook falls back to heuristic and exits 0.
- **Daemon stale**: heartbeat timestamp > 30 s old → skip DB entirely, run heuristic, exit 0.
- **Image OCR fails**: `extract_text()` returns `""`, `to_toast()` returns `"(no content)"` → silently omitted.
- **Config unreadable**: `tomllib` failure → `MAX_DEPTH` defaults to `3`.

## Performance Notes

- `_t0 = time.perf_counter()` is set before any import.
- A warning is printed to **stderr** if elapsed > 40 ms (approaching the 50 ms hard limit).
- All `src.*` imports are deferred behind the daemon-alive guard so the offline fallback path uses only stdlib.
- On native Linux with local NVMe, the offline path runs in ~15–25 ms. WSL2 + Windows filesystem incurs ~150–250 ms due to filesystem overhead.
