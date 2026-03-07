#!/bin/bash
set -e

# ─── Kasset — One-Command Launcher ─────────────────────────────
# Usage: ./start.sh [--update]
# Flags: --update  Force reinstall of all dependencies
# Handles: venv creation, dependency install, port checks,
#          backend + frontend startup, and clean shutdown.
# ────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colors ──
R='\033[0;31m'    # Red
G='\033[0;32m'    # Green
Y='\033[0;33m'    # Yellow
B='\033[0;34m'    # Blue
M='\033[0;35m'    # Magenta
C='\033[0;36m'    # Cyan
W='\033[1;37m'    # White bold
D='\033[0;90m'    # Dim
N='\033[0m'       # Reset

ok()   { echo -e "  ${G}✓${N} $1"; }
fail() { echo -e "  ${R}✗${N} $1"; }
warn() { echo -e "  ${Y}⚠${N} $1"; }
info() { echo -e "  ${C}→${N} $1"; }
dim()  { echo -e "  ${D}$1${N}"; }

# ── Flags ──
FORCE_UPDATE=false
for arg in "$@"; do
    case "$arg" in
        --update) FORCE_UPDATE=true ;;
    esac
done

# ── Branding ──
echo ""
echo -e "  ${M}╔═══════════════════════════════════════╗${N}"
echo -e "  ${M}║${N}         ${W}🎮  K A S S E T${N}               ${M}║${N}"
echo -e "  ${M}║${N}   ${D}Local AI · Mac · Apple Silicon${N}      ${M}║${N}"
echo -e "  ${M}╚═══════════════════════════════════════╝${N}"
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
    fail "Python 3.10+ not found"
    dim "  brew install python@3.12"
    ERRORS=$((ERRORS + 1))
else
    PY_VER=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
    ok "Python ${W}${PY_VER}${N}"
fi

# ── Check Node.js 18+ ──
if ! command -v node &>/dev/null; then
    fail "Node.js not found"
    dim "  brew install node"
    ERRORS=$((ERRORS + 1))
else
    NODE_MAJOR=$(node -e 'console.log(process.versions.node.split(".")[0])' 2>/dev/null || echo "0")
    if [ "$NODE_MAJOR" -lt 18 ]; then
        fail "Node.js 18+ required (found $(node --version))"
        dim "  brew upgrade node"
        ERRORS=$((ERRORS + 1))
    else
        ok "Node.js ${W}$(node --version | tr -d 'v')${N}"
    fi
fi

# ── Check npm ──
if ! command -v npm &>/dev/null; then
    fail "npm not found (usually comes with Node.js)"
    ERRORS=$((ERRORS + 1))
fi

# ── Bail if missing dependencies ──
if [ "$ERRORS" -gt 0 ]; then
    echo ""
    echo -e "  ${R}❌ Missing $ERRORS dependency(ies). Install them and try again.${N}"
    exit 1
fi

# ── Check ports ──
check_port() {
    if lsof -i :"$1" -sTCP:LISTEN &>/dev/null; then
        local PID_LIST=$(lsof -i :"$1" -sTCP:LISTEN -t 2>/dev/null | head -3 | tr '\n' ' ')
        fail "Port $1 in use ${D}(PID: ${PID_LIST})${N}"
        dim "  lsof -i :$1 -t | xargs kill -9"
        return 1
    fi
    return 0
}
PORT_OK=true
check_port 7861 || PORT_OK=false
check_port 3000 || PORT_OK=false
if [ "$PORT_OK" = false ]; then
    echo ""
    echo -e "  ${R}❌ Free the ports above and try again.${N}"
    exit 1
fi
ok "Ports ${W}7861${N}, ${W}3000${N} available"

# ── Check Apple Silicon ──
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
    ok "Apple Silicon ${D}($ARCH)${N}"
else
    warn "Apple Silicon recommended for MLX ${D}(detected: $ARCH)${N}"
fi

echo ""

# ═══════════════════════════════════════════
# SETUP
# ═══════════════════════════════════════════

FIRST_RUN=false

# ── Python venv ──
if [ ! -d "venv" ]; then
    FIRST_RUN=true
    info "Creating Python virtual environment..."
    "$PYTHON_CMD" -m venv venv
fi
source venv/bin/activate

# ── Backend dependencies ──
if [ "$FIRST_RUN" = true ] || [ "$FORCE_UPDATE" = true ]; then
    info "Installing backend dependencies ${D}(this may take a few minutes)${N}..."
    pip install --upgrade pip -q 2>&1 | tail -1
    pip install -r backend/requirements.txt -q 2>&1 | tail -1
    ok "Backend dependencies installed"
    echo ""
else
    # Verify critical imports even on subsequent runs
    if ! python -c "import fastapi, uvicorn, mlx_vlm" 2>/dev/null; then
        info "Reinstalling backend dependencies..."
        pip install -r backend/requirements.txt -q 2>&1 | tail -1
        ok "Backend dependencies restored"
    fi
