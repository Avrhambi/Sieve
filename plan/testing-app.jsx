import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  Play, Settings, Layers, Zap, Target, AlertTriangle, RefreshCw, BarChart3,
  Copy, Check, X, ChevronRight, ChevronLeft, Menu, Activity,
  Wifi, WifiOff, AlertCircle, Terminal, Clock, Trash2, Download, Upload,
  CheckCircle2
} from 'lucide-react';

// ─── Config ──────────────────────────────────────────────────────────────────
const BACKEND = 'http://localhost:8765';

const DEFAULT_CONFIG = {
  sieve:    '/c/Users/avrha/Documents/projects/Sieve-testing/sieve',
  requests: '/c/Users/avrha/Documents/projects/Sieve-testing/projects/requests',
  click:    '/c/Users/avrha/Documents/projects/Sieve-testing/projects/click',
  httpx:    '/c/Users/avrha/Documents/projects/Sieve-testing/projects/httpx',
};

const PHASES = [
  { id: 0, label: 'Automated',    icon: Play          },
  { id: 1, label: 'Setup',        icon: Settings      },
  { id: 2, label: 'Core',         icon: Layers        },
  { id: 3, label: 'Advanced',     icon: Zap           },
  { id: 4, label: 'Answer Quality', icon: Target      },
  { id: 5, label: 'Edge Cases',   icon: AlertTriangle },
  { id: 6, label: 'Consistency',  icon: RefreshCw     },
];

