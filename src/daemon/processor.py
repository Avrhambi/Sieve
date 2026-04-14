"""Background processor — consumes the watcher queue and updates context_cache.

Key guarantees
--------------
* **AST-hash gate**: ``summarize()`` is called only when the file's AST
  structure changes.  Whitespace-only or comment-only edits leave the hash
  unchanged → no LLM round-trip.
* **Resource governors**: If available RAM or VRAM drops below the thresholds
  in ``sieve.config.toml``, processing pauses (``asyncio.sleep``) until
  resources recover.  The hook is never blocked — all work is async.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import subprocess
from pathlib import Path

from src.core.skeletonizer import skeletonize
from src.core.inference import summarize
from src.data.ledger import Ledger, LedgerError
from src.daemon.watcher import get_queue
from src.main import load_config

logger = logging.getLogger(__name__)

_RESOURCE_POLL_INTERVAL: float = 5.0   # seconds to sleep while resources are low
_QUEUE_TIMEOUT: float = 1.0            # seconds to wait on an empty queue

# Maps file extension → language string used by skeletonizer / summarize.
_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".md": "markdown",
    ".markdown": "markdown",
}


# ---------------------------------------------------------------------------
# Resource helpers (self-contained to avoid importing private inference symbols)
# ---------------------------------------------------------------------------

def _available_ram_mb() -> int:
    """Return available RAM in MB from /proc/meminfo (Linux)."""
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return 999_999


def _available_vram_mb() -> int:
    """Return free VRAM in MB via nvidia-smi; 999_999 if no GPU present."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            timeout=3,
            stderr=subprocess.DEVNULL,
        )
        values = [int(v.strip()) for v in out.decode().splitlines() if v.strip()]
        return max(values) if values else 999_999
    except Exception:
        return 999_999


def _resources_ok() -> bool:
    """Return True when both RAM and VRAM are above configured thresholds."""
    config = load_config()
    if _available_vram_mb() < config.thresholds.VRAM_THRESHOLD_MB:
        logger.debug("VRAM below threshold — processor will pause")
        return False
    if _available_ram_mb() < config.thresholds.RAM_THRESHOLD_MB:
        logger.debug("RAM below threshold — processor will pause")
        return False
    return True


# ---------------------------------------------------------------------------
# AST-hash computation
# ---------------------------------------------------------------------------

def _compute_ast_hash(source: bytes, ext: str) -> str:
    """Return a 16-char hex digest that reflects the *structure* of the file.

    * **.py** — uses the stdlib ``ast`` module which completely omits comments
      and whitespace, so the hash is invariant to comment/whitespace edits.
    * **Other supported types** — hashes the skeletonised output (body-stripped)
      which is invariant to changes inside function bodies.
    * **Fallback** — raw SHA-256 of the source bytes.
    """
    if ext == ".py":
        try:
            import ast as _ast
            tree = _ast.parse(source)
            return hashlib.sha256(_ast.dump(tree).encode()).hexdigest()[:16]
        except SyntaxError:
            pass  # fall through to skeleton-based hash

    lang = _EXT_TO_LANG.get(ext, "")
    if lang:
        skeleton = skeletonize(source, lang)
        return hashlib.sha256(skeleton.encode()).hexdigest()[:16]

    return hashlib.sha256(source).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Core processing logic
# ---------------------------------------------------------------------------

async def process_file(path: Path) -> None:
    """Process a single changed file — update ledger and context_cache.

    Decision tree:

    1. File gone or extension not supported → skip.
    2. Resources below threshold → skip (caller will requeue or drop).
    3. File exceeds ``MAX_FILE_SIZE_KB`` → skip.
    4. AST hash unchanged → upsert mtime only, skip ``summarize()``.
    5. AST hash changed (or new file) → skeletonize + summarize, upsert both.
    """
    ext = path.suffix.lower()
    lang = _EXT_TO_LANG.get(ext)
    if lang is None:
        return

    if not path.exists():
        logger.debug("File gone, skipping: %s", path)
        return

    config = load_config()

    if not _resources_ok():
        logger.info("Resources below threshold — skipping %s", path)
        return

    try:
        source = path.read_bytes()
    except OSError as exc:
        logger.warning("Cannot read %s: %s", path, exc)
        return

    if len(source) > config.thresholds.MAX_FILE_SIZE_KB * 1024:
        logger.debug("File exceeds MAX_FILE_SIZE_KB, skipping: %s", path)
        return

    ast_hash = _compute_ast_hash(source, ext)
    path_str = str(path)

    try:
        mtime = path.stat().st_mtime
    except OSError:
        return

    try:
        with Ledger() as ledger:
            existing = ledger.get_file(path_str)

            if existing and existing["ast_hash"] == ast_hash:
                # Structure unchanged — refresh mtime, skip LLM call.
                ledger.upsert_file(path_str, mtime, ast_hash)
                logger.debug("AST unchanged — no re-summary: %s", path)
                return

            # New file or structural change — full pipeline.
            skeleton = skeletonize(source, lang)
            summary = await summarize(source.decode("utf-8", errors="replace"), lang)

            ledger.upsert_file(path_str, mtime, ast_hash)
            ledger.upsert_cache(path_str, skeleton, summary)
            logger.info("Cache updated: %s", path)

    except LedgerError as exc:
        logger.warning("Ledger error for %s: %s", path, exc)


# ---------------------------------------------------------------------------
# Public coroutine
# ---------------------------------------------------------------------------

async def start_processor(root: Path) -> None:  # noqa: ARG001
    """Consume the watcher queue and process each changed file.

    Pauses via ``asyncio.sleep`` when RAM or VRAM is below the configured
    thresholds, resuming automatically once resources recover.  ``root`` is
    accepted for API symmetry with ``start_watcher`` but is not used — the
    queue is global.
    """
    queue = get_queue()
    logger.info("Processor started")

    while True:
        # Resource gate — back-off before touching the queue.
        while not _resources_ok():
            logger.info(
                "Resources below threshold — processor sleeping %.0fs",
                _RESOURCE_POLL_INTERVAL,
            )
            await asyncio.sleep(_RESOURCE_POLL_INTERVAL)

        try:
            path = await asyncio.wait_for(queue.get(), timeout=_QUEUE_TIMEOUT)
        except asyncio.TimeoutError:
            continue

        try:
            await process_file(path)
        except Exception as exc:
            logger.exception("Unexpected error processing %s: %s", path, exc)
        finally:
            queue.task_done()
