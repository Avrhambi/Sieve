# Sieve — Test Results

Date: 2026-04-17
Platform: Windows 11, Git Bash, Python 3.14, Claude Sonnet 4.6
Test project: psf/requests

---

## TEST-01 — Daemon offline fallback

**Status: PASS**

When the daemon is not running, the hook falls back to a file-tree heuristic and injects the list of source files before the prompt. Verified via the `[sieve] daemon offline — file-tree heuristic` system-reminder appearing in every prompt in the Sieve session.

---

## TEST-02 — Skeleton injection (A/B)

**Status: SAME**

Prompt: `Where would I add retry logic to the HTTP request flow in requests/adapters.py?`

| Dimension | Mode A (no Sieve) | Mode B (with Sieve) |
|---|---|---|
| Named HTTPAdapter.send()? | Yes | Yes |
| Correct file (adapters.py)? | Yes | Yes |
| Follow-ups needed | 0 | 0 |
| Tool calls | 2 (search + read) | 4 (2 searches + read) |
| Answer quality | Better — showed code sketch, mentioned `__init__` | Good — cited line numbers, urllib3 Retry |
| Verdict | baseline | Same |

**Notes:** Mode B used *more* tool calls because the 145KB full-dump injection didn't help Claude navigate faster for a targeted single-file question. Selective injection (only inject files relevant to the prompt) would improve this result.

---

## TEST-03 — @full override

**Status: PASS**

Prompt: `@full src/requests/api.py what does the get() function do line by line?`

Claude answered the question entirely from the injected file content — no `Read` or `Search` tool calls. The full 158-line file was prepended to the prompt by the hook before Claude received it.

**Notes:**
- Original syntax `!full` conflicted with Claude Code's `!` shell command prefix — fixed to `@full`.
- Token efficiency confirmed: zero tool call overhead for the file read.

---

## Bugs fixed during testing

| Bug | Fix | Commit |
|---|---|---|
| `add_signal_handler` not supported on Windows | Fall back to `signal.signal` | `2212c58` |
| `main.py` was a placeholder — daemon never started | Wired up watcher, processor, heartbeat | `8669f4f` |
| `Ledger.__init__` default arg bound at import time | Read `_DB_PATH` dynamically | `2fc03e3` |
| Resource thresholds blocked processor on Windows | Set thresholds to 0 | `31b3dd4` |
| Hook read `ledger.db` from sieve root, not watched project | Use `Path.cwd() / "ledger.db"` | `b920a84` |
| Paths stored with backslashes, queried with forward slashes | Normalize all paths to `/` in ledger | `cc9152b` |
| `context_cache.file_id` stored with backslashes | Normalize in `upsert_cache` and `get_cache` | `5397bd3` |
| Hook crashed on non-ASCII characters (cp1255) | Force UTF-8 stdout | `e8b20e2` |
| `select.select` on stdin not supported on Windows | Direct blocking stdin read, cached | `01a0da4` |
| `!full` path extraction included trailing question text | Take only first token after `@full` | `8279d74` |
| `!full` conflicted with Claude Code `!` shell prefix | Renamed to `@full` | `89b604e` |

---

## Next tests

- TEST-04 — Hybrid context
- TEST-05 — Token reduction measurement
- TEST-06 — PostCompact re-injection
