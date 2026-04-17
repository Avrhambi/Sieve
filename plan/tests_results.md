# Sieve — Test Results

Date: 2026-04-17
Platform: Windows 11, Git Bash, Python 3.14, Claude Sonnet 4.6
Test project: psf/requests

---

## TEST-01 — Daemon offline fallback

**Status: PASS**

**What it tests:** When the Sieve daemon is not running, does the hook still provide something useful to Claude rather than failing silently?

**Result:** The hook correctly detected the daemon was offline (no heartbeat in `ledger.db`) and fell back to scanning the file tree, injecting a list of source files before every prompt. Verified by the `[sieve] daemon offline — file-tree heuristic` message appearing consistently in the Sieve development session.

**What this means:** Sieve is resilient — even without a running daemon, Claude gets at minimum a file map of the project. Claude can use this to navigate without manually searching. The fallback is also fast (pure stdlib, no third-party imports), meeting the <50ms latency target.

**Problems identified:** None for this test.

**Insight:** The offline fallback is the most reliable part of the system. It always fires, costs almost nothing, and gives Claude a structural map even when the expensive pipeline (Ollama, watchdog, SQLite) is unavailable.

---

## TEST-02 — Skeleton injection (A/B)

**Status: SAME**

**What it tests:** Does injecting pre-built file skeletons help Claude answer architecture questions faster and more accurately than using its tools alone?

**Prompt:** `Where would I add retry logic to the HTTP request flow in requests/adapters.py?`

| Dimension | Mode A (no Sieve) | Mode B (with Sieve) |
|---|---|---|
| Named HTTPAdapter.send()? | Yes | Yes |
| Correct file (adapters.py)? | Yes | Yes |
| Follow-ups needed | 0 | 0 |
| Tool calls | 2 (search + read) | 4 (2 searches + read) |
| Answer quality | Better — showed code sketch, mentioned `__init__` | Good — cited line numbers, urllib3 Retry |
| Verdict | baseline | Same |

**What this means:** For a targeted single-file question on a small codebase (34 files), Sieve provided no advantage. Claude found the answer equally well on its own in fewer steps. Mode B actually used more tool calls — Claude searched for the file even though the skeleton was already in context, because the 145KB injection was too large and noisy to navigate efficiently.

**Problems identified:**
1. **Injection is indiscriminate** — all 34 files are dumped into context regardless of relevance. This buries useful signals in noise.
2. **Claude prefers tools for targeted questions** — when Claude knows exactly which file to look in, reading it directly is faster than scanning a large pre-injected blob.
3. **Data files inflate the injection** — `flask_theme_support.py` (a Pygments style dict) has no functions to strip, so the skeletonizer injected it in full, wasting ~60KB.

**Insight:** Sieve's value for this use case requires **selective injection** — only inject skeletons for files semantically related to the prompt. The current all-or-nothing approach works against Claude's agentic tool use on small projects. Expected to perform better on large codebases (100+ files) where tool search is expensive.

---

## TEST-03 — @full override

**Status: PASS**

**What it tests:** Can a user force Sieve to inject a complete file (not just the skeleton) for questions that need full implementation detail?

**Prompt:** `@full src/requests/api.py what does the get() function do line by line?`

**Result:** Claude answered entirely from the injected file content — zero `Read` or `Search` tool calls. The hook intercepted the prompt, read the full 158-line file, prepended it as context, and Claude reasoned from that alone.

**What this means:** `@full` is the highest-value feature for implementation questions. Instead of Claude making 2–3 tool calls (search → find path → read), the user pays one upfront injection and Claude answers immediately. For files Claude would need to read anyway, this saves round-trips and keeps the conversation faster.

**Problems identified:**
1. **`!full` conflicted with Claude Code's `!` shell prefix** — `!full file.py` was executed as a bash command, not passed to the hook. Renamed to `@full`.
2. **`select.select` on stdin doesn't work on Windows** — the hook couldn't read the prompt text from stdin to detect `@full`. Replaced with a direct blocking read.
3. **File path extraction was too greedy** — `@full api.py explain this` tried to open a file named `api.py explain this`. Fixed to take only the first token after `@full`.

