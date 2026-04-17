# Sieve — Testing & Evaluation Guide

Last updated: 2026-04-16

---

## Path Reference (used throughout this guide)

```
SIEVE   = /c/Users/avrha/Documents/projects/Sieve-testing/sieve
REQUESTS= /c/Users/avrha/Documents/projects/Sieve-testing/projects/requests
CLICK   = /c/Users/avrha/Documents/projects/Sieve-testing/projects/click
HTTPX   = /c/Users/avrha/Documents/projects/Sieve-testing/projects/httpx
```

Set these as shell variables for convenience:
```bash
SIEVE=/c/Users/avrha/Documents/projects/Sieve-testing/sieve
REQUESTS=/c/Users/avrha/Documents/projects/Sieve-testing/projects/requests
CLICK=/c/Users/avrha/Documents/projects/Sieve-testing/projects/click
HTTPX=/c/Users/avrha/Documents/projects/Sieve-testing/projects/httpx
```

---

## Quick Start — Run Your First Test in 5 Minutes

### Step 1 — Clone the test project (once)

```bash
git clone https://github.com/psf/requests $REQUESTS
```

### Step 2 — Open three terminals (all Git Bash)

**Terminal 1 — Sieve daemon:**
```bash
cd $SIEVE
source .venv/Scripts/activate
python src/main.py $REQUESTS
```
You should see: `Watching /c/Users/.../requests ...`

**Terminal 2 — Test backend (for the guide UI):**
```bash
cd $SIEVE
source .venv/Scripts/activate
python plan/server.py
```
You should see: `Sieve Test Runner API → http://127.0.0.1:8765`

**Terminal 3 — Commands (ad-hoc testing):**
```bash
cd $REQUESTS
source $SIEVE/.venv/Scripts/activate
```

### Step 3 — Install the hook (once per test repo)

```bash
mkdir -p $REQUESTS/.claude
cat > $REQUESTS/.claude/settings.json << 'EOF'
{
  "hooks": {
    "UserPromptSubmit": [{"hooks": [{"command": "python3 /c/Users/avrha/Documents/projects/Sieve-testing/sieve/bin/sieve-hook --mode=prompt", "type": "command"}]}],
    "PostCompact":      [{"hooks": [{"command": "python3 /c/Users/avrha/Documents/projects/Sieve-testing/sieve/bin/sieve-hook --mode=compact", "type": "command"}]}]
  }
}
EOF
cp $REQUESTS/.claude/settings.json $REQUESTS/.claude/settings.json.bak
echo "Hook installed"
```

### Step 4 — Trigger the cache

```bash
touch $REQUESTS/src/requests/api.py
```
Wait 3 seconds. The daemon writes the skeleton to `ledger.db`.

### Step 5 — Open Claude Code in the test project

```bash
cd $REQUESTS
claude
```
Claude Code must open from the `requests/` directory to pick up `.claude/settings.json`.

### Step 6 — Send your first test prompt

```
What functions are available in requests/api.py?
```

**What you should see injected before your prompt:**
```
### requests/api.py
def request(method, url, **kwargs):
    """Constructs a Request..."""
    ...

def get(url, params=None, **kwargs):
    """Sends a GET request."""
    ...
```

---

## Setup Checklist (Before Any Test)

- [ ] Daemon running: `python src/main.py $REQUESTS`
- [ ] Ollama running (check Windows system tray, or run `ollama serve`)
- [ ] Hook installed: `$REQUESTS/.claude/settings.json` exists with `UserPromptSubmit` + `PostCompact`
- [ ] Backup exists: `$REQUESTS/.claude/settings.json.bak`
- [ ] Cache populated: run the cache check below
- [ ] Claude Code opened from inside `$REQUESTS/`

**Cache check:**
```bash
python3 -c "
import sqlite3, os
db = '$REQUESTS/ledger.db'
if not os.path.exists(db):
    print('FAIL: ledger.db not found — touch a .py file and wait 5s')
else:
    conn = sqlite3.connect(db)
    cc = conn.execute('SELECT COUNT(*) FROM context_cache').fetchone()[0]
    si = conn.execute('SELECT COUNT(*) FROM symbol_index').fetchone()[0]
    ig = conn.execute('SELECT COUNT(*) FROM ledger WHERE is_ignored=1').fetchone()[0]
    print(f'context_cache: {cc}  |  symbol_index: {si}  |  ignored: {ig}')
    print('OK' if cc > 0 else 'WARN: cache empty — touch .py files then wait 5s')
"
```

