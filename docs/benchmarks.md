# Sieve benchmarks

All numbers below are **measured**, not estimated. Each has a reproduce command,
the raw result, and the environment it was taken on. Every quantitative claim in
`README.md` traces back to a row here.

- **Date measured:** 2026-09-06
- **Environment:** Windows 11, Python 3.14.3 (CPython), `python` on PATH, deps
  installed globally, all commands run from the repo root on branch
  `deterministic-index`.
- **Machine:** developer laptop (single run, not a controlled benchmark rig —
  throughput is indicative, not a spec).

> **On "reduction" numbers:** every reduction figure here is a **character
> count** — `len()` on the source text vs `len()` on the skeleton string. It is a
> proxy for token savings, not a tokenizer measurement. Character count and
> sub-word token count are monotonically correlated for source code, so the
> direction is right, but the exact percentage would shift a few points under a
> real BPE tokenizer.

---

## 1. Test suite

**Reproduce:**
```bash
python -m pytest tests/ -q
```

**Result:** `111 passed in ~1.9s` (1.9s/1.8s/2.1s across runs).

**Per-file breakdown** (`for f in tests/test_*.py; do python -m pytest "$f" -q; done`).
The per-file wall times sum to more than the whole-suite total because each
separate `pytest` invocation re-pays interpreter startup and tree-sitter import:

| File | Tests | Wall time | Covers |
|---|---|---|---|
| `test_skeleton.py` | 27 | 0.30s | AST body-stripping — Python, JS, TS, Markdown, Go, Rust |
| `test_determinism.py` | 26 | 2.31s | **Determinism suite** (see §5) — pure-function repeats, `PYTHONHASHSEED` cross-process, end-to-end pipeline, AST-hash gate |
| `test_mcp.py` | 26 | 0.04s | `sieve_find` scoring, keyword/stem extraction, silence gate |
| `test_json_api.py` | 8 | 0.51s | `cs` JSON shape — skeleton, repo-map, diff |
| `test_benchmark.py` | 7 | 0.51s | Reduction ≥70% + semantic preservation, 3 languages (see §3) |
| `test_cli.py` | 8 | 0.42s | `cs` dispatch, JSON round-trip, ledger discovery (`--db` / `$SIEVE_DB` / walk-up) |
| `test_snapshot_writer.py` | 4 | 0.29s | Commit-queue consumer → `structural_snapshots` |
| `test_watcher_commit.py` | 4 | 0.30s | Reflog-based commit detection; checkout/reset events ignored |
| `test_integration.py` | 1 | 0.52s | Reduction >70% on a synthetic 60-file project (see §3) |

**26 of 111 tests (23%) are determinism tests** — the largest single group.

---

## 2. Skeleton reduction on Sieve's own `src/` (real code)

**Reproduce:**
```bash
python docs/bench/bench.py
```
(Section 1 of the script. It skeletonizes every `src/**/*.py` and reports
`len(skeletonize(source, "python"))` vs `len(source)` — a character count.)

**Result** (14 files, Python only — the repo has no JS/TS/Go/Rust source; those
languages are exercised only by fixtures in `tests/`, see §3):

| File | Source chars | Skeleton chars | Reduction |
|---|---|---|---|
| `src/cli.py` | 4,115 | 1,148 | 72.1% |
| `src/config.py` | 534 | 481 | 9.9% |
| `src/core/inference.py` | 4,338 | 1,527 | 64.8% |
| `src/core/registry.py` | 1,023 | 992 | 3.0% |
| `src/core/skeletonizer.py` | 13,962 | 4,563 | 67.3% |
| `src/daemon/heartbeat.py` | 2,243 | 1,467 | 34.6% |
| `src/daemon/processor.py` | 10,107 | 4,241 | 58.0% |
| `src/daemon/snapshot_writer.py` | 2,046 | 774 | 62.2% |
| `src/daemon/watcher.py` | 7,511 | 3,809 | 49.3% |
| `src/data/ledger.py` | 8,823 | 4,124 | 53.3% |
| `src/layers/json_api.py` | 7,655 | 2,370 | 69.0% |
| `src/main.py` | 2,690 | 1,069 | 60.3% |
| `src/mcp/scoring.py` | 2,039 | 1,283 | 37.1% |
| `src/mcp/server.py` | 8,811 | 4,095 | 53.5% |
| **AGGREGATE** | **75,897** | **31,943** | **57.9%** |

**Reading this honestly:** Sieve's own source is *not* body-heavy — it is small
functions with long docstrings, module-level constant tables (`registry.py`,
`config.py` barely shrink), and comment blocks the skeletonizer keeps. Reduction
scales with body density; see §3 for body-heavy inputs where it reaches 75–89%.

### 2b. Multi-language fixtures (`tests/`)

The repo has no non-Python source. The only JS/TS/Go/Rust inputs are the small
(~25–40 line) fixtures in `tests/test_determinism.py`. Section `1b` of
`bench.py` skeletonizes each:

| Language | Source chars | Skeleton chars | Reduction |
|---|---|---|---|
| python | 894 | 690 | 22.8% |
| javascript | 646 | 331 | 48.8% |
| typescript | 820 | 505 | 38.4% |
| go | 451 | 295 | 34.6% |
| rust | 581 | 378 | 34.9% |

