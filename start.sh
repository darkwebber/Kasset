#!/bin/bash
set -e

# ─── Cartridge Console — One-Command Launcher ──────────────────
# Usage: ./start.sh
# Handles: venv creation, dependency install, port checks,
#          backend + frontend startup, and clean shutdown.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  🎮 Kasset"
echo "  ═══════════════"
echo "  Local AI Console"
echo ""

# ═══════════════════════════════════════════
# PRE-FLIGHT CHECKS
# ═══════════════════════════════════════════

# ── Check Python 3.10+ ──
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PY_MINOR=$("$cmd" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo "0")
        PY_MAJOR=$("$cmd" -c 'import sys; print(sys.version_info.major)' 2>/dev/null || echo "0")
        if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done
if [ -z "$PYTHON_CMD" ]; then
    echo "  ❌ Python 3.10+ is required but not found."
    echo "     Install: brew install python@3.12"
    exit 1
fi
echo "  ✓ Python: $($PYTHON_CMD --version 2>&1)"

# ── Check Node.js ──
if ! command -v node &>/dev/null; then
    echo "  ❌ Node.js is required but not found."
    echo "     Install: brew install node"
    exit 1
fi
NODE_MAJOR=$(node -e 'console.log(process.versions.node.split(".")[0])' 2>/dev/null || echo "0")
if [ "$NODE_MAJOR" -lt 18 ]; then
    echo "  ❌ Node.js 18+ required. Found: $(node --version)"
    echo "     Upgrade: brew install node"
    exit 1
fi
echo "  ✓ Node.js: $(node --version)"

# ── Check npm ──
if ! command -v npm &>/dev/null; then
    echo "  ❌ npm is required but not found."
    exit 1
fi

# ── Check ports ──
check_port() {
    if lsof -i :"$1" -sTCP:LISTEN &>/dev/null; then
        echo "  ❌ Port $1 is already in use."
        echo "     Free it: lsof -i :$1 -t | xargs kill -9"
        exit 1
    fi
}
check_port 7861
check_port 3000
echo "  ✓ Ports 7861, 3000 available"

# ── Check Apple Silicon (warning only) ──
ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
    echo "  ⚠  Apple Silicon (arm64) recommended for MLX. Detected: $ARCH"
fi

echo ""

# ═══════════════════════════════════════════
# SETUP (first run only)
# ═══════════════════════════════════════════

FIRST_RUN=false

# ── Python venv ──
if [ ! -d "venv" ]; then
    FIRST_RUN=true
    echo "  → Creating Python virtual environment..."
    "$PYTHON_CMD" -m venv venv
fi
# Always activate from the project's venv
source venv/bin/activate

if [ "$FIRST_RUN" = true ]; then
    echo "  → Installing backend dependencies (this may take a few minutes)..."
    pip install --upgrade pip -q 2>&1 | tail -1
    pip install -r backend/requirements.txt -q 2>&1 | tail -1
    echo "  ✅ Backend dependencies installed"
    echo ""
fi

# ── Verify critical backend imports ──
python -c "import fastapi, uvicorn, mlx_vlm" 2>/dev/null || {
    echo "  → Some backend dependencies missing, reinstalling..."
    pip install -r backend/requirements.txt -q 2>&1 | tail -1
}

# ── Frontend node_modules ──
if [ ! -d "frontend/node_modules" ]; then
    echo "  → Installing frontend dependencies..."
    (cd frontend && npm install --loglevel=error)
    echo "  ✅ Frontend dependencies installed"
    echo ""
fi

# ═══════════════════════════════════════════
# USER DATA DIRECTORY
# ═══════════════════════════════════════════
# Ensure ~/.qwen-studio/ exists for user data (chats, memory, context, uploads)
mkdir -p "$HOME/.qwen-studio/chats"
mkdir -p "$HOME/.qwen-studio/context/cartridges"
mkdir -p "$HOME/.qwen-studio/cache"
mkdir -p "$HOME/.qwen-studio/uploads"
mkdir -p "$HOME/.qwen-studio/workspace"

# ═══════════════════════════════════════════
# PROCESS MANAGEMENT
# ═══════════════════════════════════════════

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo ""
    echo "  Shutting down..."
    [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null && wait "$FRONTEND_PID" 2>/dev/null
    [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null && wait "$BACKEND_PID" 2>/dev/null
    echo "  Goodbye! 👋"
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# ═══════════════════════════════════════════
# START BACKEND (FastAPI + MLX)
# ═══════════════════════════════════════════

echo "  Starting backend on 0.0.0.0:7861..."
python -m uvicorn backend.api:app --host 0.0.0.0 --port 7861 --log-level warning &
BACKEND_PID=$!

# Wait for backend to be ready (max 120s for first-run model download)
echo -n "  Waiting for backend "
TIMEOUT=120
for i in $(seq 1 $TIMEOUT); do
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo ""
        echo "  ❌ Backend process crashed. Check errors above."
        exit 1
    fi
    if curl -sf http://127.0.0.1:7861/api/cartridges >/dev/null 2>&1; then
        echo ""
        echo "  ✅ Backend ready!"
        break
    fi
    if [ "$i" -eq "$TIMEOUT" ]; then
        echo ""
        echo "  ❌ Backend did not respond within ${TIMEOUT}s."
        echo "     Check logs: python -m uvicorn backend.api:app --log-level debug"
        exit 1
    fi
    echo -n "."
    sleep 1
done

# ═══════════════════════════════════════════
# START FRONTEND (Next.js)
# ═══════════════════════════════════════════

echo "  Starting frontend on 0.0.0.0:3000..."
(cd frontend && npx next dev --hostname 0.0.0.0 --port 3000 2>&1) &
FRONTEND_PID=$!

# Brief wait for Next.js to compile
sleep 3

echo ""
# Detect LAN IP for mobile access
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "<your-ip>")

echo "  ════════════════════════════════════════════"
echo "  🎮 Kasset is running!"
echo ""
echo "     Local:   http://localhost:3000"
echo "     Network: http://$LAN_IP:3000"
echo "     Data:    ~/.qwen-studio/"
echo ""
echo "  📱 Open the Network URL on your phone!"
echo "     (shell commands are disabled for network clients)"
echo ""
echo "  Press Ctrl+C to stop"
echo "  ════════════════════════════════════════════"
echo ""

# Wait for either process to exit
wait
