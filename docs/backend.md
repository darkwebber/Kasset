# Backend Reference

The backend is a Python FastAPI application in `backend/`. It handles model inference, agent orchestration, tool execution, and data persistence.

## Module Map

| Module | Purpose |
|--------|---------|
| `api.py` | FastAPI routes, SSE streaming, cancel registry, middleware |
| `model_server.py` | MLX model loading, prompt building, streaming inference |
| `utils.py` | Image validation helpers |
| `core/agent.py` | Multi-round agent loop, context assembly, tool dispatch |
| `core/tool_registry.py` | Tool definitions (Python sandbox, file ops, shell, web, etc.) |
| `core/tool_executor.py` | Tool execution wrapper with failure tracking and result context |
| `core/tool_parser.py` | Robust extraction of tool calls from model output (JSON + XML) |
| `core/sandbox.py` | Sandboxed Python execution with 100+ image/data/viz builtins |
| `core/cartridge_loader.py` | Loads and merges cartridge (kasset) configurations |
| `core/context_manager.py` | Context assembly, session summarization, user settings |
| `core/knowledge_graph.py` | Conversation graph for persistent context across turns |
| `core/persistence.py` | Chat storage, user memory, prompt cache (file-backed) |
| `core/draft_manager.py` | Versioned draft documents with comments and finalization |
| `core/adaptive_sampler.py` | Dynamic temperature/top_p based on task type and round |
| `core/network_auth.py` | Password auth and rate limiting for network access |
| `core/plugin_loader.py` | Loads custom tools from `~/.kasset/forge/tools/` |
| `core/input_type_loader.py` | Loads custom input widget types |
| `core/reflection.py` | Self-reflection and output quality checks |
| `core/user_profiling.py` | Detects user expertise level for tone adaptation |
| `core/inference_backend.py` | Abstract base class for model backends |
| `core/shared.py` | Shared utilities and constants |
| `core/signal_engine/` | Real-time signal processing subsystem |

## API Endpoints

### Chat

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | SSE streaming chat with tool execution |
| POST | `/api/chat/cancel` | Cancel an in-flight chat stream |

### Kassets (Cartridges)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/kassets` | List all available kassets |
| POST | `/api/kassets/load` | Load and merge a kasset stack |

### Chat History

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/chats` | List saved chats |
| GET | `/api/chats/{id}` | Load a specific chat |
| POST | `/api/chats/{id}/save` | Save/update a chat |
| DELETE | `/api/chats/{id}` | Delete a chat |

### Drafts

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/drafts` | Create a new draft |
| GET | `/api/drafts/{id}` | Get draft with all versions |
| POST | `/api/drafts/{id}/versions` | Add a new version |
| POST | `/api/drafts/{id}/comments` | Add a comment |
| POST | `/api/drafts/{id}/finalize` | Finalize and create desktop symlink |

### System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Model and system health status |
| GET | `/api/models` | List locally cached models |
| POST | `/api/models/switch` | Switch to a different model |
| POST | `/api/image/upload` | Upload an image for vision |

## Agent Tool Loop

The agent (`core/agent.py`) runs a multi-round loop:

```
for round in range(MAX_TOOL_ROUNDS):
    1. Check cancel flag
    2. Refresh system prompt with latest knowledge graph
    3. Stream model generation (yield tokens via SSE)
    4. Parse tool call from output
    5. Execute tool (sandbox, file I/O, shell, etc.)
    6. Build enriched result context
    7. Append to conversation history
    8. Loop back for next round
```

Key features:
- **Adaptive sampling**: Temperature/top_p adjust per round and task type
- **Observation masking**: Old tool results are compressed after round 2
- **Truncation recovery**: Auto-retries when model output is cut off
- **Parse retry**: Up to 2 automatic retries on malformed tool calls
- **Cancel-aware**: Checks `cancel_event` at round start and during inference
- **Thinking repetition detection**: Monitors `<think>` content during streaming; if a 150+ char block repeats 3+ times, force-breaks the generation and injects a recovery nudge so the agent refocuses instead of looping
- **Multi-turn vision**: On round 0, falls back to `_current_image_path` if no image is explicitly attached; on subsequent rounds, always passes the current working image so the VLM can see edit results
- **Tool result enrichment**: After image tool calls, injects a `[COMPLETED: ...]` summary of what was accomplished to prevent the agent from re-planning already-done steps
- **Code dedup detection**: Identical or near-identical tool calls are caught and the agent is forced to stop looping
- **Error doc auto-resolve**: On tool failure, the system checks a local cache of known error→fix mappings. On cache miss, it automatically searches the web (DuckDuckGo), extracts an actionable fix from snippets, caches it to `~/.kasset/cache/error_docs.json`, and injects the fix into the agent's context so it can self-correct without user intervention

### Error Documentation Cache

Located in `tool_parser.py`, the error doc cache provides a three-tier error resolution system:

1. **Built-in patterns** — ~40 curated error→fix entries for common libraries (plotly, matplotlib, pandas, numpy, mediapipe, opencv, PIL, rembg, scipy, seaborn, general Python)
2. **User cache** (`~/.kasset/cache/error_docs.json`) — fixes discovered via web search, persisted across sessions
3. **Auto-resolve** (`auto_resolve_error()`) — on cache miss:
   - Extracts a searchable error signature from the traceback
   - Searches the web via DuckDuckGo
   - Scores snippets by actionability (keywords like "use", "install", "replace", "instead")
   - Caches the best fix for future reuse
   - Thread-safe with dedup to avoid redundant searches

Key functions:
- `lookup_error_doc(error_text)` — check cache only (fast path)
- `auto_resolve_error(error_text, tool_name)` — full pipeline: cache → web → cache → return
- `add_error_doc(pattern, fix, lib)` — manually add entries
- `enrich_tool_error(tool_name, tool_args, error_result)` — generic error diagnosis with cache integration

## Model Server

`model_server.py` wraps MLX-VLM for both text and vision inference:

- **Text path**: Uses native chat template via `apply_chat_template()`
- **Vision path**: Prepares images (resize, EXIF rotate, cache) and builds vision prompts
- **Streaming**: `stream_generate()` yields text chunks as a generator
- **Thread safety**: `_inference_lock` prevents concurrent inference calls
- **Thinking mode**: Supports `<think>...</think>` tags for chain-of-thought

## Configuration

Environment variables:
- `MODEL_PATH` — HuggingFace model ID (default: `mlx-community/Qwen3.5-9B-MLX-4bit`)
- `KASSET_PORT` — Backend port (default: `7861`)
- `KASSET_HOST` — Bind address (default: `127.0.0.1`)
