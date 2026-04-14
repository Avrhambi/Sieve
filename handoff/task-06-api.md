# TASK-06 API — Background Daemon (Watcher & Processor)

## Public symbols

---

### `src.daemon.watcher`

#### `start_watcher(root: Path) -> Coroutine`

Watches *root* recursively for file-save events using a watchdog `Observer`
thread.  Changed files are filtered by:

- `.gitignore` patterns loaded from `root/.gitignore` at startup
- Supported extension whitelist: `.py .js .ts .jsx .tsx .md .markdown`

Matching paths are pushed onto the shared `asyncio.Queue[Path]` via
`loop.call_soon_threadsafe` (thread-safe bridge from watchdog's OS thread
into the running asyncio event loop).  Never returns while the daemon is
alive; cleans up the Observer on cancellation.

#### `get_queue() -> asyncio.Queue[Path]`

Returns the module-level queue shared with `processor.py`.  Both
`start_watcher` (producer) and `start_processor` (consumer) use this same
object.

---

### `src.daemon.processor`

#### `process_file(path: Path) -> Coroutine`

Processes a single changed file.  Decision tree:

1. **Extension not supported or file gone** → returns immediately.
2. **RAM or VRAM below threshold** (read from `sieve.config.toml`) → logs and
   returns; the file is dropped from this cycle (it will reappear on the next
   actual save).
3. **File exceeds `MAX_FILE_SIZE_KB`** → skipped.
4. **AST hash unchanged** — for `.py` files the stdlib `ast` module is used
   (comments absent from the AST); for other types the skeletonized output is
   hashed.  When hash matches the stored value, only the `mtime` column is
   refreshed — `summarize()` is **not** called.
5. **Hash changed or new file** — `skeletonize()` + `summarize()` are called,
   then `ledger.upsert_file()` and `ledger.upsert_cache()` are called to
   update both tables.

Never raises; all errors are caught and logged.

#### `start_processor(root: Path) -> Coroutine`

Continuously consumes the shared queue produced by `start_watcher`.  Before
each dequeue the resource governors are checked; if either RAM or VRAM is
below the configured threshold, the processor sleeps `_RESOURCE_POLL_INTERVAL`
(5 s) and retries until resources recover.  `root` is accepted for API
symmetry with `start_watcher` but is unused.

---

### `src.daemon.heartbeat`

#### `start_heartbeat(db_path: Path = ..., interval: float = 10.0) -> Coroutine`

Ticks a Unix timestamp into the `daemon_heartbeat` table in `ledger.db` every
`interval` seconds.  The table schema is created on first write (no schema
migration needed).  Write failures are caught and logged; the coroutine never
raises.

#### `read_heartbeat(db_path: Path = ...) -> float | None`

Returns the last heartbeat timestamp, or `None` if the daemon has never run.
Used by the hook to decide whether the daemon is alive:

```python
import time
from src.daemon.heartbeat import read_heartbeat, STALE_THRESHOLD

ts = read_heartbeat()
daemon_alive = ts is not None and (time.time() - ts) < STALE_THRESHOLD
```

`STALE_THRESHOLD = 30.0` seconds.  A timestamp older than this (or absent)
indicates the daemon is down.
