# TASK-03 Public API

## Module: `src.core.skeletonizer`

### `skeletonize(source: bytes, language: str) -> str`

Strips function/method bodies from source bytes and returns a skeleton string.

| Arg | Type | Description |
|---|---|---|
| `source` | `bytes` | Raw file bytes |
| `language` | `str` | Language identifier: `'python'`, `'py'`, `'javascript'`, `'js'`, `'typescript'`, `'ts'`, `'markdown'`, `'md'` |

**Returns:** Skeleton string.

**Invariants:**
- Performs **no I/O** — pure in-memory transformation.
- Returns `""` if `len(source) > config.thresholds.MAX_FILE_SIZE_KB * 1024`.
- Python: function/method bodies collapsed to `...`; signatures and docstrings retained.
- JavaScript/TypeScript: function bodies collapsed to `{...}`; signatures retained.
- Markdown: reduced to header lines (`# ...`) and lines containing `[text](url)` links.
- Unknown language: returns source decoded as UTF-8 unchanged.

**Config keys read:** `thresholds.MAX_FILE_SIZE_KB`

---

## Module: `src.core.registry`

### `get_language(ext: str) -> Language | None`

Returns the tree-sitter `Language` object for the given file extension, or `None` if unsupported.

**Supported extensions:** `.py`, `.js`, `.ts`, `.jsx`, `.tsx` (case-insensitive)

### `MARKDOWN_EXTS: frozenset[str]`

Set of markdown file extensions: `{".md", ".markdown"}`. Used by `skeletonize` to route to the regex-based markdown handler (no tree-sitter grammar loaded for markdown).

---

## Config keys read

| Key | Used for |
|---|---|
| `thresholds.MAX_FILE_SIZE_KB` | Skip files larger than this limit |
