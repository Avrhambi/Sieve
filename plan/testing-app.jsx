import React, { useState, useEffect } from 'react';
import {
  Play, Settings, Layers, Zap, Target, AlertTriangle, RefreshCw, BarChart3,
  Copy, Check, ChevronRight, Menu, X, Activity, Clock, AlertCircle,
  Terminal, FileText, CheckSquare, Square, BookOpen, Cpu
} from 'lucide-react';

// ─── Copy Button ─────────────────────────────────────────────────────────────
const CopyBtn = ({ text, label = 'Copy' }) => {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={() => navigator.clipboard.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 2000); }).catch(() => {})}
      className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-600/50 text-xs text-slate-300 hover:text-white rounded-lg transition-all shrink-0"
    >
      {done ? <><Check size={11} className="text-emerald-400" /> Copied</> : <><Copy size={11} /> {label}</>}
    </button>
  );
};

// ─── Code Block ──────────────────────────────────────────────────────────────
const Code = ({ children, copyable = true }) => (
  <div className="relative group mt-3 mb-1">
    <pre className="bg-black/50 border border-slate-700/50 rounded-xl px-4 py-3 text-sm text-slate-200 font-mono overflow-x-auto leading-relaxed whitespace-pre">
      {children}
    </pre>
    {copyable && (
      <div className="absolute top-2.5 right-2.5 opacity-0 group-hover:opacity-100 transition-opacity">
        <CopyBtn text={children} />
      </div>
    )}
  </div>
);

// ─── Prompt Block ─────────────────────────────────────────────────────────────
const Prompt = ({ children }) => (
  <div className="relative group mt-3 mb-1">
    <div className="bg-blue-950/30 border border-blue-700/40 rounded-xl px-4 py-3">
      <div className="flex items-center gap-1.5 mb-2">
        <Terminal size={11} className="text-blue-400" />
        <span className="text-xs font-semibold uppercase tracking-wider text-blue-400">Prompt — copy and send to Claude</span>
      </div>
      <p className="text-sm text-slate-200 leading-relaxed font-mono">{children}</p>
    </div>
    <div className="absolute top-2.5 right-2.5 opacity-0 group-hover:opacity-100 transition-opacity">
      <CopyBtn text={children} label="Copy prompt" />
    </div>
  </div>
);

// ─── Expected Block ───────────────────────────────────────────────────────────
const Expected = ({ children }) => (
  <div className="mt-3 mb-1 bg-emerald-950/20 border border-emerald-800/40 rounded-xl px-4 py-3">
    <div className="flex items-center gap-1.5 mb-2">
      <Check size={11} className="text-emerald-400" />
      <span className="text-xs font-semibold uppercase tracking-wider text-emerald-400">Expected output</span>
    </div>
    <pre className="text-sm text-slate-300 font-mono whitespace-pre-wrap leading-relaxed">{children}</pre>
  </div>
);

// ─── Note / Warning ───────────────────────────────────────────────────────────
const Note = ({ children, variant = 'info' }) => {
  const styles = {
    info:    'bg-blue-950/20 border-blue-700/40 text-blue-300',
    warn:    'bg-amber-950/20 border-amber-700/40 text-amber-300',
    tip:     'bg-purple-950/20 border-purple-700/40 text-purple-300',
  };
  return (
    <div className={`mt-3 mb-1 border rounded-xl px-4 py-3 text-sm leading-relaxed ${styles[variant]}`}>
      {children}
    </div>
  );
};

// ─── Checklist ────────────────────────────────────────────────────────────────
const Checklist = ({ id, items }) => {
  const [checked, setChecked] = useState(() => {
    try { return JSON.parse(localStorage.getItem(`chk-${id}`) || '{}'); }
    catch { return {}; }
  });

  const toggle = (i) => {
    const next = { ...checked, [i]: !checked[i] };
    setChecked(next);
    localStorage.setItem(`chk-${id}`, JSON.stringify(next));
  };

  return (
    <div className="mt-3 space-y-2">
      {items.map((item, i) => (
        <button key={i} onClick={() => toggle(i)}
          className="w-full flex items-start gap-3 text-left group">
          <span className="mt-0.5 shrink-0">
            {checked[i]
              ? <CheckSquare size={16} className="text-emerald-400" />
              : <Square size={16} className="text-slate-500 group-hover:text-slate-400 transition-colors" />}
          </span>
          <span className={`text-sm leading-relaxed transition-colors ${checked[i] ? 'text-slate-500 line-through' : 'text-slate-300'}`}>
            {item}
          </span>
        </button>
      ))}
    </div>
  );
};

// ─── Section wrapper ──────────────────────────────────────────────────────────
const Section = ({ title, children, accent = false }) => (
  <div className={`border rounded-2xl p-7 transition-all bg-slate-900/40 ${accent ? 'border-blue-700/40' : 'border-slate-700/50'}`}>
    {title && <h3 className="text-base font-bold text-white mb-4 flex items-center gap-2">{title}</h3>}
    {children}
  </div>
);

