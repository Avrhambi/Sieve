"""Tests for src.core.skeletonizer and src.core.registry."""
import pytest
from src.core.skeletonizer import skeletonize
from src.core.registry import get_language, MARKDOWN_EXTS


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_py_language_returned(self):
        lang = get_language(".py")
        assert lang is not None

    def test_js_language_returned(self):
        lang = get_language(".js")
        assert lang is not None

    def test_ts_returns_language(self):
        lang = get_language(".ts")
        assert lang is not None

    def test_unknown_extension_returns_none(self):
        assert get_language(".xyz") is None

    def test_case_insensitive(self):
        assert get_language(".PY") == get_language(".py")

    def test_markdown_exts(self):
        assert ".md" in MARKDOWN_EXTS
        assert ".markdown" in MARKDOWN_EXTS


# ---------------------------------------------------------------------------
# Python skeletonization
# ---------------------------------------------------------------------------

FIFTY_LINE_PY = b"""\
def big_function(x, y):
    \"\"\"Compute something important.\"\"\"
    a = x + 1
    b = y + 2
    c = a * b
    d = c - 1
    e = d / 2
    f = e ** 2
    g = f + a
    h = g - b
    i = h * c
    j = i + d
    k = j - e
    l = k * f
    m = l + g
    n = m - h
    o = n * i
    p = o + j
    q = p - k
    r = q * l
    s = r + m
    t = s - n
    u = t * o
    v = u + p
    w = v - q
    aa = w * r
    bb = aa + s
    cc = bb - t
    dd = cc * u
    ee = dd + v
    ff = ee - w
    gg = ff * aa
    hh = gg + bb
    ii = hh - cc
    jj = ii * dd
    kk = jj + ee
    ll = kk - ff
    mm = ll * gg
    nn = mm + hh
    oo = nn - ii
    pp = oo * jj
    qq = pp + kk
    rr = qq - ll
    ss = rr * mm
    tt = ss + nn
    uu = tt - oo
    vv = uu * pp
    ww = vv + qq
    xx = ww - rr
    return xx
"""


class TestPythonSkeletonizer:
    def test_big_function_reduced_to_def_and_docstring(self):
        result = skeletonize(FIFTY_LINE_PY, "python")
        lines = result.splitlines()
        assert lines[0] == "def big_function(x, y):"
        assert '"""Compute something important."""' in lines[1]
        assert "..." in result
        # Body lines (return xx, etc.) must be gone
        assert "return xx" not in result
        assert "a = x + 1" not in result

    def test_function_without_docstring(self):
        src = b"def foo(x):\n    return x * 2\n"
        result = skeletonize(src, "python")
        assert result.strip() == "def foo(x):\n    ..."

    def test_function_with_docstring_only(self):
        src = b'def foo():\n    """Just a doc."""\n    pass\n'
        result = skeletonize(src, "python")
        lines = result.splitlines()
        assert lines[0] == "def foo():"
        assert '"""Just a doc."""' in lines[1]
        assert "..." in lines[2]
        assert "pass" not in result

    def test_class_with_method(self):
        src = b'class Foo:\n    def bar(self):\n        """Do bar."""\n        x = 1\n        return x\n'
        result = skeletonize(src, "python")
        assert "class Foo:" in result
        assert "def bar(self):" in result
        assert '"""Do bar."""' in result
        assert "..." in result
        assert "x = 1" not in result
        assert "return x" not in result

    def test_class_method_without_docstring(self):
        src = b"class Bar:\n    def baz(self):\n        return 42\n"
        result = skeletonize(src, "python")
        assert "class Bar:" in result
        assert "def baz(self):" in result
        assert "..." in result
        assert "return 42" not in result

    def test_top_level_imports_preserved(self):
        src = b"import os\n\ndef foo():\n    pass\n"
        result = skeletonize(src, "python")
        assert "import os" in result
        assert "def foo():" in result
        assert "..." in result

    def test_language_alias(self):
        src = b"def f():\n    pass\n"
        assert skeletonize(src, "py") == skeletonize(src, "python")

    def test_exceeds_max_file_size_returns_empty(self):
        # MAX_FILE_SIZE_KB = 100 → 100 * 1024 = 102400 bytes
        oversized = b"x = 1\n" * 20000  # ~120 KB
        result = skeletonize(oversized, "python")
        assert result == ""

    def test_multiline_signature_preserved(self):
        src = (
            b"def complex(\n"
            b"    x: int,\n"
            b"    y: str,\n"
            b") -> None:\n"
            b"    pass\n"
        )
        result = skeletonize(src, "python")
        assert "def complex(" in result
        assert "x: int," in result
        assert "y: str," in result
        assert "pass" not in result
        assert "..." in result

    def test_async_function(self):
        src = b"async def fetch():\n    await something()\n    return 1\n"
        result = skeletonize(src, "python")
        assert "async def fetch():" in result
        assert "..." in result
        assert "await something()" not in result


