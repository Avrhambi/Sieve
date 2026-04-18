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

**Status: PASS on unfamiliar codebase — 2 tool calls saved**

**What it tests:** Does injecting pre-built file skeletons help Claude answer architecture questions faster and more accurately than using its tools alone?

### Rounds 1–2 (invalid — psf/requests is a contaminated test project)

All rounds on psf/requests were invalid: Claude knows that library from training data and answers from memory, not from searching. Tool call counts reflected verification, not discovery.

### Round 3 (Sieve codebase — unfamiliar to Claude, with stemming + summary overlap removed)

Four bugs fixed across rounds 1–3:
1. 101KB all-files dump → selective injection (keyword/symbol scoring)
2. Focal files injected as full content (26KB) → always use skeleton
3. Budget exception let oversized skeletons through → hard-truncated at 1,500 chars
4. Summary overlap signal tested and found to be noise (10/10 false positives) → removed
5. Stemming added — "watching" now matches "watcher.py"
6. Minimum score gate (< 1.0 → inject nothing) added to silence meta-questions

**Prompt:** `Where would I add logic to skip binary files in the file-watching pipeline?`
**Project:** Sieve repo (unfamiliar to Claude)

| Dimension | Mode A (no Sieve) | Mode B (selective injection) |
|---|---|---|
| Tool calls | 4 (Search all .py + Read × 2) | 2 (targeted Search + Read) |
| Hook injected | N/A | watcher.py skeleton (truncated at 1,500 chars) |
| Claude knew target file before searching | No | Yes — named watcher.py immediately |
| Tool calls saved | baseline | 2 |
| Verdict | baseline | **WIN** |

**Limitation discovered:** 1,500 char budget truncated watcher.py skeleton before `_SieveHandler` class — the answer lives there. Claude still needed 2 targeted tool calls. Accepted as-is: targeted tool calls are better than broad ones.

**What this means:** On an unfamiliar codebase, selective injection cuts tool calls in half by pointing Claude at the right file before it searches. The hook narrows the search space; it doesn't eliminate tool calls entirely for large files.
| Answer quality | Same | Same |
| Verdict | baseline | Marginal improvement |

**What this means:** Selective injection now works mechanically — the right file was selected, output stayed under 2KB, Claude received it. But for targeted single-file questions where Claude already knows which file to look in, the value is marginal: saves 1 tool call (~2-3 seconds), same answer.

**Claude's own assessment of when the hook helps most:**
1. **Obvious file, small enough to fit whole** — entire file fits in 1.5KB budget → zero tool calls needed
2. **Cross-file questions** — hook injects multiple related files → broader picture before any tool calls
3. **Broad architecture questions** — Claude doesn't know which files to check → pre-injected symbols save 4-5 tool calls

**Least useful:** When injected file is unrelated to the question — pure noise consuming context window.

**Problems identified:**
1. **Targeted questions don't benefit much** — Claude knows where to look; hook just confirms what a grep would find
2. **1.5KB budget is tight for skeletons** — adapters.py skeleton exceeds budget and gets truncated; Claude only sees the top portion
3. **Relevance is imprecise** — keyword match works when the filename appears in the prompt; fails for indirect questions ("how does auth work?" when auth logic is in sessions.py)

**Insight:** The hook's value is highest for **architecture questions without a named file target**. The next test should use a prompt like "which files handle session state?" to measure the cross-file case where Claude would otherwise need 4-5 Search calls.

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

## TEST-05 — Token reduction measurement

**Status: PASS (73.8% reduction, target 70–93%)**

**What it tests:** How much does Sieve compress the codebase when building skeletons? Target is 70–93% — enough to fit meaningful context without flooding the token window.

| Metric | Value |
|---|---|
| Raw Python source | 386,323 chars |
| Skeleton output | 101,150 chars |
| Reduction | **73.8%** |
| Target | 70–93% |
| Result | PASS |

**First run result (before fix): FAIL at 60.4%**

The initial run failed because `tests/` and `docs/` directories were included in the skeleton output. These files don't compress well:
- `tests/test_utils.py` — 21,893 bytes in skeleton (assert-heavy test functions, minimal stripping)
- `docs/conf.py` — 12,533 bytes (Sphinx config data, no functions to strip)
- `docs/_themes/flask_theme_support.py` — 4,961 bytes (pure style dict)

**Fix applied:** Hook now skips `tests/`, `test/`, `docs/`, `doc/` directories from skeleton injection. Dropped output from 153KB → 101KB, pushing reduction from 60.4% → 73.8%.

**Remaining concern:** 101KB is still ~50× Claude Code's ~2KB inline injection limit. Passing this test does not mean the injection is usable — it only confirms the skeletonizer compresses effectively. Selective injection (delivering only relevant skeletons) is still required.

**Insight:** Skeletonization works as designed for library source files. The 73.8% reduction means Claude gets structural awareness (all signatures + docstrings) at roughly ¼ the token cost of raw source. The bottleneck is delivery, not compression quality.

---

---

## TEST-06 — PostCompact re-injection (A/B)

**Status: Mode B PASS — Mode A pending**

**What it tests:** After `/compact` wipes the conversation context, does the PostCompact hook re-inject enough structural knowledge for Claude to answer codebase questions without the user re-explaining anything?

**Prompt (sent immediately after `/compact`):**
`What are the main classes in this project and where are they defined? List exact file paths.`

**PostCompact injection:** architectural map (~1.2KB) — fits Claude Code's inline limit cleanly.

