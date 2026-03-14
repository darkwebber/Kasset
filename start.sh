#!/bin/bash
set -euo pipefail

# ─── Kasset — One-Command Launcher ─────────────────────────────
# Usage: ./start.sh [--update] [--no-browser] [--no-install] [--kill-ports] [--help]
# Flags:
#   --update      Force reinstall of all dependencies
#   --no-browser  Don't auto-open the browser on startup
#   --no-install  Skip automatic dependency installation (brew)
#   --kill-ports  Auto-kill stale listeners on 7861/3000
#   --help        Show usage and exit
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
AUTO_BROWSER=true
AUTO_INSTALL=true
KILL_PORTS=false

# ── Runtime config (can be overridden via env) ──
BACKEND_HOST="${KASSET_HOST:-0.0.0.0}"
BACKEND_PORT="${KASSET_PORT:-7861}"
FRONTEND_HOST="${KASSET_FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${KASSET_FRONTEND_PORT:-3000}"

for arg in "$@"; do
    case "$arg" in
        --update) FORCE_UPDATE=true ;;
        --no-browser) AUTO_BROWSER=false ;;
        --no-install) AUTO_INSTALL=false ;;
        --kill-port) KILL_PORTS=true ;;
        --kill-ports) KILL_PORTS=true ;;
        --help|-h)
            echo "Usage: ./start.sh [--update] [--no-browser] [--no-install] [--kill-ports] [--help]"
            echo ""
            echo "Flags:"
            echo "  --update       Force reinstall of all dependencies"
            echo "  --no-browser   Don't auto-open browser on startup"
            echo "  --no-install   Skip automatic dependency installation (brew)"
            echo "  --kill-ports   Auto-kill processes on ports 7861/3000 before starting"
            echo "  --help, -h     Show this help message"
            echo ""
            echo "Requirements: Python 3.10+, Node.js 18+, ~8GB RAM"
            echo "Recommended:  macOS with Apple Silicon (M1/M2/M3/M4)"
            echo ""
            echo "Data stored in: ~/.kasset/"
            exit 0
            ;;
    esac
done

# ═══════════════════════════════════════════
# INSTANT PRELOADER (opens browser immediately)
# ═══════════════════════════════════════════
PRELOADER_OPENED=false

