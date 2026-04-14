"""Local inference with tiered heuristic → Ollama → fallback logic."""
import asyncio
import logging
import re
import subprocess
from typing import Optional

import aiohttp

from src.main import load_config

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5-coder:1.5b"
HEURISTIC_LINE_THRESHOLD = 5

# Semaphore is created lazily on first use to avoid binding to a specific event loop.
_semaphore: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        config = load_config()
        _semaphore = asyncio.Semaphore(config.thresholds.OLLAMA_NUM_PARALLEL)
    return _semaphore


def _available_ram_mb() -> int:
    """Return available RAM in MB using /proc/meminfo (Linux)."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return kb // 1024
    except OSError:
        pass
    return 999_999  # assume sufficient if unreadable


def _available_vram_mb() -> int:
    """Return free VRAM in MB via nvidia-smi; returns large value if no GPU detected."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            timeout=3,
            stderr=subprocess.DEVNULL,
        )
        values = [int(v.strip()) for v in out.decode().splitlines() if v.strip()]
        return max(values) if values else 999_999
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        # No NVIDIA GPU — CPU-only inference, treat VRAM as non-limiting
        return 999_999


def _heuristic_summary(source: str, language: str) -> str:
    """Fast regex-based summary for tiny files — no LLM call."""
    non_blank = [l for l in source.splitlines() if l.strip()]

    if language == "python":
        defs = re.findall(r"^(?:async\s+)?def\s+(\w+)|^class\s+(\w+)", source, re.MULTILINE)
        symbols = [d[0] or d[1] for d in defs]
        if symbols:
            return f"Defines: {', '.join(symbols)}"
    elif language in ("javascript", "typescript"):
        defs = re.findall(
            r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\()",
            source,
        )
        symbols = [d[0] or d[1] for d in defs]
        if symbols:
            return f"Defines: {', '.join(symbols)}"

    return f"Short {language} snippet ({len(non_blank)} lines)"


async def _ollama_summarize(source: str, language: str) -> Optional[str]:
    """Async Ollama call — sequential batching enforced by semaphore."""
    prompt = (
        f"Summarize this {language} code in one concise sentence (max 20 words). "
        f"Return only the summary, no preamble.\n\n{source}"
    )
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}

    async with _get_semaphore():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    OLLAMA_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("response", "").strip() or None
        except (
            aiohttp.ClientConnectorError,
            aiohttp.ServerConnectionError,
            asyncio.TimeoutError,
        ):
            logger.debug("Ollama unreachable — falling back to heuristic")

    return None


async def summarize(source: str, language: str) -> str:
    """Return a one-sentence summary of the given source code.

    Tier selection (in order):
    1. **Heuristic** — source has ≤5 non-blank lines.
    2. **Ollama** (Qwen2.5-Coder-1.5B) — async, semaphore-bounded to
       ``config.thresholds.OLLAMA_NUM_PARALLEL`` (always 1).
       Skipped if available VRAM < ``VRAM_THRESHOLD_MB`` or
       available RAM < ``RAM_THRESHOLD_MB``.
    3. **Fallback** — heuristic summary when Ollama is unreachable;
       no exception is raised.

    Config keys read:
    - ``config.thresholds.VRAM_THRESHOLD_MB``
    - ``config.thresholds.RAM_THRESHOLD_MB``
    - ``config.thresholds.OLLAMA_NUM_PARALLEL``
    """
    config = load_config()
    non_blank = [l for l in source.splitlines() if l.strip()]

    # Tier 1: heuristic for tiny files
    if len(non_blank) <= HEURISTIC_LINE_THRESHOLD:
        return _heuristic_summary(source, language)

    # Resource guard: skip Ollama if system is under threshold
    if _available_vram_mb() < config.thresholds.VRAM_THRESHOLD_MB:
        logger.debug("VRAM below threshold — using heuristic")
        return _heuristic_summary(source, language)

    if _available_ram_mb() < config.thresholds.RAM_THRESHOLD_MB:
        logger.debug("RAM below threshold — using heuristic")
        return _heuristic_summary(source, language)

    # Tier 2: Ollama
    result = await _ollama_summarize(source, language)

    # Tier 3: fallback if Ollama unreachable
    if result is None:
        return _heuristic_summary(source, language)

    return result
