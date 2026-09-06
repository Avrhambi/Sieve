"""Sieve configuration loading — kept separate from the daemon entry point so
leaf modules can import it without pulling in ``src.main``."""
from pathlib import Path

import toml
from pydantic import BaseModel

CONFIG_PATH = Path(__file__).parent.parent / "config" / "sieve.config.toml"


class SieveThresholds(BaseModel):
    MAX_FILE_SIZE_KB: int


class SieveConfig(BaseModel):
    thresholds: SieveThresholds


def load_config(path: Path = CONFIG_PATH) -> SieveConfig:
    raw = toml.load(str(path))
    return SieveConfig(**raw)
