"""Determinism guarantees for Sieve's offline code index.

Every stage of the pipeline that produces indexed content must be
*byte-reproducible*: the same input bytes always yield the same skeleton,
summary, symbol set and AST hash, regardless of interpreter hash
randomization or dict/AST iteration order.  These tests turn that promise
into an enforced, green guarantee.

The headline test is :class:`TestEndToEndPipelineDeterminism` — it drives
the real ``process_file`` coroutine twice against a wiped ledger and
asserts the full result sets are identical.
"""
import asyncio
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from src.core.skeletonizer import skeletonize
from src.core.inference import summarize
from src.daemon.processor import _extract_symbols, _compute_ast_hash, process_file
from src.data.ledger import Ledger, set_db_path

REPO_ROOT = Path(__file__).resolve().parents[1]

_REPEAT = 5


# ---------------------------------------------------------------------------
# Non-trivial fixtures: a class + 2 functions + imports + a docstring, per
# language.  Kept deliberately structural so AST-walk / dict ordering has a
# chance to leak if it is going to.
# ---------------------------------------------------------------------------

PY_FIXTURE = b'''\
"""Widget registry: tracks named widgets and their revisions."""
import json
import os
from collections import OrderedDict


def load_registry(path: str) -> dict:
    """Read a registry file and return the parsed mapping."""
    with open(path) as fh:
        return json.load(fh)


def save_registry(path: str, data: dict) -> None:
    """Serialize *data* to *path* as JSON."""
    with open(path, "w") as fh:
        json.dump(data, fh)


class Registry:
    """In-memory widget store keyed by name."""

    def __init__(self, root: str) -> None:
        self._root = root
        self._items = OrderedDict()

    def add(self, name: str, revision: int) -> None:
        """Register *name* at *revision*."""
        self._items[name] = revision

    def resolve(self, name: str) -> int:
        """Return the revision for *name*, or -1 if unknown."""
        return self._items.get(name, -1)
'''

JS_FIXTURE = b'''\
/* Widget registry: tracks named widgets and their revisions. */
import { readFile } from "fs/promises";
import path from "path";

export function loadRegistry(file) {
    const raw = readFile(file, "utf8");
    return JSON.parse(raw);
}

export function saveRegistry(file, data) {
    const text = JSON.stringify(data, null, 2);
    return writeFile(file, text);
}

export class Registry {
    constructor(root) {
        this.root = root;
        this.items = new Map();
    }

    add(name, revision) {
        this.items.set(name, revision);
    }

    resolve(name) {
        return this.items.has(name) ? this.items.get(name) : -1;
    }
}
'''

TS_FIXTURE = b'''\
/* Widget registry: tracks named widgets and their revisions. */
import { readFile } from "fs/promises";
import path from "path";

export function loadRegistry(file: string): Promise<Record<string, number>> {
    const raw = readFile(file, "utf8");
    return JSON.parse(raw as unknown as string);
}

export function saveRegistry(file: string, data: Record<string, number>): void {
    const text = JSON.stringify(data, null, 2);
    writeFile(file, text);
}

export class Registry {
    private items: Map<string, number>;

    constructor(private root: string) {
        this.items = new Map();
    }

    add(name: string, revision: number): void {
        this.items.set(name, revision);
    }

    resolve(name: string): number {
        return this.items.has(name) ? (this.items.get(name) as number) : -1;
    }
}
'''

MD_FIXTURE = b'''\
# Widget Registry

Tracks named widgets and their revisions across the project.

## Loading

See [the loader](https://example.com/loader) for details.

### Notes

Some prose that should be dropped by the skeletonizer.

## Saving

Widgets are written as [JSON](https://example.com/json) documents.
'''

GO_FIXTURE = b'''\
// Package registry tracks named widgets and their revisions.
package registry

import (
	"encoding/json"
	"os"
)

type Registry struct {
	root  string
	items map[string]int
}

func LoadRegistry(path string) (map[string]int, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var out map[string]int
	return out, json.Unmarshal(data, &out)
}

func (r *Registry) Add(name string, revision int) {
	r.items[name] = revision
}
'''

RUST_FIXTURE = b'''\
// Widget registry: tracks named widgets and their revisions.
use std::collections::HashMap;
use std::fs;

pub struct Registry {
    root: String,
    items: HashMap<String, i64>,
}

pub fn load_registry(path: &str) -> HashMap<String, i64> {
    let data = fs::read_to_string(path).unwrap_or_default();
    serde_json::from_str(&data).unwrap_or_default()
}

impl Registry {
    pub fn add(&mut self, name: String, revision: i64) {
        self.items.insert(name, revision);
    }

    pub fn resolve(&self, name: &str) -> i64 {
        *self.items.get(name).unwrap_or(&-1)
    }
}
'''

