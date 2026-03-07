<p align="center">
  <img src="branding/logo.png" alt="Kasset" width="420" />
</p>

<p align="center">
  <strong>A local AI assistant for Mac with swappable agent kassets, tool calling, and streaming — powered by Qwen 3.5 on Apple Silicon.</strong>
</p>

<p align="center">
  Run a fully private, multimodal AI on your Mac. No cloud, no API keys, no data leaves your machine.
</p>

---

## Features

- **Kasset System** — swap between specialized agents: General Assistant, Code Pilot, Tutor, Data Analyst, Terminal, Writer, DevOps, Web Pilot
- **Kasset Forge** — create your own kassets and custom tools through an in-app GUI studio
- **Tool Plugin System** — extend the agent with custom Python tools (plotly 3D charts, audio processing, web artifacts, anything)
- **Vision** — upload images, solve problems from screenshots, describe photos
- **Streaming** — real-time token streaming with thinking/reasoning display
- **Tool Calling** — file access, shell commands, Python sandbox, web search, C++ execution, and user plugins
- **HTML Artifacts** — custom tools can return interactive HTML rendered inline (plotly, web apps, visualizations)
- **Context Management** — session summaries, per-kasset memory, global user profile
- **Inline Attachments** — attach files/directories as inline chips in your messages
- **Visualization** — matplotlib plots auto-captured, built-in `qchart_*` helpers, Mermaid diagram support
- **Persistent Memory** — learns your preferences across conversations
- **LaTeX & Code** — renders math equations and syntax-highlighted code blocks

## Quick Start

> **Requirements:** macOS with Apple Silicon (M1+), Python 3.10+, Node.js 18+, ~6GB RAM free

```bash
git clone https://github.com/darkwebber/Local-Studio.git
cd Local-Studio
chmod +x start.sh
./start.sh
```

That's it. `start.sh` handles everything:
1. Checks Python 3.10+, Node.js 18+, and port availability
2. Creates a Python virtual environment (first run only)
3. Installs all backend and frontend dependencies
4. Creates user data directories at `~/.qwen-studio/`
5. Starts the backend API server (port 7861)
6. Starts the Next.js frontend (port 3000)

Open **http://localhost:3000** and press **Ctrl+C** to stop.

> **First run?** The model (~5GB) downloads automatically from Hugging Face. Subsequent starts are much faster.

## Project Structure

```
qwen-studio/
├── backend/                    # Python FastAPI backend
│   ├── api.py                  # REST + SSE + Forge Studio API endpoints
│   ├── model_server.py         # MLX-VLM model wrapper
│   ├── utils.py                # Image validation
│   └── core/
│       ├── agent.py            # Agent orchestration & tool loop
│       ├── cartridge_loader.py # Cartridge loading, stacking & user CRUD
│       ├── context_manager.py  # Multi-layer context management
│       ├── persistence.py      # Chat storage & user memory
│       ├── plugin_loader.py    # Custom tool plugin discovery & execution
│       ├── sandbox.py          # Python execution sandbox
│       └── tool_registry.py    # Built-in tools + plugin dispatch
├── frontend/                   # Next.js React frontend
│   └── src/
│       ├── components/
│       │   ├── Console.tsx         # Main chat UI
│       │   ├── CartridgeCarousel.tsx # Cartridge selector
│       │   ├── ChatDrawer.tsx      # Chat history
│       │   ├── Tutorial.tsx        # Onboarding guide
│       │   └── studio/
│       │       └── ForgeStudio.tsx  # Cartridge & tool creator GUI
│       └── stores/             # Zustand state (cartridges, chats, settings)
├── cartridges/
│   ├── builtins/               # Built-in cartridge definitions (JSON)
│   └── schema.json             # Cartridge schema specification
├── start.sh                    # One-command launcher
└── README.md
```

## User Data

All user-generated data is stored at `~/.qwen-studio/` (never in the repo):

```
~/.qwen-studio/
├── cartridges/                 # User-created cartridges (JSON)
├── tools/                      # User-created tool plugins
│   └── <tool-id>/
│       ├── manifest.json       # Tool metadata & parameter schema
│       └── handler.py          # Python implementation
├── chats/                      # Saved conversations
├── context/
│   ├── global_profile.json     # App-wide user understanding
│   └── cartridges/             # Per-cartridge context
├── cache/                      # Summary cache
├── uploads/                    # Pasted/uploaded files
├── user_memory.json            # Learned user preferences
└── settings.json               # User toggles
```

## Kasset Forge

Open **Kasset Forge** from the kasset carousel or the wrench icon in the Console top bar.

### Creating a Kasset

1. Go to **Kassets** tab → **New Kasset**
2. Fill in name, description, system prompt, and select tools
3. Customize theme colors and boot animation
4. Click **Save** — your kasset appears in the carousel immediately

### Creating a Custom Tool

1. Go to **Tools** tab → **New Tool**
2. Define the tool name, description (what the model sees), and parameters
3. Choose output type: `text`, `html`, `image`, or `mixed`
4. Write the handler function in Python
5. Click **Test** to verify, then **Save**

The tool is instantly available to assign to any kasset.

## Tool Plugin Standard

Each custom tool lives in `~/.qwen-studio/tools/<tool-id>/` with two files:

### `manifest.json`

```json
{
  "id": "plotly_3d",
  "name": "Plotly 3D Chart",
  "version": "1.0.0",
  "description": "Create interactive 3D visualizations using Plotly",
  "author": "user",
  "icon": "cube",
  "color": "#636efa",
  "parameters": {
    "code": {
      "type": "string",
      "description": "Python code using plotly to create 3D visualizations",
      "required": true
    }
  },
  "output_type": "html",
  "handler": "handler.py",
  "entry_point": "execute",
  "sandbox": {
    "timeout": 30,
    "imports": ["plotly"],
    "pre_run": "import plotly.graph_objects as go"
  }
}
```