**Insight:** `@full` is a power-user feature that delivers measurable token savings. The UX issue is discoverability — users need to know the syntax exists. A good next step would be auto-triggering `@full` when the prompt explicitly mentions a filename and asks for implementation details.

---

## Overall Windows compatibility issues found

The original codebase was developed and tested on Linux/Mac. Running on Windows (Git Bash + Python 3.14) uncovered 11 bugs before a single test passed:

| Category | Bug count | Root cause |
|---|---|---|
| Unix-only APIs | 3 | `add_signal_handler`, `select.select`, `/proc/meminfo` |
| Path separator mismatch | 2 | Backslash vs forward slash in SQLite queries |
| Hardcoded paths | 2 | `ledger.db` path relative to sieve root, not watched project |
| Python default arg gotcha | 1 | `Ledger(db_path=_DB_PATH)` bound at class definition time |
| Encoding | 1 | Windows cp1255 can't encode `✓` |
| CLI conflict | 1 | `!full` vs Claude Code's `!` shell prefix |
| Incomplete implementation | 1 | `main.py` was a placeholder — daemon never started |

**Insight:** The system needs a Windows CI test run before any future release. Most fixes were one-liners, but they blocked all testing until resolved.

---

## TEST-04 — Hybrid context

**Status: PARTIAL PASS (mechanism works, delivery blocked)**

**What it tests:** When a file is named in the prompt, does Sieve inject it in full while keeping other files as skeletons?

**Result:** The hybrid context mechanism fires correctly — manual test confirmed `[sieve] hybrid context: 1 file(s) full, 44 skeleton(s)`. Focal file detection was fixed to handle src-layout repos (e.g. `requests/adapters.py` resolving to `src/requests/adapters.py`). However, Claude still made `Read` tool calls in the Claude Code session.

**Root cause discovered — critical finding:**

Claude Code's harness caps inline hook injection at approximately **2KB**. The hook outputs **149KB** (44 files). The harness saves the excess to a temp file and only gives Claude a 2KB preview — which happens to be README/markdown content, not Python skeletons. Claude never sees the Python source skeletons and falls back to tool reads.

Claude confirmed this directly:
> *"The output was 149KB, which the harness flagged as too large to include inline — I only received a 2KB preview showing markdown files, not the Python source. So the actual adapters.py content wasn't visible to me from the hook, and I fell back to using the Read tool directly."*

**What this means:** The whole-codebase dump approach is fundamentally incompatible with Claude Code's injection limit. This is the root cause of TEST-02 and TEST-04 failures, and explains why Claude used tools even with Sieve ON.

**Exception — TEST-03 worked** because `@full` exits immediately after printing one file (~5KB), which fits within the inline limit.

**Problems identified:**
1. **Injection size (149KB) far exceeds Claude Code's ~2KB inline limit** — the core design assumption is broken
2. **Docs/markdown files inflating output** — `flask_theme_support.py`, README, conf.py injected unnecessarily
3. **Focal file detection failed for src-layout repos** — fixed in commit `9306856`

**Insight — architectural pivot required:**

The current approach (inject everything, let Claude pick what's relevant) is the opposite of what works. The injection must be:
- **Small** (<2KB to fit inline) — roughly 3–5 skeletons max
- **Selective** — only files semantically related to the prompt
- **Ranked** — most relevant file first

This requires a keyword/symbol match between the prompt and the ledger's `symbol_index` table, which already exists in the schema. The data is there; the hook just needs to query it intelligently instead of dumping everything.

---

## Critical blocker: injection size limit

**All A/B tests (TEST-02, TEST-04) are invalid until this is fixed.** The baseline and Sieve-ON conditions were effectively identical — Claude received the same 2KB markdown preview in both cases and used tools in both cases.

**Recommended fix before continuing tests:**
Update the hook to select only the top 3–5 most relevant files based on symbol/keyword overlap with the prompt, keeping total output under 2KB.

---

## Next tests

- **Fix injection size first** — implement selective injection (symbol-index keyword match, output cap ~1.5KB)
- TEST-05 — Token reduction measurement (still valid — measures compression ratio independently of delivery)
- TEST-06 — PostCompact re-injection (re-run after fix — this is the highest-value test)
- Re-run TEST-02 and TEST-04 after fix