fi

# ── Frontend dependencies ──
if [ ! -d "frontend/node_modules" ] || [ "$FORCE_UPDATE" = true ]; then
    info "Installing frontend dependencies..."
    (cd frontend && npm install --loglevel=error 2>&1)
    ok "Frontend dependencies installed"
    echo ""
fi

# ── User data directory ──
# Migrate from old ~/.qwen-studio/ if it exists
if [ -d "$HOME/.qwen-studio" ] && [ ! -d "$HOME/.kasset" ]; then
    info "Migrating user data from ~/.qwen-studio/ to ~/.kasset/..."
    mv "$HOME/.qwen-studio" "$HOME/.kasset"
    ok "Data migrated"
elif [ -d "$HOME/.qwen-studio" ] && [ -d "$HOME/.kasset" ]; then
    warn "Both ~/.qwen-studio/ and ~/.kasset/ exist. Using ~/.kasset/."
    dim "  You can manually merge or delete ~/.qwen-studio/ if needed."
fi
mkdir -p "$HOME/.kasset"/{chats,context/cartridges,cache,uploads,workspace,tools,cartridges}

# ═══════════════════════════════════════════
# PROCESS MANAGEMENT
# ═══════════════════════════════════════════

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo ""
    echo -e "  ${D}Shutting down Kasset...${N}"
    # Kill process groups to catch child processes
    [ -n "$FRONTEND_PID" ] && kill -- -"$FRONTEND_PID" 2>/dev/null || kill "$FRONTEND_PID" 2>/dev/null || true
    [ -n "$BACKEND_PID" ] && kill -- -"$BACKEND_PID" 2>/dev/null || kill "$BACKEND_PID" 2>/dev/null || true
    wait 2>/dev/null
    echo -e "  ${G}Done.${N} See you next time."
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# ═══════════════════════════════════════════
# START BACKEND
# ═══════════════════════════════════════════

info "Starting backend ${D}(port 7861)${N}..."
python -m uvicorn backend.api:app --host 0.0.0.0 --port 7861 --log-level warning &
BACKEND_PID=$!

# Wait for backend to be ready
# First run downloads the model (~5GB) so we allow up to 300s
if [ "$FIRST_RUN" = true ]; then
    echo -e "  ${Y}⏳${N} First run — downloading model ${W}(~5 GB)${N}. One-time download."
    TIMEOUT=300
else
    TIMEOUT=60
fi
echo -ne "  ${D}Waiting for backend${N}"
for i in $(seq 1 $TIMEOUT); do
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo ""
        fail "Backend crashed. Debug with:"
        dim "  source venv/bin/activate"
        dim "  python -m uvicorn backend.api:app --log-level debug"
        exit 1
    fi
    if curl -sf http://127.0.0.1:7861/api/kassets >/dev/null 2>&1; then
        echo ""
        ok "Backend ready"
        break
    fi
    if [ "$i" -eq "$TIMEOUT" ]; then
        echo ""
        fail "Backend timed out after ${TIMEOUT}s."
        exit 1
    fi
    # Show dots, with a progress update every 30s
    if [ $((i % 30)) -eq 0 ]; then
        echo ""
        echo -ne "  ${D}Still loading (${i}s)${N}"
    fi
    echo -ne "${D}.${N}"
    sleep 1
done

# ═══════════════════════════════════════════
# START FRONTEND
# ═══════════════════════════════════════════

info "Starting frontend ${D}(port 3000)${N}..."
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
echo -e "  ${G}╔═══════════════════════════════════════╗${N}"
echo -e "  ${G}║${N}       ${W}Kasset is ready!${N}                ${G}║${N}"
echo -e "  ${G}╟───────────────────────────────────────╢${N}"
echo -e "  ${G}║${N}  ${C}Local:${N}   http://localhost:3000       ${G}║${N}"
if [ -n "$LAN_IP" ]; then
printf "  ${G}║${N}  ${C}Network:${N} http://%-21s${G}║${N}\n" "$LAN_IP:3000"
fi
echo -e "  ${G}║${N}  ${C}API:${N}     http://localhost:7861/docs  ${G}║${N}"
echo -e "  ${G}║${N}  ${C}Data:${N}    ~/.kasset/                  ${G}║${N}"
echo -e "  ${G}╟───────────────────────────────────────╢${N}"
if [ -n "$LAN_IP" ]; then
echo -e "  ${G}║${N}  ${M}📱 Open Network URL on your phone${N}    ${G}║${N}"
fi
echo -e "  ${G}║${N}  Press ${W}Ctrl+C${N} to stop                 ${G}║${N}"
echo -e "  ${G}╚═══════════════════════════════════════╝${N}"
echo ""

# Keep running until a process exits or user hits Ctrl+C
wait
