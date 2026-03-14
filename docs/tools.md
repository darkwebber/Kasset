# Tool System

Kasset's tool system enables agents to execute actions beyond text generation — running code, manipulating files, searching the web, and interacting with users through widgets.

## How Tools Work

1. The agent's system prompt includes tool definitions (name, description, parameters)
2. During generation, the model outputs a tool call in XML or JSON format
3. `tool_parser.py` extracts and validates the call
4. `tool_executor.py` dispatches to `tool_registry.py` which executes it
5. The result is fed back into the conversation for the next round

## Built-in Tools

### Code Execution

| Tool | Description |
|------|-------------|
| `execute_python` | Runs Python in a sandboxed environment with 100+ pre-loaded libraries (numpy, pandas, matplotlib, plotly, PIL, etc.). Variables persist across calls within a session. |
| `execute_cpp` | Compiles and runs C++ code via `clang++`. |

### File Operations

| Tool | Description |
|------|-------------|
| `read_file` | Read file contents with optional line range |
| `write_file` | Create or overwrite a file |
| `edit_file` | Apply targeted find-and-replace edits |
| `list_directory` | List directory contents with metadata |
| `search_files` | Find files by name pattern (glob) |
| `grep_code` | Search file contents with regex |

### Shell

| Tool | Description |
|------|-------------|
| `run_command` | Execute shell commands. Requires user consent for safety. |

### Web

| Tool | Description |
|------|-------------|
| `web_search` | Search the web via DuckDuckGo |
| `web_fetch` | Fetch and extract content from a URL |

### Visualization

| Tool | Description |
|------|-------------|
| `html_preview` | Render interactive HTML in a sandboxed iframe. Used for dashboards, demos, widgets. Includes copy/download buttons. |

### Interactive

| Tool | Description |
|------|-------------|
| `request_user_input` | Show interactive widgets — forms, editors, choices, embeds, diffs. Supports persistent widgets that update across turns. |

### Utility

| Tool | Description |
|------|-------------|
| `save_notes` | Persist working notes for multi-turn continuity |
| `get_weather` | Get current weather data |
| `get_location` | Get approximate location via IP |

## Sandbox (execute_python)

The Python sandbox (`core/sandbox.py`) provides a rich execution environment:

### Pre-loaded Libraries
`numpy`, `pandas`, `matplotlib`, `plotly`, `PIL/Pillow`, `scipy`, `sympy`, `json`, `re`, `math`, `datetime`, `collections`, `itertools`, `functools`, `textwrap`, `pathlib`, `csv`, `io`, `base64`

### Image Editing Functions (100+)
When the `image-editor` kasset is active, these are available:
- **Basic**: `img_load`, `img_save`, `img_show`, `img_resize`, `img_crop`, `img_rotate`
- **Adjustments**: `img_brightness`, `img_contrast`, `img_saturation`, `img_hue`, `img_gamma`
- **Filters**: `img_blur`, `img_sharpen`, `img_edge_detect`, `img_emboss`, `img_denoise`
- **Drawing**: `img_draw_rect`, `img_draw_circle`, `img_draw_line`, `img_draw_text`
- **Advanced**: `img_remove_bg`, `img_face_detect`, `img_depth_map`, `img_inpaint`
- **Batch**: `batch_load`, `batch_apply`, `batch_save`, `batch_resize`

### Security
- No `os.system`, `subprocess`, `exec`, `eval`, `__import__` in user-facing context
- File I/O restricted to `~/.kasset/` and explicitly allowed paths
- Network access restricted to specific safe APIs
- Shell commands require explicit user consent

## Tool Parser

`tool_parser.py` handles multiple output formats robustly:

1. **Qwen3-Coder XML**: `<tool_call><function=name><parameter=key>value</parameter></function></tool_call>`
2. **JSON in XML**: `<tool_call>{"name": "...", "arguments": {...}}</tool_call>`
3. **Raw JSON**: `{"name": "...", "arguments": {...}}`
4. **Fallback extraction**: Direct string scanning for large content (write_file, html_preview)

Auto-retry: If parsing fails, the agent gets diagnostic feedback and retries up to 2 times.

### Error Documentation Cache

`tool_parser.py` also manages a three-tier error resolution system:

1. **Built-in patterns** (~40 entries) — curated error→fix mappings for plotly, matplotlib, pandas, numpy, mediapipe, opencv, PIL, rembg, scipy, seaborn, and general Python errors
2. **Persistent user cache** (`~/.kasset/cache/error_docs.json`) — fixes discovered via web search, persisted across sessions and app restarts
3. **Auto-resolve** (`auto_resolve_error()`) — on cache miss, extracts the error signature, searches the web via DuckDuckGo, scores snippets by actionability, caches the best fix, and returns it for injection into the agent's context

This means the agent learns from errors over time — a fix discovered once is instantly available for all future sessions.

## Tool Executor

`tool_executor.py` wraps execution with:
- **Failure tracking**: Counts consecutive failures, forces stop after 3
- **Loop detection**: Detects repeated identical failing calls
- **Error auto-resolve**: On failure, calls `auto_resolve_error()` which checks the local cache first, then searches the web for a fix if needed, caches the result, and injects it alongside generic hints
- **Error enrichment**: Provides specific fix suggestions from built-in heuristics (`enrich_tool_error()`)
- **Result context**: Builds informative context strings for the agent's next round
- **Stop signals**: For HTML artifacts and images, appends strong "task complete" signals

## Custom Tools (Plugin System)

Create custom tools in `~/.kasset/forge/tools/`:

```python
# ~/.kasset/forge/tools/my_tool.py
"""
tool_name: my_custom_tool
tool_description: Does something useful
tool_parameters:
  input:
    type: string
    description: The input to process
    required: true
"""

def execute(input: str) -> str:
    return f"Processed: {input}"
```

The `PluginLoader` auto-discovers and registers these at startup.
