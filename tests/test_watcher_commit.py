"""Commit-detection tests for src.daemon.watcher.

Covers the switch from the racy .git/COMMIT_EDITMSG trigger (written before the
ref moves) to .git/logs/HEAD (appended after the ref moves).
"""
import asyncio

from src.daemon.watcher import _SieveHandler


class _StubLoop:
    """call_soon_threadsafe that runs inline — no event loop lifecycle."""

    def call_soon_threadsafe(self, fn, *args):
        fn(*args)


def _handler(root):
    commit_q: asyncio.Queue[str] = asyncio.Queue()
    handler = _SieveHandler(root, _StubLoop(), asyncio.Queue(), commit_q, [])
    return handler, commit_q


def _write_reflog(root, line: str) -> str:
    d = root / ".git" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    (d / "HEAD").write_text(line)
    return str(d / "HEAD")


def test_reflog_commit_enqueues_new_sha(tmp_path):
    old, new = "a" * 40, "b" * 40
    path = _write_reflog(
        tmp_path,
        f"{old} {new} Tester <t@e.com> 1700000000 +0000\tcommit: add feature\n",
    )
    handler, q = _handler(tmp_path)
    handler._enqueue(path)
    assert q.get_nowait() == "b" * 12  # the NEW hash, not the parent


def test_reflog_amend_enqueues_new_sha(tmp_path):
    old, new = "a" * 40, "b" * 40
    path = _write_reflog(
        tmp_path,
        f"{old} {new} Tester <t@e.com> 1700000000 +0000\tcommit (amend): reword\n",
    )
    handler, q = _handler(tmp_path)
    handler._enqueue(path)
    assert q.get_nowait() == "b" * 12


def test_reflog_checkout_does_not_enqueue(tmp_path):
    old, new = "a" * 40, "b" * 40
    path = _write_reflog(
        tmp_path,
        f"{old} {new} Tester <t@e.com> 1700000000 +0000\tcheckout: moving from main to dev\n",
    )
    handler, q = _handler(tmp_path)
    handler._enqueue(path)
    assert q.empty()


def test_reflog_missing_falls_back_to_head(tmp_path):
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "refs" / "heads" / "main").write_text("c" * 40 + "\n")
    handler, q = _handler(tmp_path)
    handler._enqueue(str(git / "logs" / "HEAD"))  # logs/HEAD does not exist
    assert q.get_nowait() == "c" * 12