// ─── Test Definitions ─────────────────────────────────────────────────────────
function buildTests(c) {
  const hook     = `python3 "${c.sieve}/bin/sieve-hook"`;
  const hookCfg  = `${c.requests}/.claude/settings.json`;
  const hookBak  = `${c.requests}/.claude/settings.json.bak`;

  const disableA = `python3 -c "import json; s=json.load(open('${hookCfg}')); s.setdefault('hooks',{}).pop('UserPromptSubmit',None); json.dump(s,open('${hookCfg}','w'),indent=2)" && echo "✓ Mode A ready — Sieve DISABLED"`;
  const enableB  = `cp "${hookBak}" "${hookCfg}" && echo "✓ Mode B ready — Sieve ENABLED"`;

  return [
    // ── Phase 0: Automated ───────────────────────────────────────────────────
    {
      id: 'pytest', phase: 0,
      name: 'pytest — Full suite (31 tests)',
      description: 'Validates the core pipeline. Run first — if any fail, stop here.',
      type: 'shell',
      cmd: `cd "${c.sieve}" && python3 -m pytest tests/ -v --tb=short 2>&1`,
      timeout: 90,
      score: (out, rc) => rc === 0
        ? { status: 'pass', msg: out.match(/\d+ passed/)?.[0] || 'All passed' }
        : { status: 'fail', msg: (out.match(/FAILED [^\n]+/g) || []).slice(0, 2).join(' | ') || 'Tests failed' },
    },
    {
      id: 'benchmark', phase: 0,
      name: 'pytest — Benchmark (74–89% reduction)',
      description: 'Proves token reduction with semantic preservation across Python/JS/TS.',
      type: 'shell',
      cmd: `cd "${c.sieve}" && python3 -m pytest tests/test_benchmark.py -v -s 2>&1`,
      timeout: 30,
      score: (out, rc) => rc === 0
        ? { status: 'pass', msg: '74–89% reduction confirmed' }
        : { status: 'fail', msg: 'Benchmark assertions failed' },
    },

    // ── Phase 1: Setup ───────────────────────────────────────────────────────
    {
      id: 'p1-check', phase: 1,
      name: 'Verify all repos exist',
      description: 'Checks sieve, requests, click, and httpx are cloned at the configured paths.',
      type: 'shell',
      cmd: [
        `[ -d "${c.sieve}"    ] && echo "✓ sieve"    || echo "✗ sieve MISSING"`,
        `[ -d "${c.requests}" ] && echo "✓ requests" || echo "✗ requests MISSING — git clone https://github.com/psf/requests ${c.requests}"`,
        `[ -d "${c.click}"    ] && echo "✓ click"    || echo "✗ click MISSING — git clone https://github.com/pallets/click ${c.click}"`,
        `[ -d "${c.httpx}"    ] && echo "✓ httpx"    || echo "✗ httpx MISSING — git clone https://github.com/encode/httpx ${c.httpx}"`,
      ].join('\n'),
      timeout: 10,
      score: (out) => out.includes('✗')
        ? { status: 'fail', msg: 'Some repos missing — see output' }
        : { status: 'pass', msg: 'All four repos found' },
    },
    {
      id: 'p1-hook', phase: 1,
      name: 'Install Claude hook in requests repo',
      description: 'Creates .claude/settings.json with hook config and saves a backup for A/B switching.',
      type: 'shell',
      cmd: `mkdir -p "${c.requests}/.claude"
cat > "${c.requests}/.claude/settings.json" << 'EOF'
{
  "hooks": {
    "UserPromptSubmit": [{"hooks": [{"command": "python3 ${c.sieve}/bin/sieve-hook --mode=prompt", "type": "command"}]}],
    "PostCompact":      [{"hooks": [{"command": "python3 ${c.sieve}/bin/sieve-hook --mode=compact", "type": "command"}]}]
  }
}
EOF
cp "${c.requests}/.claude/settings.json" "${hookBak}"
echo "PASS: Hook installed + backup saved at ${hookBak}"`,
      timeout: 10,
      score: (out, rc) => out.includes('PASS')
        ? { status: 'pass', msg: 'Hook ready, backup created' }
        : { status: 'fail', msg: out.slice(-120) },
    },
    {
      id: 'p1-cache', phase: 1,
      name: 'Populate cache (daemon must be running)',
      description: 'Touches all .py files to trigger daemon processing. Start daemon first.',
      type: 'shell',
      prereq: 'Start the daemon: python3 src/main.py /path/to/requests',
      cmd: `find "${c.requests}" -name "*.py" | xargs touch
echo "Waiting 12s for daemon to process..."
sleep 12
COUNT=$(python3 -c "import sqlite3,os; db='${c.requests}/ledger.db'; conn=sqlite3.connect(db) if os.path.exists(db) else None; print(conn.execute('SELECT COUNT(*) FROM context_cache').fetchone()[0] if conn else 0)" 2>/dev/null || echo 0)
[ "$COUNT" -gt 5 ] && echo "PASS: Cache has $COUNT entries" || echo "WARN: Only $COUNT entries — start daemon first"`,
      timeout: 25,
      score: (out) => out.includes('PASS')
        ? { status: 'pass', msg: out.match(/Cache has \d+ entries/)?.[0] || 'Populated' }
        : { status: 'warn', msg: 'Start daemon then re-run' },
    },

    // ── Phase 2: Core ────────────────────────────────────────────────────────
    {
      id: 'test-01', phase: 2,
      name: 'TEST-01 — Daemon offline fallback',
      description: 'Hook must output file-tree heuristic when daemon is not running.',
      type: 'shell',
      prereq: 'Stop the daemon before running.',
      cmd: `cd "${c.requests}" && SIEVE_PROMPT='list files' ${hook} --mode=prompt 2>&1`,
      timeout: 10,
      score: (out, rc) => (out.includes('daemon offline') || out.includes('file-tree heuristic'))
        ? { status: 'pass', msg: 'Fallback triggered — file list injected' }
        : { status: rc === 0 ? 'warn' : 'fail', msg: rc === 0 ? 'Daemon may still be running' : `Exit ${rc}` },
    },
    {
      id: 'test-02', phase: 2,
      name: 'TEST-02 — Skeleton injection',
      description: 'Mode B should point to HTTPAdapter.send without you naming it. Mode A guesses.',
      type: 'ab',
      prompt: 'Where would I add retry logic to the HTTP request flow in requests/adapters.py?',
      setupA: disableA, setupB: enableB,
      groundTruth: 'Expected keywords: HTTPAdapter, adapters.py, .send()',
      autoScore: (a, b) => {
        if (!a || !b) return null;
        const kw = ['httpadapter', 'adapters.py', '.send(', 'httpadapter.send'];
        const bHits = kw.filter(k => b.toLowerCase().includes(k)).length;
        const aHits = kw.filter(k => a.toLowerCase().includes(k)).length;
        return bHits > aHits ? 'better' : bHits === aHits ? 'same' : 'worse';
      },
    },
    {
      id: 'test-03', phase: 2,
      name: 'TEST-03 — !full override',
      description: 'The !full command injects the complete raw file — bodies present, no ... placeholders.',
      type: 'shell',
      cmd: `cd "${c.requests}"
OUT=$(SIEVE_PROMPT='!full requests/api.py' ${hook} --mode=prompt 2>&1)
LINES=$(echo "$OUT" | wc -l)
DOTS=$(echo "$OUT" | grep -c '    \.\.\.' || true)
echo "Lines injected: $LINES"
echo "Skeleton markers ('...'): $DOTS"
echo "$OUT" | head -25
[ "$LINES" -gt 50 ] && echo "PASS: Full file injected ($LINES lines)" || echo "FAIL: Only $LINES lines — may still be skeleton"`,
      timeout: 10,
      score: (out) => out.includes('PASS')
        ? { status: 'pass', msg: out.match(/Full file injected \(\d+ lines\)/)?.[0] || 'Full file' }
        : { status: 'fail', msg: 'Too few lines — skeleton may still be active' },
    },
    {
      id: 'test-04', phase: 2,
      name: 'TEST-04 — Hybrid context',
      description: 'Naming a file injects it in full. Mode B explains impl details, Mode A cannot.',
      type: 'ab',
      prompt: 'Look at requests/adapters.py and explain step by step what the send() method does internally.',
      setupA: disableA, setupB: enableB,
      groundTruth: 'Expected implementation keywords: urllib3, pool, connection, timeout, socket, ssl',
      autoScore: (a, b) => {
        if (!a || !b) return null;
        const impl = ['urllib3', 'connection', 'pool', 'timeout', 'socket', 'ssl', 'chunked'];
        const bHits = impl.filter(w => b.toLowerCase().includes(w)).length;
        const aHits = impl.filter(w => a.toLowerCase().includes(w)).length;
        return bHits > aHits + 1 ? 'better' : bHits >= aHits ? 'same' : 'worse';
      },
    },
    {
      id: 'test-05', phase: 2,
      name: 'TEST-05 — Token reduction',
      description: 'Skeleton must achieve ≥70% reduction. Target: 10–30% of raw source size.',
      type: 'shell',
      cmd: `SIEVE_OUT=$(SIEVE_PROMPT='test' ${hook} --mode=prompt 2>/dev/null)
SKEL=$(echo "$SIEVE_OUT" | wc -c)
RAW=$(find "${c.requests}" -name "*.py" | xargs wc -c 2>/dev/null | tail -1 | awk '{print $1}')
python3 -c "
s=$SKEL; r=$RAW
if r == 0: print('FAIL: could not read raw size'); exit(1)
red=(1-s/r)*100
print(f'Skeleton:  {s:>8,} chars')
print(f'Raw total: {r:>8,} chars')
print(f'Reduction: {red:.1f}%')
if   70 <= red <= 95: print('PASS: in target range (70–95%)')
elif red < 70:        print('FAIL: below 70% target')
else:                 print('WARN: above 95% — check docstrings')
"`,
      timeout: 15,
      score: (out) => {
        const red = parseFloat(out.match(/Reduction: ([\d.]+)/)?.[1]);
        if (isNaN(red)) return { status: 'fail', msg: 'Parse error' };
        if (red >= 70 && red <= 95) return { status: 'pass', msg: `${red.toFixed(1)}% reduction ✓` };
        return { status: red < 70 ? 'fail' : 'warn', msg: `${red.toFixed(1)}% — out of range` };
      },
    },

    // ── Phase 3: Advanced ────────────────────────────────────────────────────
    {
      id: 'test-06', phase: 3,
      name: 'TEST-06 — PostCompact re-injection',
      description: 'After /compact, Mode B re-injects skeletons and still knows the codebase. Mode A goes blank.',
      type: 'ab',
      prompt: 'What are the main classes in this project and where are they defined? List exact file paths.',
      setupA: `python3 -c "import json; s=json.load(open('${hookCfg}')); [s.setdefault('hooks',{}).pop(k,None) for k in ['UserPromptSubmit','PostCompact']]; json.dump(s,open('${hookCfg}','w'),indent=2)" && echo "✓ Mode A ready — ALL hooks disabled"`,
      setupB: enableB,
      note: 'Run /compact in Claude first, then send this prompt.',
      groundTruth: 'Expected: Session, Request, Response, PreparedRequest, HTTPAdapter + their file paths',
      autoScore: (a, b) => {
        if (!a || !b) return null;
        const cls = ['session', 'preparedrequest', 'httpadapter', 'adapters', 'sessions'];
        const bH = cls.filter(c => b.toLowerCase().includes(c)).length;
        const aH = cls.filter(c => a.toLowerCase().includes(c)).length;
        return bH > aH ? 'better' : bH === aH ? 'same' : 'worse';
      },
    },
    {
      id: 'test-08', phase: 3,
      name: 'TEST-08 — DB integrity after shutdown',
      description: 'ledger.db must pass PRAGMA integrity_check after Ctrl+C.',
      type: 'shell',
      prereq: 'Kill the daemon (Ctrl+C) first, then run this check.',
      cmd: `python3 -c "
import sqlite3, os
db = '${c.requests}/ledger.db'
if not os.path.exists(db):
    print('SKIP: no ledger.db yet (run some tests with daemon first)')
    exit(0)
conn = sqlite3.connect(db)
r = conn.execute('PRAGMA integrity_check').fetchone()
if r[0] == 'ok':
    rows = conn.execute('SELECT COUNT(*) FROM context_cache').fetchone()[0]
    print(f'PASS: DB integrity OK — {rows} cache entries preserved')
else:
    print(f'FAIL: {r[0]}')
"`,
      timeout: 10,
      score: (out) => out.includes('PASS')
        ? { status: 'pass', msg: out.match(/\d+ cache entries/)?.[0] || 'DB OK' }
        : out.includes('SKIP')
          ? { status: 'warn', msg: 'No DB yet' }
          : { status: 'fail', msg: 'DB corrupted' },
    },

    // ── Phase 4: Answer Quality ──────────────────────────────────────────────
    {
      id: 't10-p1', phase: 4,
      name: 'PROMPT-1 — Navigation (keyword check)',
      description: 'Mode B should name adapters.py + HTTPAdapter.send. Auto-checked via keyword matching.',
      type: 'ab',
      prompt: 'Where would I add support for a custom certificate authority in the requests library?\nReply with ONLY a JSON object: {"files": ["..."], "functions": ["..."]}',
      setupA: disableA, setupB: enableB,
      groundTruth: '{"files":["requests/adapters.py","requests/sessions.py"],"functions":["HTTPAdapter.send","Session.merge_environment_settings"]}',
      autoScore: (a, b) => {
        if (!b) return null;
        const gt = ['adapters.py', 'httpadapter', 'send', 'merge_environment'];
        const bH = gt.filter(k => b.toLowerCase().includes(k)).length;
        const aH = gt.filter(k => (a || '').toLowerCase().includes(k)).length;
        if (bH >= 3) return 'better';
        if (bH >= 1 && bH >= aH) return 'same';
        return 'worse';
      },
    },
    {
      id: 't10-p2', phase: 4,
      name: 'PROMPT-2 — Impact analysis (precision / recall)',
      description: 'Paste Claude\'s JSON array. Click "Score" to run automated precision/recall against grep.',
      type: 'ab-precision',
      prompt: 'If I rename the PreparedRequest class to CompiledRequest, what other files in the codebase would need updating?\nReply with ONLY a JSON array: ["file1.py", "file2.py", ...]',
      setupA: disableA, setupB: enableB,
      groundTruthCmd: `cd "${c.requests}" && grep -rl 'PreparedRequest' . --include="*.py" | sed 's|^./||' | sort`,
    },
    {
      id: 't10-p3', phase: 4,
      name: 'PROMPT-3 — Write a test (run pytest)',
      description: 'Paste Claude\'s generated test code. Click "Run Code" to execute pytest.',
      type: 'ab-code',
      prompt: 'Write a pytest unit test for requests.get() that mocks the HTTP call.\nMust: import from requests directly, mock requests.adapters.HTTPAdapter.send, assert .status_code exists.\nOutput ONLY the Python code.',
      setupA: disableA, setupB: enableB,
      runCode: (code, mode) =>
        `cat > /tmp/t10p3_${mode}.py << 'PYEOF'\n${code}\nPYEOF\ncd "${c.requests}" && python3 -m pytest /tmp/t10p3_${mode}.py -v --tb=short 2>&1`,
      scoreCode: (out, rc) => rc === 0
        ? { status: 'pass', msg: 'pytest passed ✓' }
        : { status: 'fail', msg: out.match(/E\s+\w+Error[^\n]*/)?.[0]?.slice(0, 60) || 'pytest failed' },
    },
    {
      id: 't10-p5', phase: 4,
      name: 'PROMPT-5 — Implementation (ast + pytest)',
      description: 'Paste Claude\'s modified get() function. Click "Run Code" to validate parameter + loop.',
      type: 'ab-code',
      prompt: 'Add a retry_on_status parameter to requests.get() that retries on HTTP 429 or 503, up to 3 times.\nShow only the complete modified get() function.\nOutput ONLY Python code.',
      setupA: disableA, setupB: enableB,
      runCode: (code, mode) =>
        `cat > /tmp/t10p5_${mode}.py << 'PYEOF'\n${code}\nPYEOF\npython3 - << 'EOF'\nimport ast, sys\ntry: tree=ast.parse(open('/tmp/t10p5_${mode}.py').read())\nexcept SyntaxError as e: print(f'FAIL: syntax error — {e}'); sys.exit(1)\nfns=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='get']\nif not fns: print('FAIL: no get() function found'); sys.exit(1)\nargs=[a.arg for a in fns[0].args.args+fns[0].args.kwonlyargs]\nprint('PASS: retry_on_status present' if 'retry_on_status' in args else 'FAIL: retry_on_status missing')\nsrc=open('/tmp/t10p5_${mode}.py').read().lower()\nprint('PASS: retry loop found' if any(k in src for k in ['for ','while ','range(']) else 'WARN: no retry loop')\nEOF`,
      scoreCode: (out, rc) => {
        const allPass = (out.match(/PASS/g) || []).length;
        const fails = (out.match(/FAIL/g) || []).length;
        if (fails > 0) return { status: 'fail', msg: out.match(/FAIL:[^\n]*/)?.[0]?.slice(0, 60) || 'Failed' };
        return allPass >= 2 ? { status: 'pass', msg: 'Parameter + loop verified ✓' } : { status: 'warn', msg: 'Partial — check output' };
      },
    },

    // ── Phase 5: Edge Cases ──────────────────────────────────────────────────
    {
      id: 'edge-big', phase: 5,
      name: 'Big file (>100KB) — silently skipped',
      type: 'shell',
      cmd: `dd if=/dev/zero bs=1024 count=150 2>/dev/null | tr '\\0' 'x' > "${c.requests}/bigfile_test.py"
sleep 3
OUT=$(SIEVE_PROMPT='test' ${hook} --mode=prompt 2>/dev/null)
rm -f "${c.requests}/bigfile_test.py"
echo "$OUT" | grep -q "bigfile_test" && echo "FAIL: big file appeared in context" || echo "PASS: big file correctly skipped"`,
      timeout: 20,
      score: (out) => out.includes('PASS') ? { status: 'pass', msg: 'Big file skipped' } : { status: 'fail', msg: 'Big file in context' },
    },
    {
      id: 'edge-syntax', phase: 5,
      name: 'Syntax error — no crash',
      type: 'shell',
      cmd: `echo "def foo(:" > "${c.requests}/syntax_test.py"
sleep 3
SIEVE_PROMPT='test' ${hook} --mode=prompt > /dev/null 2>&1
RC=$?
rm -f "${c.requests}/syntax_test.py"
[ $RC -eq 0 ] && echo "PASS: hook exits cleanly after syntax error file" || echo "FAIL: hook crashed (exit $RC)"`,
      timeout: 15,
      score: (out) => out.includes('PASS') ? { status: 'pass', msg: 'No crash' } : { status: 'fail', msg: 'Crash detected' },
    },
    {
      id: 'edge-rapid', phase: 5,
      name: 'Rapid saves — AST hash gate fires',
      type: 'shell',
      prereq: 'Daemon must be running with visible logs.',
      cmd: `LOG=/tmp/sieve_rapid_$$.log
python3 "${c.sieve}/src/main.py" "${c.requests}" >"$LOG" 2>&1 &
DPID=$!; sleep 2
for i in $(seq 1 10); do touch "${c.requests}/requests/api.py"; done
sleep 8
kill $DPID 2>/dev/null; wait $DPID 2>/dev/null
SKIP=$(grep -c "AST unchanged" "$LOG" 2>/dev/null || echo 0)
UPD=$(grep -c "Cache updated" "$LOG" 2>/dev/null || echo 0)
echo "AST unchanged (skipped): $SKIP"
echo "Cache updated (Ollama):  $UPD"
rm -f "$LOG"
[ "$SKIP" -ge 9 ] && echo "PASS: hash gate fired $SKIP times (saved $SKIP Ollama calls)" || echo "WARN: only $SKIP skips — gate may not be working"`,
      timeout: 25,
      score: (out) => {
        const skip = parseInt(out.match(/skipped\): (\d+)/)?.[1] || 0);
        return skip >= 9
          ? { status: 'pass', msg: `Gate fired ${skip}×` }
          : { status: 'warn', msg: `Only ${skip} skips` };
      },
    },

    // ── Phase 6: Consistency ─────────────────────────────────────────────────
    {
      id: 'cons-01', phase: 6,
      name: 'CONSISTENCY-01 — Skeleton determinism (5 runs)',
      type: 'shell',
      cmd: `cd "${c.requests}"
for i in 1 2 3 4 5; do
  SIEVE_PROMPT='test' ${hook} --mode=prompt > /tmp/sieve_r$i.txt 2>/dev/null
  sleep 1
done
DIFFS=0
for i in 2 3 4 5; do
  diff -q /tmp/sieve_r1.txt /tmp/sieve_r$i.txt >/dev/null 2>&1 || DIFFS=$((DIFFS+1))
done
[ $DIFFS -eq 0 ] && echo "PASS: All 5 runs produce identical output" || echo "FAIL: $DIFFS run(s) differ"`,
      timeout: 30,
      score: (out) => out.includes('PASS') ? { status: 'pass', msg: '5/5 identical' } : { status: 'fail', msg: 'Non-deterministic output' },
    },
    {
      id: 'cons-02', phase: 6,
      name: 'CONSISTENCY-02 — Latency stability (10 runs, p100 <50ms)',
      type: 'shell',
      cmd: `cd "${c.requests}"
OVER=0; MAX=0
for i in $(seq 1 10); do
  S=$(date +%s%N)
  SIEVE_PROMPT='test' ${hook} --mode=prompt >/dev/null 2>&1
  E=$(date +%s%N)
  MS=$(( (E-S)/1000000 ))
  [ $MS -gt $MAX ] && MAX=$MS
  echo "Run $i: ${MS}ms$([ $MS -gt 50 ] && echo ' ← OVER LIMIT')"
  [ $MS -gt 50 ] && OVER=$((OVER+1))
done
echo "---"
echo "Peak: ${MAX}ms"
[ $OVER -eq 0 ] && echo "PASS: All 10 runs under 50ms" || echo "FAIL: $OVER run(s) exceeded 50ms"`,
      timeout: 60,
      score: (out) => {
        const max = parseInt(out.match(/Peak: (\d+)ms/)?.[1] || 0);
        return out.includes('PASS')
          ? { status: 'pass', msg: `p100 = ${max}ms` }
          : { status: 'fail', msg: `Peak = ${max}ms > 50ms` };
      },
    },
    {
      id: 'cons-03', phase: 6,
      name: 'CONSISTENCY-03 — Cross-project reduction (requests/click/httpx)',
      type: 'shell',
      cmd: `for PROJECT in "${c.requests}" "${c.click}" "${c.httpx}"; do
  NAME=$(basename "$PROJECT")
  find "$PROJECT" -name "*.py" | head -30 | xargs touch 2>/dev/null
  sleep 8
  SKEL=$(SIEVE_PROMPT='test' ${hook} --mode=prompt 2>/dev/null | wc -c)
  RAW=$(find "$PROJECT" -name "*.py" | head -30 | xargs wc -c 2>/dev/null | tail -1 | awk '{print $1}')
  python3 -c "
s=$SKEL; r=$RAW; n='$NAME'
if r==0: print(f'{n}: SKIP (no files)'); exit()
red=(1-s/r)*100
print(f'{n}: {red:.1f}% reduction (skeleton {s:,} / raw {r:,})')
print(f'  PASS' if red>=70 else '  WARN: below 70%')
"
done`,
      timeout: 90,
      score: (out) => {
        const pct = out.match(/\d+\.\d+% reduction/g) || [];
        const all = pct.every(p => parseFloat(p) >= 70);
        return all && pct.length === 3
          ? { status: 'pass', msg: pct.map(p => p.split('%')[0] + '%').join(' | ') }
          : { status: 'warn', msg: pct.length < 3 ? 'Some projects not populated' : 'One or more below 70%' };
      },
    },
    {
      id: 'cons-06', phase: 6,
      name: 'CONSISTENCY-06 — AST hash gate (comment vs structural change)',
      type: 'shell',
      cmd: `cd "${c.requests}"
LOG=/tmp/sieve_ast_$$.log
python3 "${c.sieve}/src/main.py" "${c.requests}" >"$LOG" 2>&1 &
DPID=$!; sleep 2

# Test 1: comment only — should NOT call Ollama
echo "# sieve hash test $(date +%s)" >> requests/api.py
sleep 5

# Test 2: new function — SHOULD call Ollama
printf "\\ndef _sieve_hash_test():\\n    return True\\n" >> requests/api.py
sleep 7

kill $DPID 2>/dev/null; wait $DPID 2>/dev/null
SKIP=$(grep -c "AST unchanged" "$LOG" 2>/dev/null || echo 0)
UPD=$(grep -c "Cache updated" "$LOG" 2>/dev/null || echo 0)
echo "AST unchanged (skipped): $SKIP"
echo "Cache updated (processed): $UPD"
rm -f "$LOG"
git -C "${c.requests}" checkout requests/api.py 2>/dev/null || true
[ "$SKIP" -ge 1 ] && [ "$UPD" -ge 1 ] && echo "PASS: comment skipped, structural change processed" || echo "FAIL: skip=$SKIP update=$UPD"`,
      timeout: 30,
      score: (out) => out.includes('PASS')
        ? { status: 'pass', msg: 'Hash gate working correctly' }
        : { status: 'fail', msg: out.match(/skip=\d+ update=\d+/)?.[0] || 'Gate not working' },
    },
  ];
}