These fixtures are almost all signature + one-line bodies, so reduction is low —
they confirm the skeletonizer *runs* on all six languages, not a headline ratio.
For body-heavy JS/TS see §3.

---

## 3. Reduction thresholds asserted by the test suite

These tests already assert reduction floors. Numbers below are what they compute
(captured via `-s`; assertions unchanged).

**Reproduce** (the `PYTHONIOENCODING` prefix only matters on a non-UTF-8 console
such as Windows `cp1255`, where the test's `→` in a `-s` print would otherwise
raise `UnicodeEncodeError` *after* computing the numbers):
```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_benchmark.py::test_reduction_summary -s -q -o addopts=""
PYTHONIOENCODING=utf-8 python -m pytest tests/test_integration.py -s -q -o addopts=""
```

**`test_benchmark.py`** — synthetic body-heavy fixtures (~300 lines each),
character count, asserts ratio ≤ 0.30 (≥70% reduction):

| Language | Source chars | Skeleton chars | Reduction |
|---|---|---|---|
| Python | 14,858 | 2,256 | 84.8% |
| JavaScript | 10,000 | 1,113 | 88.9% |
| TypeScript | 7,747 | 1,952 | 74.8% |

**`test_integration.py`** — synthetic **60-file** Python project, 50 lines/file
(13-line signature+docstring header, 35-line body). Uses a `len(bytes)/4`
token approximation, asserts >70%:

- raw ≈ 36,098 tokens → skeleton ≈ 4,898 tokens → **86.4% reduction**.

---

## 4. Index throughput

**Reproduce:**
```bash
python docs/bench/bench.py
```
(Section 2. For each of 3 runs: wipe the ledger, then drive the real
`src.daemon.processor.process_file` over all 14 `src/**/*.py` files with a fresh
`asyncio.Queue`; time with `time.perf_counter`; report best of 3.)

**Result** (independent invocations, best-of-3 each):
- `237–261 ms` for 14 files across runs → **53–59 files/sec** on this machine
- a second machine (Windows 11, Python 3.14) measured **51–53 files/sec**
- **~50–60 files/sec (~17–20 ms/file)** for 14 files — timing varies with
  machine and load; treat as indicative, not a spec

This is the full pipeline per file: `_compute_ast_hash` (parse) →
`skeletonize` (tree-sitter) → `summarize` → `_extract_symbols` (`ast.walk` +
`ast.unparse`) → 4 SQLite upserts. On a warm ledger where the AST hash is
unchanged, the gate short-circuits after the parse and the per-file cost drops
(not separately benchmarked). Small absolute numbers — this is a side-project
index over a single tree, run once per file-save in practice, not a batch job.

---

## 5. Determinism proof

The guarantee: **the same repository state always produces a byte-identical
index** — no LLM, no clock, no RNG, no subprocess in the indexing path, and
dict/set iteration order (hash-seed dependent) never leaks into output.

**Reproduce:**
```bash
python -m pytest tests/test_determinism.py -q
python -m pytest tests/test_determinism.py::TestEndToEndPipelineDeterminism -q
```

**Result:** `26 passed`. The end-to-end proof
(`TestEndToEndPipelineDeterminism`, 2 tests, passing):

- `test_two_full_runs_produce_identical_index` — builds a multi-file project
  (Python + JS + Markdown), runs `process_file` over all of it, dumps
  `context_cache` + `symbol_index`, **wipes the DB**, runs the identical
  pipeline again, and asserts the two dumps are equal row-for-row.
- `test_index_is_stable_over_many_runs` — repeats the wipe-and-rerun 3× and
  asserts `len({repr(dump) for run}) == 1` (exactly one distinct index state).

Supporting guarantees also enforced in the same file:
- `TestHashRandomizationIsInert` — spawns subprocesses with `PYTHONHASHSEED=0`
  vs `1`; `summarize` / `_extract_symbols` output must be identical.
- `TestAstHashGate` — same bytes → same hash; whitespace/comment-only edit →
  **unchanged** hash (re-processing skipped); signature change → hash changes.

---

## Appendix: numbers used in README.md

| README claim | Source | Command |
|---|---|---|
| 111 tests, ~1.9s | §1 | `python -m pytest tests/ -q` |
| 26 determinism tests | §1 | `python -m pytest tests/test_determinism.py -q` |
| 57.9% char reduction on `src/` | §2 | `python docs/bench/bench.py` |
| 74.8–88.9% reduction on body-heavy code | §3 | `PYTHONIOENCODING=utf-8 python -m pytest tests/test_benchmark.py::test_reduction_summary -s -o addopts=""` |
| 86.4% on the 60-file synthetic project | §3 | `PYTHONIOENCODING=utf-8 python -m pytest tests/test_integration.py -s -o addopts=""` |
| ~50–60 files/sec indexing | §4 | `python docs/bench/bench.py` |
| skeletonizer runs on all 6 languages | §2b | `python docs/bench/bench.py` |
| byte-identical index across runs | §5 | `pytest tests/test_determinism.py::TestEndToEndPipelineDeterminism -q` |