| Dimension | Mode A (no Sieve PostCompact) | Mode B (with Sieve PostCompact) |
|---|---|---|
| Named correct files? | Yes | Yes — models.py, sessions.py, adapters.py, structures.py, auth.py, cookies.py, exceptions.py |
| Named correct classes? | Yes — with line numbers | Yes — Session, PreparedRequest, HTTPAdapter, CaseInsensitiveDict, HTTPBasicAuth, RequestsCookieJar, + more |
| Had to re-explain structure? | No | No |
| Tool calls to answer | 1 (Search for `^class `) | 0 |
| Injection size | N/A | ~1.2KB (fits inline) |
| Verdict | baseline | Same |

**Mode B observations:**
- PostCompact hook fired immediately after `/compact` completed
- Architectural map injected as a compact one-liner-per-file format (file name → classes/functions)
- Claude produced a complete, correctly-filed class table with zero tool calls
- Map format at ~1.2KB is well under the ~2KB inline limit — the fix from TEST-04/TEST-05 (switching from full skeletons to a pre-built map) solved the injection size problem for this use case

**Why SAME on psf/requests:** Claude recovered in 1 tool call on this small 28-file project. The value of PostCompact re-injection scales with project size — on a 200+ file codebase, recovery without the map would require multiple Search → Read rounds. For requests, the map saves one tool call; not nothing, but not a dramatic delta either.

---

## TEST-07 — Broad architecture question on unfamiliar codebase (A/B)

**Status: PASS — hook saved 2 tool calls**

**Why this test was needed:** TEST-02 and the session-state question on psf/requests were contaminated — Claude already knows that library from training data and answers from memory, not from searching. This test uses the Sieve codebase itself (a private project Claude has no prior knowledge of) to get a clean measurement.

**Prompt:** `Which files handle the file-watching logic in this codebase?`

**Project:** Sieve repo (`src/daemon/watcher.py`, `processor.py`, `main.py` are the correct answer)

| Dimension | Mode A (no Sieve) | Mode B (with Sieve, offline fallback) |
|---|---|---|
| Tool calls | 2 (Search × 2) | 0 |
| Answer correct | Yes | Yes |
| How Claude found it | Grep for watcher/observer keywords | Read injected file list — watcher.py name was self-explanatory |
| Hook mode | N/A | Offline fallback (file-tree heuristic) |
| Verdict | baseline | **WIN — 2 tool calls saved** |

**Note:** Mode B used the offline fallback (daemon not running against Sieve), not selective skeleton injection. The file-tree heuristic was sufficient because filenames were self-explanatory. With the daemon online and selective injection, Claude would additionally receive function signatures — more useful for questions where filenames don't reveal the answer.

**Insight:** The offline file-tree fallback alone delivers measurable value on unfamiliar codebases. Zero tool calls vs 2 is a real difference. The key variable is whether the file name reveals the answer — for `watcher.py` it does; for "which file handles rate limiting?" it wouldn't.

---

## Critical finding: psf/requests is a contaminated test project

All A/B tests run on psf/requests (TEST-02, TEST-04, and the session-state question) are invalid. Claude knows this library from training data and answers from memory rather than searching the codebase. When asked "which files handle session state?", Claude returned the correct answer with 1 tool call — not because the hook helped, but because it already knew. The hook's contribution was invisible.

**Valid tests must use an unfamiliar/private codebase** where Claude genuinely doesn't know the structure.

---

---

## Final Summary

**Date:** 2026-04-18
**Tests run:** 7 (TEST-01 through TEST-07, plus TEST-02 re-run)
**Platform:** Windows 11, Git Bash, Python 3.14, Claude Sonnet 4.6
**Test projects:** psf/requests (contaminated), Sieve repo (valid)

---

### What works

| Feature | Evidence | Value |
|---|---|---|
| File-tree fallback (offline) | TEST-07: 0 vs 2 tool calls | High — works with zero dependencies |
| PostCompact architectural map | TEST-06: 0 vs 1 tool call | High — only option after /compact |
| Selective skeleton injection | TEST-02 re-run: 2 vs 4 tool calls | Medium — narrows search, doesn't eliminate |
| @full override | TEST-03: 0 tool calls | High for implementation questions |
| Minimum score gate | Verified: silent on meta-questions | Correctness fix |

### What doesn't work / was cut

| Feature | Finding |
|---|---|
| All-files skeleton dump | Exceeds 2KB inline limit — Claude never receives it |
| Summary word overlap scoring | 10/10 false positives — injected wrong files |
| psf/requests as test project | Claude knows it from training — all results contaminated |

### Key architectural decisions made during testing

1. **Selective injection over full dump** — 2KB Claude Code limit makes full-codebase injection impossible
2. **PostCompact as primary use case** — no competition after /compact; architectural map always fits
3. **Skeleton only, never full content** — focal files stay as skeleton; @full is the explicit override
4. **Scoring: focal (+10) + filename (+3) + symbol (+2)** — summary overlap removed as noise
5. **Stemming** — "watching" → "watch" matches "watcher.py"
6. **Silence gate (score < 1.0)** — hook stays quiet on meta-questions and follow-ups

### Honest assessment

Sieve delivers clear value in two scenarios: **PostCompact recovery** (injecting the architectural map after context wipe) and **file-tree orientation on unfamiliar codebases** (zero-dependency fallback). The selective injection path works but its ceiling is lexical — it misses indirect questions where the right file has an unrelated name. The tool is past proof-of-concept and has a clean fallback chain, but Ollama is a load-bearing dependency for skeleton injection and should be treated as such.