---

## A/B Testing — Methodology

Several tests compare **Mode A (Sieve OFF)** vs **Mode B (Sieve ON)** on the same prompt.

### The two modes

**Mode A — No Sieve (baseline):**
Hook removed from `.claude/settings.json`. Claude receives only your bare prompt.

**Mode B — Sieve active:**
Hook enabled, daemon running with a populated cache. Claude receives prompt + file skeletons.

### Quick-switch commands

```bash
# Disable hook (Mode A)
python3 -c "
import json
s = json.load(open('$REQUESTS/.claude/settings.json'))
s.setdefault('hooks', {}).pop('UserPromptSubmit', None)
json.dump(s, open('$REQUESTS/.claude/settings.json', 'w'), indent=2)
" && echo "✓ Mode A — Sieve OFF"

# Re-enable hook (Mode B)
cp $REQUESTS/.claude/settings.json.bak $REQUESTS/.claude/settings.json && echo "✓ Mode B — Sieve ON"
```

### Scorecard — fill in for each A/B test

```
Project: psf/requests
Prompt: [exact text]

| Dimension              | Mode A (no Sieve) | Mode B (with Sieve) |
|------------------------|-------------------|---------------------|
| Correct file located?  | Y / N / N/A       | Y / N / N/A         |
| Answer correct?        | Y / Partial / N   | Y / Partial / N     |
| Follow-ups needed      | [count]           | [count]             |
| Hallucinated anything? | Y / N             | Y / N               |
| Context size (chars)   | [measure]         | [measure]           |
| Verdict                | baseline          | Better / Same / Worse |
| Reason                 | —                 | [one sentence]      |
```

Measure context size (Mode B):
```bash
cd $REQUESTS
SIEVE_PROMPT='your prompt here' python3 $SIEVE/bin/sieve-hook --mode=prompt | wc -c
```

### Interpreting verdicts

| Verdict | Meaning | Action |
|---|---|---|
| Better | Skeleton gives Claude enough structure to navigate accurately | Ship |
| Same | Compression without quality loss — token savings with no downside | Ship |
| Worse — navigation | Skeleton stripped too much for structural reasoning | Add import references to skeletons |
| Worse — implementation | User needed full code, not just signature | Document: use `@full` for implementation tasks |

**Minimum runs to trust:** 3 different prompts per test. If 2 of 3 are Same or Better, the test passes.

### Which tests have A/B variants

| Test | A/B applicable? | Evaluation method |
|---|---|---|
| TEST-02 | Yes | Ground truth + grep |
| TEST-04 | Yes — 3 modes | Ground truth + grep |
| TEST-05 | Partial | Automated (wc -c) |
| TEST-06 | Yes | Ground truth + grep |
| TEST-07 | Yes | Visual check (is OCR text quoted?) |
| TEST-09 | Yes — 3 modes | Ground truth + grep |
| TEST-10 | Yes — primary | Objective (see TEST-10 section) |

### Evaluation rule

If Claude names a file or function, `grep` the source to verify it exists. If Claude writes code, run it. Only use human judgment when output is inherently visual (OCR quality, UI rendering).

---

## Test Cases

---

### TEST-01 — Daemon offline fallback

**Goal:** Verify the hook injects a file-tree heuristic when the daemon is not running.

**Prerequisites:** Daemon is NOT running.

**Steps:**
1. Open Claude Code in any project
2. Submit any prompt

**Expected output (injected before your prompt):**
```
[sieve] daemon offline — file-tree heuristic
  src/core/inference.py
  src/daemon/watcher.py
  ...
```

**What to check:**
- Hook exits in <50ms (no hang)
- File list matches actual project files up to MAX_DEPTH=3
- Claude responds normally

Verify: ask Claude *"What files do you know about?"* — the list should match what was injected.

---

### TEST-02 — Skeleton injection

**Goal:** Verify the cache is populated and file skeletons are injected.

**Prerequisites:** Daemon running, cache populated (touch a .py file, wait 3s), hook enabled (Mode B).

**Steps:**
1. Open Claude Code in `$REQUESTS`
2. Send this prompt:

