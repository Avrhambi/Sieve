"""Integration tests for Sieve deployment targets.

Passing criteria:
  - Token reduction >70% for a synthetic project of 60 Python files
"""
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Token reduction >70% on a 60-file synthetic project
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
