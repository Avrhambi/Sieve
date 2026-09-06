<!-- reviewed-at: 88af1bb -->
<!-- covers: src/main.py, src/daemon/ -->

# The daemon pipeline

## The 4 async tasks

`src/main.py::start(root)` creates one `asyncio.Event` (`_shutdown_event`,
module global), points the ledger and heartbeat at `<root>/ledger.db`, then
launches four coroutines with `asyncio.create_task` and awaits the shutdown
event:

| Task | Source | Loop behaviour |
| --- | --- | --- |
| `start_watcher(root)` | `daemon/watcher.py` | Starts a `watchdog` `Observer` thread, then `await asyncio.sleep(1)` forever. On cancel: `observer.stop()` + `join()`. |
| `start_processor(root)` | `daemon/processor.py` | Loads `.gitignore` patterns once into module globals `_gitignore_patterns` / `_repo_root`; loops `queue.get()` with a 1 s `wait_for` timeout; checks `_main_module._shutdown_event` before and after each file. |
| `start_snapshot_writer(commit_queue)` | `daemon/snapshot_writer.py` | Blocking `await commit_queue.get()`; writes a snapshot per hash; never exits on its own (cancelled at shutdown). |
| `start_heartbeat(db_path)` | `daemon/heartbeat.py` | Every 10 s writes `time.time()` into `daemon_heartbeat` (id=1). Never raises — write failures are logged warnings. |

On Windows, `loop.add_signal_handler` is unavailable, so `SIGINT`/`SIGTERM` are
registered with `signal.signal` and a `call_soon_threadsafe` shim.

Shutdown: `_shutdown_event.wait()` returns → every task is `.cancel()`ed →
`asyncio.gather(*tasks, return_exceptions=True)`.

## Watcher → queue

`_SieveHandler` (a `watchdog.FileSystemEventHandler`) handles `on_modified` and
`on_created` for files (not directories). For each event `_enqueue(src_path)`:

1. **Commit signal.** If the path is `.git/logs/HEAD` (the reflog), read its
   last line — git appends it *after* the ref moves, format
   `<old> <new> <ident> <ts> <tz>\t<message>`. If `<message>` starts with
   `commit` (covers `commit:`, `commit (initial):`, `commit (amend):`), take
   field 2 (`<new>`), truncate to 12 chars, and
   `call_soon_threadsafe(commit_queue.put_nowait, hash)`. Non-commit reflog
   entries (`checkout:`, `reset:`, `merge …`) are ignored. Then return — the
   reflog never enters the file queue. Because the reflog is written post-move,
   the hash is always the new commit (the old `COMMIT_EDITMSG` off-by-one,
   `--amend` included, is resolved). Fallback: if `.git/logs/HEAD` can't be
   read (`core.logAllRefUpdates=false`), follow `.git/HEAD` →
   `.git/refs/heads/<branch>` instead, where the race can still occur.
2. **Extension filter.** `path.suffix.lower()` must be in `_SUPPORTED_EXTS`
   (`.py .js .ts .jsx .tsx .go .rs .md .markdown`).
3. **Gitignore filter.** `_is_ignored(path, root, patterns)` — see below.
4. Otherwise `call_soon_threadsafe(file_queue.put_nowait, path)`.

The watchdog callback runs on the observer thread; `call_soon_threadsafe` is the
only safe bridge into the running loop. `file_queue` and `commit_queue` are
module-level `asyncio.Queue` objects in `watcher.py`, retrieved elsewhere via
`get_queue()` / `get_commit_queue()`.

### gitignore filtering

`_load_gitignore_patterns(root)` walks `root.rglob(".gitignore")`, and for each
file prefixes non-rooted patterns with that file's directory (so a nested
`.gitignore` scopes correctly), stripping a leading `/` from rooted ones.
Patterns are read **once at startup**; editing `.gitignore` requires a daemon
restart.

`_is_ignored(path, root, patterns)` computes the POSIX relative path and, for
each pattern, tests: `fnmatch(rel, pattern)`, `fnmatch(rel, "**/"+pattern)`,
`fnmatch(path.name, pattern.rstrip("/"))`, and for `dir/` patterns each
intermediate path component. The processor re-checks `_is_ignored` itself and,
when it matches, writes a `ledger` row with `is_ignored=1` and skips all
content processing.

## processor.process_file — decision tree

`process_file(path, queue)` is `async` but does no awaiting internally (the
`queue` arg is unused; kept for signature stability). Steps:

1. `ext = path.suffix.lower()`; look up `lang` in `_EXT_TO_LANG` (py, js/jsx,
   ts/tsx, go, rs, md/markdown). Unknown extension → return. Go/Rust are
   skeletonized and summarized but produce no `symbol_index` rows
   (`_extract_symbols` is Python/JS-only).