```
Where would I add retry logic to the HTTP request flow in requests/adapters.py?
```

**Expected:** Mode B should name `HTTPAdapter.send()` without you specifying the file or class. Mode A will ask "which file?" or give a generic answer.

**What to check:**
- Function signatures present in injected context
- Function bodies replaced with `...`
- Docstrings preserved

**Verify with grep:**
```bash
grep -rn "class HTTPAdapter" $REQUESTS/requests/
# Expected: requests/adapters.py:class HTTPAdapter
```

**A/B scorecard:**

| Dimension | Mode A | Mode B |
|---|---|---|
| Named HTTPAdapter.send()? | | |
| Correct file (adapters.py)? | | |
| Follow-ups needed | | |
| Context chars | ~60 (bare prompt) | |
| Verdict | baseline | |

---

### TEST-03 — @full override

**Goal:** Verify that `@full <path>` injects the complete raw file instead of a skeleton.

**Steps:**
1. In Claude Code, send:

```
@full requests/api.py
```

**Expected:** Full file content injected — every line, no `...` placeholders.

**Manual verification:**
```bash
cd $REQUESTS
SIEVE_PROMPT='@full requests/api.py' python3 $SIEVE/bin/sieve-hook --mode=prompt | head -50
```

**What to check:**
- Full function bodies present
- Line count matches `wc -l $REQUESTS/requests/api.py`
- Ask Claude: *"What does the `get()` function do line by line?"* — it should answer from the full implementation

---

### TEST-04 — Hybrid context

**Goal:** Verify that files explicitly named in the prompt are injected in full while others stay as skeletons.

**Prerequisites:** Daemon running with populated cache.

**Steps:**
1. In Claude Code, send:

```
Look at requests/adapters.py and explain step by step what the send() method does internally.
```

**Expected stderr:**
```
[sieve] hybrid context: 1 file(s) full, 12 skeleton(s)
```

**Expected context:**
- `requests/adapters.py` → full content (with `[full]` marker in header)
- All other files → skeletons

**Three-mode A/B (this test has Mode C):**

- **Mode A:** Hook disabled — bare prompt only
- **Mode B:** Hook enabled, file NOT named — all files as skeletons
- **Mode C:** Hook enabled, file named in prompt — target file full, rest skeleton

| Dimension | Mode A — bare | Mode B — all skeleton | Mode C — hybrid |
|---|---|---|---|
| Correct method found? | | | |
| Implementation detail explained? | | | |
| Follow-ups needed | | | |
| Context chars | ~70 | | |
| Verdict vs Mode A | baseline | | |

**Expected pattern:** Mode A struggles with implementation. Mode B knows the method exists but can't explain body. Mode C explains fully.

---

### TEST-05 — Token reduction measurement

**Goal:** Quantify how much Sieve compresses the requests codebase. Target: 70–93%.

**Steps:**

```bash
cd $REQUESTS

# 1. Capture skeleton output
SIEVE_PROMPT='test' python3 $SIEVE/bin/sieve-hook --mode=prompt > /tmp/sieve-out.txt

# 2. Measure
SKEL=$(wc -c < /tmp/sieve-out.txt)
RAW=$(find . -name "*.py" | xargs wc -c 2>/dev/null | tail -1 | awk '{print $1}')

python3 -c "
skel=$SKEL; raw=$RAW
red=(1-skel/raw)*100
print(f'Skeleton:  {skel:,} chars')
print(f'Raw total: {raw:,} chars')
print(f'Reduction: {red:.1f}%')
if   70 <= red <= 93: print('PASS — in target range')
elif red < 70:        print('FAIL — below 70%')
else:                 print('WARN — above 93%, check docstrings')
"
```

**Expected reduction ranges:**
- 70–80%: normal for files with moderate function bodies
- 80–93%: excellent (heavy implementation files)
- <60%: files are mostly docstrings or constants — still correct but less dramatic

---

### TEST-06 — PostCompact re-injection

**Goal:** Verify that after `/compact`, Sieve re-injects the architectural skeleton.

**Note:** This is one of the highest-value A/B tests — context loss after compact is a real daily pain point.

**Steps:**
1. Have a long conversation until Claude compacts, or run `/compact` manually
2. Immediately after compact, send:

