#!/bin/bash
set -e

# ─── Qwen Studio — One-Command Launcher ──────────────────
# Usage: ./start.sh
# This script sets up the environment (first run) and starts both servers.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  🧠 Qwen Studio"
echo "  ════════════════"
echo ""

# ── Pre-flight checks ──
if [ ! -f "app.py" ] || [ ! -f "model_server.py" ]; then
    echo "❌ Missing project files. Re-clone the repo."
    exit 1
fi

PYTHON=${PYTHON:-python3}
PY_VERSION=$($PYTHON -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo "0")
if [ "$PY_VERSION" -lt 10 ]; then
    echo "❌ Python 3.10+ required. Found: $($PYTHON --version 2>&1)"
    echo "   Install: brew install python@3.12"
    exit 1
fi

ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
    echo "⚠️  Apple Silicon (arm64) recommended. Detected: $ARCH"
fi

# ── Setup (only on first run or if venv is missing) ──
if [ ! -d "venv" ]; then
    echo "→ First run — creating virtual environment..."
    $PYTHON -m venv venv
    source venv/bin/activate
    echo "→ Installing dependencies (this may take a minute)..."
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    echo "✅ Setup complete!"
    echo ""
else
    source venv/bin/activate
fi

# Verify key packages
python -c "import gradio, mlx_vlm" 2>/dev/null || {
    echo "→ Installing missing dependencies..."
    pip install -r requirements.txt -q
}

echo "  Python:  $(python --version)"
echo "  venv:    ✓ active"
echo ""

# ── Cleanup handler — kill background server on exit ──
MODEL_PID=""
cleanup() {
    echo ""
    echo "  Shutting down..."
    if [ -n "$MODEL_PID" ] && kill -0 "$MODEL_PID" 2>/dev/null; then
        kill "$MODEL_PID" 2>/dev/null
        wait "$MODEL_PID" 2>/dev/null
    fi
    echo "  Goodbye! 👋"
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# ── Start model server (background) ──
echo "  Starting model server on :7861..."
echo "  (Model downloads ~5GB on first launch)"
echo ""
python model_server.py &
MODEL_PID=$!

# Wait for model server to be ready (poll every 2s, max 120s)
echo -n "  Waiting for model server "
for i in $(seq 1 60); do
    if ! kill -0 "$MODEL_PID" 2>/dev/null; then
        echo ""
        echo "❌ Model server crashed. Check logs above."
        exit 1
    fi
    if python -c "
from gradio_client import Client
try:
    Client('http://127.0.0.1:7861', verbose=False)
    exit(0)
except:
    exit(1)
" 2>/dev/null; then
        echo ""
        echo "  ✅ Model server ready!"
        break
    fi
    echo -n "."
    sleep 2
done

echo ""
echo "  Starting chat UI on :7860..."
echo "  ════════════════════════════════════════════"
echo "  Open http://localhost:7860 in your browser"
echo "  Press Ctrl+C to stop both servers"
echo "  ════════════════════════════════════════════"
echo ""

# ── Start app server (foreground) ──
python app.py