2. `path.exists()` false → return.
3. `_is_ignored` → write `is_ignored=1` ledger row, return.
4. `len(source) > MAX_FILE_SIZE_KB * 1024` → return (no ledger row).
5. Compute `ast_hash = _compute_ast_hash(source, ext)`.
6. If a ledger row exists with the **same** `ast_hash` → `upsert_file` (mtime
   refresh only), return. `summarize` / `skeletonize` are skipped.
7. New file or changed hash → full pipeline:
   `skeleton = skeletonize(source, lang)`;
   `summary = summarize(source.decode(errors="replace"), lang)`;
   `upsert_file` + `upsert_cache(path, skeleton, summary)`;
   `symbols = _extract_symbols(source, path, lang)` then one
   `upsert_symbol(name, path, refs, signature)` per symbol.

Everything runs inside a single `with Ledger() as ledger:` block. `LedgerError`
(DB locked > 500 ms) is caught and logged; other exceptions propagate to
`start_processor`, which logs them and calls `queue.task_done()`.

## The AST-hash gate

`_compute_ast_hash(source: bytes, ext: str) -> str` returns a 16-hex-char digest
of file *structure*:

- **`.py`** — `hashlib.sha256(ast.dump(ast.parse(source)).encode()).hexdigest()[:16]`.
  `ast` drops comments and all whitespace, so a comment-only or reformat-only
  edit yields the identical hash and step 6 short-circuits. A `SyntaxError`
  falls through to the skeleton hash.
- **Other supported exts** — `sha256(skeletonize(source, lang).encode())[:16]`.
  Invariant to edits *inside* function bodies (bodies are collapsed to `{...}`),
  but not to whitespace outside them.
- **Fallback** — `sha256(source)[:16]` of the raw bytes.

Determinism: `ast.dump` emits fields in a fixed order and `skeletonize` is a
pure function, so the hash is byte-stable across processes and hash seeds
(`tests/test_determinism.py::TestAstHashGate`).

## The deterministic skeletonize → summarize → extract-symbols flow

No step touches the network, the clock, a subprocess, or a random source.

- **`skeletonize(source, language)`** — `MAX_FILE_SIZE_KB` guard returns `""`
  for oversized input. Markdown: tree-sitter (`tree_sitter_markdown`) walk
  keeping heading lines, fenced-code opening fences and single-line links, with
  a line-regex fallback if the grammar import or parse fails. Go/Rust:
  tree-sitter, keeping
  type/import/struct/enum/trait/use declarations in full and collapsing
  fn bodies to `{...}`, with a line-regex fallback. Python: collect
  `(start_line, end_line, "    ...")` replacements from the tree, apply
  bottom-up. JS/TS: collect `statement_block` byte ranges, splice `{...}` in
  left-to-right. Traversal order is deterministic; replacements are explicitly
  sorted.
- **`summarize(source, language)`** — three tiers, first hit wins:
  (1) module docstring / leading `/* */` or `//` comment / first `#` heading →
  first sentence, whitespace-collapsed, capped at 120 chars;
  (2) top-level def/class/function names → `Defines: a, b, c` (≤ 8, `…` if more);
  (3) `Short {language} snippet ({n} lines)` with `n` = non-blank line count.
  Python tiers use `ast`; the name list is `tree.body` order (source order), not
  hash order.
- **`_extract_symbols(source, path, lang)`** — returns
  `list[(symbol_name, references, signature)]`.
  Python: `ast.walk` collects every `FunctionDef` / `AsyncFunctionDef` /
  `ClassDef` (nested included) plus `Import` / `ImportFrom` module names; the
  full import list is attached as `references` to **every** symbol; `signature`
  is rebuilt with `ast.unparse` (`def f(x: int) -> str`, `class C(Base)`).
  JS/TS: regex for `import ... from "x"` and `function|class|const|let|var NAME`;
  `signature` is always `None`. Other languages: `[]`.
  `ast.walk` is BFS with a `deque` — order is structural and reproducible; the
  determinism suite spawns subprocesses with `PYTHONHASHSEED=0` vs `1` to prove
  no dict/set iteration order leaks into the output.

## The commit-queue path

`git commit` appends to `.git/logs/HEAD` → watcher pushes the new 12-char hash →
`start_snapshot_writer` pops it → `_write_snapshot(commit_hash)`:

```
SELECT symbol_name, source_file, signature FROM symbol_index
```

If empty, skip. Otherwise `INSERT OR IGNORE` one
`(commit_hash, filepath, symbol_name, signature, snapshot_at)` row per symbol,
`snapshot_at = int(time.time())`. `INSERT OR IGNORE` + the composite PK make a
repeated hash idempotent. `cs diff --json` (`json_api.get_diff_json`) then reads
the most recent snapshot (`ORDER BY snapshot_at DESC LIMIT 1`) or an explicit
hash and diffs signatures against the live `symbol_index`.
