#!/bin/bash
set -e

# ─── Kasset — One-Command Launcher ─────────────────────────────
# Usage: ./start.sh
# Handles: venv creation, dependency install, port checks,
#          backend + frontend startup, and clean shutdown.
# ────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Branding ──
echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║         🎮  K A S S E T               ║"
echo "  ║   Local AI · Mac · Apple Silicon      ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# ═══════════════════════════════════════════
# PRE-FLIGHT CHECKS
# ═══════════════════════════════════════════

ERRORS=0

# ── Check Python 3.10+ ──
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PY_MAJOR=$("$cmd" -c 'import sys; print(sys.version_info.major)' 2>/dev/null || echo "0")
        PY_MINOR=$("$cmd" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo "0")
        if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done
if [ -z "$PYTHON_CMD" ]; then
    echo "  ✗ Python 3.10+ not found"
    echo "    → brew install python@3.12"
    ERRORS=$((ERRORS + 1))
else
    echo "  ✓ Python $($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
fi

# ── Check Node.js 18+ ──
if ! command -v node &>/dev/null; then
    echo "  ✗ Node.js not found"
    echo "    → brew install node"
    ERRORS=$((ERRORS + 1))
else
    NODE_MAJOR=$(node -e 'console.log(process.versions.node.split(".")[0])' 2>/dev/null || echo "0")
    if [ "$NODE_MAJOR" -lt 18 ]; then
        echo "  ✗ Node.js 18+ required (found $(node --version))"
        echo "    → brew upgrade node"
        ERRORS=$((ERRORS + 1))
    else
        echo "  ✓ Node.js $(node --version | tr -d 'v')"
    fi
fi

# ── Check npm ──
if ! command -v npm &>/dev/null; then
    echo "  ✗ npm not found (usually comes with Node.js)"
    ERRORS=$((ERRORS + 1))
fi

# ── Bail if missing dependencies ──
if [ "$ERRORS" -gt 0 ]; then
    echo ""
    echo "  ❌ Missing $ERRORS dependency(ies). Install them and try again."
    exit 1
fi

# ── Check ports ──
check_port() {
    if lsof -i :"$1" -sTCP:LISTEN &>/dev/null; then
        echo "  ✗ Port $1 is in use"
        echo "    → lsof -i :$1 -t | xargs kill -9"
        return 1
    fi
    return 0
}
PORT_OK=true
check_port 7861 || PORT_OK=false
check_port 3000 || PORT_OK=false
if [ "$PORT_OK" = false ]; then
    echo ""
    echo "  ❌ Free the ports above and try again."
    exit 1
fi
echo "  ✓ Ports 7861, 3000 available"

# ── Check Apple Silicon ──
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
    echo "  ✓ Apple Silicon ($ARCH)"
else
    echo "  ⚠ Apple Silicon recommended for MLX (detected: $ARCH)"
fi

echo ""

# ═══════════════════════════════════════════
# SETUP
# ═══════════════════════════════════════════

FIRST_RUN=false

# ── Python venv ──
if [ ! -d "venv" ]; then
    FIRST_RUN=true
    echo "  → Creating Python virtual environment..."
    "$PYTHON_CMD" -m venv venv
fi
source venv/bin/activate

# ── Backend dependencies ──
if [ "$FIRST_RUN" = true ]; then
    echo "  → Installing backend dependencies (this may take a few minutes)..."
    pip install --upgrade pip -q 2>&1 | tail -1
    pip install -r backend/requirements.txt -q 2>&1 | tail -1
    echo "  ✓ Backend dependencies installed"
    echo ""
else
    # Verify critical imports even on subsequent runs
    python -c "import fastapi, uvicorn, mlx_vlm" 2>/dev/null || {
        echo "  → Reinstalling backend dependencies..."
        pip install -r backend/requirements.txt -q 2>&1 | tail -1
    }
fi