FIXTURES: dict[str, bytes] = {
    "python": PY_FIXTURE,
    "javascript": JS_FIXTURE,
    "typescript": TS_FIXTURE,
    "markdown": MD_FIXTURE,
    "go": GO_FIXTURE,
    "rust": RUST_FIXTURE,
}

_LANG_TO_SUFFIX = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "markdown": ".md",
    "go": ".go",
    "rust": ".rs",
}


# ---------------------------------------------------------------------------
# 1. Pure-function determinism
# ---------------------------------------------------------------------------


class TestPureFunctionDeterminism:
    @pytest.mark.parametrize("language", list(FIXTURES))
    def test_skeletonize_is_byte_identical_across_repeats(self, language):
        source = FIXTURES[language]
        outputs = {skeletonize(source, language) for _ in range(_REPEAT)}
        assert len(outputs) == 1, (
            f"skeletonize({language}) produced {len(outputs)} distinct outputs "
            f"across {_REPEAT} calls"
        )

    @pytest.mark.parametrize("language", list(FIXTURES))
    def test_summarize_is_byte_identical_across_repeats(self, language):
        text = FIXTURES[language].decode()
        outputs = {summarize(text, language) for _ in range(_REPEAT)}
        assert len(outputs) == 1, (
            f"summarize({language}) produced {len(outputs)} distinct outputs "
            f"across {_REPEAT} calls"
        )

    @pytest.mark.parametrize("language", list(FIXTURES))
    def test_extract_symbols_is_byte_identical_across_repeats(self, language):
        source = FIXTURES[language]
        path = f"proj/mod{_LANG_TO_SUFFIX[language]}"
        outputs = {
            repr(_extract_symbols(source, path, language)) for _ in range(_REPEAT)
        }
        assert len(outputs) == 1, (
            f"_extract_symbols({language}) produced {len(outputs)} distinct "
            f"outputs across {_REPEAT} calls"
        )

    def test_python_symbols_have_expected_shape(self):
        """Guard: the Python fixture really exercises class + funcs + imports."""
        syms = _extract_symbols(PY_FIXTURE, "proj/mod.py", "python")
        names = {name for name, _refs, _sig in syms}
        assert {"load_registry", "save_registry", "Registry", "add", "resolve"} <= names
        # imports are attached as references to every symbol
        _n, refs, _s = syms[0]
        assert "json" in refs and "os" in refs and "collections" in refs


# ---------------------------------------------------------------------------
# 2. No hidden nondeterminism source (hash randomization)
# ---------------------------------------------------------------------------

_SUBPROCESS_SNIPPET = textwrap.dedent(
    """
    import sys
    sys.path.insert(0, {repo!r})
    from src.core.inference import summarize
    from src.daemon.processor import _extract_symbols, _compute_ast_hash
    src = open({fixture!r}, "rb").read()
    print(summarize(src.decode(), "python"))
    print(repr(_extract_symbols(src, "proj/mod.py", "python")))
    print(_compute_ast_hash(src, ".py"))
    """
)


class TestHashRandomizationIsInert:
    def _run(self, tmp_path, seed: str) -> str:
        fixture = tmp_path / "fixture.py"
        fixture.write_bytes(PY_FIXTURE)
        code = _SUBPROCESS_SNIPPET.format(repo=str(REPO_ROOT), fixture=str(fixture))
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = seed
        proc = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, (
            f"subprocess (PYTHONHASHSEED={seed}) failed:\n{proc.stderr}"
        )
        return proc.stdout

    def test_summarize_and_symbols_survive_hash_seed_change(self, tmp_path):
        out0 = self._run(tmp_path, "0")
        out1 = self._run(tmp_path, "1")
        assert out0 == out1, (
            "Interpreter hash randomization leaked into summarize / "
            "_extract_symbols / _compute_ast_hash output:\n"
            f"--- PYTHONHASHSEED=0 ---\n{out0}\n"
            f"--- PYTHONHASHSEED=1 ---\n{out1}"
        )


# ---------------------------------------------------------------------------
# 3. End-to-end pipeline determinism  (the headline guarantee)
# ---------------------------------------------------------------------------