// ─── AB Table ────────────────────────────────────────────────────────────────
const ABTable = ({ rows, headers = ['Dimension', 'Mode A — No Sieve', 'Mode B — Sieve ON'] }) => (
  <div className="mt-3 overflow-x-auto rounded-xl border border-slate-700/50">
    <table className="w-full text-sm">
      <thead className="bg-slate-800/60 text-xs font-semibold uppercase tracking-wider text-slate-400">
        <tr>
          {headers.map(h => <th key={h} className="px-4 py-3 text-left">{h}</th>)}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i} className="border-t border-slate-800/50">
            <td className="px-4 py-2.5 text-slate-400 text-xs font-medium whitespace-nowrap">{row[0]}</td>
            {row.slice(1).map((cell, j) => (
              <td key={j} className={`px-4 py-2.5 text-xs ${cell === 'baseline' ? 'text-slate-600 italic' : 'text-slate-300'}`}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

// ─── Page content ─────────────────────────────────────────────────────────────

const PAGES = [
  { id: 'quickstart', label: 'Quick Start',     icon: Play },
  { id: 'setup',      label: 'Setup Checklist', icon: Settings },
  { id: 'ab-method',  label: 'A/B Methodology', icon: BarChart3 },
  { id: 'test-01',    label: 'TEST-01 — Offline fallback',  icon: Layers },
  { id: 'test-02',    label: 'TEST-02 — Skeleton injection', icon: Layers },
  { id: 'test-03',    label: 'TEST-03 — !full override',    icon: Layers },
  { id: 'test-04',    label: 'TEST-04 — Hybrid context',    icon: Layers },
  { id: 'test-05',    label: 'TEST-05 — Token reduction',   icon: Zap },
  { id: 'test-06',    label: 'TEST-06 — PostCompact',       icon: RefreshCw },
  { id: 'test-07',    label: 'TEST-07 — OCR pipeline',      icon: FileText },
  { id: 'test-08',    label: 'TEST-08 — Graceful shutdown', icon: Activity },
  { id: 'test-09',    label: 'TEST-09 — MCP tools',         icon: Cpu },
  { id: 'test-10',    label: 'TEST-10 — Answer quality',    icon: Target },
  { id: 'consistency',label: 'Consistency checks',          icon: AlertTriangle },
];

function QuickStartPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">Quick Start</h2>
        <p className="text-slate-400 text-sm">Run your first test in 5 minutes using the <code className="bg-slate-800 px-1.5 py-0.5 rounded text-slate-300">psf/requests</code> repo.</p>
      </div>

      <Section title="1 — Clone the test project" accent>
        <Code>{`git clone https://github.com/psf/requests /c/Users/avrha/Documents/projects/Sieve-testing/projects/requests
cd /c/Users/avrha/Documents/projects/Sieve-testing/projects/requests`}</Code>
      </Section>

      <Section title="2 — Open two terminals">
        <p className="text-sm text-slate-400 mb-3">Open two Git Bash windows.</p>
        <p className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">Terminal 1 — Sieve daemon</p>
        <Code>{`cd /c/Users/avrha/Documents/projects/Sieve-testing/sieve
source .venv/Scripts/activate
python src/main.py /c/Users/avrha/Documents/projects/Sieve-testing/projects/requests`}</Code>
        <Expected>Watching /c/Users/.../requests ...</Expected>
        <p className="text-xs font-bold uppercase tracking-wider text-slate-500 mt-4 mb-1">Terminal 2 — Test backend (for UI)</p>
        <Code>{`cd /c/Users/avrha/Documents/projects/Sieve-testing/sieve
source .venv/Scripts/activate
python plan/server.py`}</Code>
        <Expected>Sieve Test Runner API → http://127.0.0.1:8765</Expected>
      </Section>

      <Section title="3 — Trigger the cache">
        <Code>{`touch /c/Users/avrha/Documents/projects/Sieve-testing/projects/requests/requests/api.py`}</Code>
        <Note variant="info">Wait ~3 seconds. The daemon processes the file and writes its skeleton to ledger.db.</Note>
      </Section>

      <Section title="4 — Install the hook">
        <p className="text-sm text-slate-400 mb-3">Run this once to register Sieve as a Claude Code hook in the requests project:</p>
        <Code>{`mkdir -p /c/Users/avrha/Documents/projects/Sieve-testing/projects/requests/.claude
cat > /c/Users/avrha/Documents/projects/Sieve-testing/projects/requests/.claude/settings.json << 'EOF'
{
  "hooks": {
    "UserPromptSubmit": [{"hooks": [{"command": "python3 /c/Users/avrha/Documents/projects/Sieve-testing/sieve/bin/sieve-hook --mode=prompt", "type": "command"}]}],
    "PostCompact":      [{"hooks": [{"command": "python3 /c/Users/avrha/Documents/projects/Sieve-testing/sieve/bin/sieve-hook --mode=compact", "type": "command"}]}]
  }
}
EOF
cp /c/Users/avrha/Documents/projects/Sieve-testing/projects/requests/.claude/settings.json \
   /c/Users/avrha/Documents/projects/Sieve-testing/projects/requests/.claude/settings.json.bak`}</Code>
      </Section>

      <Section title="5 — Open Claude Code in the test project">
        <Code>{`cd /c/Users/avrha/Documents/projects/Sieve-testing/projects/requests
claude`}</Code>
        <Note variant="info">Claude Code must be opened from the <strong>requests</strong> directory so it picks up the .claude/settings.json hook.</Note>
      </Section>

      <Section title="6 — Send your first test prompt">
        <Prompt>What functions are available in requests/api.py?</Prompt>
        <Expected>{`### requests/api.py
def request(method, url, **kwargs):
    """Constructs a Request..."""
    ...

def get(url, params=None, **kwargs):
    """Sends a GET request."""
    ...`}</Expected>
        <p className="text-sm text-slate-400 mt-3">Claude should answer accurately from the injected skeleton — without you pasting any code.</p>
      </Section>
    </div>
  );
}

function SetupPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">Setup Checklist</h2>
        <p className="text-slate-400 text-sm">Complete all items before running any test. State is saved locally.</p>
      </div>

      <Section title="Before any test" accent>
        <Checklist id="setup-main" items={[
          'Daemon is running: python src/main.py /path/to/test-repo',
          'Ollama is running (check system tray or ollama serve in a terminal)',
          'Hook is registered in test-repo/.claude/settings.json (UserPromptSubmit + PostCompact)',
          'At least one .py file has been touched to populate the cache',
          'Cache is populated: python3 -c "import sqlite3; conn=sqlite3.connect(\'ledger.db\'); print(conn.execute(\'SELECT COUNT(*) FROM context_cache\').fetchone()[0], \'entries\')"',
          'Test backend running: python plan/server.py (for automated tests only)',
          'Claude Code is opened from inside the test repo directory',
        ]} />
      </Section>

      <Section title="Verify cache is working">
        <p className="text-sm text-slate-400 mb-2">Run this from inside the test repo:</p>
        <Code>{`python3 -c "
import sqlite3, os
db = 'ledger.db'
if not os.path.exists(db):
    print('FAIL: ledger.db not found')
else:
    conn = sqlite3.connect(db)
    cc = conn.execute('SELECT COUNT(*) FROM context_cache').fetchone()[0]
    si = conn.execute('SELECT COUNT(*) FROM symbol_index').fetchone()[0]
    print(f'context_cache: {cc} entries')
    print(f'symbol_index:  {si} entries')
    print('OK' if cc > 0 else 'WARN: cache empty — touch some .py files then wait 5s')
"`}</Code>
      </Section>

      <Section title="A/B mode quick-switch commands">
        <p className="text-sm text-slate-400 mb-2">Save these — you'll use them for every A/B test.</p>
        <p className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">Disable hook (Mode A — baseline)</p>
        <Code>{`python3 -c "import json; s=json.load(open('.claude/settings.json')); s.setdefault('hooks',{}).pop('UserPromptSubmit',None); json.dump(s,open('.claude/settings.json','w'),indent=2)" && echo "✓ Mode A ready"`}</Code>
        <p className="text-xs font-bold uppercase tracking-wider text-slate-500 mt-4 mb-1">Re-enable hook (Mode B — Sieve ON)</p>
        <Code>{`cp .claude/settings.json.bak .claude/settings.json && echo "✓ Mode B ready"`}</Code>
      </Section>
    </div>
  );
}

function ABMethodPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">A/B Testing Methodology</h2>
        <p className="text-slate-400 text-sm">How to run controlled comparisons and interpret the results.</p>
      </div>

      <Section title="The two modes" accent>
        <div className="space-y-3">
          <div className="bg-slate-800/50 border border-slate-700/40 rounded-xl px-4 py-3">
            <p className="text-sm font-bold text-slate-300 mb-1">Mode A — No Sieve (baseline)</p>
            <p className="text-sm text-slate-400">Hook disabled. Claude receives only your bare prompt — no file context injected. This is what every Claude Code user gets without Sieve.</p>
          </div>
          <div className="bg-blue-950/20 border border-blue-700/40 rounded-xl px-4 py-3">
            <p className="text-sm font-bold text-slate-300 mb-1">Mode B — Sieve active</p>
            <p className="text-sm text-slate-400">Hook enabled, daemon running with a populated cache. Claude receives your prompt + all file skeletons (or full file + skeletons for hybrid context).</p>
          </div>
        </div>
      </Section>

      <Section title="Scorecard — fill in for every A/B test">
        <ABTable
          headers={['Dimension', 'Mode A (no Sieve)', 'Mode B (with Sieve)']}
          rows={[
            ['Correct file located?', 'Y / N / N/A', 'Y / N / N/A'],
            ['Answer correct?', 'Y / Partial / N', 'Y / Partial / N'],
            ['Follow-ups needed', '[count]', '[count]'],
            ['Hallucinated anything?', 'Y / N', 'Y / N'],
            ['Context size (chars)', 'baseline', ''],
            ['Verdict', '—', 'Better / Same / Worse'],
            ['Reason', '—', '[one sentence]'],
          ]}
        />
      </Section>

      <Section title="Interpreting verdicts">
        <ABTable
          headers={['Verdict', 'Meaning', 'Action']}
          rows={[
            ['Better', 'Skeleton gives Claude enough structure to reason accurately', 'Ship ✓'],
            ['Same', 'Compression without quality loss — token savings with no downside', 'Ship ✓'],
            ['Worse — navigation', 'Skeleton stripped too much for structural reasoning', 'Add more context to skeletons'],
            ['Worse — implementation', 'User needed full code, not just signature', 'User should use !full for this task class'],
          ]}
        />
        <Note variant="info" className="mt-3">
          <strong>Minimum runs to trust:</strong> 3 different prompts per test. If 2 of 3 are Same or Better, the test passes.
        </Note>
      </Section>

      <Section title="Evaluation methods by test type">
        <ABTable
          headers={['Test type', 'Evaluation method', 'Objective?']}
          rows={[
            ['pytest suite', 'Pass/fail output', 'Yes — fully automated'],
            ['Infrastructure (TEST-01, TEST-08)', 'Output format, DB integrity', 'Yes — scripted checks'],
            ['Feature fires (TEST-03)', 'grep injected content', 'Yes — grep for expected string'],
            ['OCR fires (TEST-07)', 'Did Claude quote screenshot text?', 'Human-visual'],
            ['Navigation quality (TEST-02, TEST-04)', 'grep source for correct file/function', 'Yes — ground truth verifiable'],
            ['Impact analysis (TEST-09, TEST-10)', 'Precision/recall against grep', 'Yes — scripted'],
            ['Code generation (TEST-10)', 'Run pytest on generated code', 'Yes — execution-based'],
          ]}
        />
        <Note variant="tip" className="mt-3">
          <strong>General rule:</strong> if Claude names a file or function, <code className="bg-black/30 px-1 rounded">grep</code> the source to verify it exists. If Claude writes code, run it. Only use human judgment for inherently visual outputs (OCR quality, UI rendering).
        </Note>
      </Section>
    </div>
  );
}

function Test01Page() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">TEST-01 — Daemon offline fallback</h2>
        <p className="text-slate-400 text-sm">Verify the hook still works and injects a file-tree heuristic when the daemon is not running.</p>
      </div>
      <Section title="Prerequisites">
        <Checklist id="t01-pre" items={['Daemon is NOT running (stop it or don\'t start it)', 'Hook is registered in .claude/settings.json']} />
      </Section>
      <Section title="Steps" accent>
        <ol className="space-y-3 text-sm text-slate-300">
          <li className="flex gap-3"><span className="shrink-0 w-6 h-6 rounded-full bg-blue-600/30 text-blue-300 text-xs font-bold flex items-center justify-center">1</span>Make sure the daemon is stopped.</li>
          <li className="flex gap-3"><span className="shrink-0 w-6 h-6 rounded-full bg-blue-600/30 text-blue-300 text-xs font-bold flex items-center justify-center">2</span>Open Claude Code in any project.</li>
          <li className="flex gap-3"><span className="shrink-0 w-6 h-6 rounded-full bg-blue-600/30 text-blue-300 text-xs font-bold flex items-center justify-center">3</span>Submit any prompt.</li>
        </ol>
      </Section>
      <Section title="Expected output — injected before your prompt">
        <Expected>{`[sieve] daemon offline — file-tree heuristic
  src/core/inference.py
  src/daemon/watcher.py
  src/main.py
  ...`}</Expected>
      </Section>
      <Section title="What to check">
        <Checklist id="t01-check" items={[
          'Hook exits in <50ms — no hang before Claude responds',
          'File list is accurate (matches actual project files up to MAX_DEPTH=3)',
          'Claude still responds normally',
        ]} />
        <p className="text-sm text-slate-400 mt-3">Verify Claude saw it: ask <em>"What files do you know about?"</em> — the list should match what was injected.</p>
      </Section>
    </div>
  );
}

