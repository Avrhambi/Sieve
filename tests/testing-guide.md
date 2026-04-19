# Sieve — Testing Guide

Last updated: 2026-04-19

---

## Architecture overview (read first)

Sieve has three delivery mechanisms. Each is tested differently:

| Mechanism | When it fires | How to test |
|---|---|---|
| **PostCompact hook** | After `/compact` wipes context | TEST-06 |
| **Offline file-tree fallback** | Every prompt when daemon is not running | TEST-01 |
| **MCP — sieve_find / sieve_file** | When Claude actively searches | TEST-09 |

The UserPromptSubmit hook does **not** inject skeletons when the daemon is online. Active codebase search is handled by the MCP server.

---

## Path reference

Set these once in your shell:

```bash
SIEVE=/path/to/sieve
PROJECT=/path/to/your/project   # the codebase you want to index
```

---

## Quick Start — first run in 5 minutes

### Step 1 — Start the daemon

```bash
cd $SIEVE
source bin/activate  # or .venv/Scripts/activate on Windows
python src/main.py $PROJECT
```

Expected: `Watching /path/to/project ...`

### Step 2 — Install hooks in the target project

```bash
mkdir -p $PROJECT/.claude
cat > $PROJECT/.claude/settings.json << 'EOF'
{
  "hooks": {
    "UserPromptSubmit": [{"hooks": [{"command": "python3 /path/to/sieve/bin/sieve-hook --mode=prompt", "type": "command"}]}],
    "PostCompact":      [{"hooks": [{"command": "python3 /path/to/sieve/bin/sieve-hook --mode=compact", "type": "command"}]}]
  },
  "mcpServers": {
    "sieve": {
      "command": "python3",
      "args": ["-m", "src.mcp.server", "/path/to/project/ledger.db"],
      "cwd": "/path/to/sieve"
    }
  }
}
EOF
```

### Step 3 — Trigger initial cache build

```bash
touch $PROJECT/your_main_file.py
```

Wait 3–5 seconds. The daemon writes skeletons to `ledger.db`.

**Verify cache:**
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('$PROJECT/ledger.db')
cc = conn.execute('SELECT COUNT(*) FROM context_cache').fetchone()[0]
si = conn.execute('SELECT COUNT(*) FROM symbol_index').fetchone()[0]
print(f'context_cache: {cc}  |  symbol_index: {si}')
print('OK' if cc > 0 else 'WARN: cache empty — touch .py files then wait 5s')
"
```

### Step 4 — Open Claude Code in the project

```bash
cd $PROJECT && claude
```

Claude must open from inside the project directory to pick up `.claude/settings.json`.

---

## Automated tests (run after every code change)

```bash
cd $SIEVE
python3 -m pytest tests/ -v --tb=short
```

| File | What it covers |
|---|---|
| `test_skeleton.py` | AST stripping — Python, JS, TS, Markdown |
| `test_integration.py` | Hook latency <50ms, token reduction >70% |
| `test_benchmark.py` | Reduction + semantic preservation, 3 languages |
| `test_mcp.py` | MCP scoring logic, keyword extraction, stemming |

All four must pass before any commit.

---

## Manual tests

---

### TEST-01 — Daemon offline fallback

**Goal:** Hook injects a file-tree listing when the daemon is not running.

**Setup:** Stop the daemon.

**Steps:** Open Claude Code in any project and send any prompt.

**Expected output injected before the prompt:**
```
[sieve] daemon offline — file-tree heuristic
  src/core/inference.py
  src/daemon/watcher.py
  ...
