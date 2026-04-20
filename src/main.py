"""Sieve daemon entry point."""
import asyncio
import logging
import signal
import sys
from pathlib import Path

# Ensure the repo root is on sys.path so `src.*` imports work when this
# script is invoked directly (python src/main.py) rather than as a module.
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import toml
from pydantic import BaseModel

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "sieve.config.toml"

_shutdown_event: asyncio.Event | None = None


class SieveThresholds(BaseModel):
    VRAM_THRESHOLD_MB: int
    RAM_THRESHOLD_MB: int
    MAX_FILE_SIZE_KB: int
    OLLAMA_NUM_PARALLEL: int


class SieveConfig(BaseModel):
    thresholds: SieveThresholds


def load_config(path: Path = CONFIG_PATH) -> SieveConfig:
    raw = toml.load(str(path))
    return SieveConfig(**raw)


async def start(root: Path) -> None:
    global _shutdown_event
    _shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _set_shutdown(*_):
        loop.call_soon_threadsafe(_shutdown_event.set)

    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _shutdown_event.set)
    except NotImplementedError:
        # Windows: add_signal_handler is not supported
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, _set_shutdown)

    # Point the ledger at the watched project directory.
    from src.data.ledger import set_db_path
    db_path = root / "ledger.db"
    set_db_path(db_path)

    # Also point heartbeat at the same DB.
    import src.daemon.heartbeat as _heartbeat_mod
    _heartbeat_mod._DB_PATH = db_path

    load_config()
    logger.info("Sieve daemon starting — watching %s", root)

    from src.daemon.watcher import start_watcher, get_commit_queue
    from src.daemon.processor import start_processor
    from src.daemon.heartbeat import start_heartbeat
    from src.daemon.snapshot_writer import start_snapshot_writer

    tasks = [
        asyncio.create_task(start_watcher(root)),
        asyncio.create_task(start_processor(root)),
        asyncio.create_task(start_snapshot_writer(get_commit_queue())),
        asyncio.create_task(start_heartbeat(db_path)),
    ]

    await _shutdown_event.wait()

    logger.info("Shutdown signal received — stopping daemon")
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Daemon stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print("Usage: python src/main.py <path-to-watch>")
        sys.exit(1)
    root_path = Path(sys.argv[1]).resolve()
    asyncio.run(start(root_path))