function Test02Page() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">TEST-02 — Skeleton injection</h2>
        <p className="text-slate-400 text-sm">Verify the cache is populated and file skeletons are injected into the prompt.</p>
      </div>
      <Section title="Prerequisites">
        <Checklist id="t02-pre" items={['Daemon running', 'Cache populated (touch a .py file, wait 3s)', 'Hook enabled (Mode B)']} />
      </Section>
      <Section title="Steps" accent>
        <ol className="space-y-3 text-sm text-slate-300">
          <li className="flex gap-3"><span className="shrink-0 w-6 h-6 rounded-full bg-blue-600/30 text-blue-300 text-xs font-bold flex items-center justify-center">1</span>Open Claude Code in the requests repo.</li>
          <li className="flex gap-3"><span className="shrink-0 w-6 h-6 rounded-full bg-blue-600/30 text-blue-300 text-xs font-bold flex items-center justify-center">2</span>Submit this prompt:</li>
        </ol>
        <Prompt>Where would I add retry logic to the HTTP request flow in requests/adapters.py?</Prompt>
      </Section>
      <Section title="Expected — Mode B should point directly to HTTPAdapter.send">
        <Expected>{`### requests/adapters.py
class HTTPAdapter:
    """The built-in HTTP Adapter for urllib3."""

    def send(self, request, stream=False, timeout=None, ...):
        ...`}</Expected>
        <p className="text-sm text-slate-400 mt-2">Claude should name <code className="bg-slate-800 px-1 rounded">HTTPAdapter.send()</code> without you telling it which file or class to look in.</p>
      </Section>
      <Section title="What to check">
        <Checklist id="t02-check" items={[
          'Function signatures are present in injected context',
          'Function bodies are replaced with "..."',
          'Docstrings are preserved',
          'Mode A requires Claude to ask "which file?" or gives a generic answer',
        ]} />
      </Section>
      <Section title="A/B comparison">
        <p className="text-sm text-slate-400 mb-3">Run the same prompt in Mode A then Mode B. Verify with grep:</p>
        <Code>{`grep -rn "HTTPAdapter" /c/.../requests/requests/`}</Code>
        <ABTable rows={[
          ['Correct file located?', '', ''],
          ['Named HTTPAdapter.send()?', '', ''],
          ['Follow-ups needed', '', ''],
          ['Context size (chars)', '~60 (bare prompt)', 'wc -c on hook output'],
          ['Verdict', 'baseline', ''],
        ]} />
      </Section>
    </div>
  );
}

function Test03Page() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">TEST-03 — !full override</h2>
        <p className="text-slate-400 text-sm">Verify that <code className="bg-slate-800 px-1 rounded">!full &lt;path&gt;</code> injects the complete raw file instead of a skeleton.</p>
      </div>
      <Section title="Steps" accent>
        <ol className="space-y-3 text-sm text-slate-300">
          <li className="flex gap-3"><span className="shrink-0 w-6 h-6 rounded-full bg-blue-600/30 text-blue-300 text-xs font-bold flex items-center justify-center">1</span>Daemon can be running or stopped (doesn't matter for this test).</li>
          <li className="flex gap-3"><span className="shrink-0 w-6 h-6 rounded-full bg-blue-600/30 text-blue-300 text-xs font-bold flex items-center justify-center">2</span>In Claude Code, send this prompt:</li>
        </ol>
        <Prompt>!full requests/api.py</Prompt>
      </Section>
      <Section title="Expected">
        <Expected>{`### requests/api.py
[complete file contents — every line, including all function bodies]

def request(method, url, **kwargs):
    """Constructs a :class: Request, ..."""
    with sessions.Session() as session:
        return session.request(method=method, url=url, **kwargs)
...`}</Expected>
      </Section>
      <Section title="What to check">
        <Checklist id="t03-check" items={[
          'Full file body is present — no "..." placeholders',
          'Line count matches actual file (wc -l requests/api.py)',
          'Ask Claude: "What does the post() function do line by line?" — it should answer from implementation detail',
        ]} />
      </Section>
      <Section title="Manual verification">
        <Code>{`# Run the hook manually — output should have full file
cd /c/Users/avrha/Documents/projects/Sieve-testing/projects/requests
SIEVE_PROMPT='!full requests/api.py' \\
  python3 /c/Users/avrha/Documents/projects/Sieve-testing/sieve/bin/sieve-hook --mode=prompt | head -40`}</Code>
      </Section>
    </div>
  );
}

