#!/bin/bash
set -e

# ─── Cartridge Console — One-Command Launcher ──────────────────
# Usage: ./start.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  🎮 Cartridge Console"
echo "  ══════════════════════"
echo ""

# ── Setup Python venv ──
if [ ! -d "venv" ]; then
    echo "→ Creating Python virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "→ Installing backend dependencies..."
    pip install --upgrade pip -q
    pip install -r backend/requirements.txt -q
    echo "✅ Backend setup complete!"
    echo ""
else
    source venv/bin/activate
fi

# ── Setup Next.js ──
if [ ! -d "frontend/node_modules" ]; then
    echo "→ Installing frontend dependencies..."
    cd frontend && npm install && cd ..
    echo "✅ Frontend setup complete!"
    echo ""
fi

# ── Cleanup handler ──
MODEL_PID=""
FRONTEND_PID=""
cleanup() {
    echo ""
    echo "  Shutting down..."
    if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        kill "$FRONTEND_PID" 2>/dev/null
    fi
    if [ -n "$MODEL_PID" ] && kill -0 "$MODEL_PID" 2>/dev/null; then
        kill "$MODEL_PID" 2>/dev/null
    fi
    echo "  Goodbye! 👋"
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# ── Start Backend (FastAPI + MLX) ──
echo "  Starting model server on :7861..."
python -m backend.api &
MODEL_PID=$!

# Wait for backend
echo -n "  Waiting for model server "
for i in $(seq 1 60); do
    if ! kill -0 "$MODEL_PID" 2>/dev/null; then
        echo ""
        echo "❌ Backend crashed. Check logs above."
        exit 1
    fi
    if curl -s http://127.0.0.1:7861/api/cartridges >/dev/null; then
        echo ""
        echo "  ✅ Backend ready!"
        break
    fi
    echo -n "."
    sleep 2
done

# ── Start Frontend (Next.js) ──
echo "  Starting console UI on :3000..."
cd frontend && npm run dev &
FRONTEND_PID=$!

echo ""
echo "  ════════════════════════════════════════════"
echo "  Open http://localhost:3000 in your browser"
echo "  Press Ctrl+C to stop both servers"
echo "  ════════════════════════════════════════════"
echo ""

wait
