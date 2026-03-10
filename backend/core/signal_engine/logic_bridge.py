import asyncio
import websockets
import json
import logging
import numpy as np
import os
import sys

# Configure logging for standalone execution
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger("signal_engine")

try:
    from .processor import LogicProcessor  # as backend submodule
except ImportError:
    from processor import LogicProcessor    # standalone execution

# System Initialization
ASSET_ROOT = os.path.join(os.path.dirname(__file__), "assets/engine_data.npz")
has_weights = os.path.exists(ASSET_ROOT)
logger.info(f"Weight file: {ASSET_ROOT} (exists={has_weights}, size={os.path.getsize(ASSET_ROOT) if has_weights else 0} bytes)")

try:
    proc = LogicProcessor(ASSET_ROOT if has_weights else None)
    logger.info("LogicProcessor initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize LogicProcessor: {e}")
    proc = None

async def handle_stream(ws):
    client = ws.remote_address
    logger.info(f"Client connected: {client}")
    reg = ['UP', 'DOWN', 'LEFT', 'RIGHT']
    msg_count = 0

    if proc is None:
        logger.error("LogicProcessor not available — sending fallback directions")
        async for msg in ws:
            await ws.send(json.dumps({"action": "RIGHT"}))
        return

    async for msg in ws:
        msg_count += 1
        try:
            p = json.loads(msg)
            size = p.get('grid_size', 20)
            nodes = p.get('snake', [])
            tgt = p.get('food', {'x': 15, 'y': 10})
            
            if not nodes:
                logger.debug(f"[{client}] Empty snake data, skipping")
                continue

            # Spatial Analysis
            dirs = [(0, -1), (0, 1), (1, 0), (-1, 0), (1, -1), (-1, -1), (1, 1), (-1, 1)]
            h = nodes[0]
            v = []
            
            mask = set((s['x'], s['y']) for s in nodes)
            
            for dx, dy in dirs:
                dw, df, db = 0, 0, 0
                cx, cy = h['x'], h['y']
                it = 1
                t_f, b_f = False, False
                
                while True:
                    cx += dx
                    cy += dy
                    if cx < 0 or cx >= size or cy < 0 or cy >= size:
                        dw = it / size
                        if not b_f: db = dw
                        break
                    
                    if not b_f and (cx, cy) in mask:
                        db = it / size
                        b_f = True
                        
                    if not t_f and cx == tgt['x'] and cy == tgt['y']:
                        df = 1.0
                        t_f = True
                    it += 1
                v.extend([dw, df, db])
                
            cur = 'RIGHT'
            if len(nodes) > 1:
                dx_cur = nodes[0]['x'] - nodes[1]['x']
                dy_cur = nodes[0]['y'] - nodes[1]['y']
                if dx_cur == 1: cur = 'RIGHT'
                elif dx_cur == -1: cur = 'LEFT'
                elif dy_cur == 1: cur = 'DOWN'
                elif dy_cur == -1: cur = 'UP'
                
            v.extend([cur == 'UP', cur == 'DOWN', cur == 'LEFT', cur == 'RIGHT'])
            v.extend([tgt['y'] < h['y'], tgt['y'] > h['y'], tgt['x'] < h['x'], tgt['x'] > h['x']])
            
            def _scan(sx, sy):
                if (sx < 0 or sx >= size or sy < 0 or sy >= size or (sx, sy) in mask):
                    return 0
                v_s = set([(sx, sy)])
                q_s = [(sx, sy)]
                l_s = len(nodes) + 1
                while q_s and len(v_s) < l_s:
                    nx, ny = q_s.pop(0)
                    for d_x, d_y in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        tx, ty = nx + d_x, ny + d_y
                        if (0 <= tx < size and 0 <= ty < size and (tx, ty) not in v_s and (tx, ty) not in mask):
                            v_s.add((tx, ty))
                            q_s.append((tx, ty))
                return len(v_s)
                
            sh = len(nodes)
            v.extend([1.0 if _scan(h['x'], h['y'] - 1) >= sh else 0.0,
                     1.0 if _scan(h['x'], h['y'] + 1) >= sh else 0.0,
                     1.0 if _scan(h['x'] - 1, h['y']) >= sh else 0.0,
                     1.0 if _scan(h['x'] + 1, h['y']) >= sh else 0.0])
            
            res = proc.solve(np.array(v, dtype=np.float32))
            action = reg[res]
            await ws.send(json.dumps({"action": action}))
            
            if msg_count <= 3 or msg_count % 50 == 0:
                logger.debug(f"[{client}] msg={msg_count} head=({h['x']},{h['y']}) food=({tgt['x']},{tgt['y']}) -> {action}")
            
        except json.JSONDecodeError as e:
            logger.warning(f"[{client}] Invalid JSON: {e}")
        except Exception as e:
            logger.error(f"[{client}] Error processing message {msg_count}: {e}", exc_info=True)
            try:
                await ws.send(json.dumps({"action": "RIGHT", "error": str(e)}))
            except Exception:
                pass

    logger.info(f"Client disconnected: {client} (processed {msg_count} messages)")

async def serve():
    port = int(os.environ.get("SIGNAL_PORT", 8765))
    logger.info(f"Starting signal engine on 0.0.0.0:{port}")
    try:
        async with websockets.serve(handle_stream, "0.0.0.0", port) as s:
            logger.info(f"Signal engine listening on ws://0.0.0.0:{port}")
            await asyncio.Future()
    except OSError as e:
        logger.error(f"Failed to start signal engine: {e}")
        if "Address already in use" in str(e):
            logger.error(f"Port {port} is already in use. Kill the existing process or set SIGNAL_PORT env var.")
        raise

if __name__ == "__main__":
    asyncio.run(serve())