function Test04Page() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">TEST-04 — Hybrid context</h2>
        <p className="text-slate-400 text-sm">Verify that files explicitly mentioned in the prompt are injected in full while all others remain skeletons.</p>
      </div>
      <Section title="Steps" accent>
        <ol className="space-y-3 text-sm text-slate-300">
          <li className="flex gap-3"><span className="shrink-0 w-6 h-6 rounded-full bg-blue-600/30 text-blue-300 text-xs font-bold flex items-center justify-center">1</span>Daemon running with populated cache.</li>
          <li className="flex gap-3"><span className="shrink-0 w-6 h-6 rounded-full bg-blue-600/30 text-blue-300 text-xs font-bold flex items-center justify-center">2</span>Send a prompt that names a specific file:</li>
        </ol>
        <Prompt>Look at requests/adapters.py and explain step by step what the send() method does internally.</Prompt>
      </Section>
      <Section title="Expected">
        <Expected>{`[sieve] hybrid context: 1 file(s) full, 12 skeleton(s)

### requests/adapters.py [full]
class HTTPAdapter:
    def send(self, request, stream=False, ...):
        # full implementation here — no "..." placeholders`}</Expected>
      </Section>
      <Section title="Three-mode A/B (this test has Mode C)">
        <Note variant="warn">This test has three states. Run all three with the same prompt:</Note>
        <Prompt>Explain exactly what happens inside the send() method in requests/adapters.py</Prompt>
        <ABTable
          headers={['Dimension', 'Mode A — bare', 'Mode B — all skeleton', 'Mode C — hybrid']}
          rows={[
            ['Correct method found?', '', '', ''],
            ['Implementation detail?', '', '', ''],
            ['Follow-ups needed', '', '', ''],
            ['Context chars', '~70', '', ''],
            ['Verdict vs Mode A', 'baseline', '', ''],
          ]}
        />
        <p className="text-sm text-slate-400 mt-3"><strong className="text-slate-300">Expected pattern:</strong> Mode A struggles with implementation. Mode B knows the method exists but can't explain body. Mode C explains fully. This shows the exact value of each Sieve layer.</p>
      </Section>
    </div>
  );
}

function Test05Page() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">TEST-05 — Token reduction measurement</h2>
        <p className="text-slate-400 text-sm">Quantify how much Sieve compresses your codebase. Target: 70–93% reduction.</p>
      </div>
      <Section title="Measure skeleton output size" accent>
        <Code>{`cd /c/Users/avrha/Documents/projects/Sieve-testing/projects/requests

# 1. Capture skeleton output
SIEVE_PROMPT='test' \\
  python3 /c/Users/avrha/Documents/projects/Sieve-testing/sieve/bin/sieve-hook --mode=prompt > /tmp/sieve-out.txt

# 2. Count skeleton chars
wc -c /tmp/sieve-out.txt

# 3. Count raw source chars
find . -name "*.py" | xargs wc -c 2>/dev/null | tail -1

# 4. Calculate reduction
python3 -c "
skel = int(input('Skeleton chars: '))
raw  = int(input('Raw chars: '))
print(f'Reduction: {(1 - skel/raw)*100:.1f}%')
"`}</Code>
      </Section>
      <Section title="Expected">
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-3"><span className="w-32 text-slate-500">70–80%</span><span className="text-slate-300">Normal — files with long functions</span></div>
          <div className="flex items-center gap-3"><span className="w-32 text-emerald-400 font-medium">80–93%</span><span className="text-slate-300">Excellent — heavy implementation files</span></div>
          <div className="flex items-center gap-3"><span className="w-32 text-amber-400">Below 60%</span><span className="text-slate-300">Check for files with very long docstrings or constants</span></div>
        </div>
      </Section>
      <Section title="A/B — what each token budget buys">
        <Code>{`# Mode A — bare prompt only
echo -n "What does requests/api.py export?" | wc -c

# Mode B — with Sieve
SIEVE_PROMPT='What does requests/api.py export?' \\
  python3 .../sieve/bin/sieve-hook --mode=prompt > /tmp/b.txt
wc -c /tmp/b.txt

# Mode C (ceiling) — full file
wc -c requests/api.py`}</Code>
        <ABTable
          headers={['Dimension', 'Mode A (~40 chars)', 'Mode B (skeleton)', 'Mode C (full file)']}
          rows={[
            ['Correct answer?', '', '', ''],
            ['Names all exports?', '', '', ''],
            ['Context chars', '~40', '', ''],
            ['Verdict vs full file', 'baseline', '', 'ceiling'],
          ]}
        />
        <Note variant="tip" className="mt-3"><strong>Goal:</strong> Mode B score should match Mode C at 10–30% of Mode C's token cost.</Note>
      </Section>
    </div>
  );
}

function Test06Page() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">TEST-06 — PostCompact re-injection</h2>
        <p className="text-slate-400 text-sm">Verify that after Claude compacts context, Sieve re-injects the architectural skeleton.</p>
      </div>
      <Note variant="warn">This is one of the <strong>highest-value A/B tests</strong> — context loss after /compact is a real daily pain point for Claude Code users.</Note>
      <Section title="Steps" accent>
        <ol className="space-y-3 text-sm text-slate-300">
          <li className="flex gap-3"><span className="shrink-0 w-6 h-6 rounded-full bg-blue-600/30 text-blue-300 text-xs font-bold flex items-center justify-center">1</span>Start a long conversation until Claude compacts, or trigger it manually with <code className="bg-slate-800 px-1 rounded">/compact</code>.</li>
          <li className="flex gap-3"><span className="shrink-0 w-6 h-6 rounded-full bg-blue-600/30 text-blue-300 text-xs font-bold flex items-center justify-center">2</span>Immediately after compact, send:</li>
        </ol>
        <Prompt>What are the main classes in this project and where are they defined? List exact file paths.</Prompt>
      </Section>
      <Section title="Expected">
        <p className="text-sm text-slate-300">Claude should still name <code className="bg-slate-800 px-1 rounded">Session</code>, <code className="bg-slate-800 px-1 rounded">PreparedRequest</code>, <code className="bg-slate-800 px-1 rounded">HTTPAdapter</code> with their correct file paths — without you re-explaining the codebase.</p>
      </Section>
      <Section title="A/B comparison">
        <p className="text-sm text-slate-400 mb-3">Run a long conversation in both modes until compact. Immediately after, ask the same question.</p>
        <ABTable rows={[
          ['Named correct files?', '', ''],
          ['Named correct classes?', '', ''],
          ['Had to re-explain structure?', 'Y (always)', 'N (Sieve re-injects)'],
          ['Verdict', 'baseline', ''],
        ]} />
      </Section>
    </div>
  );
}