_PROJECT_FILES: dict[str, bytes] = {
    "app.py": PY_FIXTURE,
    "pkg/mod.py": (
        b'"""Helper package module."""\n'
        b"import app\n\n\n"
        b"def helper(n: int) -> int:\n"
        b'    """Double *n*."""\n'
        b"    return n * 2\n\n\n"
        b"class Widget:\n"
        b'    """A widget."""\n\n'
        b"    def name(self) -> str:\n"
        b"        return 'w'\n"
    ),
    "pkg/util.js": JS_FIXTURE,
    "notes.md": MD_FIXTURE,
}


def _build_project(root: Path) -> list[Path]:
    paths = []
    for rel, data in _PROJECT_FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        paths.append(p)
    return paths


def _wipe_db(db_path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        f = Path(str(db_path) + suffix)
        if f.exists():
            f.unlink()


def _dump_ledger() -> tuple[list, list]:
    with Ledger() as ledger:
        cache = ledger._conn.execute(
            "SELECT file_id, skeleton, summary FROM context_cache ORDER BY file_id"
        ).fetchall()
        symbols = ledger._conn.execute(
            'SELECT symbol_name, source_file, "references", signature '
            "FROM symbol_index ORDER BY symbol_name, source_file"
        ).fetchall()
    return [tuple(r) for r in cache], [tuple(r) for r in symbols]


def _run_pipeline(paths: list[Path]) -> None:
    async def _drive() -> None:
        queue: asyncio.Queue = asyncio.Queue()
        for p in paths:
            await process_file(p, queue)

    asyncio.run(_drive())


class TestEndToEndPipelineDeterminism:
    def test_two_full_runs_produce_identical_index(self, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        db_path = tmp_path / "ledger.db"
        set_db_path(db_path)
        paths = _build_project(project)

        _run_pipeline(paths)
        cache_a, symbols_a = _dump_ledger()

        assert cache_a, "first run indexed nothing — fixture/pipeline broken"
        assert symbols_a, "first run extracted no symbols — fixture/pipeline broken"

        _wipe_db(db_path)
        _run_pipeline(paths)
        cache_b, symbols_b = _dump_ledger()

        assert cache_b == cache_a, (
            "context_cache differs between two identical pipeline runs.\n"
            f"run A: {cache_a}\nrun B: {cache_b}"
        )
        assert symbols_b == symbols_a, (
            "symbol_index differs between two identical pipeline runs.\n"
            f"run A: {symbols_a}\nrun B: {symbols_b}"
        )

    def test_index_is_stable_over_many_runs(self, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        db_path = tmp_path / "ledger.db"
        set_db_path(db_path)
        paths = _build_project(project)

        snapshots = set()
        for _ in range(3):
            _wipe_db(db_path)
            _run_pipeline(paths)
            snapshots.add(repr(_dump_ledger()))
        assert len(snapshots) == 1, (
            f"pipeline produced {len(snapshots)} distinct index states over 3 runs"
        )


# ---------------------------------------------------------------------------
# 4. AST-hash gate is content-addressed
# ---------------------------------------------------------------------------

_BASE_PY = b'''\
"""A module."""
import os


def greet(name: str) -> str:
    """Say hello."""
    return f"hello {name}"


class Thing:
    def method(self, x: int) -> int:
        return x + 1
'''

_WHITESPACE_COMMENT_EDIT = b'''\
"""A module."""
import os


def greet(name: str) -> str:
    """Say hello."""
    # a brand new comment that changes nothing structural
    return   f"hello {name}"



class Thing:

    def method(self, x: int) -> int:

        return x + 1
'''

_SIGNATURE_CHANGE = b'''\
"""A module."""
import os


def greet(name: str, loud: bool = False) -> str:
    """Say hello."""
    return f"hello {name}"


class Thing:
    def method(self, x: int) -> int:
        return x + 1
'''


class TestAstHashGate:
    def test_same_bytes_same_hash(self):
        assert _compute_ast_hash(_BASE_PY, ".py") == _compute_ast_hash(_BASE_PY, ".py")

    def test_hash_is_deterministic_across_repeats(self):
        hashes = {_compute_ast_hash(_BASE_PY, ".py") for _ in range(_REPEAT)}
        assert len(hashes) == 1

    def test_whitespace_and_comment_edit_keeps_hash(self):
        assert _compute_ast_hash(_WHITESPACE_COMMENT_EDIT, ".py") == _compute_ast_hash(
            _BASE_PY, ".py"
        )

    def test_signature_change_changes_hash(self):
        assert _compute_ast_hash(_SIGNATURE_CHANGE, ".py") != _compute_ast_hash(
            _BASE_PY, ".py"
        )
