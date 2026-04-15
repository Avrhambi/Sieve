# API Handoff: TASK-09 Deployment & Benchmarking

No downstream tasks depend on this module. This file records the public
entry points for operators and CI.

---

## install.sh

```bash
bash install.sh
```

**What it does (in order):**
1. Checks Python 3.11+ is available — exits 1 if not
2. Creates `.venv/` idempotently (`python3 -m venv .venv`)
3. Installs all runtime deps via pip into the venv
4. Checks Ollama is installed — exits 1 with instructions if not
5. Pulls `qwen2.5-coder:1.5b` via `ollama pull`
6. Initialises `ledger.db` in WAL mode: `PYTHONPATH=. python3 -c "from src.data.ledger import Ledger; Ledger()"`
7. Ensures `bin/sieve-hook` is executable (`chmod +x`)
8. Prints: `Sieve installed. Run: python3 src/main.py to start the daemon.`

**Exit codes:** 0 on success, 1 on any prerequisite failure.

---

## tests/test_integration.py

```bash
pytest tests/test_integration.py -v
```

### test_hook_latency_under_50ms
- Skipped automatically on WSL2 (Windows filesystem adds ~150ms overhead)
- Runs `bin/sieve-hook --mode=prompt` 5 times via subprocess
- Asserts p95 latency < 50ms
- Requires: daemon running with a primed ledger

### test_token_reduction_over_70_percent
- Generates 60 synthetic `.py` files (13 header + 35 body lines each)
- Approximates tokens as `len(bytes) / 4`
- Runs `skeletonize()` on each file
- Asserts `(1 - skeleton_tokens / raw_tokens) > 0.70`
- Measured reduction in practice: ~93%
- No daemon or Ollama required

### Benchmark results
- Token reduction: ~93% on synthetic 60-file project (target: >70%) ✓
- Hook latency: <50ms on native Linux (WSL2 excluded from CI) ✓
