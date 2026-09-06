"""Deterministic, offline summary generation.

``summarize(source, language)`` is pure and synchronous: given the same input
it always returns the same string.  No subprocess, network, filesystem or clock
access.  Three tiers, tried in order:

1. **Docstring** — a module-level docstring / leading comment / first heading:
   return its first sentence (whitespace collapsed, capped at ~120 chars).
2. **Symbols** — top-level def/class/function names: ``Defines: a, b, c`` (at
   most 8 names, ``…`` appended when more).
3. **Snippet** — ``Short {language} snippet ({n} lines)`` where *n* is the
   non-blank line count.
"""
import ast
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_SENTENCE_CHARS = 120
_MAX_NAMES = 8


def _first_sentence(text: str) -> str:
    """Collapse whitespace, take the first sentence, cap length."""
    collapsed = " ".join(text.split())
    match = re.match(r"(.+?[.!?])(?:\s|$)", collapsed)
    sentence = match.group(1) if match else collapsed
    if len(sentence) > _MAX_SENTENCE_CHARS:
        sentence = sentence[: _MAX_SENTENCE_CHARS - 1].rstrip() + "…"
    return sentence


def _leading_line_comment(source: str) -> Optional[str]:
    """Return the text of the leading ``//`` comment block, or None."""
    lines = source.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    collected: list[str] = []
    while i < len(lines) and lines[i].lstrip().startswith("//"):
        collected.append(lines[i].lstrip()[2:].lstrip("/!").strip())
        i += 1
    text = " ".join(part for part in collected if part)
    return text or None


def _leading_block_comment(source: str) -> Optional[str]:
    """Return the text of a leading ``/* ... */`` (or ``//``) comment, or None."""
    stripped = source.lstrip()
    if stripped.startswith("/*"):
        end = stripped.find("*/")
        if end == -1:
            return None
        body = stripped[2:end]
        cleaned = " ".join(
            line.strip().lstrip("*").strip() for line in body.splitlines()
        )
        return cleaned.strip() or None
    if stripped.startswith("//"):
        return _leading_line_comment(source)
    return None


def _module_docstring(source: str, language: str) -> Optional[str]:
    if language == "python":
        try:
            return ast.get_docstring(ast.parse(source))
        except (SyntaxError, ValueError):
            return None
    if language == "markdown":
        for line in source.splitlines():
            s = line.strip()
            if s.startswith("#"):
                return s.lstrip("#").strip() or None
        return None
    if language in ("javascript", "typescript"):
        return _leading_block_comment(source)
    if language in ("go", "rust"):
        return _leading_line_comment(source)
    return None


def _top_level_names(source: str, language: str) -> list[str]:
    if language == "python":
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            return []
        return [
            node.name
            for node in tree.body
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            )
        ]
    if language in ("javascript", "typescript"):
        defs = re.findall(
            r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\()",
            source,
        )
        return [d[0] or d[1] for d in defs]
    return []


def summarize(source: str, language: str) -> str:
    """Return a deterministic one-line summary of *source*.

    Pure and synchronous — see the module docstring for the tier logic.
    """
    language = (language or "").lower()

    # Tier 1: module-level docstring / leading comment / first heading.
    doc = _module_docstring(source, language)
    if doc:
        return _first_sentence(doc)

    # Tier 2: top-level symbol names.
    names = _top_level_names(source, language)
    if names:
        shown = ", ".join(names[:_MAX_NAMES])
        if len(names) > _MAX_NAMES:
            shown += ", …"
        return f"Defines: {shown}"

    # Tier 3: bare snippet description.
    non_blank = sum(1 for line in source.splitlines() if line.strip())
    return f"Short {language or 'code'} snippet ({non_blank} lines)"
