"""Sieve daemon entry point."""
import asyncio
import logging
import os
from pathlib import Path

import toml
from pydantic import BaseModel

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "sieve.config.toml"


class SieveThresholds(BaseModel):
    VRAM_THRESHOLD_MB: int
    RAM_THRESHOLD_MB: int
    MAX_FILE_SIZE_KB: int
    MAX_DEPTH: int
    OLLAMA_NUM_PARALLEL: int


class SieveConfig(BaseModel):
    thresholds: SieveThresholds


def load_config(path: Path = CONFIG_PATH) -> SieveConfig:
    raw = toml.load(str(path))
    return SieveConfig(**raw)


async def start() -> None:
    """Placeholder coroutine — daemon logic implemented in TASK-06."""
    config = load_config()
    logger.info("Sieve daemon starting")
    await asyncio.sleep(0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start())