# ---------------------------------------------------------------------------
# JavaScript skeletonization
# ---------------------------------------------------------------------------

JS_FUNCTION = b"""\
function add(a, b) {
    const result = a + b;
    console.log(result);
    return result;
}
"""

JS_ARROW = b"""\
const multiply = (a, b) => {
    const temp = a * b;
    return temp;
};
"""

JS_CLASS = b"""\
class Calculator {
    add(a, b) {
        return a + b;
    }

    subtract(a, b) {
        return a - b;
    }
}
"""


class TestJavaScriptSkeletonizer:
    def test_function_declaration_body_collapsed(self):
        result = skeletonize(JS_FUNCTION, "javascript")
        assert "function add(a, b)" in result
        assert "{...}" in result
        assert "console.log" not in result
        assert "return result" not in result

    def test_arrow_function_body_collapsed(self):
        result = skeletonize(JS_ARROW, "javascript")
        assert "multiply" in result
        assert "{...}" in result
        assert "const temp" not in result

    def test_class_methods_collapsed(self):
        result = skeletonize(JS_CLASS, "javascript")
        assert "Calculator" in result
        assert "add" in result
        assert "subtract" in result
        assert "{...}" in result
        assert "return a + b" not in result
        assert "return a - b" not in result

    def test_js_language_alias(self):
        assert skeletonize(JS_FUNCTION, "js") == skeletonize(JS_FUNCTION, "javascript")

    def test_typescript_alias(self):
        src = b"function greet(name: string): string {\n    return 'Hello ' + name;\n}\n"
        result = skeletonize(src, "typescript")
        assert "greet" in result
        assert "{...}" in result
        assert "Hello" not in result


# ---------------------------------------------------------------------------
# Markdown skeletonization
# ---------------------------------------------------------------------------

MD_SOURCE = b"""\
# Main Title

Some prose that should be removed.

## Section One

More prose to drop.

- [Link A](https://example.com/a)
- Plain list item (no link, should be dropped)

### Sub-section

[Another link](https://example.com/b) in a paragraph.

Plain paragraph text.
"""


class TestMarkdownSkeletonizer:
    def test_headers_kept(self):
        result = skeletonize(MD_SOURCE, "markdown")
        assert "# Main Title" in result
        assert "## Section One" in result
        assert "### Sub-section" in result

    def test_prose_removed(self):
        result = skeletonize(MD_SOURCE, "markdown")
        assert "Some prose that should be removed" not in result
        assert "More prose to drop" not in result
        assert "Plain paragraph text" not in result

    def test_links_kept(self):
        result = skeletonize(MD_SOURCE, "markdown")
        assert "[Link A](https://example.com/a)" in result
        assert "[Another link](https://example.com/b)" in result

    def test_plain_list_item_removed(self):
        result = skeletonize(MD_SOURCE, "markdown")
        assert "Plain list item" not in result

    def test_md_language_alias(self):
        assert skeletonize(MD_SOURCE, "md") == skeletonize(MD_SOURCE, "markdown")

    def test_headers_only_source(self):
        src = b"# H1\n## H2\n### H3\n"
        result = skeletonize(src, "markdown")
        assert result == "# H1\n## H2\n### H3\n"