function Test07Page() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">TEST-07 — OCR pipeline</h2>
        <p className="text-slate-400 text-sm">Verify screenshot text is extracted and injected. Requires rapidocr-onnxruntime (Python ≤3.13).</p>
      </div>
      <Note variant="warn">OCR requires Python 3.13 or earlier. If you're on Python 3.14, skip this test — rapidocr doesn't support 3.14 yet.</Note>
      <Section title="Steps" accent>
        <Code>{`# Copy any screenshot to the image cache directory
mkdir -p ~/.claude/image-cache
cp /path/to/any/screenshot.png ~/.claude/image-cache/`}</Code>
        <p className="text-sm text-slate-400 mt-3">Then submit any prompt in Claude Code.</p>
      </Section>
      <Section title="Expected">
        <Expected>{`[image: screenshot.png]
• def calculate_total(items):
• Returns sum after discount`}</Expected>
      </Section>
      <Section title="A/B — does Claude actually use the OCR text?">
        <p className="text-sm text-slate-400 mb-3">Take a screenshot of a stack trace or error. Place in <code className="bg-slate-800 px-1 rounded">~/.claude/image-cache/</code>. Run both modes:</p>
        <Prompt>What does this error mean and how do I fix it?</Prompt>
        <ABTable rows={[
          ['Claude referenced image content?', 'N (didn\'t see it)', ''],
          ['Answer used the specific error?', 'N / generic', ''],
          ['Needed follow-up to paste content?', 'Y', ''],
          ['Verdict', 'baseline', ''],
        ]} />
        <Note variant="info">This is a <strong>visual check</strong>, not a judgment call — either the OCR text appears in Claude's response verbatim or it doesn't.</Note>
      </Section>
    </div>
  );
}

function Test08Page() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">TEST-08 — Graceful shutdown</h2>
        <p className="text-slate-400 text-sm">Verify the daemon exits cleanly without corrupting ledger.db.</p>
      </div>
      <Section title="Steps" accent>
        <ol className="space-y-3 text-sm text-slate-300">
          <li className="flex gap-3"><span className="shrink-0 w-6 h-6 rounded-full bg-blue-600/30 text-blue-300 text-xs font-bold flex items-center justify-center">1</span>Start the daemon.</li>
          <li className="flex gap-3"><span className="shrink-0 w-6 h-6 rounded-full bg-blue-600/30 text-blue-300 text-xs font-bold flex items-center justify-center">2</span>Save several files rapidly to create processing load.</li>
          <li className="flex gap-3"><span className="shrink-0 w-6 h-6 rounded-full bg-blue-600/30 text-blue-300 text-xs font-bold flex items-center justify-center">3</span>Press <kbd className="bg-slate-700 px-1.5 py-0.5 rounded text-xs">Ctrl+C</kbd> while files are being processed.</li>
        </ol>
        <Expected>Shutdown signal received — processor exiting</Expected>
      </Section>
      <Section title="Verify DB integrity">
        <Code>{`python3 -c "
import sqlite3, os
db = 'ledger.db'
conn = sqlite3.connect(db)
r = conn.execute('PRAGMA integrity_check').fetchone()
rows = conn.execute('SELECT COUNT(*) FROM context_cache').fetchone()[0]
print(f'Integrity: {r[0]}')
print(f'Cache entries: {rows}')
"`}</Code>
        <Expected>Integrity: ok
Cache entries: [some number]</Expected>
      </Section>
      <Section title="What to check">
        <Checklist id="t08-check" items={[
          'Daemon logs "shutdown signal received" — no Python traceback',
          'integrity_check returns "ok"',
          'No cache entries were lost (count before and after)',
        ]} />
      </Section>
    </div>
  );
}

function Test09Page() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">TEST-09 — MCP tools</h2>
        <p className="text-slate-400 text-sm">Verify the dependency graph and route matching tools work via MCP.</p>
      </div>
      <Section title="Prerequisites">
        <Checklist id="t09-pre" items={[
          'Daemon has run and populated symbol_index',
          'Check: python3 -c "import sqlite3; conn=sqlite3.connect(\'ledger.db\'); print(conn.execute(\'SELECT COUNT(*) FROM symbol_index\').fetchone()[0], \'symbols\')"',
          'MCP server is started: python3 -m src.mcp.server',
          'Claude Code is configured to use the MCP server',
        ]} />
      </Section>
      <Section title="Steps" accent>
        <Prompt>What are the dependencies of requests/adapters.py?</Prompt>
      </Section>
      <Section title="Expected">
        <p className="text-sm text-slate-300">A nested dependency graph showing which files <code className="bg-slate-800 px-1 rounded">adapters.py</code> imports and what those files import in turn.</p>
      </Section>
      <Section title="Three-mode A/B">
        <Prompt>If I change the json parameter handling in requests/api.py, which other files could be affected?</Prompt>
        <ABTable
          headers={['Dimension', 'Mode A — bare', 'Mode B — skeleton only', 'Mode C — MCP + skeleton']}
          rows={[
            ['Named affected files?', '', '', ''],
            ['Traced multi-hop deps?', '', '', ''],
            ['Precision vs grep', '', '', ''],
            ['Verdict', 'baseline', '', ''],
          ]}
        />
        <p className="text-sm text-slate-400 mt-3">Verify with: <code className="bg-slate-800 px-1 rounded">grep -rn "api" /c/.../requests/requests/</code> and compare files Claude named against grep output.</p>
      </Section>
    </div>
  );
}

