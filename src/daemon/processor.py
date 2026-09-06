"""Background processor — consumes the watcher queue and updates context_cache.

Key guarantees
--------------
* **AST-hash gate**: ``summarize()`` is called only when the file's AST
  structure changes.  Whitespace-only or comment-only edits leave the hash
  unchanged → no re-summary.
* **Deterministic pipeline**: ``summarize()`` is pure and synchronous — there
  are no resource governors and no LLM/network round-trips.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import logging
import re
from pathlib import Path

from src.core.skeletonizer import skeletonize
from src.core.inference import summarize
from src.data.ledger import Ledger, LedgerError
import src.main as _main_module
from src.daemon.watcher import get_queue, _load_gitignore_patterns, _is_ignored
from src.main import load_config

logger = logging.getLogger(__name__)

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
# Symbol extraction
# ---------------------------------------------------------------------------

def _py_signature(node: ast.AST) -> str | None:
    """Reconstruct a one-line signature for a Python def/class node."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        try:
            args = ast.unparse(node.args)
        except Exception:
            return None
        ret = ""
        if node.returns is not None:
            try:
                ret = " -> " + ast.unparse(node.returns)
            except Exception:
                ret = ""
        return f"{prefix} {node.name}({args}){ret}"
    if isinstance(node, ast.ClassDef):
        try:
            bases = ", ".join(ast.unparse(b) for b in node.bases)
        except Exception:
            bases = ""
        return f"class {node.name}({bases})" if bases else f"class {node.name}"
    return None


def _extract_symbols(
    source: bytes, path: str, lang: str
) -> list[tuple[str, list[str], str | None]]:
    """Return (symbol_name, references, signature) tuples for the given source.

    * Python: uses ast.parse to collect function/class definitions and imports;
      signatures reconstructed via ast.unparse.
    * JS/TS: uses regex to collect names and imports; signature is None (v1
      punts on JS/TS structured signatures).
    * Other: returns [].
    """
    ext = Path(path).suffix.lower()

    if ext == ".py":
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        imports: list[str] = []
        symbols: list[tuple[str, str | None]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.append((node.name, _py_signature(node)))
            elif isinstance(node, ast.Import):
                imports += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        return [(name, imports, sig) for name, sig in symbols]

    if ext in (".js", ".ts", ".jsx", ".tsx"):
        text = source.decode("utf-8", errors="ignore")
        refs = re.findall(r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]", text)
        names = re.findall(r"(?:function|class|const|let|var)\s+(\w+)", text)
        return [(name, refs, None) for name in names]

    return []


# ---------------------------------------------------------------------------
# Module-level gitignore state (populated by start_processor)
# ---------------------------------------------------------------------------

_gitignore_patterns: list[str] = []
_repo_root: Path | None = None


# ---------------------------------------------------------------------------
# Core processing logic
# ---------------------------------------------------------------------------

async def process_file(path: Path, queue: asyncio.Queue) -> None:
    """Process a single changed file — update ledger and context_cache.

    Decision tree:

    1. File gone or extension not supported → skip.
    2. File matches gitignore patterns → mark ignored in ledger, skip.
    3. File exceeds ``MAX_FILE_SIZE_KB`` → skip.
    4. AST hash unchanged → upsert mtime only, skip ``summarize()``.
    5. AST hash changed (or new file) → skeletonize + summarize + symbols, upsert all.
    """
    ext = path.suffix.lower()
    lang = _EXT_TO_LANG.get(ext)
    if lang is None:
        return

    if not path.exists():
        logger.debug("File gone, skipping: %s", path)
        return

    path_str = str(path)

    # Gitignore gate — mark ignored files in ledger and skip processing.
    _root_for_ignore = _repo_root if _repo_root is not None else path.parent
    if _is_ignored(path, _root_for_ignore, _gitignore_patterns):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        try:
            with Ledger() as ledger:
                ledger.upsert_file(path_str, mtime, "", is_ignored=True)
        except LedgerError as exc:
            logger.warning("Ledger error marking ignored %s: %s", path, exc)
        return

    config = load_config()

    try:
        source = path.read_bytes()
    except OSError as exc:
        logger.warning("Cannot read %s: %s", path, exc)
        return

    if len(source) > config.thresholds.MAX_FILE_SIZE_KB * 1024:
        logger.debug("File exceeds MAX_FILE_SIZE_KB, skipping: %s", path)
        return

    ast_hash = _compute_ast_hash(source, ext)

    try:
        mtime = path.stat().st_mtime
    except OSError:
        return

    try:
        with Ledger() as ledger:
            existing = ledger.get_file(path_str)

            if existing and existing["ast_hash"] == ast_hash:
                # Structure unchanged — refresh mtime, skip re-skeletonize.
                ledger.upsert_file(path_str, mtime, ast_hash)
                logger.debug("AST unchanged — no re-summary: %s", path)
                return

            # New file or structural change — full pipeline.
            skeleton = skeletonize(source, lang)
            summary = summarize(source.decode("utf-8", errors="replace"), lang)

            ledger.upsert_file(path_str, mtime, ast_hash)
            ledger.upsert_cache(path_str, skeleton, summary)

            # Symbol extraction and upsert.
            symbols = _extract_symbols(source, path_str, lang)
            for sym_name, refs, signature in symbols:
                ledger.upsert_symbol(sym_name, path_str, refs, signature)

            logger.info("Cache updated: %s", path)

    except LedgerError as exc:
        logger.warning("Ledger error for %s: %s", path, exc)


# ---------------------------------------------------------------------------
# Public coroutine
# ---------------------------------------------------------------------------

async def start_processor(root: Path) -> None:
    """Consume the watcher queue and process each changed file.

    Loads gitignore patterns from *root* at startup.  Exits cleanly when a
    shutdown event is set.
    """
    global _gitignore_patterns, _repo_root
    _repo_root = root
    _gitignore_patterns = _load_gitignore_patterns(root)
    logger.info(
        "Processor started — root: %s, %d gitignore pattern(s)",
        root, len(_gitignore_patterns),
    )

    queue = get_queue()

    while True:
        # Shutdown gate — check before blocking on queue.
        if _main_module._shutdown_event and _main_module._shutdown_event.is_set():
            logger.info("Shutdown signal received — processor exiting")
            break

        try:
            path = await asyncio.wait_for(queue.get(), timeout=_QUEUE_TIMEOUT)
        except asyncio.TimeoutError:
            continue

        try:
            await process_file(path, queue)
        except Exception as exc:
            logger.exception("Unexpected error processing %s: %s", path, exc)
        finally:
            queue.task_done()

        # Shutdown gate — check after each file is processed.
        if _main_module._shutdown_event and _main_module._shutdown_event.is_set():
            logger.info("Shutdown signal received — processor exiting")
            break