// ─── API ──────────────────────────────────────────────────────────────────────
async function callBackend(cmd, timeout = 60) {
  const res = await fetch(`${BACKEND}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command: cmd, timeout }),
  });
  const d = await res.json();
  return {
    output: (d.stdout || '') + (d.stderr ? '\n' + d.stderr : ''),
    returncode: d.returncode,
    ok: d.ok,
  };
}

// ─── Small UI pieces ──────────────────────────────────────────────────────────
const Terminal = ({ output, status }) => (
  <div className={`bg-[#0a0d14] rounded-lg border text-xs font-mono p-4 whitespace-pre-wrap overflow-auto max-h-72 leading-relaxed mt-3
    ${status === 'pass' ? 'border-emerald-900' : status === 'fail' ? 'border-red-900' : status === 'warn' ? 'border-amber-900' : 'border-slate-800'}`}>
    {output
      ? <span className="text-slate-300">{output}</span>
      : <span className="text-slate-600 italic">No output yet — click Run</span>}
  </div>
);

const Badge = ({ status, msg }) => {
  const s = {
    pass:    'bg-emerald-500/10 text-emerald-400 border-emerald-700/50',
    fail:    'bg-red-500/10    text-red-400    border-red-700/50',
    warn:    'bg-amber-500/10  text-amber-400  border-amber-700/50',
    better:  'bg-emerald-500/10 text-emerald-400 border-emerald-700/50',
    same:    'bg-blue-500/10   text-blue-400   border-blue-700/50',
    worse:   'bg-red-500/10    text-red-400    border-red-700/50',
    partial: 'bg-purple-500/10 text-purple-400 border-purple-700/50',
  };
  const ic = { pass: '✓', fail: '✗', warn: '⚠', better: '↑', same: '=', worse: '↓', partial: '~' };
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-medium ${s[status] || 'bg-slate-800 text-slate-500 border-slate-700'}`}>
      {ic[status] || '○'} {msg || status || '—'}
    </span>
  );
};

