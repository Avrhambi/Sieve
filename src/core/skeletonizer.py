"""Tree-sitter skeletonizer — strips function bodies, retains signatures and docstrings.

No I/O is performed here. Takes source bytes, returns a skeleton string.
"""
from __future__ import annotations

import re
from tree_sitter import Node, Parser

from src.main import load_config
from src.core.registry import MARKDOWN_EXTS, get_language

# Maps language name strings to canonical file extension keys.
_LANG_TO_EXT: dict[str, str] = {
    "python": ".py",
    "py": ".py",
    "javascript": ".js",
    "js": ".js",
    "typescript": ".ts",
    "ts": ".ts",
    "jsx": ".jsx",
    "tsx": ".tsx",
    "markdown": ".md",
    "md": ".md",
}


def skeletonize(source: bytes, language: str) -> str:
    """Strip function bodies from *source*, returning a skeleton string.

    Args:
        source:   Raw file bytes.
        language: Language identifier ('python', 'javascript', 'markdown', etc.)

    Returns:
        Skeleton string with function bodies collapsed to '...' (Python) or
        '{...}' (JavaScript).  Markdown is reduced to headers and links.
        Returns an empty string if the file exceeds MAX_FILE_SIZE_KB.

    Invariants:
        - No I/O is performed.
        - config.thresholds.MAX_FILE_SIZE_KB is respected.
    """
    config = load_config()
    if len(source) > config.thresholds.MAX_FILE_SIZE_KB * 1024:
        return ""

    ext = _LANG_TO_EXT.get(language.lower(), "")

    if ext in MARKDOWN_EXTS or language.lower() in ("md", "markdown"):
        return _skeletonize_markdown(source)

    lang_obj = get_language(ext)
    if lang_obj is None:
        return source.decode("utf-8", errors="replace")

    parser = Parser(lang_obj)
    tree = parser.parse(source)

    if ext == ".py":
        return _skeletonize_python(tree.root_node, source)
    else:  # .js / .ts / .jsx / .tsx
        return _skeletonize_js(tree.root_node, source)


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

_PY_FN_TYPES = frozenset({"function_definition", "async_function_definition"})


def _py_docstring_end_row(block: Node) -> int | None:
    """Return the end row of a docstring if the block starts with one, else None."""
    for child in block.children:
        if child.type == "expression_statement":
            for sub in child.children:
                if sub.type == "string":
                    return child.end_point[0]
            break
        # Skip any leading comment-or-newline tokens before first real statement
        if child.type not in ("comment", "newline", "indent", "dedent", ""):
            break
    return None


def _collect_py_replacements(
    node: Node,
    replacements: list[tuple[int, int, str]],
) -> None:
    """Walk the Python AST and collect (replace_start_line, replace_end_line_excl, text)."""

    if node.type == "module":
        for child in node.children:
            _collect_py_replacements(child, replacements)

    elif node.type in _PY_FN_TYPES:
        block = next((c for c in node.children if c.type == "block"), None)
        if block is None:
            return
        body_indent = " " * block.start_point[1]
        ds_end_row = _py_docstring_end_row(block)
        replace_start = (ds_end_row + 1) if ds_end_row is not None else block.start_point[0]
        replace_end = node.end_point[0] + 1
        if replace_start < replace_end:
            replacements.append((replace_start, replace_end, body_indent + "...\n"))

    elif node.type == "class_definition":
        block = next((c for c in node.children if c.type == "block"), None)
        if block is None:
            return
        for child in block.children:
            _collect_py_replacements(child, replacements)

    elif node.type == "decorated_definition":
        definition = next(
            (c for c in node.children if c.type in _PY_FN_TYPES or c.type == "class_definition"),
            None,
        )
        if definition is not None:
            _collect_py_replacements(definition, replacements)


def _skeletonize_python(root: Node, source: bytes) -> str:
    src = source.decode("utf-8", errors="replace")
    lines = src.splitlines(keepends=True)

    replacements: list[tuple[int, int, str]] = []
    _collect_py_replacements(root, replacements)

    # Apply from the bottom of the file upward so line indices stay valid.
    replacements.sort(key=lambda r: r[0], reverse=True)
    for start, end, replacement in replacements:
        lines[start:end] = [replacement]

    return "".join(lines)


# ---------------------------------------------------------------------------
# JavaScript / TypeScript
# ---------------------------------------------------------------------------

_JS_FN_TYPES = frozenset(
    {
        "function_declaration",
        "function_expression",
        "generator_function_declaration",
        "generator_function",
        "method_definition",
        "arrow_function",
    }
)


def _collect_js_blocks(
    node: Node,
    blocks: list[tuple[int, int]],
) -> None:
    """Collect (start_byte, end_byte) of statement_blocks that are direct function bodies."""
    if node.type in _JS_FN_TYPES:
        body = next((c for c in node.children if c.type == "statement_block"), None)
        if body is not None:
            blocks.append((body.start_byte, body.end_byte))
            return  # don't recurse into the body we're collapsing
    for child in node.children:
        _collect_js_blocks(child, blocks)


def _skeletonize_js(root: Node, source: bytes) -> str:
    blocks: list[tuple[int, int]] = []
    _collect_js_blocks(root, blocks)

    # Apply replacements left-to-right on the raw bytes.
    blocks.sort(key=lambda b: b[0])

    parts: list[str] = []
    prev = 0
    for start, end in blocks:
        parts.append(source[prev:start].decode("utf-8", errors="replace"))
        parts.append("{...}")
        prev = end
    parts.append(source[prev:].decode("utf-8", errors="replace"))

    return "".join(parts)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

_LINK_RE = re.compile(r"\[.+?\]\(.+?\)")


def _skeletonize_markdown(source: bytes) -> str:
    src = source.decode("utf-8", errors="replace")
    result: list[str] = []
    for line in src.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            result.append(line)
        elif _LINK_RE.search(line):
            result.append(line)
    return "".join(result)
