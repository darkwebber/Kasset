# Contributing to Kasset

Kasset is an open-source project in alpha stage. Contributions are welcome!

## Getting Started

1. **Fork and clone** the repository
2. **Run `./start.sh`** — it handles venv creation, dependency installation, and startup
3. Make your changes
4. Test with `pytest` (from the repo root)
5. Submit a PR

## Project Structure

```
kasset/
├── backend/           # Python FastAPI backend
│   ├── api.py         # REST + SSE endpoints
│   ├── model_server.py # MLX inference wrapper
│   └── core/          # Agent, tools, persistence, context
├── frontend/          # Next.js React frontend
│   └── src/
│       ├── components/ # UI components
│       ├── stores/     # Zustand state stores
│       └── lib/        # Shared utilities
├── cartridges/        # Kasset definitions
│   └── builtins/      # Built-in kassets + input types
├── tests/             # Python test suite
├── docs/              # Documentation (you are here)
├── branding/          # Logo and favicon
└── start.sh           # One-command startup script
```

## Development Workflow

### Backend
- Backend runs on port `7861` by default
- Hot-reload is **not** automatic; restart the backend after Python changes
- The backend uses `uvicorn` with the FastAPI app at `backend.api:app`

### Frontend
- Frontend runs on port `3000` with Next.js hot-reload
- Uses TailwindCSS for styling — follow existing patterns
- State lives in Zustand stores (`frontend/src/stores/`)

### Adding a New Tool

1. Define the tool function in `backend/core/tool_registry.py`
2. Add it to the `TOOL_DEFINITIONS` dict with name, description, and parameter schema
3. Register it in the `execute_tool()` dispatcher
4. Add the tool ID to relevant kasset JSON files in `cartridges/builtins/`

### Adding a New Kasset

1. Create a JSON file in `cartridges/builtins/` following the schema in `cartridges/schema.json`
2. Define at minimum: `id`, `name`, `system_prompt`, `tools`
3. The kasset appears automatically in the carousel

### Adding a Frontend Component

1. Place it in the appropriate subdirectory under `frontend/src/components/`
2. Use TypeScript and follow existing naming conventions
3. Use CSS variables (`var(--accent)`, `var(--glow)`) for theme-aware styling

## Code Style

### Python
- Follow PEP 8 with 120-char line limit
- Use type hints for function signatures
- Use `logger` (module-level) instead of `print()`
- Keep imports organized: stdlib → third-party → local

### TypeScript/React
- Functional components with hooks
- Zustand for shared state (no prop drilling)
- TailwindCSS utility classes (no CSS modules)
- `"use client"` directive where needed

## Testing

```bash
# Run all tests
pytest

# Run a specific test file
pytest tests/test_agent_logic.py

# Run with verbose output
pytest -v
```

Tests are in `tests/` and use `pytest` with fixtures from `conftest.py`.

## Common Pitfalls

- **Don't hardcode colors** — use `var(--accent)` and `var(--glow)` CSS variables
- **Don't use `cd` in shell commands** — use `cwd` parameter instead
- **Don't modify sandbox globals directly** — use the session-scoped `get_session()` API
- **Don't store user data in the repo** — everything goes to `~/.kasset/`
- **Always check `cancel_event`** in long-running agent operations
- **BroadcastChannel sync** — when updating Zustand state from a remote message, set a `remoteUpdate` guard flag to prevent the subscribe callback from echoing the change back (creates infinite feedback loops, especially with zoom/pan)
- **Don't remove `parse_thinking()`** — the `thought, text = parse_thinking(accumulated)` call after the streaming loop is critical; `text` and `thought` are used by all downstream processing (tool parsing, truncation detection, final answer cleanup)
- **Agent thinking loops** — the model can get stuck repeating the same paragraph in `<think>` blocks; the repetition detector in `agent.py` handles this, but always test multi-turn conversations after changes to the generation loop
- **Error doc cache** — when adding support for a new library, add built-in error patterns to `_BUILTIN_ERROR_DOCS` in `tool_parser.py`; the auto-resolve web search is a fallback, not a replacement for known common errors. User-discovered fixes persist in `~/.kasset/cache/error_docs.json` — delete this file to reset learned fixes
- **Auto-resolve thread safety** — `auto_resolve_error()` uses a lock and dedup set; never call it from within another lock to avoid deadlocks

## Reporting Issues

Please include:
- macOS version and chip (M1/M2/M3/M4)
- Model being used
- Steps to reproduce
- Console logs (browser + terminal)
- Screenshot/Link to short video if its a UI/UX issue.