const CopyBtn = ({ text, label = 'Copy' }) => {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={() => navigator.clipboard.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 2000); }).catch(() => {})}
      className="flex items-center gap-1.5 px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 rounded-lg transition-colors shrink-0"
    >
      {done ? <><Check size={11} className="text-emerald-400" /> Copied!</> : <><Copy size={11} /> {label}</>}
    </button>
  );
};

const RunBtn = ({ onClick, running, label = 'Run' }) => (
  <button
    onClick={onClick}
    disabled={running}
    className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
  >
    {running
      ? <><RefreshCw size={13} className="animate-spin" /> Running...</>
      : <><Play size={13} /> {label}</>}
  </button>
);

// ─── Shell Test Card ──────────────────────────────────────────────────────────
const ShellCard = ({ test, result, running, onRun }) => {
  const score = result?.score;
  const borderColor = score?.status === 'pass' ? 'border-emerald-900/60'
    : score?.status === 'fail' ? 'border-red-900/60'
    : 'border-slate-800 hover:border-blue-500/20';

  return (
    <div className={`bg-[#11151d] border rounded-2xl p-6 transition-all ${borderColor}`}>
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold text-white text-base">{test.name}</h3>
            {score && <Badge status={score.status} msg={score.msg} />}
          </div>
          <p className="text-sm text-slate-400 mt-1">{test.description}</p>
          {test.prereq && (
            <div className="mt-2 flex items-center gap-1.5 text-amber-400 text-xs">
              <AlertCircle size={11} /> {test.prereq}
            </div>
          )}
        </div>
        <RunBtn onClick={onRun} running={running} />
      </div>

      <div className="flex items-center justify-between mt-2 mb-1">
        <span className="text-xs text-slate-600 font-mono">command</span>
        <CopyBtn text={test.cmd} />
      </div>
      <pre className="text-xs text-slate-600 font-mono bg-black/20 rounded-lg px-3 py-2 overflow-x-auto max-h-12 whitespace-pre">
        {test.cmd.split('\n')[0]}{test.cmd.includes('\n') ? '\n…' : ''}
      </pre>

      {result?.output && <Terminal output={result.output} status={score?.status} />}
      {result?.timestamp && (
        <p className="text-xs text-slate-700 mt-2 flex items-center gap-1">
          <Clock size={10} /> {new Date(result.timestamp).toLocaleTimeString()}
        </p>
      )}
    </div>
  );
};

