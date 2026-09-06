"""Sieve micro-benchmarks — run from the repo root with `python docs/bench/bench.py`.

Measures, against Sieve's own `src/*.py` (real code, not synthetic fixtures):

1. Skeleton character reduction: len(skeletonize(src, "python")) vs len(src),
   per file and aggregate. This is a CHARACTER count (a proxy for tokens), not a
   tokenizer count.
2. Index throughput: process every src/ file through the real
   `src.daemon.processor.process_file` against a fresh ledger, best-of-3 wall time.

No source or test logic is imported for mutation; this is measurement only.
"""
from __future__ import annotations

import asyncio
import platform
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.core.skeletonizer import skeletonize  # noqa: E402
from src.daemon.processor import process_file  # noqa: E402
from src.data.ledger import Ledger, set_db_path  # noqa: E402

SRC_FILES = sorted((REPO_ROOT / "src").rglob("*.py"))


def bench_multilang_fixtures() -> None:
    """Reduction on the JS/TS/Go/Rust (and Python) fixtures under tests/.

    The repo has no non-Python source, so these small fixtures from
    tests/test_determinism.py are the only multi-language inputs available.
    """
    print("\n=== 1b. Skeleton reduction on tests/ multi-language fixtures ===")
    sys.path.insert(0, str(REPO_ROOT / "tests"))
    import test_determinism as td  # noqa: E402

    cases = [
        ("python", td.PY_FIXTURE),
        ("javascript", td.JS_FIXTURE),
        ("typescript", td.TS_FIXTURE),
        ("go", td.GO_FIXTURE),
        ("rust", td.RUST_FIXTURE),
    ]
    print(f"{'language':<12} {'source ch':>10} {'skel ch':>9} {'reduction':>10}")
    print("-" * 45)
    for lang, src in cases:
        s = len(src.decode("utf-8", "replace"))
        k = len(skeletonize(src, lang))
        print(f"{lang:<12} {s:>10,} {k:>9,} {1 - k / s:>9.1%}")


def bench_reduction() -> None:
    print("\n=== 1. Skeleton character reduction (src/*.py) ===")
    print(f"{'file':<34} {'source ch':>10} {'skel ch':>9} {'reduction':>10}")
    print("-" * 66)
    tot_src = tot_skel = 0
    for p in SRC_FILES:
        src = p.read_bytes()
        skel = skeletonize(src, "python")
        s, k = len(src.decode("utf-8", "replace")), len(skel)
        tot_src += s
        tot_skel += k
        rel = p.relative_to(REPO_ROOT).as_posix()
        print(f"{rel:<34} {s:>10,} {k:>9,} {1 - k / s:>9.1%}")
    print("-" * 66)
    print(
        f"{'AGGREGATE':<34} {tot_src:>10,} {tot_skel:>9,} {1 - tot_skel / tot_src:>9.1%}"
        f"   ({len(SRC_FILES)} files)"
    )


def bench_throughput() -> None:
    print("\n=== 2. Index throughput (process_file over src/*.py) ===")
    db_path = REPO_ROOT / "docs" / "bench" / "_bench_ledger.db"

    async def one_run() -> float:
        for suffix in ("", "-wal", "-shm"):
            f = Path(str(db_path) + suffix)
            if f.exists():
                f.unlink()
        set_db_path(db_path)
        with Ledger():
            pass
        queue: asyncio.Queue = asyncio.Queue()
        t0 = time.perf_counter()
        for p in SRC_FILES:
            await process_file(p, queue)
        return time.perf_counter() - t0

    times = [asyncio.run(one_run()) for _ in range(3)]
    for suffix in ("", "-wal", "-shm"):
        f = Path(str(db_path) + suffix)
        if f.exists():
            f.unlink()
    best = min(times)
    n = len(SRC_FILES)
    print(f"runs (s): {[round(t, 4) for t in times]}")
    print(f"best of 3: {best * 1000:.1f} ms for {n} files "
          f"-> {n / best:.1f} files/sec ({best / n * 1000:.2f} ms/file)")


def main() -> None:
    print(f"Python {platform.python_version()} on {platform.system()} {platform.release()}")
    print(f"repo: {REPO_ROOT}")
    bench_reduction()
    bench_multilang_fixtures()
    bench_throughput()


if __name__ == "__main__":
    main()
