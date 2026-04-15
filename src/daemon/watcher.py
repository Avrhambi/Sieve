"""File-system watcher — monitors for file saves and feeds the processor queue.

Uses watchdog for OS-level file events.  .gitignore patterns from the repo
root are loaded at startup and applied to every event so ignored files are
never queued.  The sync watchdog callback is bridged into the running asyncio
event loop via ``loop.call_soon_threadsafe``.
"""
from __future__ import annotations

import asyncio
import fnmatch
import logging
from pathlib import Path

from watchdog.events import (
    FileCreatedEvent,
    FileModifiedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from src.core.registry import MARKDOWN_EXTS
from src.main import load_config

logger = logging.getLogger(__name__)

# Extensions the processor can handle.
_SUPPORTED_EXTS: frozenset[str] = frozenset(
    {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs"} | MARKDOWN_EXTS
)

# Module-level queue shared with processor.py.
_file_queue: asyncio.Queue[Path] = asyncio.Queue()


def get_queue() -> asyncio.Queue[Path]:
    """Return the shared inter-coroutine file queue."""
    return _file_queue


# ---------------------------------------------------------------------------
# .gitignore helpers
# ---------------------------------------------------------------------------

def _load_gitignore_patterns(root: Path) -> list[str]:
    """Return gitignore patterns from all .gitignore files under *root*."""
    from pathlib import Path as _Path

    patterns: list[str] = []
    root_path = _Path(root)
    # Walk all subdirectories for .gitignore files
    for gitignore_file in root_path.rglob(".gitignore"):
        try:
            rel_dir = gitignore_file.parent.relative_to(root_path)
            prefix = str(rel_dir) + "/" if str(rel_dir) != "." else ""
            for line in gitignore_file.read_text(errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Prefix non-rooted patterns with their directory
                if not line.startswith("/") and prefix:
                    patterns.append(prefix + line)
                else:
                    patterns.append(line.lstrip("/"))
        except (OSError, ValueError):
            continue
    return patterns


def _is_ignored(path: Path, root: Path, patterns: list[str]) -> bool:
    """Return True if *path* matches any of the .gitignore *patterns*.

    Matching is done against:
    - the full relative POSIX path (e.g. ``src/foo/bar.py``)
    - the file name alone (e.g. ``bar.py``)
    - each directory component for patterns ending in ``/``
    """
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        return False

    for pattern in patterns:
        bare = pattern.rstrip("/")
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel, f"**/{pattern}"):
            return True
        if fnmatch.fnmatch(path.name, bare):
            return True
        if pattern.endswith("/"):
            for part in rel.split("/")[:-1]:
                if fnmatch.fnmatch(part, bare):
                    return True
    return False


# ---------------------------------------------------------------------------
# watchdog handler
# ---------------------------------------------------------------------------

class _SieveHandler(FileSystemEventHandler):
    """Put modified/created files onto the asyncio queue (thread-safe)."""

    def __init__(
        self,
        root: Path,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[Path],
        patterns: list[str],
    ) -> None:
        super().__init__()
        self._root = root
        self._loop = loop
        self._queue = queue
        self._patterns = patterns

    def _enqueue(self, src_path: str) -> None:
        path = Path(src_path)
        if path.suffix.lower() not in _SUPPORTED_EXTS:
            return
        if _is_ignored(path, self._root, self._patterns):
            logger.debug("Ignored (gitignore): %s", path)
            return
        logger.debug("Queuing: %s", path)
        self._loop.call_soon_threadsafe(self._queue.put_nowait, path)

    def on_modified(self, event: FileModifiedEvent) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._enqueue(event.src_path)

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._enqueue(event.src_path)


# ---------------------------------------------------------------------------
# Public coroutine
# ---------------------------------------------------------------------------

async def start_watcher(root: Path) -> None:
    """Watch *root* recursively for file saves and enqueue changed paths.

    Spawns a watchdog ``Observer`` thread.  Enqueued paths are consumed by
    ``start_processor`` in ``processor.py``.

    .gitignore patterns are read once at startup.  If ``.gitignore`` changes
    while the daemon is running, restart the daemon to pick up new patterns.
    """
    patterns = _load_gitignore_patterns(root)
    logger.info(
        "Watcher starting — root: %s, %d gitignore pattern(s)", root, len(patterns)
    )

    loop = asyncio.get_running_loop()
    queue = get_queue()

    handler = _SieveHandler(root, loop, queue, patterns)
    observer = Observer()
    observer.schedule(handler, str(root), recursive=True)
    observer.start()
    logger.info("Watcher active")

    try:
        while True:
            await asyncio.sleep(1)
    finally:
        observer.stop()
        observer.join()
        logger.info("Watcher stopped")
