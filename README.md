# Qwen Studio

**A local AI assistant for Mac with vision, tool calling, and streaming — powered by Qwen 3.5 on Apple Silicon.**

Run a fully private, multimodal AI chat on your Mac. No cloud, no API keys, no data leaves your machine.

## Features

- **Vision** — upload images, solve problems from screenshots, describe photos
- **Streaming** — tokens appear as they generate (real-time thinking display)
- **Tool Calling** — manage files, check system info, search, run safe shell commands via natural language
- **Chain-of-Thought** — toggle reasoning mode for complex problems
- **LaTeX & Code** — renders math and syntax-highlighted code blocks
- **Secure** — all tools are read-only with whitelisted commands, path validation, and timeouts

## Quick Start

> **Requirements:** macOS with Apple Silicon (M1/M2/M3/M4), Python 3.10+, ~6GB RAM free

### One-command setup

```bash
git clone https://github.com/YOUR_USERNAME/qwen-studio.git
cd qwen-studio
chmod +x setup.sh && ./setup.sh
```

### Start

```bash
# Terminal 1 — model server (loads the model, takes ~30s first time)
source venv/bin/activate
python model_server.py

# Terminal 2 — web UI
source venv/bin/activate
python app.py
```

Open **http://localhost:7860** in your browser.

> **First run?** The model (~5GB) downloads automatically from Hugging Face on first launch.

## Built-in Tools

The assistant can use these tools when you ask it to interact with your system:

| Tool | What it does | Example prompt |
|------|-------------|----------------|
| `get_current_time` | Current date & time | *"What time is it?"* |
| `list_directory` | Browse files with sizes | *"Show me what's in my Downloads folder"* |
| `get_system_info` | OS, disk, uptime | *"How much disk space do I have?"* |
| `search_files` | Find files by pattern | *"Find all .py files in my projects"* |
| `read_file` | Read text files | *"Show me the contents of ~/.zshrc"* |
| `run_command` | Shell commands with pipes | *"What's the largest folder in my home dir?"* |
| `calculate` | Safe math evaluator | *"What's sqrt(144) + 3^4?"* |

The model **automatically chains** multiple tool calls to complete complex tasks — no need to say "continue".

### Security Model

- **Command whitelist** — only read-only commands allowed (`ls`, `ps`, `df`, `du`, `grep`, `sort`, `cat`, `curl`, etc.)
- **Safe pipes** — pipe chains like `du -h | sort -rh | head` are supported (each stage validated)
- **No destructive ops** — `rm`, `sudo`, `kill`, `shutdown`, `mv`, `cp` are blocked
- **No shell injection** — redirects (`>`), chaining (`;`, `&&`), backticks, `$()` are blocked
- **Path sandboxing** — file access restricted to home directory and temp folders
- **Timeouts** — all commands have a 10-second timeout
- **Output limits** — command output capped at 5000 characters

## Architecture

```
┌─────────────────────┐       ┌─────────────────────────┐
│   app.py (:7860)    │──────▶│  model_server.py (:7861)│
│   Gradio Chat UI    │◀──────│  MLX-VLM Inference      │
│   Tool execution    │stream │  Vision + Text           │
│   History mgmt      │       │  Streaming generate     │
└─────────────────────┘       └─────────────────────────┘
```

- **`model_server.py`** — loads the Qwen 3.5 9B model, exposes `/chat` and `/chat_stream` API endpoints
- **`app.py`** — chat UI, tool execution, streaming display, image handling
- **`utils.py`** — shared image validation and security checks

## Configuration

Set these environment variables before starting (all optional):

```bash
export MODEL_PATH="mlx-community/Qwen3.5-9B-MLX-4bit"  # default model
```

### Tuning

| Setting | Default | Notes |
|---------|---------|-------|
| Max tokens | 32,768 | Model's context window |
| Default tokens | 4,096 | Per-response limit |
| Vision cap | 4,096 tokens | Prevents long vision inference |
| Max image | 10MB, 768px | Auto-resized for speed |
| History | 50 messages | Vision tasks use last 6 only |

## Troubleshooting

**Model won't load?**
```bash
# Ensure you have enough RAM (~6GB) and the right Python
python3 --version  # needs 3.10+
pip install --upgrade mlx-vlm gradio gradio_client
```

**Port in use?**
```bash
lsof -i :7860 -i :7861  # find what's using the ports
kill -9 <PID>            # free them
```

**Slow vision inference?**
- Disable thinking (CoT) for simple image tasks
- Images are auto-resized to 768px max — larger originals are fine

**Model server disconnected?**
- The UI auto-reconnects. Check that `model_server.py` is still running in Terminal 1.

## Adding Custom Tools

1. Add a function to `app.py` (in the tools section):
```python
def my_tool(arg1: str) -> str:
    """Description of what it does."""
    return "result"
```

2. Register it:
```python
AVAILABLE_TOOLS["my_tool"] = my_tool
```

3. Add it to the system prompt in `_build_system_prompt()`.

## License

MIT. Use it however you like.