### `handler.py`

```python
def execute(code: str) -> dict:
    """Entry point called by the agent. Return types:
        str  -> displayed as text
        dict -> { "output": str, "images": [base64], "html": str }
    """
    import plotly.graph_objects as go
    # ... execute user code, capture figure ...
    return {
        "output": "3D chart created",
        "html": fig.to_html(include_plotlyjs=True)
    }
```

### Output Types

| Type | Return | Frontend Rendering |
|------|--------|--------------------|
| `text` | `str` | Plain text in tool result |
| `html` | `dict` with `html` key | Sandboxed iframe artifact |
| `image` | `dict` with `images` key (base64) | Inline images |
| `mixed` | `dict` with any combination | All applicable renderers |

### Example Use Cases

- **3D Visualization Bot** — plotly tool returning interactive HTML
- **Music Bot** — waveform visualization tool with audio playback HTML
- **Web Dev Bot** — tool that renders HTML/CSS/JS artifacts inline
- **API Integration** — tool that calls external APIs and returns structured data
- **File Converter** — tool that transforms file formats

None of these require changing the plugin standard — just a new `manifest.json` + `handler.py`.

## Built-in Kassets

| Kasset | Icon | Purpose |
|-----------|------|---------|
| General Assistant | 🤖 | Default all-purpose helper |
| Code Pilot | 🚀 | Pair programming, debugging, code review |
| Tutor | 🎓 | Teaching with examples and analogies |
| Data Analyst | 📊 | Data analysis, statistics, visualization |
| Terminal | 💻 | Natural language shell interface |
| Writer | ✍️ | Creative and technical writing |
| DevOps | 🔧 | Git, Docker, CI/CD, infrastructure |
| Web Pilot | 🌐 | Web research and information synthesis |

## Built-in Tools

| Tool | Description |
|------|-------------|
| `get_current_time` | Current date and time |
| `list_directory` | Browse files with sizes |
| `get_system_info` | OS, hardware, disk, uptime |
| `search_files` | Glob-based recursive file search |
| `read_file` | Read text files (up to 50KB) |
| `run_command` | Shell commands with consent flow for write operations |
| `calculate` | Safe math evaluator (sqrt, trig, factorial, etc.) |
| `execute_python` | Stateful Python sandbox with pandas, numpy, matplotlib, scipy, seaborn |
| `execute_cpp` | Compile and run C++ code (C++17) |
| `search_web` | DuckDuckGo web search |
| `read_url` | Fetch and extract text from web pages |

## Context Management

Three layers of context, each toggleable in the **Context** tab:

- **Session Summary** — when conversations get long, older messages are intelligently summarized to free context space
- **Kasset Context** — remembers topics and patterns from previous chats with the same kasset
- **Global Profile** — app-wide understanding of you across all kassets (usage patterns, languages, preferences)

## Architecture

```
┌──────────────────────────┐        ┌──────────────────────────┐
│  Next.js Frontend (:3000) │───────▶│  FastAPI Backend (:7861)  │
│  React + Zustand          │◀──SSE──│  Agent + Tool Loop        │
│  KassetCarousel           │        │  MLX-VLM Inference        │
│  Console (chat UI)        │        │  Built-in Tools           │
│  ForgeStudio (creator)    │        │  Plugin Loader            │
│  ChatDrawer (history)     │        │  Python Sandbox           │
└──────────────────────────┘        │  Context Manager          │
                                    └──────────────────────────┘
                                               │
                                      ~/.qwen-studio/
                                      ├── cartridges/   (user)
                                      ├── tools/        (plugins)
                                      ├── chats/
                                      └── memory, context, settings
```

## Security Model

- **Blocklist + Consent** — destructive commands (`rm`, `sudo`, `kill`) are blocked; write operations (`mkdir`, `cp`, `git commit`, `pip install`) require user approval via an in-chat consent UI
- **Shell chaining** — `&&`, `;`, `||` supported; each sub-command validated individually
- **Pipes** — `cmd1 | cmd2 | cmd3` supported; each stage validated
- **Path sandboxing** — file access restricted to home directory and temp folders
- **Timeouts** — all commands have a 30-second timeout
- **Output limits** — command output capped at 8000 characters
- **Plugin isolation** — custom tool handlers run with stdout capture; errors are caught and reported

## Forge Studio API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/forge/tools` | GET | List all tools (builtin + user) |
| `/api/forge/tools/{id}` | GET | Get tool manifest + handler code |
| `/api/forge/tools` | POST | Create/update a tool plugin |
| `/api/forge/tools/{id}` | DELETE | Delete a user tool |
| `/api/forge/tools/test` | POST | Test-execute a tool |
| `/api/forge/cartridges/{id}` | GET | Get kasset JSON for editing |
| `/api/forge/cartridges` | POST | Create/update a user kasset |
| `/api/forge/cartridges/{id}` | DELETE | Delete a user kasset |
| `/api/forge/all-tool-ids` | GET | All tool IDs for kasset editor |
| `/api/forge/tool-meta` | GET | Frontend rendering metadata |

## Troubleshooting

**`start.sh` says Python not found?**
```bash
brew install python@3.12
```

**`start.sh` says Node.js not found?**
```bash
brew install node
```

**Port in use?**
```bash
lsof -i :7861 -i :3000
kill -9 <PID>
```

**Backend crashes on start?**
```bash
# Check with verbose logging:
source venv/bin/activate
python -m uvicorn backend.api:app --log-level debug
```

## License

MIT. Use it however you like.
