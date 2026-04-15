#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# On Windows (Git Bash), Python is installed as "python" not "python3".
# Try each candidate and pick the first one that actually returns a version.
PY=""
for candidate in python python3; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" --version 2>&1 | awk '{print $2}')
        if [ -n "$ver" ]; then
            PY="$candidate"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
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

python -m pip install --quiet --upgrade pip
python -m pip install --quiet \
    "toml>=0.10" \
    "pydantic>=2.0" \
    "aiohttp>=3.9" \
    "watchdog>=4.0" \
    "tree-sitter>=0.25" \
    "tree-sitter-python>=0.23" \
    "tree-sitter-javascript>=0.23" \
    "tree-sitter-typescript>=0.23" \
    "mcp>=1.0"
echo "    Core dependencies installed"

echo "==> Installing OCR dependency (optional — skip if Python >3.13)..."
if python -m pip install --quiet "rapidocr-onnxruntime>=1.3" 2>/dev/null; then
    echo "    rapidocr-onnxruntime installed"
else
    echo "    WARN: rapidocr-onnxruntime skipped (not yet compatible with your Python version)"
    echo "         OCR screenshot features will be unavailable — all other features work normally"
fi

echo "==> Checking Ollama..."
# On Windows, Ollama is a system tray app and may not be on Git Bash PATH.
# Check PATH first, then common Windows install locations.
OLLAMA_CMD=""
if command -v ollama &>/dev/null; then
    OLLAMA_CMD="ollama"
elif [ -f "$LOCALAPPDATA/Programs/Ollama/ollama.exe" ]; then
    OLLAMA_CMD="$LOCALAPPDATA/Programs/Ollama/ollama.exe"
elif [ -f "/c/Users/$USERNAME/AppData/Local/Programs/Ollama/ollama.exe" ]; then
    OLLAMA_CMD="/c/Users/$USERNAME/AppData/Local/Programs/Ollama/ollama.exe"
fi

if [ -z "$OLLAMA_CMD" ]; then
    echo "    WARN: Ollama not found — LLM summaries will use heuristic fallback."
    echo "         Install from https://ollama.com/download for full functionality."
else
    echo "    Ollama found: $OLLAMA_CMD"
    echo "==> Pulling model qwen2.5-coder:1.5b (this may take a few minutes)..."
    "$OLLAMA_CMD" pull qwen2.5-coder:1.5b
    echo "Verifying Ollama model..."
    if "$OLLAMA_CMD" run qwen2.5-coder:1.5b "ping" 2>&1 | grep -q "."; then
        echo "    Model OK"
    else
        echo "    WARN: Model verification failed — re-run install.sh to retry."
    fi
fi

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
