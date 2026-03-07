# Cartridge — Single-Binary Distribution Plan

## Goal
Package Cartridge into a single distributable artifact so non-technical users can install and run it with no terminal, no `pip install`, no `npm install`.

---

## Constraints

| Factor | Detail |
|--------|--------|
| **Platform** | macOS only (MLX requires Apple Silicon) |
| **Python deps** | ~800MB installed (torch, torchvision, mlx-vlm, scipy, pandas, etc.) |
| **Node.js** | Only needed at build time if frontend is pre-built |
| **ML model** | 5–10 GB (Qwen3.5-9B-4bit) — too large to bundle, must download on first launch |
| **User data** | `~/.qwen-studio/` (chats, memory, uploads, tools) |

---

## Recommended Architecture: macOS .app Bundle

### Overview

```
Qwen Studio.app/
├── Contents/
│   ├── Info.plist
│   ├── MacOS/
│   │   └── qwen-studio          # Main launcher (shell or compiled)
│   ├── Resources/
│   │   ├── icon.icns
│   │   ├── backend/             # Frozen Python backend (PyInstaller onedir)
│   │   │   ├── qwen-backend     # PyInstaller executable
│   │   │   └── _internal/       # Bundled Python + packages
│   │   ├── frontend/            # Static Next.js export (HTML/JS/CSS)
│   │   └── cartridges/          # Built-in cartridge JSONs
│   └── Frameworks/              # (empty — all deps in _internal)
```

### Step-by-step approach

#### Phase 1: Eliminate Node.js runtime dependency

Convert the frontend from `next dev` (requires Node.js) to a **static export** served directly by FastAPI.

1. Set `output: 'export'` in `next.config.ts` to produce static HTML/JS/CSS
2. Run `next build` at build time → produces `frontend/out/` directory
3. Add a FastAPI static file mount:
   ```python
   from fastapi.staticfiles import StaticFiles
   app.mount("/", StaticFiles(directory="frontend_dist", html=True), name="frontend")
   ```
4. Both backend API and frontend are now served from port 7861 — **no Node.js needed at runtime**

**Blocker to investigate**: `next export` doesn't support some features (API routes, middleware, SSR). Console.tsx is already fully client-side, so this should work. The only server-side thing is `allowedDevOrigins` (dev-only, not needed in production).

#### Phase 2: Bundle Python backend with PyInstaller

1. Create a `pyinstaller.spec` file:
   ```
   Entry point: backend/__main__.py (new file that runs uvicorn)
   Hidden imports: mlx, mlx_vlm, torch, torchvision, PIL, etc.
   Data files: cartridges/builtins/*.json, frontend_dist/
   Mode: onedir (not onefile — faster startup, easier debugging)
   ```

2. The `__main__.py` entry point:
   ```python
   import uvicorn
   import sys, os
   
   # Set up paths for bundled resources
   if getattr(sys, 'frozen', False):
       bundle_dir = sys._MEIPASS
       os.environ['QWEN_BUNDLE_DIR'] = bundle_dir
   
   from backend.api import app
   uvicorn.run(app, host="0.0.0.0", port=7861)
   ```

3. Key PyInstaller challenges:
   - **torch** (~2GB): Use `--collect-all torch` and `--collect-all torchvision`
   - **mlx/mlx_vlm**: Must collect `.metallib` files for GPU kernels
   - **numpy/scipy**: Binary wheels with C extensions — usually work fine
   - **Total bundle size**: ~1.5–2.5 GB compressed

#### Phase 3: First-launch model downloader

Since the ML model is 5–10 GB, it cannot be bundled. On first launch:

1. Check if model exists in `~/.qwen-studio/models/`
2. If not, show a download progress screen (can be a simple HTML page served by the backend)
3. Download from Hugging Face Hub using `huggingface_hub.snapshot_download()`
4. Cache in `~/.qwen-studio/models/` (survives app updates)

#### Phase 4: macOS .app wrapper + DMG

1. **Launcher script** (`Contents/MacOS/qwen-studio`):
   ```bash
   #!/bin/bash
   DIR="$(cd "$(dirname "$0")/../Resources" && pwd)"
   export QWEN_FRONTEND_DIR="$DIR/frontend"
   export QWEN_CARTRIDGES_DIR="$DIR/cartridges"
   
   # Start backend
   "$DIR/backend/qwen-backend" &
   BACKEND_PID=$!
   
   # Wait for backend, then open browser
   sleep 2
   open "http://localhost:7861"
   
   # Keep alive until backend exits
   wait $BACKEND_PID
   ```

2. **DMG creation**: Use `create-dmg` or `hdiutil` to produce a drag-and-drop installer:
   ```
   ┌─────────────────────────────┐
   │  🎮 Qwen Studio             │
   │                             │
   │   [App Icon] → [Applications]│
   │                             │
   └─────────────────────────────┘
   ```

3. **Code signing** (optional but recommended):
   - Sign with Apple Developer certificate to avoid Gatekeeper warnings
   - Without signing: users must right-click → Open on first launch

---

## Alternative: Homebrew Cask (simpler, less self-contained)

If a true .app bundle proves too complex due to PyInstaller + torch issues:

```ruby
cask "qwen-studio" do
  version "1.0.0"
  url "https://github.com/user/qwen-studio/releases/download/v1.0.0/qwen-studio-1.0.0.tar.gz"
  
  depends_on formula: "python@3.12"
  depends_on formula: "node"
  
  postflight do
    system "#{staged_path}/setup.sh"
  end
end
```

This is easier to maintain but requires Homebrew.

---

## Build Pipeline

```
1. npm run build          # Static frontend export → frontend/out/
2. cp -r frontend/out backend/frontend_dist/
3. pyinstaller qwen-studio.spec   # Bundle Python + deps
4. create-dmg ...         # Package as .dmg
```

Estimated build time: ~10 minutes
Estimated .dmg size: ~1.5–2 GB (compressed)
First-launch model download: ~5–10 GB additional

---

## Milestones

| # | Milestone | Effort |
|---|-----------|--------|
| 1 | Static frontend export + FastAPI serving | 2–4 hours |
| 2 | PyInstaller spec + hidden imports resolution | 4–8 hours |
| 3 | First-launch model downloader UI | 2–3 hours |
| 4 | macOS .app wrapper + launcher script | 1–2 hours |
| 5 | DMG packaging + icons | 1–2 hours |
| 6 | Testing on clean macOS install | 2–4 hours |
| **Total** | | **12–23 hours** |

---

## Risk Mitigation

- **PyInstaller + torch fails**: Fall back to embedding a minimal Python via `python-build-standalone` (prebuilt Python binaries from Gregory Szorc) + `pip install` into an embedded site-packages
- **Static export breaks Next.js features**: All current features are client-side rendered, so this should be safe. If issues arise, use `next build` + `next start` with an embedded Node.js binary (~40MB)
- **Code signing costs $99/year**: Can ship unsigned initially; users right-click → Open once
- **App size too large**: Strip debug symbols from torch (`--strip`), exclude unused torch backends (CUDA, ROCm — only need CPU/MPS)
