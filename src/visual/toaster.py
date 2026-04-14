"""Toaster — converts raw OCR text into compact bulleted Structural Toasts."""
from __future__ import annotations

import re


# Patterns that identify lines unlikely to carry semantic value.
_NOISE_RE = re.compile(
    r"""
    ^\s*$                       # blank lines
    | ^\s*[-–—_=*]{3,}\s*$      # horizontal rules / separators
    | ^\s*[│┃|]\s*$             # lone box-drawing characters
    """,
    re.VERBOSE,
)

# Collapse runs of whitespace inside a line.
_WHITESPACE_RE = re.compile(r"\s{2,}")


def to_toast(raw_text: str) -> str:
    """Format *raw_text* (from :func:`~src.visual.ocr_pipeline.extract_text`)
    into a bulleted Structural Toast.

    Each non-trivial line from *raw_text* becomes one bullet.  Duplicate lines
    are deduplicated while preserving first-occurrence order.  Blank output
    (no meaningful lines) returns the sentinel string ``"(no content)"``.

    Args:
        raw_text: Multi-line string produced by the OCR pipeline.

    Returns:
        A bulleted list string, e.g.::

            • def calculate_total(items: list[Item]) -> float:
            • Returns sum of item prices after discount
            • raise ValueError if items is empty

        or ``"(no content)"`` when nothing meaningful was detected.

    Invariants:
        - No I/O; pure transformation.
        - No VRAM-heavy models imported or called.
        - Deduplication is case-sensitive and order-preserving.
    """
    if not raw_text or not raw_text.strip():
        return "(no content)"

    seen: set[str] = set()
    bullets: list[str] = []

    for line in raw_text.splitlines():
        # Normalise internal whitespace.
        cleaned = _WHITESPACE_RE.sub(" ", line).strip()

        # Skip noise lines.
        if _NOISE_RE.match(cleaned):
            continue

        # Skip duplicates.
        if cleaned in seen:
            continue

        seen.add(cleaned)
        bullets.append(f"• {cleaned}")

    if not bullets:
        return "(no content)"

    return "\n".join(bullets)