# ── Frontend dependencies ──
if [ ! -d "frontend/node_modules" ]; then
    echo "  → Installing frontend dependencies..."
    (cd frontend && npm install --loglevel=error)
    echo "  ✓ Frontend dependencies installed"
    echo ""
fi

# ── User data directory ──
# Migrate from old ~/.qwen-studio/ if it exists
if [ -d "$HOME/.qwen-studio" ] && [ ! -d "$HOME/.kasset" ]; then
    echo "  → Migrating user data from ~/.qwen-studio/ to ~/.kasset/..."
    mv "$HOME/.qwen-studio" "$HOME/.kasset"
    echo "  ✓ Data migrated"
elif [ -d "$HOME/.qwen-studio" ] && [ -d "$HOME/.kasset" ]; then
    echo "  ⚠ Both ~/.qwen-studio/ and ~/.kasset/ exist. Using ~/.kasset/."
    echo "    You can manually merge or delete ~/.qwen-studio/ if needed."
fi
mkdir -p "$HOME/.kasset"/{chats,context/cartridges,cache,uploads,workspace,tools,cartridges}

# ═══════════════════════════════════════════
# PROCESS MANAGEMENT
# ═══════════════════════════════════════════

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo ""
    echo "  Shutting down Kasset..."
    [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null && wait "$FRONTEND_PID" 2>/dev/null
    [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null && wait "$BACKEND_PID" 2>/dev/null
    echo "  Done. See you next time."
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# ═══════════════════════════════════════════
# START BACKEND
# ═══════════════════════════════════════════

echo "  Starting backend (port 7861)..."
python -m uvicorn backend.api:app --host 0.0.0.0 --port 7861 --log-level warning &
BACKEND_PID=$!

# Wait for backend to be ready
# First run downloads the model (~5GB) so we allow up to 180s
if [ "$FIRST_RUN" = true ]; then
    echo "  ⏳ First run — downloading model (~5GB). This is a one-time download."
    TIMEOUT=180
else
    TIMEOUT=60
fi
echo -n "  Waiting for backend"
for i in $(seq 1 $TIMEOUT); do
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo ""
        echo "  ❌ Backend crashed. Run with verbose logging to debug:"
        echo "     source venv/bin/activate"
        echo "     python -m uvicorn backend.api:app --log-level debug"
        exit 1
    fi
    if curl -sf http://127.0.0.1:7861/api/cartridges >/dev/null 2>&1; then
        echo ""
        echo "  ✓ Backend ready"
        break
    fi
    if [ "$i" -eq "$TIMEOUT" ]; then
        echo ""
        echo "  ❌ Backend timed out after ${TIMEOUT}s."
        exit 1
    fi
    # Show dots, with a longer message every 30s
    if [ $((i % 30)) -eq 0 ]; then
        echo ""
        echo -n "  Still loading (${i}s)"
    fi
    echo -n "."
    sleep 1
done

# ═══════════════════════════════════════════
# START FRONTEND
# ═══════════════════════════════════════════

echo "  Starting frontend (port 3000)..."
(cd frontend && npx next dev --hostname 0.0.0.0 --port 3000 2>&1) &
FRONTEND_PID=$!

# Wait for Next.js to compile
sleep 3

# ═══════════════════════════════════════════
# READY
# ═══════════════════════════════════════════

# Detect LAN IP for mobile/tablet access
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "")

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║       Kasset is ready!                ║"
echo "  ╟───────────────────────────────────────╢"
echo "  ║  Local:   http://localhost:3000       ║"
if [ -n "$LAN_IP" ]; then
printf "  ║  Network: http://%-21s║\n" "$LAN_IP:3000"
fi
echo "  ║  API:     http://localhost:7861/docs  ║"
echo "  ║  Data:    ~/.kasset/                  ║"
echo "  ╟───────────────────────────────────────╢"
if [ -n "$LAN_IP" ]; then
echo "  ║  📱 Open Network URL on your phone    ║"
fi
echo "  ║  Press Ctrl+C to stop                 ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# Keep running until a process exits or user hits Ctrl+C
wait
