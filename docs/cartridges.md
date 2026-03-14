# Cartridge (Kasset) System

Kassets are modular agent personas that define how the AI behaves. Each kasset is a JSON file that configures the system prompt, available tools, sampling parameters, and UI theme.

## Built-in Kassets

| Kasset | ID | Description |
|--------|----|-------------|
| General Assistant | `general-assistant` | Default all-purpose assistant |
| Code Pilot | `code-pilot` | Software engineering focus |
| Data Analyst | `data-analyst` | Data analysis and visualization |
| Image Editor | `image-editor` | Image editing with 100+ tools |
| Writer | `writer` | Collaborative document writing |
| 3D Visualizer | `3d-visualizer` | 3D data visualization |
| Terminal | `terminal` | System command execution |
| Tutor | `tutor` | Educational explanations |
| Web Researcher | `web-researcher` | Web search and summarization |
| Creative Studio | `creative-studio` | Creative content generation |

## Kasset JSON Schema

```json
{
  "id": "my-kasset",
  "name": "My Kasset",
  "version": "1.0.0",
  "description": "What this kasset does",
  "icon": "🎯",
  "author": "Your Name",
  "system_prompt": "You are a helpful assistant that...",
  "tools": ["execute_python", "read_file", "write_file"],
  "suggested_temperature": 0.6,
  "suggested_top_p": 0.95,
  "suggested_tokens": 4096,
  "suggested_thinking": true,
  "suggested_max_rounds": 6,
  "theme": {
    "accent": "#10b981",
    "glow": "#34d399"
  },
  "collaboration_mode": false,
  "welcome_message": "How can I help?",
  "suggestions": [
    "Write a Python script that...",
    "Analyze this dataset..."
  ],
  "workflows": {
    "quick-start": {
      "name": "Quick Start",
      "steps": ["Step 1 instruction", "Step 2 instruction"]
    }
  }
}
```

## Key Fields

### `system_prompt`
The core instruction that shapes agent behavior. This is prepended to every conversation. Write clear, specific instructions about:
- What the agent should/shouldn't do
- Output format preferences
- Tool usage patterns
- Domain-specific knowledge

### `tools`
Array of tool IDs the agent can use. Available built-in tools:

| Tool | Description |
|------|-------------|
| `execute_python` | Run Python code in sandbox |
| `execute_cpp` | Compile and run C++ code |
| `read_file` | Read file contents |
| `write_file` | Write/create files |
| `edit_file` | Edit existing files |
| `list_directory` | List directory contents |
| `search_files` | Search for files by name |
| `grep_code` | Search file contents (regex) |
| `run_command` | Execute shell commands (with consent) |
| `html_preview` | Render interactive HTML artifact |
| `request_user_input` | Show interactive widgets (forms, editors) |
| `save_notes` | Persist working notes |
| `web_search` | Search the web |
| `web_fetch` | Fetch a web page |
| `get_weather` | Get weather data |
| `get_location` | Get approximate location |

### `suggested_thinking`
When `true`, the model uses chain-of-thought reasoning inside `<think>...</think>` tags. Recommended for complex tasks.

### `collaboration_mode`
When `true`, injects the Collaboration Protocol which requires the agent to:
1. Collect user preferences via forms first
2. Use persistent widgets for iterative editing
3. Show diffs for changes
4. Respect rejections

### `theme`
Sets CSS variables `--accent` and `--glow` for the frontend UI when this kasset is active.

## Kasset Stacking

Multiple kassets can be stacked. The `CartridgeLoader` merges them:
- System prompts are concatenated
- Tool lists are unioned
- Numeric parameters use the last kasset's values
- Theme uses the last kasset's theme

## Custom Kassets (Kasset Forge)

Users can create custom kassets via the Kasset Forge UI (⌘⇧F) or by placing JSON files in `~/.kasset/forge/kassets/`. Custom kassets follow the same schema and appear alongside built-ins in the carousel.

## Custom Tools

Custom tools can be created in `~/.kasset/forge/tools/` as Python files with a specific structure. They are auto-loaded by the `PluginLoader` and become available to any kasset.

## Custom Input Types

Custom interactive widget types can be defined in `~/.kasset/forge/input_types/` or `cartridges/builtins/input_types/`. Each has a `manifest.json` describing the widget schema.