```

**Verify:**
- Hook exits in <50ms (no hang)
- File list matches actual source files up to MAX_DEPTH=3
- Claude responds normally

---

### TEST-02 — @full override

**Goal:** `@full <path>` injects complete raw file content.

**Steps:** In Claude Code, send:
```
@full src/core/skeletonizer.py what does the skeletonize function do line by line?
```

**Expected:** Claude answers with zero `Read` or `Search` tool calls.

**Manual check:**
```bash
SIEVE_PROMPT='@full src/core/skeletonizer.py' python3 $SIEVE/bin/sieve-hook --mode=prompt | head -20
```

Expected: full file content (no `...` placeholders).

---

### TEST-03 — PostCompact re-injection

**Goal:** After `/compact`, Claude recovers structural knowledge from the injected architectural map with zero tool calls.

**Why this test needs a large project:** The original evidence (TEST-06 in `plan/tests_results.md`) was collected on psf/requests — 28 files, partially known to Claude from training. On that project Claude recovers in 1 tool call anyway. The test is valid but understates the real value. This protocol fixes that.

---

#### TEST-03A — Retest on a 100+ file private codebase (the number that matters)

**Project requirements:**
- 100+ Python source files
- Private or obscure enough that Claude has no training knowledge of it
- Daemon has been running against it long enough to populate `ledger.db`

**Suggested project if you don't have one:**
Clone an obscure but well-structured open source Python project Claude is unlikely to know (avoid top-1000 GitHub stars). Good candidates: domain-specific tools, internal-framework ports, or mid-size scientific Python libraries.

**Verify file count before starting:**
```bash
find $PROJECT -name "*.py" | grep -v __pycache__ | wc -l
# Must be ≥ 100 for this test to be meaningful
```

**Setup:**
1. Start daemon: `python src/main.py $PROJECT`
2. Wait for cache to populate (check with the DB query from Quick Start)
3. Open Claude Code in `$PROJECT` with the PostCompact hook configured
4. Have a real working session — ask questions, read files — until the context fills or run `/compact` manually

**Mode A (baseline — PostCompact hook disabled):**

Remove the PostCompact entry from `.claude/settings.json`, then run `/compact`. Immediately send:
```
What are the main components of this system and where are they defined? List the key files and what each one is responsible for.
```

Record every tool call Claude makes to reconstruct its orientation.

**Mode B (PostCompact hook enabled):**

Restore the hook, restart, repeat the same session and `/compact`. Send the same prompt immediately after.

**A/B scorecard:**

| Dimension | Mode A — no map | Mode B — with map |
|---|---|---|
| Tool calls to orient after compact | count | count |
| Named correct files without searching? | Y / N | Y / N |
| Named correct classes/functions? | Y / N | Y / N |
| Wrong guesses / backtracking? | count | count |
| Time to first correct answer (approx) | seconds | seconds |
| Verdict | baseline | |

**What a strong result looks like:** Mode A makes 4–8 tool calls (Grep → Read → wrong file → Grep again). Mode B makes 0. That's the number that makes the value proposition obvious.

**Record the result in `plan/tests_results.md` as TEST-09.**

---

#### TEST-03B — Small project baseline (the original test, for reference)

Run the same protocol on psf/requests (28 files). This confirms the result scales — not that the tool works on small projects.

**Expected:** Mode A: 1–2 tool calls. Mode B: 0. Delta is small. This is the *floor*, not the ceiling.

---

**Quick-switch commands:**

```bash
# Disable PostCompact (Mode A)
python3 -c "
import json
s = json.load(open('$PROJECT/.claude/settings.json'))
s.get('hooks', {}).pop('PostCompact', None)
json.dump(s, open('$PROJECT/.claude/settings.json', 'w'), indent=2)
" && echo "Mode A — PostCompact OFF"

