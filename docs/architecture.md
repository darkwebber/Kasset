# Architecture Overview

Kasset is a local-first AI studio built around **cartridge-based agents** that run entirely on your machine using Apple Silicon (MLX). It pairs a Python/FastAPI backend with a Next.js React frontend, communicating via SSE (Server-Sent Events) for real-time streaming.

## High-Level Diagram

```
┌──────────────────────────────────────────────────┐
│                  Frontend (Next.js)               │
│  ┌────────────┐ ┌──────────┐ ┌────────────────┐  │
│  │  Console    │ │  Stores  │ │  Components    │  │
│  │  (SSE ↔ BE)│ │ (Zustand)│ │  chat/ image/  │  │
│  └────────────┘ └──────────┘ └────────────────┘  │
└────────────────────┬─────────────────────────────┘
                     │ HTTP + SSE (port 3000 → 7861)
┌────────────────────▼─────────────────────────────┐
│                  Backend (FastAPI)                 │
│  ┌────────┐ ┌───────────┐ ┌────────────────────┐ │
│  │  API   │ │   Agent   │ │  Model Server      │ │
│  │ (api.py│ │ (agent.py)│ │  (model_server.py) │ │
│  └────────┘ └───────────┘ └────────────────────┘ │
│  ┌──────────────────────────────────────────────┐ │
│  │              Core Modules                     │ │
│  │  cartridge_loader · tool_registry · sandbox   │ │
│  │  tool_parser · tool_executor · persistence    │ │
│  │  context_manager · knowledge_graph            │ │
│  └──────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │   MLX Runtime (Apple Silicon) │
        │   Qwen3.5 / Vision models     │
        └───────────────────────────────┘
```

## Request Flow

1. **User sends a message** → Frontend POSTs to `/api/chat` with message history, cartridge IDs, and optional image path.
2. **API layer** creates an `Agent` instance with the merged cartridge config, registers a cancel event, and returns a `StreamingResponse`.
3. **Agent.chat_stream()** builds the system prompt (cartridge prompt + tools + context), then enters a multi-round tool loop:
   - Calls `ModelClient.stream_generate()` which yields tokens from MLX inference.
   - Parses the generation for tool calls via `tool_parser`.
   - Executes tools via `ToolExecutor` → `tool_registry` (sandboxed Python, file ops, shell, etc.).
   - Builds enriched context from tool results and loops for the next round.
   - Yields SSE events (`token`, `think_token`, `think_end`, `tool_call`, `tool_result`, `interactive`, `done`) throughout.
4. **Frontend** processes SSE events in `Console.tsx`, building up `Segment[]` arrays that render as `ThinkingBlock`, `ToolCallCard`, `InteractiveWidget`, and markdown text.

## Cancellation

- Frontend calls `/api/chat/cancel` with the `chat_id`.
- Backend sets a `threading.Event` that the agent checks at the top of each tool round and inside the token streaming loop.
- On client disconnect (`GeneratorExit`), the cancel event is also set automatically.

## Data Storage

All user data lives in `~/.kasset/`:

| Directory | Purpose |
|-----------|---------|
| `~/.kasset/chats/` | Chat history (JSON) |
| `~/.kasset/memory/` | User memory store |
| `~/.kasset/drafts/` | Draft documents (versioned) |
| `~/.kasset/finalized/` | Finalized drafts + desktop symlinks |
| `~/.kasset/forge/` | Custom kassets and tools |
| `~/.kasset/cache/` | Prompt cache, preloader HTML |
| `~/.kasset/cache/error_docs.json` | Auto-learned error→fix mappings (web-resolved, persisted across sessions) |
| `~/.kasset/settings.json` | User preferences |

## Key Design Decisions

- **Local-first**: No cloud dependencies. Model runs on-device via MLX.
- **Cartridge system**: Modular agent personas with stackable configs.
- **Sandboxed execution**: Python code runs in a restricted sandbox with curated builtins.
- **SSE streaming**: Real-time token delivery without WebSocket complexity.
- **Cooperative cancellation**: Thread events enable clean termination of inference and tool loops.
- **Error auto-resolve**: On code errors, the system checks a local cache of known fixes, falls back to web search if needed, and caches discovered fixes for future sessions.
