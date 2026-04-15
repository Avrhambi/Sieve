#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# On Windows (Git Bash), Python is installed as "python" not "python3".
# Detect whichever is available.
if command -v python3 &>/dev/null; then
    PY=python3
elif command -v python &>/dev/null; then
    PY=python
else
    echo "ERROR: Python not found in PATH." >&2
    exit 1
fi

echo "==> Checking Python version..."
python_version=$($PY --version 2>&1 | awk '{print $2}')
major=$(echo "$python_version" | cut -d. -f1)
minor=$(echo "$python_version" | cut -d. -f2)

if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 11 ]; }; then
    echo "ERROR: Python 3.11+ required, found $python_version." >&2
    exit 1
fi
echo "    Python $python_version — OK"

echo "==> Creating virtual environment..."
if [ ! -d ".venv" ]; then
    $PY -m venv .venv
    echo "    Created .venv/"
else
    echo "    .venv/ already exists — skipping"
fi

echo "==> Activating venv and installing dependencies..."
# Windows (Git Bash) uses Scripts/activate; Linux/Mac uses bin/activate
if [ -f ".venv/Scripts/activate" ]; then
    # shellcheck disable=SC1091
    source .venv/Scripts/activate
else
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

pip install --quiet --upgrade pip
pip install --quiet \
    "toml>=0.10" \
    "pydantic>=2.0" \
    "aiohttp>=3.9" \
    "watchdog>=4.0" \
    "tree-sitter>=0.25" \
    "tree-sitter-python>=0.23" \
    "tree-sitter-javascript>=0.23" \
    "tree-sitter-typescript>=0.23" \
    "rapidocr-onnxruntime>=1.3" \
    "mcp>=1.0"
echo "    Dependencies installed"

echo "==> Checking Ollama..."
if ! command -v ollama &>/dev/null; then
    echo ""
    echo "ERROR: Ollama is not installed." >&2
    echo "  Install it from: https://ollama.com/download" >&2
    echo "  Then re-run this script." >&2
    exit 1
fi
echo "    Ollama found"

echo "==> Pulling model qwen2.5-coder:1.5b (this may take a few minutes)..."
ollama pull qwen2.5-coder:1.5b
echo "Verifying Ollama model..."
if ollama run qwen2.5-coder:1.5b "ping" 2>&1 | grep -q "."; then
    echo "Model OK"
else
    echo "ERROR: Model verification failed — the pull may be incomplete or corrupted."
    echo "Re-run install.sh to retry."
    exit 1
fi
echo "    Model ready"

echo "==> Initialising SQLite WAL database..."
PYTHONPATH="$REPO_ROOT" $PY -c "
import sys
sys.path.insert(0, '.')
from src.data.ledger import Ledger
with Ledger() as l:
    pass
print('    ledger.db initialised')
"

echo "==> Making bin/sieve-hook executable..."
chmod +x bin/sieve-hook

echo ""
echo "Sieve installed. Run: python src/main.py to start the daemon."