function Test10Page() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">TEST-10 — Answer quality</h2>
        <p className="text-slate-400 text-sm">Comprehensive objective evaluation of answer quality with and without Sieve.</p>
      </div>

      <Section title="PROMPT-1 — Structural JSON response (grep-verifiable)" accent>
        <Prompt>{`List the top-5 most-imported modules in the requests codebase.
For each, return a JSON object: {"module": "name", "imported_by": ["file1", "file2"]}.
Return only the JSON array, no prose.`}</Prompt>
        <Code>{`# Verify each file Claude named actually exists:
python3 -c "
import json, subprocess
response = '''[paste Claude's JSON here]'''
data = json.loads(response)
for item in data:
    for f in item.get('imported_by', []):
        p = f.lstrip('./')
        result = subprocess.run(['find', '.', '-name', p.split('/')[-1]], capture_output=True, text=True)
        status = '✓' if result.stdout.strip() else '✗ NOT FOUND'
        print(f'{status}  {p}')
"`}</Code>
        <Note variant="info">Pass = all named files exist in the repo.</Note>
      </Section>

      <Section title="PROMPT-2 — Precision/recall against ground truth">
        <Prompt>List every Python file in the requests/ subdirectory. Return just the file paths, one per line, no prose.</Prompt>
        <Code>{`# Ground truth (run this yourself):
find /c/Users/avrha/Documents/projects/Sieve-testing/projects/requests/requests \\
  -name "*.py" | sed 's|.*/requests/||'

# Then compare Claude's list to ground truth
python3 -c "
gt = set(open('ground_truth.txt').read().strip().splitlines())
cl = set(open('claude_answer.txt').read().strip().splitlines())
cl = {p.lstrip('./') for p in cl}
tp = len(gt & cl)
print(f'Precision: {tp/len(cl)*100:.0f}%')
print(f'Recall:    {tp/len(gt)*100:.0f}%')
print(f'Missing:  {gt - cl}')
print(f'Extra:    {cl - gt}')
"`}</Code>
        <Note variant="info">Pass = Precision ≥80% and Recall ≥80%.</Note>
      </Section>

      <Section title="PROMPT-3 — Code generation (execution-based)">
        <Prompt>{`Write a Python function that fetches a URL using the requests library,
retries up to 3 times on connection errors, and returns the response text.
Include a pytest test for it that mocks requests.get.`}</Prompt>
        <Code>{`# Save Claude's code to /tmp/test_fetch.py then run:
python3 -m pytest /tmp/test_fetch.py -v`}</Code>
        <Note variant="info">Pass = pytest exits 0 (all tests pass).</Note>
      </Section>

      <Section title="PROMPT-4 — LLM-as-judge">
        <p className="text-sm text-slate-400 mb-2">Use Ollama to evaluate whether Claude's answer about a specific implementation is correct:</p>
        <Code>{`ollama run qwen2.5-coder:1.5b "
You are evaluating an AI answer about the requests library source code.
Question: 'How does HTTPAdapter.send() handle SSL verification?'
Correct answer must mention: verify parameter, ssl_context, cert, urllib3.
Score the following answer 0-10 for factual accuracy.

Answer: [paste Claude's response here]

Reply with just: SCORE: X/10 VERDICT: pass|fail
"`}</Code>
        <Note variant="info">Pass = Score ≥ 7/10.</Note>
      </Section>

      <Section title="PROMPT-5 — AST structural check">
        <Prompt>{`Write a Python function called process_items(items) that loops over items,
skips None values, and returns a list of processed results.`}</Prompt>
        <Code>{`python3 -c "
import ast, sys
src = open('/tmp/claude_code.py').read()
tree = ast.parse(src)
has_param = any(
    arg.arg == 'items'
    for node in ast.walk(tree)
    if isinstance(node, ast.FunctionDef) and node.name == 'process_items'
    for arg in node.args.args
)
has_loop = any(isinstance(n, (ast.For, ast.While)) for n in ast.walk(tree))
print('✓ param' if has_param else '✗ missing items param')
print('✓ loop' if has_loop else '✗ missing loop')
"`}</Code>
        <Note variant="info">Pass = both checks print ✓.</Note>
      </Section>
    </div>
  );
}

function ConsistencyPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">Consistency Checks</h2>
        <p className="text-slate-400 text-sm">Verify the hook behaves identically across repeated runs and edge cases.</p>
      </div>

      <Section title="CONSISTENCY-01 — Determinism (5 runs, identical output)" accent>
        <Code>{`cd /c/Users/avrha/Documents/projects/Sieve-testing/projects/requests
SIEVE_PROMPT='test' python3 .../sieve/bin/sieve-hook --mode=prompt > /tmp/sieve_r1.txt
for i in 2 3 4 5; do
  SIEVE_PROMPT='test' python3 .../sieve/bin/sieve-hook --mode=prompt > /tmp/sieve_r$i.txt
  diff -q /tmp/sieve_r1.txt /tmp/sieve_r$i.txt >/dev/null 2>&1 && echo "Run $i: identical" || echo "Run $i: DIFFERS"
done`}</Code>
        <Note variant="info">Pass = all 5 runs produce identical output.</Note>
      </Section>

      <Section title="CONSISTENCY-02 — Latency stability (10 runs, p100 &lt;50ms)">
        <Code>{`OVER=0; MAX=0
for i in $(seq 1 10); do
  S=$(date +%s%N)
  SIEVE_PROMPT='test' python3 .../sieve/bin/sieve-hook --mode=prompt >/dev/null 2>&1
  E=$(date +%s%N)
  MS=$(( (E-S)/1000000 ))
  [ $MS -gt $MAX ] && MAX=$MS
  echo "Run $i: ${MS}ms"
  [ $MS -gt 50 ] && OVER=$((OVER+1))
done
echo "Peak: ${MAX}ms — ${OVER} run(s) over 50ms"`}</Code>
        <Note variant="info">Pass = zero runs exceed 50ms. Warn if 1–2 exceed. Fail if 3+.</Note>
      </Section>

      <Section title="CONSISTENCY-03 — Cross-project reduction">
        <p className="text-sm text-slate-400 mb-2">Verify 70%+ reduction across all three test repos.</p>
        <Code>{`for repo in requests click httpx; do
  PROJ=/c/Users/avrha/Documents/projects/Sieve-testing/projects/$repo
  SIEVE_PROMPT='test' python3 .../sieve/bin/sieve-hook --mode=prompt > /tmp/sk_$repo.txt 2>/dev/null
  SKEL=$(wc -c < /tmp/sk_$repo.txt)
  RAW=$(find $PROJ -name "*.py" | xargs wc -c 2>/dev/null | tail -1 | awk '{print $1}')
  python3 -c "print(f'$repo: {(1-$SKEL/$RAW)*100:.1f}% reduction')"
done`}</Code>
        <Note variant="info">Pass = all three repos show ≥70% reduction.</Note>
      </Section>

      <Section title="CONSISTENCY-06 — AST hash gate">
        <p className="text-sm text-slate-400 mb-2">Verify comment-only edits are skipped; structural changes trigger re-summary.</p>
        <Code>{`LOG=/tmp/sieve_ast_test.log
python3 .../sieve/src/main.py .../requests >"$LOG" 2>&1 &
DPID=$!; sleep 2

# Test 1: comment only — should NOT trigger re-summary
echo "# sieve hash test $(date +%s)" >> requests/api.py
sleep 5

# Test 2: new function — SHOULD trigger re-summary
printf "\\ndef _sieve_hash_test():\\n    return True\\n" >> requests/api.py
sleep 7

kill $DPID 2>/dev/null; wait $DPID 2>/dev/null
SKIP=$(grep -c "AST unchanged" "$LOG" 2>/dev/null || echo 0)
UPD=$(grep -c "Cache updated" "$LOG" 2>/dev/null || echo 0)
echo "AST unchanged (skipped): $SKIP"
echo "Cache updated (processed): $UPD"
git checkout requests/api.py 2>/dev/null || true
rm -f "$LOG"
[ "$SKIP" -ge 1 ] && [ "$UPD" -ge 1 ] && echo "PASS" || echo "FAIL: skip=$SKIP update=$UPD"`}</Code>
        <Note variant="info">Pass = SKIP ≥ 1 and UPD ≥ 1.</Note>
      </Section>
    </div>
  );
}

