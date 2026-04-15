"""Integration tests for Sieve deployment targets.

Passing criteria (from Section 9 of the design):
  - Hook latency <50ms p95 for cached files (native Linux; skipped on WSL2)
  - Token reduction >70% for a synthetic project of 60 Python files
  - Zero SQLITE_BUSY errors during concurrent daemon/hook access
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def _is_wsl2() -> bool:
    """Detect WSL2: hook adds ~150 ms I/O overhead that cannot be code-optimised."""
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text()
        return "microsoft" in release.lower()
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Test 1 — Hook latency <50 ms (p95), cached path
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    _is_wsl2(),
    reason=(
        "WSL2 Windows-filesystem I/O adds ~150 ms Python startup overhead "
        "that cannot be eliminated in code (documented in TASK-07 notes). "
        "Run on native Linux to verify the <50 ms target."
    ),
)
def test_hook_latency_under_50ms(tmp_path):
    """p95 of five subprocess runs of bin/sieve-hook must be <50 ms.

    The daemon is intentionally kept offline so the fast stdlib-only fallback
    path (file-tree heuristic) is exercised — the same path that runs in
    production whenever the daemon restarts.
    """
    hook = str(REPO_ROOT / "bin" / "sieve-hook")
    python = sys.executable

    # Warm the .pyc cache with two throwaway runs so compilation cost is
    # excluded from the timed sample.
    for _ in range(2):
        subprocess.run(
            [python, hook, "--mode=prompt"],
            capture_output=True,
            cwd=str(REPO_ROOT),
        )

    latencies_ms: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        result = subprocess.run(
            [python, hook, "--mode=prompt"],
            capture_output=True,
            cwd=str(REPO_ROOT),
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies_ms.append(elapsed_ms)
        assert result.returncode == 0, (
            f"sieve-hook exited {result.returncode}; "
            f"stderr: {result.stderr.decode()}"
        )

    latencies_ms.sort()
    p95_ms = latencies_ms[int(len(latencies_ms) * 0.95)]  # index 4 of 5

    assert p95_ms < 50.0, (
        f"Hook p95 latency {p95_ms:.1f} ms exceeds 50 ms limit. "
        f"All samples: {[f'{v:.1f}' for v in latencies_ms]}"
    )


# ---------------------------------------------------------------------------
# Test 2 — Token reduction >70% on a 60-file synthetic project
# ---------------------------------------------------------------------------

def _generate_py_file(index: int) -> bytes:
    """Return a 50-line Python source as bytes (function + docstring)."""
    lines = [
        f'"""Module {index}: synthetic file for token-reduction benchmarking."""',
        "",
        "",
        f"def compute_{index}(value: int, multiplier: float) -> float:",
        f'    """Compute a scaled result for index {index}.',
        "    ",
        "    Args:",
        "        value: integer input operand.",
        "        multiplier: float scaling factor.",
        "    ",
        "    Returns:",
        "        Scaled float result.",
        '    """',
    ]
    # Add body lines to reach ~50 total lines
    for j in range(35):
        lines.append(f"    step_{j} = value * multiplier + {j} * 0.1  # iteration {j}")
    lines.append("    return step_34")
    return "\n".join(lines).encode()


def test_token_reduction_over_70_percent():
    """Skeletonizing 60 Python files must reduce approximate token count by >70%.

    Token approximation: len(source_bytes) / 4  (matches GPT-family rule of thumb).
    This is intentionally coarse — the real reduction will be higher because
    tree-sitter collapses multi-line bodies to a single '...' line.
    """
    # Ensure src package is importable without a venv
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from src.core.skeletonizer import skeletonize  # noqa: PLC0415

    n_files = 60
    total_raw_tokens = 0.0
    total_skeleton_tokens = 0.0

    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(n_files):
            source = _generate_py_file(i)
            path = Path(tmpdir) / f"module_{i:03d}.py"
            path.write_bytes(source)

            raw_tokens = len(source) / 4.0
            skeleton = skeletonize(source, "python")
            skeleton_tokens = len(skeleton.encode("utf-8")) / 4.0

            total_raw_tokens += raw_tokens
            total_skeleton_tokens += skeleton_tokens

    assert total_raw_tokens > 0, "No tokens counted — file generation failed"
    reduction = 1.0 - (total_skeleton_tokens / total_raw_tokens)

    assert reduction > 0.70, (
        f"Token reduction {reduction:.1%} did not exceed 70% target. "
        f"Raw: {total_raw_tokens:.0f} tokens, "
        f"Skeleton: {total_skeleton_tokens:.0f} tokens across {n_files} files."
    )