# Re-enable PostCompact (Mode B)
cp $PROJECT/.claude/settings.json.bak $PROJECT/.claude/settings.json && echo "Mode B — PostCompact ON"
```

---

### TEST-04 — MCP sieve_find

**Goal:** `sieve_find` returns ranked skeletons and Claude uses them without further tool calls.

**Prerequisites:** Daemon running, cache populated.

**Steps:** In Claude Code (with MCP configured), send:
```
Which files handle the file-watching logic in this codebase?
```

**Expected:** Claude names the correct files (e.g., `watcher.py`, `processor.py`) from the MCP response — zero additional Grep or Read calls.

**A/B comparison:**

| Dimension | No MCP (Grep) | With sieve_find |
|---|---|---|
| Tool calls | 2–4 (Grep + Read) | 1 (sieve_find) |
| Answer structure | Raw lines | Signatures + docstrings |
| Import graph included? | No | Yes (second-degree files at 50% score) |
| Verdict | baseline | |

**Verify the MCP server is reachable:**
```bash
cd $SIEVE
python3 -m src.mcp.server $PROJECT/ledger.db
# Should start without errors
```

---

### TEST-05 — Token reduction measurement

**Goal:** Skeletonization reduces raw source by ≥70%. Target: 70–93%.

```bash
# Run the automated benchmark (covers Python, JS, TypeScript)
cd $SIEVE
python3 -m pytest tests/test_benchmark.py -v -s
```

Expected output includes a cross-language table. All languages must show ≥70% reduction.

**For a real project:**
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('$PROJECT/ledger.db')
rows = conn.execute('SELECT path, length(skeleton) FROM context_cache ORDER BY 2 DESC LIMIT 10').fetchall()
for path, size in rows:
    print(f'{size:>8,}  {path}')
"
```

---

### TEST-06 — Graceful shutdown

**Goal:** Daemon exits cleanly without corrupting `ledger.db`.

**Steps:**
1. Start the daemon
2. Save several files rapidly
3. Press `Ctrl+C` while processing

**Expected:** `Shutdown signal received — processor exiting`

**Verify DB integrity:**
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('$PROJECT/ledger.db')
r = conn.execute('PRAGMA integrity_check').fetchone()
rows = conn.execute('SELECT COUNT(*) FROM context_cache').fetchone()[0]
print(f'Integrity: {r[0]}')
print(f'Cache entries preserved: {rows}')
"
```

Expected: `Integrity: ok`

---

## Edge cases

| Edge case | How to trigger | Expected result |
|---|---|---|
| File > 100KB | `python3 -c "open('big.py','w').write('x'*110000)"` | Daemon skips it silently |
| Syntax error in .py | Save `def foo(:` | Falls back to SHA-256 hash; no crash |
| Rapid saves (10× in 2s) | Loop `touch file.py` | AST hash gate fires; re-summary called once |
| File deleted while watching | `rm file.py` while daemon runs | No crash, no injection for that file |
| Gitignored file | Add file to `.gitignore`, save it | Not indexed |
| Ollama not running | Stop Ollama, save a file | Falls back to heuristic; no crash |

---

## Diagnostic reference

### Hook latency

| Latency | Meaning | Action |
|---|---|---|
| <25ms | Healthy | None |
| 25–40ms | Acceptable | None |
| 40–50ms | Marginal | Checkpoint WAL |
| >50ms | Violation | Check filesystem, WAL size |

```bash
# Force WAL checkpoint
python3 -c "import sqlite3; sqlite3.connect('$PROJECT/ledger.db').execute('PRAGMA wal_checkpoint(TRUNCATE)')"
```

### Daemon log messages

| Message | Meaning |
|---|---|
| `AST unchanged — no re-summary` | Comment/whitespace edit — no LLM call |
| `Cache updated` | Structural change processed |
| `Ollama unreachable — falling back to heuristic` | Ollama down; heuristic used |
| `Shutdown signal received — processor exiting` | Clean Ctrl+C shutdown |

### What each test covers

| What you're checking | Test |
|---|---|
| Core pipeline not broken | `pytest tests/ -v` |
| Offline fallback works | TEST-01 |
| @full override | TEST-02 |
| PostCompact map injected correctly | TEST-03 |
| MCP search returns correct files | TEST-04 |
| Compression ratio on real codebase | TEST-05 |
| DB not corrupted on crash | TEST-06 |

---

## When to run what

| Trigger | What to run |
|---|---|
| Any code change | `pytest tests/ -v` (~30s) |
| Before committing `bin/sieve-hook` or `processor.py` | TEST-01, TEST-02, TEST-03 |
| Before committing `src/mcp/server.py` | TEST-04 |
| Before release | All manual tests |