launch_preloader() {
    local preload_file="$HOME/.kasset/cache/kasset-preloader.html"
    local frontend_url="http://localhost:${FRONTEND_PORT}"
    mkdir -p "$HOME/.kasset/cache"

    cat > "$preload_file" <<'PRELOADER_EOF'
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Kasset Booting...</title>
  <style>
    :root {
      --bg0: #06080a;
      --bg1: #0c1115;
      --line: rgba(255, 255, 255, 0.04);
      --accent: #26ffd5;
      --accent2: #ffbe6b;
      --text: #c7d5d9;
      --muted: #6f8389;
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background:
        radial-gradient(circle at 20% 20%, rgba(38, 255, 213, 0.09), transparent 40%),
        radial-gradient(circle at 80% 70%, rgba(255, 190, 107, 0.08), transparent 45%),
        linear-gradient(160deg, var(--bg0), var(--bg1));
      color: var(--text);
      font-family: Menlo, Monaco, "Cascadia Mono", "SF Mono", monospace;
    }
    .scan {
      position: fixed;
      inset: 0;
      pointer-events: none;
      background: repeating-linear-gradient(
        to bottom,
        transparent 0px,
        transparent 2px,
        rgba(255,255,255,0.03) 3px,
        transparent 4px
      );
      opacity: 0.3;
      mix-blend-mode: screen;
    }
    .wrap {
      height: 100%;
      display: grid;
      place-items: center;
      padding: 24px;
    }
    .panel {
      width: min(780px, 100%);
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(7, 12, 15, 0.82);
      backdrop-filter: blur(4px);
      box-shadow: 0 0 0 1px rgba(38,255,213,0.12) inset, 0 30px 80px rgba(0,0,0,0.45);
      overflow: hidden;
    }
    .head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
      letter-spacing: 0.06em;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
    }
    .brand {
      color: var(--accent);
      text-shadow: 0 0 8px rgba(38,255,213,0.4);
    }
    .body { padding: 20px 16px 16px; }
    .title {
      margin: 0 0 8px;
      font-size: 22px;
      color: #eaf9fd;
      letter-spacing: 0.02em;
    }
    .subtitle {
      margin: 0 0 14px;
      color: var(--muted);
      font-size: 13px;
    }
    .bar {
      height: 10px;
      border-radius: 99px;
      border: 1px solid var(--line);
      overflow: hidden;
      background: rgba(255,255,255,0.02);
      margin-bottom: 12px;
    }
    .fill {
      height: 100%;
      width: 18%;
      background: linear-gradient(90deg, var(--accent), #4cf7ff, var(--accent2));
      box-shadow: 0 0 14px rgba(76,247,255,0.35);
      animation: drift 2.2s ease-in-out infinite;
      transform-origin: left center;
    }
    @keyframes drift {
      0%   { transform: translateX(0) scaleX(0.8); }
      50%  { transform: translateX(360%) scaleX(1.35); }
      100% { transform: translateX(0) scaleX(0.8); }
    }
    .status {
      font-size: 13px;
      color: var(--text);
      min-height: 20px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .blink::after {
      content: "_";
      animation: blink 1s steps(2, start) infinite;
      margin-left: 2px;
      color: var(--accent);
    }
    @keyframes blink { to { visibility: hidden; } }
    .hint {
      margin-top: 14px;
      color: #8ca2a8;
      font-size: 12px;
    }
  </style>
</head>
<body>
  <div class="scan"></div>
  <div class="wrap">
    <section class="panel" aria-live="polite">
      <div class="head">
        <span class="brand">KASSET BOOTLOADER</span>
        <span>local://mac-arm64</span>
      </div>
      <div class="body">
        <h1 class="title">Warming up the retro cores</h1>
        <p class="subtitle">Starting backend + frontend engines. This tab will auto-jump when ready.</p>
        <div class="bar"><div class="fill"></div></div>
        <div id="status" class="status blink">Summoning caffeinated hamsters...</div>
        <div class="hint">Tip: next launches are usually much faster after first compile/model warmup.</div>
      </div>
    </section>
  </div>

  <script>
    const statusEl = document.getElementById("status");
    const lines = [
      "Summoning caffeinated hamsters...",
      "Defragging old vibes...",
      "Aligning CRT scanlines...",
      "Polishing pixel ghosts...",
      "Untangling front-end spaghetti...",
      "Negotiating with backend goblins...",
      "Loading up tasteful nostalgia...",
      "Compiling sass into style...",
      "Asking the model nicely...",
      "Reticulating splines..."
    ];
    let i = 0;

    setInterval(() => {
      i = (i + 1) % lines.length;
      statusEl.textContent = lines[i];
    }, 1200);

    async function probe() {
      try {
        await fetch("__FRONTEND_URL__", { mode: "no-cors", cache: "no-store" });
        statusEl.textContent = "Portal stable. Jumping in...";
        setTimeout(() => { window.location.replace("__FRONTEND_URL__"); }, 250);
      } catch (_) {
        setTimeout(probe, 800);
      }
    }
    probe();
  </script>
</body>
</html>
PRELOADER_EOF

    # Inject the actual frontend URL (heredoc above uses literal strings)
    sed -i '' "s|__FRONTEND_URL__|${frontend_url}|g" "$preload_file" 2>/dev/null || \
        sed -i "s|__FRONTEND_URL__|${frontend_url}|g" "$preload_file" 2>/dev/null || true

    if command -v open &>/dev/null; then
        open "$preload_file" 2>/dev/null && PRELOADER_OPENED=true || true
    elif command -v xdg-open &>/dev/null; then
        xdg-open "$preload_file" 2>/dev/null && PRELOADER_OPENED=true || true
    fi
}

if [ "$AUTO_BROWSER" = true ]; then
    launch_preloader
fi

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
VENV_EXISTS=false
find_python() {
    # 1. Check if a valid venv already exists
    if [ -x "venv/bin/python3" ] || [ -x "venv/bin/python" ]; then
        local VENV_CMD="venv/bin/python3"
        [ ! -x "$VENV_CMD" ] && VENV_CMD="venv/bin/python"
        PY_MAJOR=$("$VENV_CMD" -c 'import sys; print(sys.version_info.major)' 2>/dev/null || echo "0")
        PY_MINOR=$("$VENV_CMD" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo "0")
        if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
            PYTHON_CMD="$VENV_CMD"
            VENV_EXISTS=true
            return 0
        fi
    fi

    # 2. Check global commands, including specific versioned ones
    for cmd in python3.12 python3.11 python3.10 python3 python; do
        if command -v "$cmd" &>/dev/null; then
            PY_MAJOR=$("$cmd" -c 'import sys; print(sys.version_info.major)' 2>/dev/null || echo "0")
            PY_MINOR=$("$cmd" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo "0")
            if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
                PYTHON_CMD="$cmd"
                return 0
            fi
        fi
    done

    # 3. Check common Homebrew installation paths explicitly (for Apple Silicon)
    for path in "/opt/homebrew/bin/python3.12" "/opt/homebrew/bin/python3.11" "/opt/homebrew/bin/python3.10" "/usr/local/bin/python3.12" "/usr/local/bin/python3"; do
        if [ -x "$path" ]; then
            PY_MAJOR=$("$path" -c 'import sys; print(sys.version_info.major)' 2>/dev/null || echo "0")
            PY_MINOR=$("$path" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo "0")
            if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
                PYTHON_CMD="$path"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON_CMD=""
if ! find_python; then
    if [ "$AUTO_INSTALL" = true ] && command -v brew &>/dev/null; then
        info "Python 3.10+ not found. Installing ${W}python@3.12${N} via Homebrew..."
        brew install python@3.12
        if ! find_python; then
            fail "Python 3.10+ discovery failed even after installation."
            ERRORS=$((ERRORS + 1))
        fi
    else
        fail "Python 3.10+ not found"
        if ! command -v brew &>/dev/null; then
            warn "Homebrew not found. Install it from https://brew.sh/"
        fi
        dim "  brew install python@3.12"
        ERRORS=$((ERRORS + 1))
    fi
fi

if [ -n "$PYTHON_CMD" ]; then
    if [ "$VENV_EXISTS" = true ]; then
        PY_VER=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
        ok "Virtual environment active ${D}(Python ${PY_VER})${N}"
    else
        PY_VER=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
        ok "Python ${W}${PY_VER}${N} found at ${D}$PYTHON_CMD${N}"
    fi
fi

# ── Check Node.js 18+ ──
check_node() {
    if ! command -v node &>/dev/null; then return 1; fi
    NODE_MAJOR=$(node -e 'console.log(process.versions.node.split(".")[0])' 2>/dev/null || echo "0")
    if [ "$NODE_MAJOR" -lt 18 ]; then return 2; fi
    return 0
}

if check_node; then
    NODE_STATUS=0
else
    NODE_STATUS=$?
fi
if [ "$NODE_STATUS" -ne 0 ]; then
    if [ "$AUTO_INSTALL" = true ] && command -v brew &>/dev/null; then
        if [ "$NODE_STATUS" -eq 1 ]; then
            info "Node.js not found. Installing ${W}node${N} via Homebrew..."
            brew install node
        else
            info "Node.js too old. Upgrading ${W}node${N} via Homebrew..."
            brew upgrade node
        fi
        if ! check_node; then
            fail "Node.js setup failed."
            ERRORS=$((ERRORS + 1))
        fi
    else
        if [ "$NODE_STATUS" -eq 1 ]; then
            fail "Node.js not found"
            dim "  brew install node"
        else
            fail "Node.js 18+ required (found $(node --version))"
            dim "  brew upgrade node"
        fi
        ERRORS=$((ERRORS + 1))
    fi
fi

if check_node; then
    ok "Node.js ${W}$(node --version | tr -d 'v')${N}"
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
free_port() {
    if lsof -i :"$1" -sTCP:LISTEN &>/dev/null; then
        local PID_LIST=$(lsof -i :"$1" -sTCP:LISTEN -t 2>/dev/null | head -3 | tr '\n' ' ')
        if [ "$KILL_PORTS" = true ]; then
            info "Killing stale processes on port $1 ${D}(PID: ${PID_LIST})${N}"
            lsof -i :"$1" -sTCP:LISTEN -t 2>/dev/null | xargs kill -9 2>/dev/null || true
            sleep 1
            if lsof -i :"$1" -sTCP:LISTEN &>/dev/null; then
                fail "Could not free port $1"
                return 1
            fi
            ok "Port $1 freed"
            return 0
        fi
        fail "Port $1 in use ${D}(PID: ${PID_LIST})${N}"
        dim "  Run with --kill-ports to auto-free, or manually:"
        dim "  lsof -i :$1 -t | xargs kill -9"
        return 1
    fi
    return 0
}
PORT_OK=true
free_port "$BACKEND_PORT" || PORT_OK=false
free_port "$FRONTEND_PORT" || PORT_OK=false
if [ "$PORT_OK" = false ]; then
    echo ""
    echo -e "  ${R}❌ Free the ports above and try again (or use --kill-ports).${N}"
    exit 1
fi
ok "Ports ${W}${BACKEND_PORT}${N}, ${W}${FRONTEND_PORT}${N} available"

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
if [ "$VENV_EXISTS" = false ]; then
    FIRST_RUN=true
    info "Creating Python virtual environment using ${D}$PYTHON_CMD${N}..."
    "$PYTHON_CMD" -m venv venv
fi
source venv/bin/activate
ok "Virtual environment synchronized"

# ── Backend dependencies ──
if [ "$FIRST_RUN" = true ] || [ "$FORCE_UPDATE" = true ]; then
    info "Installing backend dependencies ${D}(this may take a few minutes)${N}..."
    pip install --upgrade pip -q 2>&1 | tail -1
    pip install -r backend/requirements.txt -q 2>&1 | tail -1
    # Clean pip cache to reclaim disk space
    pip cache purge 2>/dev/null || true
    ok "Backend dependencies installed"
    echo ""
else
    # Verify critical imports even on subsequent runs — includes AI packages
    MISSING_DEPS=false
    python -c "import fastapi, uvicorn, mlx_vlm" 2>/dev/null || MISSING_DEPS=true
    python -c "import rembg, mediapipe, cv2, timm" 2>/dev/null || MISSING_DEPS=true
    if [ "$MISSING_DEPS" = true ]; then
        info "Missing backend packages detected — installing from requirements.txt..."
        pip install -r backend/requirements.txt -q 2>&1 | tail -1
        pip cache purge 2>/dev/null || true
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

# ── Clean stale caches ──
# Remove old __pycache__ dirs, .pyc files, and stale workspace temp files
find "$SCRIPT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$SCRIPT_DIR" -name "*.pyc" -delete 2>/dev/null || true
# Clean workspace temp images older than 7 days
find "$HOME/.kasset/workspace" -name "*.png" -mtime +7 -delete 2>/dev/null || true
find "$HOME/.kasset/workspace" -name "*.jpg" -mtime +7 -delete 2>/dev/null || true
# Clean Next.js cache if --update flag is used
if [ "$FORCE_UPDATE" = true ]; then
    rm -rf frontend/.next/cache 2>/dev/null || true
    info "Cleared frontend build cache"
fi

# ═══════════════════════════════════════════
# PROCESS MANAGEMENT
# ═══════════════════════════════════════════

BACKEND_PID=""
FRONTEND_PID=""
SIGNAL_PID=""

kill_pid() {
    local pid="$1"
    [ -z "$pid" ] && return 0
    # Try process-group kill first (captures child processes), then direct PID.
    kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
}

shutdown_processes() {
    kill_pid "$FRONTEND_PID"
    kill_pid "$SIGNAL_PID"
    kill_pid "$BACKEND_PID"
    wait 2>/dev/null || true
}

cleanup_signal() {
    echo ""
    echo -e "  ${D}Shutting down Kasset...${N}"
    shutdown_processes
    echo -e "  ${G}Done.${N} See you next time."
    exit 0
}

cleanup_exit() {
    local exit_code=$?
    # Preserve failure exit code while still cleaning spawned processes.
    if [ "$exit_code" -ne 0 ]; then
        shutdown_processes
    fi
}

trap cleanup_signal SIGINT SIGTERM
trap cleanup_exit EXIT

# ═══════════════════════════════════════════
# START BACKEND
# ═══════════════════════════════════════════

info "Starting backend ${D}(port ${BACKEND_PORT})${N}..."
python -m uvicorn backend.api:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --log-level warning &
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
    if curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/kassets" >/dev/null 2>&1; then
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

# Start signal processing subsystem (background, logs to stderr)
if [ -f "backend/core/signal_engine/logic_bridge.py" ]; then
    SIGNAL_LOG="$HOME/.kasset/cache/signal_engine.log"
    python -m backend.core.signal_engine.logic_bridge 2>"$SIGNAL_LOG" &
    SIGNAL_PID=$!
    ok "Signal engine ${D}(port 8765, log: ~/.kasset/cache/signal_engine.log)${N}"
fi

info "Starting frontend ${D}(port ${FRONTEND_PORT})${N}..."
(cd frontend && npx next dev --hostname "$FRONTEND_HOST" --port "$FRONTEND_PORT" 2>&1) &
FRONTEND_PID=$!

# Wait for frontend to be ready
echo -ne "  ${D}Waiting for frontend${N}"
for i in $(seq 1 30); do
    if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
        echo ""
        fail "Frontend crashed. Debug with:"
        dim "  cd frontend && npx next dev"
        exit 1
    fi
    if curl -sf "http://127.0.0.1:${FRONTEND_PORT}" >/dev/null 2>&1; then
        echo ""
        ok "Frontend ready"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo ""
        warn "Frontend still compiling — it may take a moment on first load"
    fi
    echo -ne "${D}.${N}"
    sleep 1
done

# ═══════════════════════════════════════════
# READY
# ═══════════════════════════════════════════

# Detect LAN IP for mobile/tablet access
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "")

echo ""
echo -e "  ${G}╔═══════════════════════════════════════╗${N}"
echo -e "  ${G}║${N}       ${W}Kasset is ready!${N}                ${G}║${N}"
echo -e "  ${G}╟───────────────────────────────────────╢${N}"
printf "  ${G}║${N}  ${C}Local:${N}   http://localhost:%-7s    ${G}║${N}\n" "$FRONTEND_PORT"
if [ -n "$LAN_IP" ]; then
printf "  ${G}║${N}  ${C}Network:${N} http://%-21s${G}║${N}\n" "$LAN_IP:$FRONTEND_PORT"
fi
printf "  ${G}║${N}  ${C}API:${N}     http://localhost:%-7s/docs${G}║${N}\n" "$BACKEND_PORT"
echo -e "  ${G}║${N}  ${C}Data:${N}    ~/.kasset/                  ${G}║${N}"
echo -e "  ${G}╟───────────────────────────────────────╢${N}"
if [ -n "$LAN_IP" ]; then
echo -e "  ${G}║${N}  ${M}📱 Open Network URL on your phone${N}    ${G}║${N}"
fi
echo -e "  ${G}║${N}  Press ${W}Ctrl+C${N} to stop                 ${G}║${N}"
echo -e "  ${G}╚═══════════════════════════════════════╝${N}"
echo ""

# Auto-open browser
if [ "$AUTO_BROWSER" = true ]; then
    sleep 1
    if [ "$PRELOADER_OPENED" = false ]; then
        if command -v open &>/dev/null; then
            open "http://localhost:${FRONTEND_PORT}" 2>/dev/null &
        elif command -v xdg-open &>/dev/null; then
            xdg-open "http://localhost:${FRONTEND_PORT}" 2>/dev/null &
        fi
    fi
fi

# Keep running until a process exits or user hits Ctrl+C
wait