// ─── AB Side-by-Side Card ─────────────────────────────────────────────────────
const ABCard = ({ test, result, running, onSetup, onSaveText, onRunCode, onSetVerdict, onScorePrecision }) => {
  const [aText, setAText] = useState(result?.modeA?.text || '');
  const [bText, setBText] = useState(result?.modeB?.text || '');

  useEffect(() => { setAText(result?.modeA?.text || ''); }, [result?.modeA?.text]);
  useEffect(() => { setBText(result?.modeB?.text || ''); }, [result?.modeB?.text]);

  const autoScore = test.autoScore ? test.autoScore(aText, bText) : null;
  const verdict = result?.verdict || autoScore;

  const ModePanel = ({ mode, label, setupDone, codeOut, codeScore, text, setText }) => {
    const modeColor = mode === 'modeA'
      ? 'border-slate-700/50 bg-slate-900/20'
      : 'border-blue-800/30 bg-blue-950/10';
    const labelColor = mode === 'modeA' ? 'text-slate-400' : 'text-blue-400';

    return (
      <div className={`flex-1 min-w-0 border rounded-xl p-4 ${modeColor}`}>
        <div className="flex items-center justify-between mb-3">
          <span className={`text-xs font-bold uppercase tracking-wider ${labelColor}`}>{label}</span>
          <button
            onClick={() => onSetup(test.id, mode, mode === 'modeA' ? test.setupA : test.setupB)}
            disabled={running[`${test.id}-${mode}-setup`]}
            className={`flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-lg font-medium transition-colors
              ${setupDone ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-700/40' : 'bg-slate-800 hover:bg-slate-700 text-slate-300'}`}
          >
            {running[`${test.id}-${mode}-setup`]
              ? <><RefreshCw size={11} className="animate-spin" /> Setting up…</>
              : setupDone
                ? <><Check size={11} /> Ready</>
                : <><Settings size={11} /> Set Mode</>}
          </button>
        </div>

        {/* Prompt */}
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-slate-600">prompt</span>
          <CopyBtn text={test.prompt} label="Copy prompt" />
        </div>
        <div className="bg-black/30 rounded-lg p-2 mb-3">
          <p className="text-xs text-slate-500 font-mono leading-relaxed line-clamp-3">{test.prompt}</p>
        </div>

        {/* Paste area */}
        <label className="text-xs text-slate-500 mb-1 block">paste Claude's response:</label>
        <textarea
          value={text}
          onChange={e => {
            setText(e.target.value);
            onSaveText(test.id, mode, e.target.value);
          }}
          placeholder="Paste Claude's response here after sending the prompt…"
          className="w-full bg-black/40 border border-slate-700/40 rounded-lg p-3 text-xs text-slate-300 font-mono h-32 resize-y focus:outline-none focus:border-blue-600/50 placeholder-slate-700"
        />

        {/* For code tests: run button + output */}
        {test.type === 'ab-code' && text && (
          <div className="mt-3">
            <button
              onClick={() => onRunCode(test.id, mode, test.runCode(text, mode === 'modeA' ? 'a' : 'b'), test.scoreCode, test.timeout)}
              disabled={running[`${test.id}-${mode}-code`]}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-600/80 hover:bg-purple-500 text-white text-xs rounded-lg font-medium transition-colors"
            >
              {running[`${test.id}-${mode}-code`]
                ? <><RefreshCw size={11} className="animate-spin" /> Running code…</>
                : <><Terminal size={11} /> Run Code</>}
            </button>
            {codeOut && <Terminal output={codeOut} status={codeScore?.status} />}
            {codeScore && <div className="mt-2"><Badge status={codeScore.status} msg={codeScore.msg} /></div>}
          </div>
        )}

        {/* For precision tests: score button */}
        {test.type === 'ab-precision' && text && (
          <div className="mt-3">
            <button
              onClick={() => onScorePrecision(test.id, mode, text, test.groundTruthCmd)}
              disabled={running[`${test.id}-${mode}-score`]}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-600/80 hover:bg-purple-500 text-white text-xs rounded-lg font-medium transition-colors"
            >
              {running[`${test.id}-${mode}-score`]
                ? <><RefreshCw size={11} className="animate-spin" /> Scoring…</>
                : <><BarChart3 size={11} /> Score precision/recall</>}
            </button>
            {result?.[mode]?.precision != null && (
              <div className="mt-2 space-y-1 text-xs">
                <div className="flex gap-4">
                  <span className="text-slate-400">Precision: <span className="text-white font-mono">{(result[mode].precision * 100).toFixed(0)}%</span></span>
                  <span className="text-slate-400">Recall: <span className="text-white font-mono">{(result[mode].recall * 100).toFixed(0)}%</span></span>
                </div>
                {result[mode].missing?.length > 0 && <p className="text-red-400">Missing: {result[mode].missing.join(', ')}</p>}
                {result[mode].extra?.length > 0 && <p className="text-amber-400">Hallucinated: {result[mode].extra.join(', ')}</p>}
                <Badge status={result[mode].precStatus} msg={result[mode].precStatus === 'pass' ? 'P≥80% R≥80%' : result[mode].precStatus === 'partial' ? 'R≥50%' : 'Low recall'} />
              </div>
            )}
          </div>
        )}

        {/* Auto keyword highlight */}
        {test.autoScore && text && mode === 'modeB' && (
          <div className="mt-2 text-xs text-slate-500">
            {autoScore && <Badge status={autoScore} msg={autoScore.charAt(0).toUpperCase() + autoScore.slice(1)} />}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="bg-[#11151d] border border-slate-800 hover:border-blue-500/20 rounded-2xl p-6 transition-all">
      <div className="mb-4">
        <div className="flex items-center gap-2 flex-wrap mb-1">
          <h3 className="font-semibold text-white text-base">{test.name}</h3>
          {verdict && <Badge status={verdict} msg={verdict.charAt(0).toUpperCase() + verdict.slice(1)} />}
        </div>
        <p className="text-sm text-slate-400">{test.description}</p>
        {test.note && (
          <div className="mt-1 flex items-center gap-1.5 text-amber-400 text-xs">
            <AlertCircle size={11} /> {test.note}
          </div>
        )}
      </div>

      {/* Side-by-side panels */}
      <div className="flex gap-4 flex-col lg:flex-row">
        <ModePanel
          mode="modeA"
          label="Mode A — Sieve OFF"
          setupDone={result?.modeA?.setupDone}
          text={aText}
          setText={setAText}
          codeOut={result?.modeA?.codeOut}
          codeScore={result?.modeA?.codeScore}
        />
        <ModePanel
          mode="modeB"
          label="Mode B — Sieve ON"
          setupDone={result?.modeB?.setupDone}
          text={bText}
          setText={setBText}
          codeOut={result?.modeB?.codeOut}
          codeScore={result?.modeB?.codeScore}
        />
      </div>

      {/* Comparison footer */}
      <div className="mt-4 pt-4 border-t border-slate-800 flex items-center justify-between flex-wrap gap-3">
        <div className="text-xs text-slate-500">
          <span className="font-medium text-slate-400">Ground truth:</span> {test.groundTruth}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">Manual verdict:</span>
          {['better', 'same', 'worse'].map(v => (
            <button
              key={v}
              onClick={() => onSetVerdict(test.id, v)}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors border
                ${result?.verdict === v
                  ? v === 'better' ? 'bg-emerald-500/20 text-emerald-400 border-emerald-700/50'
                    : v === 'same' ? 'bg-blue-500/20 text-blue-400 border-blue-700/50'
                    : 'bg-red-500/20 text-red-400 border-red-700/50'
                  : 'bg-slate-800 text-slate-500 border-slate-700 hover:border-slate-600'}`}
            >
              {v}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

// ─── Dashboard ────────────────────────────────────────────────────────────────
const Dashboard = ({ tests, results }) => {
  const counts = { pass: 0, fail: 0, warn: 0, notRun: 0 };
  tests.forEach(t => {
    const r = results[t.id];
    if (!r) { counts.notRun++; return; }
    const s = t.type === 'shell' ? r.score?.status
      : t.type === 'ab' || t.type === 'ab-code' || t.type === 'ab-precision' ? (r.verdict || r.autoScore || 'notRun')
      : 'notRun';
    if (s === 'pass' || s === 'better') counts.pass++;
    else if (s === 'fail' || s === 'worse') counts.fail++;
    else if (s === 'warn' || s === 'same' || s === 'partial') counts.warn++;
    else counts.notRun++;
  });

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-white">Dashboard</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Pass / Better', count: counts.pass,   color: 'text-emerald-400', bg: 'bg-emerald-500/5 border-emerald-900' },
          { label: 'Fail / Worse',  count: counts.fail,   color: 'text-red-400',     bg: 'bg-red-500/5 border-red-900' },
          { label: 'Warn / Same',   count: counts.warn,   color: 'text-amber-400',   bg: 'bg-amber-500/5 border-amber-900' },
          { label: 'Not Run',       count: counts.notRun, color: 'text-slate-500',   bg: 'bg-slate-800/30 border-slate-800' },
        ].map(c => (
          <div key={c.label} className={`rounded-2xl border p-5 ${c.bg}`}>
            <div className={`text-3xl font-bold mb-1 ${c.color}`}>{c.count}</div>
            <div className="text-xs text-slate-500">{c.label}</div>
          </div>
        ))}
      </div>
      <div className="rounded-2xl border border-slate-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-800/40 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3 text-left">Test</th>
              <th className="px-4 py-3 text-left">Phase</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3 text-left">Detail</th>
            </tr>
          </thead>
          <tbody>
            {tests.map(t => {
              const r = results[t.id];
              const score = t.type === 'shell' ? r?.score
                : r?.verdict ? { status: r.verdict, msg: `Manual: ${r.verdict}` }
                : r?.autoScore ? { status: r.autoScore, msg: `Auto: ${r.autoScore}` }
                : null;
              return (
                <tr key={t.id} className="border-t border-slate-800/50 hover:bg-slate-800/10">
                  <td className="px-4 py-2 text-slate-300 text-xs">{t.name}</td>
                  <td className="px-4 py-2 text-slate-500 text-xs">{PHASES.find(p => p.id === t.phase)?.label}</td>
                  <td className="px-4 py-2">
                    {score ? <Badge status={score.status} msg="" /> : <span className="text-slate-700 text-xs">—</span>}
                  </td>
                  <td className="px-4 py-2 text-slate-500 text-xs">{score?.msg || '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [config, setConfig] = useState(() => {
    try { return { ...DEFAULT_CONFIG, ...JSON.parse(localStorage.getItem('sieveConfig') || '{}') }; }
    catch { return DEFAULT_CONFIG; }
  });
  const [results, setResults] = useState(() => {
    try { return JSON.parse(localStorage.getItem('sieveResults') || '{}'); }
    catch { return {}; }
  });
  const [running, setRunning] = useState({});
  const [activePhase, setActivePhase] = useState(-1);  // -1 = dashboard
  const [showConfig, setShowConfig] = useState(false);
  const [backendStatus, setBackendStatus] = useState('checking');
  const [mobileOpen, setMobileOpen] = useState(false);
  const [configDraft, setConfigDraft] = useState(config);

  const tests = useMemo(() => buildTests(config), [config]);

  // Persist
  useEffect(() => { localStorage.setItem('sieveResults', JSON.stringify(results)); }, [results]);
  useEffect(() => { localStorage.setItem('sieveConfig', JSON.stringify(config)); }, [config]);

  // Backend ping
  useEffect(() => {
    const check = () => {
      fetch(`${BACKEND}/health`, { signal: AbortSignal.timeout(2000) })
        .then(() => setBackendStatus('online'))
        .catch(() => setBackendStatus('offline'));
    };
    check();
    const t = setInterval(check, 5000);
    return () => clearInterval(t);
  }, []);

  const setRun = (key, val) => setRunning(p => ({ ...p, [key]: val }));

  const updateResult = useCallback((id, update) =>
    setResults(p => ({ ...p, [id]: { ...(p[id] || {}), ...update } })), []);

  const updateMode = useCallback((id, mode, update) =>
    setResults(p => ({
      ...p,
      [id]: { ...(p[id] || {}), [mode]: { ...((p[id] || {})[mode] || {}), ...update } }
    })), []);

  // Run a shell test
  const onRun = useCallback(async (test) => {
    if (backendStatus === 'offline') return;
    const key = test.id;
    setRun(key, true);
    try {
      const r = await callBackend(test.cmd, test.timeout || 60);
      const score = test.score ? test.score(r.output, r.returncode) : null;
      updateResult(test.id, { output: r.output, returncode: r.returncode, score, timestamp: Date.now() });
    } catch (e) {
      updateResult(test.id, {
        output: `Backend error: ${e.message}\n\nMake sure server.py is running:\n  cd Sieve-testing && python3 server.py`,
        returncode: -1,
        score: { status: 'fail', msg: 'Backend offline' },
        timestamp: Date.now(),
      });
    }
    setRun(key, false);
  }, [backendStatus, updateResult]);

  // Setup A/B mode
  const onSetup = useCallback(async (testId, mode, cmd) => {
    const key = `${testId}-${mode}-setup`;
    setRun(key, true);
    try {
      await callBackend(cmd, 15);
      updateMode(testId, mode, { setupDone: true });
    } catch {}
    setRun(key, false);
  }, [updateMode]);

  // Save pasted text
  const onSaveText = useCallback((testId, mode, text) => {
    updateMode(testId, mode, { text });
  }, [updateMode]);

  // Run code (ab-code tests)
  const onRunCode = useCallback(async (testId, mode, cmd, scoreCode, timeout) => {
    const key = `${testId}-${mode}-code`;
    setRun(key, true);
    try {
      const r = await callBackend(cmd, timeout || 30);
      const score = scoreCode ? scoreCode(r.output, r.returncode) : null;
      updateMode(testId, mode, { codeOut: r.output, codeScore: score });
    } catch {}
    setRun(key, false);
  }, [updateMode]);

  // Score precision/recall (ab-precision tests)
  const onScorePrecision = useCallback(async (testId, mode, text, gtCmd) => {
    const key = `${testId}-${mode}-score`;
    setRun(key, true);
    try {
      const gtResult = await callBackend(gtCmd, 15);
      const groundTruth = gtResult.output.trim().split('\n').map(l => l.replace(/^\.\//, '').trim()).filter(Boolean);
      let answer = [];
      try { answer = JSON.parse(text); } catch {}
      const gtSet  = new Set(groundTruth);
      const ansSet = new Set(answer);
      const tp = [...ansSet].filter(x => gtSet.has(x)).length;
      const precision = ansSet.size > 0 ? tp / ansSet.size : 0;
      const recall    = gtSet.size  > 0 ? tp / gtSet.size  : 0;
      const missing = [...gtSet].filter(x => !ansSet.has(x));
      const extra   = [...ansSet].filter(x => !gtSet.has(x));
      const precStatus = precision >= 0.8 && recall >= 0.8 ? 'pass' : recall >= 0.5 ? 'partial' : 'fail';
      updateMode(testId, mode, { precision, recall, missing, extra, precStatus });
    } catch {}
    setRun(key, false);
  }, [updateMode]);

  // Manual verdict
  const onSetVerdict = useCallback((testId, v) => {
    updateResult(testId, { verdict: v });
  }, [updateResult]);

  const activeTests = activePhase === -1 ? [] : tests.filter(t => t.phase === activePhase);
  const phaseProgress = (phase) => {
    const pts = tests.filter(t => t.phase === phase);
    if (!pts.length) return 0;
    const done = pts.filter(t => {
      const r = results[t.id];
      if (!r) return false;
      if (t.type === 'shell') return r.score != null;
      return r.modeA?.text || r.modeB?.text || r.verdict;
    }).length;
    return Math.round((done / pts.length) * 100);
  };

  return (
    <div className="min-h-screen bg-[#090b10] text-slate-200 flex font-sans">
      {/* Mobile header */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-20 flex items-center justify-between p-4 bg-[#0d1117] border-b border-slate-800">
        <span className="font-bold flex items-center gap-2"><Activity size={18} className="text-blue-500" /> Sieve Tests</span>
        <button onClick={() => setMobileOpen(v => !v)} className="p-1.5 rounded hover:bg-slate-800">
          {mobileOpen ? <X size={18} /> : <Menu size={18} />}
        </button>
      </div>

      {/* Sidebar */}
      <aside className={`
        ${mobileOpen ? 'fixed inset-0 top-14 z-10 bg-[#090b10]' : 'hidden'}
        md:flex md:flex-col md:w-72 md:shrink-0 bg-[#0d1117] border-r border-slate-800 md:h-screen md:sticky md:top-0
      `}>
        {/* Logo */}
        <div className="p-5 hidden md:flex items-center justify-between">
          <span className="font-bold text-lg bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-emerald-400 flex items-center gap-2">
            <Activity size={20} className="text-blue-500" /> Sieve Tests
          </span>
          <button onClick={() => { setConfigDraft(config); setShowConfig(true); }} className="p-1.5 rounded hover:bg-slate-800 text-slate-400">
            <Settings size={15} />
          </button>
        </div>

        {/* Backend status */}
        <div className={`mx-4 mb-3 px-3 py-2 rounded-lg flex items-center gap-2 text-xs font-medium
          ${backendStatus === 'online' ? 'bg-emerald-500/5 text-emerald-400 border border-emerald-900' : 'bg-red-500/5 text-red-400 border border-red-900'}`}>
          {backendStatus === 'online' ? <Wifi size={12} /> : <WifiOff size={12} />}
          Backend {backendStatus === 'online' ? 'online' : 'offline — start server.py'}
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto px-3 space-y-0.5">
          <button
            onClick={() => { setActivePhase(-1); setMobileOpen(false); }}
            className={`w-full flex items-center gap-3 p-3 rounded-xl text-sm transition-colors
              ${activePhase === -1 ? 'bg-blue-500/10 text-blue-400' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'}`}
          >
            <BarChart3 size={16} /> Dashboard
          </button>
          {PHASES.map(ph => {
            const Icon = ph.icon;
            const prog = phaseProgress(ph.id);
            return (
              <button
                key={ph.id}
                onClick={() => { setActivePhase(ph.id); setMobileOpen(false); }}
                className={`w-full flex items-center justify-between p-3 rounded-xl text-sm transition-colors
                  ${activePhase === ph.id ? 'bg-blue-500/10 text-blue-400' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'}`}
              >
                <div className="flex items-center gap-3">
                  <Icon size={15} />
                  <span>Phase {ph.id} · {ph.label}</span>
                </div>
                {prog > 0 && (
                  prog === 100
                    ? <CheckCircle2 size={14} className="text-emerald-500" />
                    : <span className="text-xs font-mono bg-slate-800 px-1.5 py-0.5 rounded-full">{prog}%</span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Reset */}
        <div className="p-4 border-t border-slate-800">
          <button
            onClick={() => { if (confirm('Reset all test results?')) setResults({}); }}
            className="w-full flex items-center justify-center gap-2 py-2 bg-slate-800 hover:bg-red-900/30 text-slate-400 hover:text-red-400 rounded-lg text-xs transition-colors"
          >
            <Trash2 size={12} /> Reset all results
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto h-screen pt-14 md:pt-0">
        <div className="max-w-5xl mx-auto p-5 md:p-8 pb-24 space-y-5">
          {activePhase === -1 ? (
            <Dashboard tests={tests} results={results} />
          ) : (
            <>
              <div className="flex items-center gap-3 mb-2">
                {(() => { const Icon = PHASES.find(p => p.id === activePhase)?.icon || Play; return <Icon size={18} className="text-blue-400" />; })()}
                <h2 className="text-xl font-bold text-white">
                  Phase {activePhase} · {PHASES.find(p => p.id === activePhase)?.label}
                </h2>
              </div>
              {activeTests.map(test => {
                const r = results[test.id] || {};
                if (test.type === 'shell') {
                  return (
                    <ShellCard
                      key={test.id}
                      test={test}
                      result={r}
                      running={running[test.id]}
                      onRun={() => onRun(test)}
                    />
                  );
                }
                return (
                  <ABCard
                    key={test.id}
                    test={test}
                    result={r}
                    running={running}
                    onSetup={onSetup}
                    onSaveText={onSaveText}
                    onRunCode={onRunCode}
                    onSetVerdict={onSetVerdict}
                    onScorePrecision={onScorePrecision}
                  />
                );
              })}
              <div className="flex justify-between pt-4">
                <button onClick={() => setActivePhase(p => Math.max(-1, p - 1))}
                  className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200 transition-colors">
                  <ChevronLeft size={16} /> Prev
                </button>
                <button onClick={() => setActivePhase(p => Math.min(PHASES.length - 1, p + 1))}
                  disabled={activePhase === PHASES.length - 1}
                  className="flex items-center gap-1.5 text-sm text-blue-400 hover:text-blue-300 disabled:opacity-30 transition-colors">
                  Next <ChevronRight size={16} />
                </button>
              </div>
            </>
          )}
        </div>
      </main>

      {/* Config Modal */}
      {showConfig && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
          <div className="bg-[#11151d] border border-slate-700 rounded-2xl w-full max-w-lg p-6 shadow-2xl">
            <div className="flex items-center justify-between mb-5">
              <h2 className="font-bold text-lg">Configure Paths</h2>
              <button onClick={() => setShowConfig(false)} className="text-slate-400 hover:text-white"><X size={18} /></button>
            </div>
            <p className="text-xs text-slate-400 mb-4">Git Bash paths (<code>/c/…</code>). Pre-filled for <code>C:\Users\avrha\Documents\projects\Sieve-testing</code>. Open Git Bash (Start → Git Bash) to run the backend server.</p>
            <div className="space-y-3">
              {[
                { key: 'sieve',    label: 'Sieve repo' },
                { key: 'requests', label: 'psf/requests' },
                { key: 'click',    label: 'pallets/click' },
                { key: 'httpx',    label: 'encode/httpx' },
              ].map(({ key, label }) => (
                <div key={key}>
                  <label className="text-xs text-slate-400 mb-1 block">{label}</label>
                  <input
                    value={configDraft[key]}
                    onChange={e => setConfigDraft(p => ({ ...p, [key]: e.target.value }))}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-slate-300 focus:outline-none focus:border-blue-500"
                  />
                </div>
              ))}
            </div>
            <div className="flex gap-3 mt-5">
              <button
                onClick={() => { setConfig(configDraft); setShowConfig(false); setResults({}); }}
                className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors"
              >
                Save & reset results
              </button>
              <button onClick={() => setShowConfig(false)} className="px-4 py-2.5 bg-slate-800 text-slate-300 text-sm rounded-lg hover:bg-slate-700 transition-colors">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
