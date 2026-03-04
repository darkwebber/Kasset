#!/bin/bash
set -e

# ─── Qwen Studio — Setup ───────────────────────────────────
echo ""
echo "  Qwen Studio — Setup"
echo "  ════════════════════"
echo ""

# Check directory
if [ ! -f "app.py" ] || [ ! -f "model_server.py" ]; then
    echo "❌ Run this script from the qwen-studio directory."
    exit 1
fi

# Check Python version (need 3.10+)
PYTHON=${PYTHON:-python3}
PY_VERSION=$($PYTHON -c 'import sys; print(f"{sys.version_info.minor}")' 2>/dev/null || echo "0")
if [ "$PY_VERSION" -lt 10 ]; then
    echo "❌ Python 3.10+ required. Found: $($PYTHON --version 2>&1)"
    echo "   Install via: brew install python@3.12"
    exit 1
fi
echo "✓ Python: $($PYTHON --version)"

# Check Apple Silicon
ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
    echo "⚠️  Warning: Apple Silicon (arm64) recommended. Detected: $ARCH"
fi

# Virtual environment
if [ ! -d "venv" ]; then
    echo "→ Creating virtual environment..."
    $PYTHON -m venv venv
fi
source venv/bin/activate
echo "✓ Virtual environment active"

# Install dependencies
echo "→ Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✓ Dependencies installed"

# Verify key imports
echo "→ Verifying imports..."
python -c "import gradio, gradio_client, mlx_vlm; print('✓ All packages verified')" 2>/dev/null || {
    echo "⚠️  Some packages failed to import. Try:"
    echo "   pip install mlx-vlm gradio gradio_client Pillow"
    exit 1
}

echo ""
echo "  ✅ Setup complete!"
echo ""
echo "  Start Qwen Studio:"
echo "  ───────────────────"
echo "  Terminal 1:  source venv/bin/activate && python model_server.py"
echo "  Terminal 2:  source venv/bin/activate && python app.py"
echo "  Browser:     http://localhost:7860"
echo ""
echo "  The model (~5GB) downloads automatically on first launch."
echo ""
