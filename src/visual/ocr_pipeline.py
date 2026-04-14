"""OCR pipeline — extracts text from images using RapidOCR (CPU-only, ~30MB)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

from src.main import load_config

logger = logging.getLogger(__name__)

# Lazily initialised so import cost is zero.
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR  # ~30MB, CPU-only
        _engine = RapidOCR()
    return _engine


def extract_text(image_path: Union[str, Path]) -> str:
    """Extract all readable text from *image_path* using RapidOCR.

    Args:
        image_path: Absolute or relative path to a PNG/JPG/BMP/TIFF image.

    Returns:
        A single string with all detected text lines joined by newlines.
        Returns an empty string if no text is detected or the image cannot
        be read.

    Invariants:
        - No VRAM-heavy model is loaded; RapidOCR runs entirely on CPU.
        - Reads ``config.thresholds.VRAM_THRESHOLD_MB`` from sieve.config.toml
          but does not gate on it (CPU pipeline is always safe to run).
        - Never raises; logs warnings on failure and returns ``""``.
    """
    config = load_config()
    vram_threshold = config.thresholds.VRAM_THRESHOLD_MB
    logger.debug("extract_text: VRAM_THRESHOLD_MB=%d (CPU path always used)", vram_threshold)

    image_path = Path(image_path)
    if not image_path.exists():
        logger.warning("extract_text: file not found: %s", image_path)
        return ""

    try:
        engine = _get_engine()
        result, _elapse = engine(str(image_path))
    except Exception as exc:  # noqa: BLE001
        logger.warning("extract_text: RapidOCR failed for %s: %s", image_path, exc)
        return ""

    if not result:
        return ""

    lines: list[str] = []
    for item in result:
        # RapidOCR returns [box, text, score] per detected region.
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            text = str(item[1]).strip()
            if text:
                lines.append(text)

    return "\n".join(lines)