// ─── Page map ────────────────────────────────────────────────────────────────
const PAGE_COMPONENTS = {
  quickstart:  QuickStartPage,
  setup:       SetupPage,
  'ab-method': ABMethodPage,
  'test-01':   Test01Page,
  'test-02':   Test02Page,
  'test-03':   Test03Page,
  'test-04':   Test04Page,
  'test-05':   Test05Page,
  'test-06':   Test06Page,
  'test-07':   Test07Page,
  'test-08':   Test08Page,
  'test-09':   Test09Page,
  'test-10':   Test10Page,
  consistency: ConsistencyPage,
};

// ─── App ─────────────────────────────────────────────────────────────────────
export default function App() {
  const [activePage, setActivePage] = useState('quickstart');
  const [mobileOpen, setMobileOpen] = useState(false);

  const PageComponent = PAGE_COMPONENTS[activePage] || QuickStartPage;

  return (
    <div className="min-h-screen bg-[#090b10] text-slate-200 flex font-sans">
      {/* Mobile header */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-20 flex items-center justify-between p-4 bg-[#0d1117] border-b border-slate-800">
        <span className="font-bold flex items-center gap-2 text-sm">
          <BookOpen size={16} className="text-blue-400" /> Sieve Testing Guide
        </span>
        <button onClick={() => setMobileOpen(v => !v)} className="p-1.5 rounded hover:bg-slate-800 text-slate-400">
          {mobileOpen ? <X size={18} /> : <Menu size={18} />}
        </button>
      </div>

      {/* Sidebar */}
      <aside className={`
        ${mobileOpen ? 'fixed inset-0 top-14 z-10 bg-[#090b10]' : 'hidden'}
        md:flex md:flex-col md:w-72 md:shrink-0 bg-[#0d1117] border-r border-slate-800 md:h-screen md:sticky md:top-0
      `}>
        <div className="p-5 hidden md:flex items-center gap-2.5">
          <BookOpen size={18} className="text-blue-400 shrink-0" />
          <span className="font-bold text-base text-white">Sieve Testing Guide</span>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 pb-6 space-y-0.5">
          {/* Group dividers */}
          <p className="px-3 pt-2 pb-1 text-xs font-semibold uppercase tracking-wider text-slate-600">Getting started</p>
          {PAGES.slice(0, 3).map(pg => {
            const Icon = pg.icon;
            return (
              <button key={pg.id} onClick={() => { setActivePage(pg.id); setMobileOpen(false); }}
                className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-medium transition-all
                  ${activePage === pg.id ? 'bg-blue-500/15 text-blue-300 border border-blue-700/40' : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'}`}>
                <Icon size={15} className="shrink-0" />
                <span>{pg.label}</span>
              </button>
            );
          })}

          <p className="px-3 pt-4 pb-1 text-xs font-semibold uppercase tracking-wider text-slate-600">Test cases</p>
          {PAGES.slice(3, 13).map(pg => {
            const Icon = pg.icon;
            return (
              <button key={pg.id} onClick={() => { setActivePage(pg.id); setMobileOpen(false); }}
                className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-medium transition-all
                  ${activePage === pg.id ? 'bg-blue-500/15 text-blue-300 border border-blue-700/40' : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'}`}>
                <Icon size={15} className="shrink-0" />
                <span>{pg.label}</span>
              </button>
            );
          })}

          <p className="px-3 pt-4 pb-1 text-xs font-semibold uppercase tracking-wider text-slate-600">Quality</p>
          {PAGES.slice(13).map(pg => {
            const Icon = pg.icon;
            return (
              <button key={pg.id} onClick={() => { setActivePage(pg.id); setMobileOpen(false); }}
                className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-medium transition-all
                  ${activePage === pg.id ? 'bg-blue-500/15 text-blue-300 border border-blue-700/40' : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'}`}>
                <Icon size={15} className="shrink-0" />
                <span>{pg.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto h-screen pt-14 md:pt-0">
        <div className="max-w-3xl mx-auto p-5 md:p-10 pb-24">
          <PageComponent />

          {/* Prev / Next navigation */}
          <div className="flex justify-between items-center mt-10 pt-6 border-t border-slate-800">
            {(() => {
              const idx = PAGES.findIndex(p => p.id === activePage);
              const prev = PAGES[idx - 1];
              const next = PAGES[idx + 1];
              return (
                <>
                  {prev
                    ? <button onClick={() => setActivePage(prev.id)}
                        className="flex items-center gap-2 text-sm text-slate-400 hover:text-slate-200 transition-colors">
                        ← {prev.label}
                      </button>
                    : <div />}
                  {next
                    ? <button onClick={() => setActivePage(next.id)}
                        className="flex items-center gap-2 text-sm text-blue-400 hover:text-blue-300 transition-colors">
                        {next.label} →
                      </button>
                    : <div />}
                </>
              );
            })()}
          </div>
        </div>
      </main>
    </div>
  );
}