```
What are the main classes in this project and where are they defined? List exact file paths.
```

**Expected (Mode B):** Claude names `Session`, `PreparedRequest`, `HTTPAdapter` with correct file paths — without you re-explaining the codebase.

**A/B:**

| Dimension | Mode A — no Sieve PostCompact | Mode B — Sieve PostCompact |
|---|---|---|
| Named correct files? | | |
| Named correct classes? | | |
| Had to re-explain structure? | Y (always) | N (Sieve re-injects) |
| Verdict | baseline | |

---

### TEST-07 — OCR pipeline

**Goal:** Verify screenshot text is extracted and injected into the prompt.

**Note:** Requires Python 3.13 or earlier (rapidocr-onnxruntime doesn't support 3.14 yet). Skip if on 3.14.

**Steps:**
```bash
mkdir -p ~/.claude/image-cache
cp /path/to/any/screenshot.png ~/.claude/image-cache/
```
Then submit any prompt in Claude Code.

**Expected output appended after skeletons:**
```
[image: screenshot.png]
• def calculate_total(items):
• Returns sum after discount
```

**A/B — does Claude actually use the OCR text?**

Take a screenshot of a stack trace or error message. Run both modes:

```
What does this error mean and how do I fix it?
```

| Dimension | Mode A | Mode B |
|---|---|---|
| Claude referenced image content? | N | |
| Answer used the specific error? | N / generic | |
| Needed follow-up to paste content? | Y | |
| Verdict | baseline | |

This is a **visual check** — either the OCR text appears verbatim in Claude's response or it doesn't.

---

### TEST-08 — Graceful shutdown

**Goal:** Verify the daemon exits cleanly without corrupting `ledger.db`.

**Steps:**
1. Start the daemon
2. Save several files rapidly (create load)
3. Press `Ctrl+C` while files are being processed

**Expected daemon output:**
```
Shutdown signal received — processor exiting
```

**Verify DB integrity:**
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('$REQUESTS/ledger.db')
r = conn.execute('PRAGMA integrity_check').fetchone()
rows = conn.execute('SELECT COUNT(*) FROM context_cache').fetchone()[0]
print(f'Integrity: {r[0]}')
print(f'Cache entries preserved: {rows}')
"
```

Expected: `Integrity: ok`

---

### TEST-09 — MCP tools

**Goal:** Verify the dependency graph tools work via MCP.

**Prerequisites:**
```bash
# Check symbol_index is populated
python3 -c "
import sqlite3
conn = sqlite3.connect('$REQUESTS/ledger.db')
n = conn.execute('SELECT COUNT(*) FROM symbol_index').fetchone()[0]
print(f'symbol_index: {n} rows')
print('OK' if n > 0 else 'WARN: empty — re-save .py files and wait for daemon')
"

# Start MCP server
cd $SIEVE && python3 -m src.mcp.server
```

**Steps:**

In Claude Code (with MCP configured):
```
What are the dependencies of requests/adapters.py?
```

**Expected:** A nested dependency graph showing what `adapters.py` imports and what those files import in turn.

**Three-mode A/B:**

```
If I change the json parameter handling in requests/api.py, which other files could be affected?
```

| Dimension | Mode A — bare | Mode B — skeleton only | Mode C — MCP + skeleton |
|---|---|---|---|
| Named direct callers? | | | |
| Traced multi-hop deps? | N | | |
| Named specific files? | | | |
| Verdict | baseline | | |

Verify Claude's answer: `grep -rn "from.*api\|import.*api" $REQUESTS/requests/`

---

### TEST-10 — Answer Quality (Objective A/B)

**What this tests:** Whether Sieve makes Claude *better* — not just that it works correctly as a system.

**Setup:** Use `psf/requests` for a consistent baseline. Start fresh Claude conversations for each run — no context carryover.

---

**PROMPT-1 — Navigation (ground truth + grep)**

```
Where would I add support for a custom certificate authority in the requests library?
Reply with ONLY a JSON object: {"files": ["..."], "functions": ["..."]}
```

Ground truth (run to verify):
```bash
grep -rn "verify\|ssl\|cert\|ca_bundle" $REQUESTS/requests/ --include="*.py" -l
# Expected: adapters.py, sessions.py
grep -rn "def.*send\|def.*merge_environment" $REQUESTS/requests/adapters.py $REQUESTS/requests/sessions.py
```

**Scoring:** Mode B names `adapters.py` or `HTTPAdapter.send` → Better. Names correct files but misses one → Same. Names wrong files → Worse.

---

**PROMPT-2 — Impact analysis (precision/recall)**

```
If I rename the PreparedRequest class to CompiledRequest, what other files in the codebase
would need updating?
Reply with ONLY a JSON array of filenames: ["file1.py", "file2.py", ...]
```

Get ground truth and score automatically:
```bash
# Ground truth
grep -rl "PreparedRequest" $REQUESTS/requests/ --include="*.py" | sed "s|$REQUESTS/||" | sort

# Score Claude's answer
python3 << 'EOF'
import json
ground_truth = {'requests/adapters.py','requests/api.py','requests/auth.py',
                'requests/hooks.py','requests/models.py','requests/sessions.py'}
claude = set(json.loads(input("Paste Claude's JSON array: ")))
claude = {p.lstrip('./') for p in claude}
tp = len(ground_truth & claude)
p = tp/len(claude) if claude else 0
r = tp/len(ground_truth)
print(f"Precision: {p:.0%}  Recall: {r:.0%}")
print(f"Missing:       {ground_truth - claude}")
print(f"Hallucinated:  {claude - ground_truth}")
EOF
```

**Scoring:** Precision ≥80% AND Recall ≥80% → Better. Recall ≥50% → Same. Otherwise → Worse.

---

**PROMPT-3 — Code generation (execution-based)**

```
Write a pytest unit test for the requests.get() function that mocks the HTTP call.
The test must: import from requests directly, mock requests.adapters.HTTPAdapter.send,
assert the return value has a .status_code attribute.
Output only the Python code, no explanation.
```

Evaluate:
```bash
# Save Claude's output
cat > /tmp/test_get.py   # paste code, then Ctrl+D

# Run it
cd $REQUESTS
python3 -m pytest /tmp/test_get.py -v
echo "Exit: $?"
```

**Scoring:** Exit 0 → Better. Non-zero → Worse (skeleton gave wrong signature).

---

**PROMPT-4 — Dependency explanation (LLM-as-judge)**

```
Why does requests/sessions.py import from requests/adapters.py?
Name the specific classes and explain what would break if that import was removed.
Reply in this format:
CLASSES_IMPORTED: [comma-separated list]
REASON: [one sentence]
WOULD_BREAK: [one sentence]
```

Verify classes exist:
```bash
grep -n "from.*adapters.*import" $REQUESTS/requests/sessions.py
# Expected: from .adapters import HTTPAdapter, BaseAdapter
```

Score with Ollama:
```bash
ollama run qwen2.5-coder:1.5b "
Reference answer: sessions.py imports HTTPAdapter and BaseAdapter from adapters.py
to mount HTTP/HTTPS adapters onto the Session. Removing it breaks Session.mount() and all HTTP calls.

Claude's answer: [PASTE HERE]

Score 1-5 (5=names HTTPAdapter+BaseAdapter, explains mount(), explains what breaks).
Output ONLY: {\"score\": N}"
```

**Scoring:** Score 4–5 → Better. Score 3 → Same. Score 1–2 → Worse.

---

**PROMPT-5 — Implementation task (AST check)**

```
Add a retry_on_status parameter to requests.get() in requests/api.py that automatically
retries on HTTP 429 or 503 responses, up to 3 times.
Show only the complete modified get() function. Output only Python code.
```

Evaluate:
```bash
cat > /tmp/patched_get.py   # paste code, then Ctrl+D

python3 -c "
import ast
src = open('/tmp/patched_get.py').read()
tree = ast.parse(src)
fns = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'get']
if not fns: print('FAIL: no get() function'); exit(1)
args = [a.arg for a in fns[0].args.args] + [a.arg for a in fns[0].args.kwonlyargs]
has_param = 'retry_on_status' in args
has_loop  = any(isinstance(n, (ast.For, ast.While)) for n in ast.walk(tree))
print('✓ param' if has_param else '✗ missing retry_on_status param')
print('✓ loop'  if has_loop  else '✗ missing retry loop')
"
```

**Scoring:** Both checks pass → Better. Param present, no loop → Same. Syntax error → Worse.

---

**Aggregate scorecard:**

| Prompt | Eval method | Mode A | Mode B | Verdict |
|---|---|---|---|---|
| PROMPT-1 | grep ground truth | | | |
| PROMPT-2 | precision/recall | | | |
| PROMPT-3 | pytest exit code | PASS/FAIL | PASS/FAIL | |
| PROMPT-4 | Ollama score 1-5 | | | |
| PROMPT-5 | AST check | PASS/FAIL | PASS/FAIL | |

**Passing threshold:** 3 of 5 prompts Same or Better = tool earns its keep.

---

## Where Output Is Stored

| What | Where |
|---|---|
| Skeleton cache | `ledger.db` → `context_cache` table |
| File metadata (mtime, hash) | `ledger.db` → `ledger` table |
| Symbol index | `ledger.db` → `symbol_index` table |
| Daemon heartbeat | `ledger.db` → `daemon_heartbeat` table |
| Hook output | Injected into Claude's context — not written to disk |

**Inspect the DB:**
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('$REQUESTS/ledger.db')

print('--- context_cache (top 10 by size) ---')
for row in conn.execute('SELECT path, length(skeleton) as bytes FROM context_cache ORDER BY bytes DESC LIMIT 10').fetchall():
    print(f'  {row[1]:>8,} bytes  {row[0]}')

print()
print('--- ledger summary ---')
r = conn.execute('SELECT COUNT(*), SUM(is_ignored) FROM ledger').fetchone()
print(f'  tracked: {r[0]}  ignored: {r[1] or 0}')

print()
print('--- symbol_index sample ---')
for row in conn.execute('SELECT source_file, symbol_name FROM symbol_index LIMIT 10').fetchall():
    print(f'  {row[1]}  ({row[0]})')
"
```

---

## Coverage Map — What to Run and When

### Layer 1 — Automated (run after every code change, ~30 seconds)

```bash
cd $SIEVE
source .venv/Scripts/activate
python3 -m pytest tests/ -v --tb=short
```

| Test file | Tests | What it covers |
|---|---|---|
| `test_skeleton.py` | ~12 | AST stripping for Python, JS, TS, Markdown |
| `test_integration.py` | ~12 | SQLite WAL, upsert, ORDER BY, hook latency <50ms, token reduction >70% |
| `test_benchmark.py` | 7 | Reduction proof + semantic preservation |
| **Total** | **~31** | |

If all 31 pass, the core pipeline is healthy.

### Layer 2 — Manual functional (run before shipping, ~25 min)

| Test | Time | Priority |
|---|---|---|
| TEST-01: Daemon offline fallback | 2 min | Must |
| TEST-02: Skeleton injection | 3 min | Must |
| TEST-03: @full override | 2 min | Must |
| TEST-04: Hybrid context | 3 min | Must |
| TEST-05: Token reduction | 5 min | Must |
| TEST-06: PostCompact re-injection | 3 min | Should |
| TEST-07: OCR pipeline | 3 min | If using screenshots |
| TEST-08: Graceful shutdown | 2 min | Should |
| TEST-09: MCP dependency graph | 5 min | If using MCP |

### Layer 3 — Edge cases (~20 min)

| Edge case | How to trigger | Expected result |
|---|---|---|
| File > 100KB | `python3 -c "open('big.py','w').write('x'*110000)"` | Daemon skips it silently |
| Syntax error | Save a `.py` file with `def foo(:` | Falls back to SHA-256 hash; no crash |
| Rapid saves | Save same file 10× in 2 seconds | AST hash gate fires; re-summary called once |
| File deleted while watching | `rm requests/api.py` while daemon runs | Hook doesn't inject that file; no crash |
| Gitignored file | Add file to `.gitignore`, save it | File not in skeleton output |
| Binary with .py extension | `cp /bin/ls fake.py` | Skipped or empty skeleton; no crash |
| Ollama not running | Stop Ollama, save a file | Falls back to heuristic silently; logs: `Ollama unreachable — falling back to heuristic` |

### Minimum credible run (15 minutes, ~85% coverage)

1. `pytest tests/ -v` (~30s)
2. TEST-02 — skeleton injection (~3 min)
3. TEST-03 — `@full` override (~2 min)
4. TEST-04 — hybrid context (~3 min)
5. TEST-05 — token reduction (~5 min)
6. Edge: rapid saves + AST hash gate (~2 min)
7. Edge: syntax error — no crash (~1 min)

---

## Consistency & Scale Testing

Run this suite once after any major change to the daemon, processor, or ledger. Not needed on every commit.

### CONSISTENCY-01 — Skeleton determinism (5 runs, identical output)

```bash
cd $REQUESTS
for i in 1 2 3 4 5; do
  SIEVE_PROMPT='test' python3 $SIEVE/bin/sieve-hook --mode=prompt > /tmp/sieve_r$i.txt
done
for i in 2 3 4 5; do
  diff /tmp/sieve_r1.txt /tmp/sieve_r$i.txt && echo "Run $i: identical" || echo "Run $i: DIFFERS"
done
```

**Pass:** All diffs empty. **If diffs appear:** ORDER BY may be missing in `get_files_under()`.

---

### CONSISTENCY-02 — Latency stability (10 runs, p100 <50ms)

```bash
cd $REQUESTS
OVER=0; MAX=0
for i in $(seq 1 10); do
  S=$(date +%s%N)
  SIEVE_PROMPT='test' python3 $SIEVE/bin/sieve-hook --mode=prompt >/dev/null 2>&1
  E=$(date +%s%N)
  MS=$(( (E-S)/1000000 ))
  [ $MS -gt $MAX ] && MAX=$MS
  echo "Run $i: ${MS}ms"
  [ $MS -gt 50 ] && OVER=$((OVER+1))
done
echo "Peak: ${MAX}ms — ${OVER} run(s) over 50ms"
[ $OVER -eq 0 ] && echo "PASS" || echo "FAIL"
```

**If latency creeps up:** WAL file may be growing. Run:
```bash
python3 -c "import sqlite3; sqlite3.connect('$REQUESTS/ledger.db').execute('PRAGMA wal_checkpoint(TRUNCATE)')"
```

---

### CONSISTENCY-03 — Cross-project reduction (all three repos)

```bash
for PROJ in $REQUESTS $CLICK $HTTPX; do
  NAME=$(basename $PROJ)
  cd $PROJ
  SIEVE_PROMPT='test' python3 $SIEVE/bin/sieve-hook --mode=prompt > /tmp/sk_$NAME.txt 2>/dev/null
  SKEL=$(wc -c < /tmp/sk_$NAME.txt)
  RAW=$(find . -name "*.py" | xargs wc -c 2>/dev/null | tail -1 | awk '{print $1}')
  python3 -c "print(f'$NAME: {(1-$SKEL/$RAW)*100:.1f}% reduction ({$SKEL:,} / {$RAW:,} chars)')"
done
```

| Project | Expected reduction |
|---|---|
| requests (~20 files) | 75–90% |
| click (~50 files) | 70–88% |
| httpx (~120 files) | 70–88% |

---

### CONSISTENCY-04 — Daemon restart doesn't lose cache

```bash
cd $REQUESTS
SIEVE_PROMPT='test' python3 $SIEVE/bin/sieve-hook --mode=prompt > /tmp/before.txt

# Kill and restart daemon
kill $(pgrep -f "src/main.py") 2>/dev/null
sleep 2
python3 $SIEVE/src/main.py $REQUESTS &
sleep 3

SIEVE_PROMPT='test' python3 $SIEVE/bin/sieve-hook --mode=prompt > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt && echo "PASS: cache survived restart" || echo "CHECK: may have new files processed"
```

---

### CONSISTENCY-05 — Large project latency (httpx, ~120 files)

```bash
cd $HTTPX
find . -name "*.py" | head -50 | xargs touch
sleep 30   # give daemon time

for i in 1 2 3 4 5; do
  S=$(date +%s%N)
  SIEVE_PROMPT='test' python3 $SIEVE/bin/sieve-hook --mode=prompt >/dev/null 2>&1
  E=$(date +%s%N)
  echo "Run $i: $(( (E-S)/1000000 ))ms"
done
```

**Pass:** All runs <50ms even with 120-file corpus.

---

### CONSISTENCY-06 — AST hash gate (comment vs structural change)

```bash
cd $REQUESTS
LOG=/tmp/sieve_ast_$$.log
python3 $SIEVE/src/main.py $REQUESTS >"$LOG" 2>&1 &
DPID=$!; sleep 2

# Test 1: comment only — should NOT re-summarize
echo "# sieve hash test $(date +%s)" >> requests/api.py
sleep 5

# Test 2: new function — SHOULD re-summarize
printf "\ndef _sieve_hash_test():\n    return True\n" >> requests/api.py
sleep 7

kill $DPID 2>/dev/null; wait $DPID 2>/dev/null

SKIP=$(grep -c "AST unchanged" "$LOG" 2>/dev/null || echo 0)
UPD=$(grep -c "Cache updated" "$LOG" 2>/dev/null || echo 0)
echo "AST unchanged (skipped):  $SKIP"
echo "Cache updated (processed): $UPD"
[ "$SKIP" -ge 1 ] && [ "$UPD" -ge 1 ] && echo "PASS" || echo "FAIL: skip=$SKIP updated=$UPD"

# Restore the file
git -C $REQUESTS checkout requests/api.py 2>/dev/null || true
rm -f "$LOG"
```

Real log messages to grep for:
- `AST unchanged — no re-summary` → hash gate working (comment skipped)
- `Cache updated` → structural change processed

---

### Consistency run — time budget

| Test | Time |
|---|---|
| CONSISTENCY-01: Determinism | 3 min |
| CONSISTENCY-02: Latency stability | 2 min |
| CONSISTENCY-03: Cross-project ratios | 20 min |
| CONSISTENCY-04: Daemon restart | 3 min |
| CONSISTENCY-05: Scale latency | 10 min |
| CONSISTENCY-06: AST hash gate | 5 min |
| **Total** | **~43 min** |

---

## Diagnostic Reference

### Hook latency interpretation

| Latency | Meaning | Action |
|---|---|---|
| <25ms | Healthy — cache warm, SQLite read fast | None |
| 25–40ms | Acceptable — within <50ms target | None |
| 40–50ms | Marginal — check imports or WAL size | See below |
| >50ms | Violation | Checkpoint WAL, check filesystem |

```bash
# Force WAL checkpoint
python3 -c "import sqlite3; sqlite3.connect('$REQUESTS/ledger.db').execute('PRAGMA wal_checkpoint(TRUNCATE)')"
```

### Token reduction interpretation

| Reduction | Meaning |
|---|---|
| 80–93% | Excellent — heavy implementation files |
| 70–80% | Normal — moderate function bodies |
| 50–70% | Files are mostly signatures/docstrings — still correct |
| <50% | Markdown-heavy or data files — expected for those types |

Find which files contribute most:
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('$REQUESTS/ledger.db')
for row in conn.execute('SELECT path, length(skeleton) FROM context_cache ORDER BY 2 DESC LIMIT 10').fetchall():
    print(f'{row[1]:>8,}  {row[0]}')
"
```

### Daemon log messages (what to look for)

| Log message | Meaning |
|---|---|
| `AST unchanged — no re-summary` | Hash gate fired — comment/whitespace edit, no LLM call |
| `Cache updated` | Structural change detected — full pipeline ran |
| `Ollama unreachable — falling back to heuristic` | Ollama down or timed out — heuristic used |
| `VRAM below threshold — using heuristic` | GPU memory low — heuristic used |
| `RAM below threshold — using heuristic` | RAM low — heuristic used |
| `Shutdown signal received — processor exiting` | Clean shutdown after Ctrl+C |
| `Resources below threshold — processor sleeping` | Daemon waiting for resources to recover |

### What each test tells you

| What you learn | From |
|---|---|
| Core pipeline not broken | `pytest tests/ -v` |
| Compression ratio on actual codebase | TEST-05 |
| Cache populated, daemon healthy | TEST-02 + DB query |
| Which inference tier is being used | Daemon stdout |
| Hybrid context fires correctly | TEST-04 + stderr output |
| Symbol index usable by MCP | DB query + TEST-09 |
| Tool actually improves Claude | TEST-10 |
| DB not corrupted after crashes | TEST-08 integrity check |

**When to run what:**
- After every code change: `pytest tests/ -v`
- Before any commit touching `bin/sieve-hook`, `processor.py`, or `ledger.py`: Layer 2 manual tests
- After changes to what gets injected into context: TEST-10
- After major daemon/ledger changes: full consistency suite
