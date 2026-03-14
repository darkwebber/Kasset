<p align="center">
  <img src="branding/logo.png" alt="Kasset" width="420" />
</p>

<h3 align="center">Local AI Studio for Mac</h3>

<p align="center">
  Modular AI agents with tool calling, code execution, image editing, and interactive widgets — running entirely on Apple Silicon. No API keys. No cloud. Just your Mac.
</p>

<p align="center">
  <code>⚠️ Alpha (v0) — Expect rough edges. Contributions welcome.</code>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> · <a href="#features">Features</a> · <a href="#kassets">Kassets</a> · <a href="#tools">Tools</a> · <a href="docs/">Documentation</a> · <a href="docs/contributing.md">Contributing</a>
</p>

---

## What is Kasset?

Kasset is a local-first AI studio that runs large language models on your Mac via [MLX](https://github.com/ml-explore/mlx). It features a **cartridge system** — swap between specialized AI agents (called *kassets*) that each bring their own tools, personality, and UI theme. Think of it as a modular AI workbench where each kasset is a purpose-built agent.

## Features

- **Kasset System** — 10 built-in agent personas (code, data, image editing, writing, 3D viz, etc.) that you can swap or stack
- **Tool Calling** — agents can run Python, C++, shell commands, read/write files, search the web, and use custom plugins
- **Sandboxed Code Execution** — Python sandbox with 100+ pre-loaded libraries (numpy, pandas, matplotlib, plotly, PIL, etc.)
- **Interactive Widgets** — agents present forms, editors, choice selectors, and diffs inline in chat for structured interaction
- **HTML Artifacts** — render interactive HTML (dashboards, mini-apps, visualizations) directly in chat with copy/download buttons
- **Image Editing** — natural-language image editing with 100+ built-in functions, live canvas with pop-out window, freeform selection, undo/redo, and before/after comparison
- **Collaborative Editing** — versioned Draft Blocks with inline commenting, diff view, and one-click finalize to desktop
- **Vision** — paste images or screenshots for the AI to analyze, describe, or edit; multi-turn vision persists across tool rounds
- **Streaming** — real-time token streaming with chain-of-thought reasoning, cooperative cancellation, and automatic thinking-loop detection
- **Kasset Forge** — create custom kassets and tools through an in-app GUI studio
- **Context Management** — knowledge graph, session memory, adaptive sampling, and automatic context trimming
- **Network Access** — optional LAN sharing with password auth and rate limiting

## Quick Start

> **Requirements:** macOS with Apple Silicon (M1+), Python 3.10+, Node.js 18+, ~16 GB RAM recommended

```bash
git clone https://github.com/darkwebber/kasset.git
cd kasset
chmod +x start.sh
./start.sh
```

`start.sh` handles everything — virtual environment, dependencies, model download, and startup. Open **http://localhost:3000** when ready.

> **First run** downloads the model (~5 GB) from Hugging Face. Subsequent starts take ~10 seconds.

Press **Ctrl+C** to stop all servers cleanly.

## Kassets

| Kasset | Icon | Purpose |
|--------|------|---------|
| General Assistant | 🤖 | All-purpose helper (all tools enabled) |
| Code Pilot | 🚀 | Pair programming, debugging, code review |
| Data Analyst | 📊 | Data analysis, statistics, visualization |
| Image Editor | 🎨 | Natural-language image editing (100+ functions) |
| Writer | ✍️ | Collaborative writing with Draft Blocks |
| 3D Visualizer | 🧊 | Interactive 3D visualizations (Plotly) |
| Terminal | 💻 | Natural language shell interface |
| Tutor | 🎓 | Adaptive teaching with interactive demos |
| Web Researcher | 🌐 | Web search and information synthesis |
| Creative Studio | 🎭 | Creative content generation |

## Tools

| Tool | Description |
|------|-------------|
| `execute_python` | Sandboxed Python with numpy, pandas, matplotlib, plotly, PIL, and more |
| `execute_cpp` | Compile and run C++ (C++17) |
| `read_file` / `write_file` / `edit_file` | File operations with smart size handling |
| `run_command` | Shell commands with consent flow and smart timeouts |
| `html_preview` | Render interactive HTML artifacts with copy/download |
| `request_user_input` | Interactive widgets (forms, editors, choices, diffs) |
| `web_search` / `web_fetch` | Web search and content extraction |
| `save_notes` | Persistent scratchpad for multi-step tasks |
| `grep_code` / `search_files` | Code search across directory trees |

## Project Structure

```
kasset/
├── backend/              # Python FastAPI backend
│   ├── api.py            # REST + SSE endpoints
│   ├── model_server.py   # MLX inference wrapper
│   └── core/             # Agent, tools, sandbox, persistence, context
├── frontend/             # Next.js React frontend
│   └── src/
│       ├── components/   # UI components (chat/, console/, image/, studio/)
│       ├── stores/       # Zustand state management
│       └── lib/          # Shared utilities
├── cartridges/           # Kasset definitions (JSON)
│   └── builtins/         # 10 built-in kassets + input types
├── tests/                # Python test suite
├── docs/                 # Comprehensive documentation
├── branding/             # Logo and favicon
└── start.sh              # One-command launcher
```

All user data lives in `~/.kasset/` (chats, memory, drafts, custom kassets, tools).

## Documentation

See the [`docs/`](docs/) directory for detailed guides:

- **[Architecture](docs/architecture.md)** — system overview, request flow, data storage
- **[Backend](docs/backend.md)** — API reference, module map, agent loop, model server
- **[Frontend](docs/frontend.md)** — component structure, stores, SSE events, theming
- **[Cartridges](docs/cartridges.md)** — kasset schema, stacking, Forge, custom tools
- **[Tools](docs/tools.md)** — tool system, sandbox, parser, custom plugins
- **[Deployment](docs/deployment.md)** — configuration, network access, troubleshooting
- **[Contributing](docs/contributing.md)** — development workflow, code style, testing

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Python/Node not found | `brew install python@3.12 node` |
| Port in use | `lsof -ti:7861 | xargs kill` |
| Model download stalled | `rm -rf ~/.cache/huggingface/hub/models--Qwen* && ./start.sh` |
| Frontend won't load | `cd frontend && rm -rf node_modules .next && npm install` |

## Status

**Alpha (v0)** — Kasset is under active development. Core features work but expect rough edges. Contributions, bug reports, and feedback are very welcome.

## License

MIT
