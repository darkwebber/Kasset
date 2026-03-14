# Deployment & Configuration

Kasset runs entirely on your local machine. There is no cloud component.

## Requirements

- **macOS** with Apple Silicon (M1/M2/M3/M4)
- **Python 3.10+**
- **Node.js 18+** and npm
- **~6GB disk space** for the default model (Qwen3.5-9B-MLX-4bit)
- **16GB+ RAM** recommended (8GB minimum with smaller models)

## Quick Start

```bash
git clone https://github.com/your-org/kasset.git
cd kasset
chmod +x start.sh
./start.sh
```

`start.sh` handles everything:
1. Creates a Python virtual environment in `backend/venv/`
2. Installs Python dependencies from `backend/requirements.txt`
3. Installs frontend npm packages
4. Starts the backend on port `7861`
5. Starts the frontend on port `3000`
6. Opens `http://localhost:3000` in your browser

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_PATH` | `mlx-community/Qwen3.5-9B-MLX-4bit` | HuggingFace model ID |
| `KASSET_PORT` | `7861` | Backend API port |
| `KASSET_HOST` | `127.0.0.1` | Backend bind address |
| `KASSET_FRONTEND_PORT` | `3000` | Frontend dev server port |

### Switching Models

You can switch models at runtime via:
- The Quick Settings panel (gear icon in the UI)
- The API: `POST /api/models/switch { "model_path": "mlx-community/..." }`

Models are downloaded from HuggingFace on first use and cached in `~/.cache/huggingface/`.

### Network Access

By default, Kasset only listens on `localhost`. To enable LAN access:

```bash
KASSET_HOST=0.0.0.0 ./start.sh
```

When network access is enabled:
- A password is required (set on first network connection)
- Dangerous operations (shell, forge) are blocked for remote clients
- Rate limiting is enforced for chat endpoints

## Process Management

`start.sh` manages three processes:
- **Backend**: FastAPI/uvicorn server
- **Frontend**: Next.js dev server
- **Signal Engine**: Real-time signal processor (optional)

All processes are cleaned up on Ctrl+C via signal traps (`SIGINT`, `SIGTERM`, `EXIT`).

### Manual Startup

If you prefer manual control:

```bash
# Terminal 1: Backend
cd backend
source venv/bin/activate
uvicorn backend.api:app --host 127.0.0.1 --port 7861

# Terminal 2: Frontend
cd frontend
npm run dev
```

## User Data

All user data is stored in `~/.kasset/` (outside the repo):

```
~/.kasset/
├── chats/          # Saved conversations
├── memory/         # User memory store
├── drafts/         # Work-in-progress documents
├── finalized/      # Completed documents
├── forge/          # Custom kassets, tools, input types
│   ├── kassets/
│   ├── tools/
│   └── input_types/
├── cache/          # Prompt cache, error patterns
└── settings.json   # User preferences
```

## Troubleshooting

### Model won't load
- Ensure you have enough RAM (16GB+ for 9B models)
- Check `~/.cache/huggingface/` for corrupted downloads
- Try a smaller model: `MODEL_PATH=mlx-community/Qwen2.5-3B-Instruct-4bit`

### Port already in use
- `start.sh` auto-detects port conflicts and offers to kill existing processes
- Manually: `lsof -ti:7861 | xargs kill` or `lsof -ti:3000 | xargs kill`

### Frontend can't reach backend
- Ensure backend is running on the expected port
- Check browser console for CORS errors
- Verify `NEXT_PUBLIC_API_URL` in frontend config if customized

### Slow inference
- Close other heavy applications to free memory
- Use a smaller quantized model (4-bit recommended)
- Reduce `suggested_tokens` in kasset config
