"""Local inference with tiered heuristic → Ollama → fallback logic."""
import asyncio
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

import aiohttp

from src.main import load_config

logger = logging.getLogger(__name__)

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


def _get_free_vram_mb() -> int:
    # Try NVIDIA
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL, timeout=3
        )
        return int(out.decode().strip().split("\n")[0])
    except Exception:
        pass

    # Try AMD ROCm
    try:
        out = subprocess.check_output(
            ["rocm-smi", "--showmeminfo", "vram", "--json"],
            stderr=subprocess.DEVNULL, timeout=3
        )
        import json as _json
        data = _json.loads(out.decode())
        # rocm-smi JSON: {"card0": {"VRAM Total Memory (B)": X, "VRAM Total Used Memory (B)": Y}}
        for card in data.values():
            total = int(card.get("VRAM Total Memory (B)", 0))
            used = int(card.get("VRAM Total Used Memory (B)", 0))
            if total > 0:
                return (total - used) // (1024 * 1024)
    except Exception:
        pass

    # Try AMD sysfs
    try:
        vram_total = int(Path("/sys/class/drm/card0/device/mem_info_vram_total").read_text().strip())
        vram_used = int(Path("/sys/class/drm/card0/device/mem_info_vram_used").read_text().strip())
        return (vram_total - vram_used) // (1024 * 1024)
    except Exception:
        pass

    # No GPU detection possible — return 0 to force heuristic (safe default)
    return 0


def _available_vram_mb() -> int:
    """Return free VRAM in MB; returns large value if no GPU detected."""
    result = _get_free_vram_mb()
    if result == 0:
        # No GPU — CPU-only inference, treat VRAM as non-limiting
        return 999_999
    return result


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
    import toml as _toml
    from src.main import CONFIG_PATH as _CONFIG_PATH
    _raw = _toml.load(str(_CONFIG_PATH))
    host = _raw.get("OLLAMA_HOST", "localhost")
    port = _raw.get("OLLAMA_PORT", 11434)
    model = _raw.get("OLLAMA_MODEL", "qwen2.5-coder:1.5b")
    url = f"http://{host}:{port}/api/generate"

    prompt = (
        f"Summarize this {language} code in one concise sentence (max 20 words). "
        f"Return only the summary, no preamble.\n\n{source}"
    )
    payload = {"model": model, "prompt": prompt, "stream": False}

    async with _get_semaphore():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
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
