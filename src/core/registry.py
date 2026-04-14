"""Language registry — maps file extensions to tree-sitter Language objects."""
from __future__ import annotations

from tree_sitter import Language
import tree_sitter_python as _tspython
import tree_sitter_javascript as _tsjs

_REGISTRY: dict[str, Language] = {
    ".py": Language(_tspython.language()),
    ".js": Language(_tsjs.language()),
    ".ts": Language(_tsjs.language()),
    ".jsx": Language(_tsjs.language()),
    ".tsx": Language(_tsjs.language()),
}

# Markdown has no tree-sitter grammar in this stack — handled by regex in skeletonizer.
MARKDOWN_EXTS: frozenset[str] = frozenset({".md", ".markdown"})


def get_language(ext: str) -> Language | None:
    """Return the tree-sitter Language for *ext* (e.g. '.py'), or None if unsupported."""
    return _REGISTRY.get(ext.lower())
