"""``cs`` — command-line interface for Sieve's structured outputs.

Subcommands:
  cs skeleton <file> [--json]      per-file skeleton + dependency edges
  cs repo-map [--json]             public-interface map for the indexed repo
  cs diff [--since=last_commit] [--json]
                                   signature-level changes vs the last snapshot

Without ``--json``, output is a terse human-readable rendering. Exits non-zero
only on hard errors (file not found, ledger missing).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from src.data.ledger import set_db_path
from src.layers.json_api import (
    get_diff_json,
    get_file_skeleton_json,
    get_repo_map_json,
)


def _resolve_db_path(explicit: str | None) -> Path:
    """Resolve the ledger.db path the daemon wrote for the watched project.

    Order: ``--db`` flag, then ``$SIEVE_DB``, then the first ``ledger.db``
    found walking up from the cwd but not past the enclosing git repo root,
    else ``<cwd>/ledger.db`` (which will not exist and triggers the
    "run the daemon first" error).

    The walk stops at the directory containing ``.git`` so a stray
    ``ledger.db`` in a parent directory (e.g. the home dir) can never bind an
    unrelated project's CLI to the wrong index.
    """
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("SIEVE_DB")
    if env:
        return Path(env).expanduser().resolve()
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        candidate = parent / "ledger.db"
        if candidate.is_file():
            return candidate
        if (parent / ".git").exists():
            break  # don't look above the repo root
    return cwd / "ledger.db"


def _print_skeleton_text(payload: dict) -> None:
    if "error" in payload:
        print(f"# {payload['file']}: {payload['error']}", file=sys.stderr)
        return
    print(f"# {payload['file']}")
    for sym in payload.get("symbols", []):
        sig = sym.get("signature") or sym["name"]
        print(f"  {sig}")
    deps = payload.get("dependencies", {})
    if deps.get("imports_out"):
        print(f"\n  imports_out: {', '.join(deps['imports_out'])}")
    if deps.get("imported_in"):
        print(f"  imported_in: {', '.join(deps['imported_in'])}")


def _print_repo_map_text(payload: dict) -> None:
    for entry in payload.get("files", []):
        print(f"# {entry['file']}")
        for sym in entry["public_interface"]:
            print(f"  {sym.get('signature') or sym['name']}")


def _print_diff_text(payload: dict) -> None:
    if "error" in payload and not payload.get("changes"):
        print(f"# {payload['error']}", file=sys.stderr)
        return
    print(f"# diff since {payload.get('since')} (commit {payload.get('commit')})")
    for change in payload.get("changes", []):
        print(f"\n## {change['file']}")
        for s in change.get("added", []):
            print(f"  + {s.get('signature') or s['name']}")
        for s in change.get("removed", []):
            print(f"  - {s.get('signature') or s['name']}")
        for s in change.get("modified", []):
            print(f"  ~ {s['name']}")
            print(f"      before: {s['before']}")
            print(f"      after:  {s['after']}")


def _emit(payload: dict, as_json: bool, text_fn) -> None:
    if as_json:
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        text_fn(payload)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cs", description="Sieve structured outputs")
    parser.add_argument(
        "--db",
        metavar="PATH",
        default=None,
        help="path to the project's ledger.db (default: discovered by walking "
        "up from the current directory, or $SIEVE_DB)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sk = sub.add_parser("skeleton", help="per-file skeleton + dependencies")
    sk.add_argument("file", help="path to the file (relative or absolute)")
    sk.add_argument("--json", action="store_true", help="emit JSON instead of text")

    rm = sub.add_parser("repo-map", help="public-interface map for the indexed repo")
    rm.add_argument("--json", action="store_true", help="emit JSON instead of text")

    df = sub.add_parser("diff", help="signature changes vs the last snapshot")
    df.add_argument("--since", default="last_commit", help='"last_commit" or a short commit hash')
    df.add_argument("--json", action="store_true", help="emit JSON instead of text")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    db_path = _resolve_db_path(args.db)
    if not db_path.is_file():
        print(
            f"cs: ledger not found: {db_path}\n"
            "Run the daemon first (python src/main.py <project-path>), or point "
            "cs at it with --db <path-to-ledger.db>.",
            file=sys.stderr,
        )
        return 1
    set_db_path(db_path)

    if args.cmd == "skeleton":
        target = Path(args.file).resolve()
        payload = get_file_skeleton_json(str(target))
        _emit(payload, args.json, _print_skeleton_text)
        return 0 if "error" not in payload else 1

    if args.cmd == "repo-map":
        payload = get_repo_map_json()
        _emit(payload, args.json, _print_repo_map_text)
        return 0

    if args.cmd == "diff":
        payload = get_diff_json(args.since)
        _emit(payload, args.json, _print_diff_text)
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
