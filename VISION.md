# Cartridge Console — Vision Document

> A retro-futuristic AI interface where system prompts are cartridges,
> the model runs inside a virtual console, and capabilities are composable.

---

## 1. Philosophy

**The problem:** AI chat interfaces are generic text boxes. Every conversation starts the same way. Users copy-paste system prompts, manually configure tools, and lose context when switching tasks. There's no concept of "modes" or "personas" — it's always the same blank slate.

**The insight:** A retro gaming console is the perfect metaphor for an AI runtime. Everyone intuitively understands: *insert a cartridge, the device does something different.* This maps perfectly to AI:

| Console World | AI World |
|---------------|----------|
| The console hardware | The local model + inference engine |
| A game cartridge | A system prompt + tools + personality |
| Inserting a cartridge | Loading a configuration |
| The game store | A marketplace for AI configurations |
| Multiplayer / combo carts | Multi-cartridge stacking |
| Save files | Per-cartridge persistent memory |
| Controller input | Natural language chat |
| The screen | Response display |

**The vision:** An AI interface that feels like a physical device you own. Something with *presence* — not another web form, but a machine on your desk that you interact with. Cartridges make the AI modular, shareable, and discoverable. The retro-futuristic aesthetic makes it feel tactile and alive.

---

## 2. The Console

The console is the persistent shell — the "device" that's always present regardless of which cartridge is loaded.

### 2.1 Physical Layout

```
┌─────────────────────────────────────────────────────┐
│  ╔═══════════════════════════════════════════════╗   │
│  ║                                               ║   │
│  ║            S C R E E N  A R E A               ║   │
│  ║         (chat / response display)             ║   │
│  ║                                               ║   │
│  ║                                               ║   │
│  ╚═══════════════════════════════════════════════╝   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  🟢  [═══ CARTRIDGE SLOT ═══]  ▣ ▣ ▣        │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  > █ input area                          [⏎] │   │
│  └──────────────────────────────────────────────┘   │
│                          ┌──┐ ┌──┐ ┌──┐             │
│                          │◀ │ │▶ │ │⚙ │             │
│                          └──┘ └──┘ └──┘             │
└─────────────────────────────────────────────────────┘
```

**Elements:**
- **Screen** — CRT/LCD display with scanline effects, where all output appears
- **Cartridge Slot** — shows the active cartridge label; click to eject or swap
- **Status LEDs** — power (green), thinking (amber pulse), tool running (blue blink)
- **Input Area** — styled as a retro terminal input with blinking cursor
- **Nav Buttons** — cartridge drawer (◀), store (▶), settings (⚙)

### 2.2 Console States

| State | Visual | Description |
|-------|--------|-------------|
| **Boot** | CRT turn-on animation, scanlines, logo | App first loads |
| **No Cartridge** | Static/noise on screen, "INSERT CARTRIDGE" text | Nothing loaded |
| **Loading** | Cartridge slides in, click sound, screen flicker | Cartridge being loaded |
| **Ready** | Clean screen, cartridge label visible, green LED | Ready for input |
| **Thinking** | Scanlines intensify, amber LED pulses, subtle glow | Model generating |
| **Tool Running** | Blue LED blinks, mini terminal overlay in corner | Executing a tool |
| **Error** | Screen shake, brief static, error in retro font | Something went wrong |
| **Ejecting** | Cartridge slides out, screen fades to static | Removing cartridge |
| **Power Off** | CRT dot-shrink effect | Closing the app |

### 2.3 Aesthetic Direction

**Retro-futurism** — not pure nostalgia, but the future *as imagined by the past.* Think:
- Fallout's Pip-Boy (green-on-black, chunky UI)
- Alien's ship computer (amber on dark, industrial)
- Tron (neon grid lines, glowing edges)
- Cowboy Bebop interfaces (colorful retro-tech)

**Color Palette (default console):**
- Background: `#0a0e17` (deep space dark)
- Bezel: `#1a1f2e` with subtle metallic gradient
- Screen glass: slight reflection/glare overlay
- Text: `#e0e0e0` (warm white)
- Accent: `#00ff88` (console green, for status/LEDs)
- Each cartridge overrides the accent color and screen tint

**Typography:**
- UI labels: monospace pixel font (e.g., "Press Start 2P" or "VT323")
- Chat text: clean monospace (e.g., "JetBrains Mono" or "Fira Code")
- Headings: bold pixel font with subtle glow

---

## 3. The Cartridge

A cartridge is a self-contained AI configuration — everything the model needs to become a specialized assistant.

### 3.1 What's Inside a Cartridge

```
┌─────────────────────────────┐
│ ░░░ CARTRIDGE ░░░░░░░░░░░░ │
│                             │
│  Name:    "Code Pilot"      │
│  Icon:    🚀                │
│  Author:  darkwebber        │
│  Version: 1.2.0             │
│                             │
│  ┌───────────────────────┐  │
│  │    System Prompt      │  │
│  │    (the brain)        │  │
│  ├───────────────────────┤  │
│  │    Tools Enabled      │  │
│  │    (the hands)        │  │
│  ├───────────────────────┤  │
│  │    Theme / Aesthetic  │  │
│  │    (the look)         │  │
│  ├───────────────────────┤  │
│  │    Workflows          │  │
│  │    (the playbook)     │  │
│  ├───────────────────────┤  │
│  │    Stacking Rules     │  │
│  │    (the connectors)   │  │
│  └───────────────────────┘  │
│                             │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │
└─────────────────────────────┘
```

### 3.2 Cartridge Fields

| Field | Required | Description |
|-------|----------|-------------|
| `id` | yes | Unique identifier (slug format: `code-pilot`) |
| `name` | yes | Display name |
| `description` | yes | One-line description |
| `long_description` | no | Detailed markdown description for store listing |
| `icon` | yes | Emoji or URL to pixel art icon |
| `author` | yes | Creator name |
| `version` | yes | Semver (e.g., `1.2.0`) |
| `tags` | yes | Category tags for discovery |
| `system_prompt` | yes | The core instruction for the model |
| `tools` | yes | Array of enabled tool names |
| `theme` | no | Visual theme overrides |
| `boot_message` | no | First message shown when cartridge loads |
| `workflows` | no | Predefined multi-step sequences |
| `stacking` | no | Rules for multi-cartridge composition |
| `memory_enabled` | no | Whether to persist state across sessions |
| `suggested_tokens` | no | Recommended max token setting |
| `suggested_thinking` | no | Whether CoT should be on by default |

### 3.3 Theme Object

```json
{
  "accent_color": "#ff6b35",
  "screen_tint": "rgba(255, 107, 53, 0.03)",
  "scanline_intensity": 0.3,
  "glow_color": "#ff6b35",
  "font_override": null,
  "boot_animation": "terminal",
  "particle_effect": "sparks"
}
```

Boot animations: `"terminal"` (typing effect), `"glitch"` (digital corruption), `"fade"` (smooth), `"matrix"` (falling characters), `"scan"` (top-to-bottom reveal)

### 3.4 Stacking Object

```json
{
  "stackable": true,
  "priority": 50,
  "role": "primary | auxiliary",
  "conflicts_with": ["other-cartridge-id"],
  "requires": [],
  "merge_strategy": "append | prepend | replace"
}
```

- **`priority`** — higher number = loaded later, takes precedence on conflicts (0–100)
- **`role`** — `primary` cartridges define the main persona; `auxiliary` add capabilities
- **`merge_strategy`** — how this cartridge's system prompt combines with others

---

## 4. Multi-Cartridge System

The killer feature. Users can load **1 primary + up to 3 auxiliary** cartridges simultaneously.

### 4.1 How Stacking Works

```
SLOT 1 (Primary):   "General Assistant"     [priority: 10]
SLOT 2 (Aux):       "Python Developer"      [priority: 50]
SLOT 3 (Aux):       "Git Expert"            [priority: 60]
SLOT 4 (Aux):       "AWS Deployer"          [priority: 70]

Merged System Prompt:
  [General Assistant base prompt]
  [+ Python Developer additions]
  [+ Git Expert additions]
  [+ AWS Deployer additions]

Merged Tools:
  [Union of all cartridges' tool lists]

Theme:
  [Primary cartridge's theme, with accent from highest-priority aux]
```

### 4.2 Conflict Resolution

When two cartridges conflict (e.g., both say "always respond in JSON"):
1. Higher priority wins
2. If equal priority, the user is asked which to keep
3. `conflicts_with` prevents incompatible cartridges from being loaded together

### 4.3 Example Combos

| Use Case | Primary | Auxiliaries | Result |
|----------|---------|-------------|--------|
| Full-stack dev | Code Pilot | Git Expert + Docker Helper | Code, commit, containerize |
| Data science | Data Analyst | Python Dev + Visualizer | Analyze, code, chart |
| Content creator | Writer | SEO Expert + Social Media | Write, optimize, post |
| Sysadmin | Terminal | Network Monitor + Log Analyzer | Monitor, debug, diagnose |
| Student | Tutor | Calculator + Research | Learn, calculate, cite |

---

## 5. The Store

A marketplace where users discover, install, and share cartridges.

### 5.1 Store Views

**Browse** — grid of cartridge cards with icon, name, author, rating, install count
**Categories** — System, Code, Web, Creative, Productivity, Education, Data, Custom
**Search** — full-text search across names, descriptions, tags
**Featured** — curated collections ("Staff Picks," "Trending This Week," "New Arrivals")
**My Cartridges** — installed, created, favorites

### 5.2 Cartridge Card

```
┌─────────────────────────┐
│  🚀  Code Pilot         │
│  ─────────────────────  │
│  AI pair programmer     │
│  with deep code review  │
│                         │
│  by darkwebber          │
│  ★★★★☆  (342 reviews)  │
│  ↓ 12.4k installs      │
│                         │
│  [Install]  [Preview]   │
└─────────────────────────┘
```

### 5.3 Store Backend Options

**Phase 1 (MVP):** Git-backed repository. Cartridges are JSON files in a public repo. Users submit via PR. The app fetches the repo index on launch.

**Phase 2:** Simple REST API with user accounts, ratings, and install tracking.

**Phase 3:** Full platform with user profiles, revenue sharing for premium cartridges, collections, and social features.

### 5.4 Cartridge Creation

Users can create cartridges through:
1. **In-app editor** — form-based UI with live preview
2. **JSON file** — write directly and import
3. **Fork & remix** — start from an existing cartridge, modify it
4. **AI-generated** — describe what you want, the model creates the cartridge

---

## 6. UX & Animations

### 6.1 Core Animations

| Trigger | Animation | Duration |
|---------|-----------|----------|
| App boot | CRT power-on: horizontal line expands to full screen, scanlines fade in | 1.5s |
| Cartridge insert | Card slides down into slot, mechanical click, screen flickers briefly | 0.8s |
| Cartridge eject | Card rises out of slot, screen fades to static | 0.6s |
| Thinking start | Scanlines intensify, amber LED fades in, subtle screen vibration | 0.3s |
| Thinking end | Scanlines return to normal, LED off, text begins appearing | 0.2s |
| Tool execution | Blue LED blinks 3×, mini terminal slides in from bottom-right | 0.4s |
| Tool complete | Mini terminal slides out, result fades into chat | 0.3s |
| Error | Screen shakes (2px, 3 cycles), brief red flash | 0.5s |
| Power off | Screen content shrinks to center dot, fades out | 1.0s |
| Store open | Screen slides left, store panel slides in from right | 0.4s |
| Cartridge swap | Current ejects (0.6s) → brief static (0.3s) → new inserts (0.8s) | 1.7s |

### 6.2 Micro-interactions

- **Hover on cartridge** — slight tilt/parallax, glow intensifies
- **Click buttons** — tactile press animation (scale down 2px, spring back)
- **Active states** — touch-friendly `:active` states replace hover on mobile (scale 0.96, opacity 0.7)
- **Scroll chat** — momentum scrolling with slight CRT curve distortion at edges
- **Input focus** — cursor blink rate increases, subtle glow around input
- **New message** — text appears with typewriter effect (optional, can be instant)
- **LED indicators** — smooth pulse transitions, not abrupt on/off
- **Slot status** — cartridge label has subtle breathing glow when active
- **Swipe gestures** — carousel navigation and Snake game steering via touch swipe

### 6.4 Mobile & Touch

**Responsive design** — the console adapts from phone screens to desktop monitors:
- Full-screen on mobile (no border radius, edge-to-edge)
- Top bar collapses to essential actions; secondary actions via Command Palette
- Safe area insets for notched devices (iPhone, etc.)
- Momentum scrolling everywhere
- Touch-friendly tap targets (minimum 44px)
- Keyboard shortcut badges hidden on touch devices
- Grid view auto-selected in carousel when >12 cartridges
- Swipe left/right to navigate carousel on touch
- Snake game resizes canvas to fit screen, swipe to steer

### 6.5 Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line |
| `Escape` | Close topmost overlay / stop generation |
| `⌘K` / `Ctrl+K` | Toggle command palette |
| `⌘N` / `Ctrl+N` | New chat |
| `⌘E` / `Ctrl+E` | Export chat as Markdown |
| `⌘⇧C` | Copy full conversation to clipboard |
| `⌘⇧F` | Open Cartridge Forge |
| `⌘/` | Toggle help/tutorial |
| `⌘.` | Focus input box |
| `/` (in carousel) | Focus search bar |
| `←→` (in carousel) | Navigate cartridges |
| `Enter` (in carousel) | Load selected cartridge |

### 6.6 Command Palette

A searchable action overlay (⌘K) providing quick access to all console actions:
- New Chat, Chat History, Export, Copy Conversation
- Cartridge Forge, Quick Guide
- Mute/Unmute, Switch Cartridge
- Arrow key navigation + fuzzy search by keywords

### 6.3 Sound Design (Optional, Toggle-able)

- **Boot:** Low electronic hum building to a "ready" chime
- **Cartridge click:** Mechanical snap (like inserting a Game Boy cart)
- **Keyboard:** Soft mechanical key sounds on input
- **Send message:** Subtle "transmit" blip
- **Receive response:** Soft "receive" ping
- **Tool running:** Quiet processing hum
- **Error:** Brief static burst
- **Achievement:** 8-bit success jingle (for workflow completions)

---

## 7. Curated Starter Cartridges

These ship with the console. They demonstrate the cartridge system and are immediately useful.

### 7.1 The Collection

| Cartridge | Icon | Role | Description |
|-----------|------|------|-------------|
| **General Assistant** | 🤖 | Primary | Well-rounded helper. Default cartridge. |
| **Code Pilot** | 🚀 | Primary | AI pair programmer with code review and debugging |
| **Terminal** | 💻 | Primary | Natural language shell — control your Mac with words |
| **Data Analyst** | 📊 | Auxiliary | CSV/JSON analysis, calculations, data transformation |
| **Web Pilot** | 🌐 | Primary | Web search, URL reading, research synthesis |
| **Writer** | ✍️ | Primary | Creative and technical writing with tone control |
| **Tutor** | 🎓 | Primary | Patient teacher that explains with examples and analogies |
| **DevOps** | 🔧 | Auxiliary | Docker, git, deployment, CI/CD knowledge |

### 7.2 Cartridge Detail: "Terminal"

The Terminal cartridge turns the console into a natural language computer interface:

```
You: "what's eating my disk space?"
AI: [calls: du -d 1 -h ~ | sort -rh | head -n 10]
    Your top directories by size:
    48G   ~/Library
    12G   ~/Documents
    8.2G  ~/Downloads
    ...
    Total used: 78G of 250G (31%)

You: "delete everything in Downloads older than 30 days"
AI: I found 23 files older than 30 days (4.1GB total).
    For safety, I can't delete files directly.
    Here's the command you can run:

    find ~/Downloads -mtime +30 -type f -delete

    Want me to list the files first so you can review?
```

---

## 8. Technical Architecture

### 8.1 System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Console  │  │ Screen   │  │ Drawer   │  │  Store   │   │
│  │  Shell   │  │  (Chat)  │  │(Collect.)│  │  (Browse)│   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       └──────────────┴──────────────┴──────────────┘         │
│                          │                                    │
│  React / Next.js + Framer Motion + Tailwind                  │
│  Zustand (state) + Howler.js (sound)                         │
└──────────────────────────┬──────────────────────────────────┘
                           │ WebSocket / HTTP
┌──────────────────────────┴──────────────────────────────────┐
│                        BACKEND                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Cartridge   │  │     Tool     │  │    Session       │  │
│  │   Loader     │  │   Registry   │  │    Manager       │  │
│  │  (merge &    │  │  (all tools) │  │  (per-cartridge  │  │
│  │   resolve)   │  │              │  │   memory/state)  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────────┘  │
│         └─────────────────┼─────────────────┘               │
│                           │                                  │
│  ┌────────────────────────┴──────────────────────────────┐  │
│  │              Model Server (MLX-VLM)                    │  │
│  │         Qwen 3.5 9B / swappable model                 │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  FastAPI + Python                                            │
└──────────────────────────────────────────────────────────────┘
```

### 8.2 Cartridge Loader

The cartridge loader is the core engine that:
1. Reads cartridge JSON files
2. Validates against the schema
3. Merges multiple cartridges' system prompts (respecting priority & strategy)
4. Resolves tool conflicts
5. Applies theme to the frontend
6. Initializes per-cartridge memory/state

```python
# Pseudocode
def load_cartridges(primary: Cartridge, auxiliaries: List[Cartridge]) -> LoadedConfig:
    # Sort by priority
    all_carts = sorted([primary] + auxiliaries, key=lambda c: c.stacking.priority)

    # Merge system prompts
    merged_prompt = ""
    for cart in all_carts:
        if cart.stacking.merge_strategy == "append":
            merged_prompt += "\n\n" + cart.system_prompt
        elif cart.stacking.merge_strategy == "prepend":
            merged_prompt = cart.system_prompt + "\n\n" + merged_prompt
        elif cart.stacking.merge_strategy == "replace":
            merged_prompt = cart.system_prompt

    # Union of all tools
    enabled_tools = set()
    for cart in all_carts:
        enabled_tools.update(cart.tools)

    # Theme from primary, accent from highest-priority
    theme = primary.theme
    if auxiliaries:
        theme.accent_color = all_carts[-1].theme.accent_color

    return LoadedConfig(prompt=merged_prompt, tools=enabled_tools, theme=theme)
```

### 8.3 File Structure

```
Local-Studio/
├── frontend/                  # React app (the console UI)
│   ├── src/
│   │   ├── components/
│   │   │   ├── Console.tsx    # The device shell
│   │   │   ├── Screen.tsx     # Chat display with CRT effects
│   │   │   ├── CartridgeSlot.tsx
│   │   │   ├── CartridgeDrawer.tsx
│   │   │   ├── Store.tsx
│   │   │   └── effects/       # Scanlines, glow, animations
│   │   ├── stores/            # Zustand state
│   │   └── sounds/            # Audio assets
│   └── public/
├── backend/                   # Python API
│   ├── app.py                 # FastAPI server
│   ├── model_server.py        # MLX-VLM inference
│   ├── cartridge_loader.py    # Cartridge merging engine
│   ├── tool_registry.py       # All available tools
│   ├── session_manager.py     # Per-cartridge state
│   └── utils.py               # Shared utilities
├── cartridges/
│   ├── schema.json            # Cartridge JSON schema
│   └── builtins/              # Ships with the console
│       ├── general-assistant.json
│       ├── code-pilot.json
│       ├── terminal.json
│       ├── data-analyst.json
│       ├── web-pilot.json
│       ├── writer.json
│       ├── tutor.json
│       └── devops.json
├── store/                     # Store index and metadata
│   └── index.json
├── start.sh
└── README.md
```

### 8.4 Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend framework | React + Next.js | Component model, SSR, ecosystem |
| Styling | Tailwind CSS | Rapid, consistent, responsive |
| Animations | Framer Motion | Physics-based, declarative, performant |
| State | Zustand | Simple, no boilerplate |
| Sound | Howler.js | Cross-browser, sprite support |
| CRT effects | Custom CSS + WebGL shaders | Scanlines, glow, curvature |
| Backend | FastAPI | Async, fast, typed |
| Model | MLX-VLM (Qwen 3.5 9B) | Local, fast on Apple Silicon |
| Cartridge format | JSON | Universal, easy to edit |
| Store (MVP) | Git repo + JSON index | Zero infrastructure |

---

## 9. Roadmap

### Phase 1 — Console MVP ✅
- [x] React frontend with console shell, screen, and input
- [x] CRT visual effects (scanlines, glow, screen curvature)
- [x] Single cartridge loading (from JSON file)
- [x] Boot and cartridge insertion animations
- [x] Connect to existing model server backend
- [x] Port all existing chat functionality to new UI
- [x] Ship with 8 built-in cartridges (General, Code Pilot, Terminal, Writer, Tutor, Data Analyst, DevOps, Web Pilot)

### Phase 2 — Multi-Cartridge & Drawer ✅
- [x] Cartridge drawer UI (carousel + grid with search, categories)
- [x] Multi-cartridge stacking (1 primary + 3 aux)
- [x] Prompt merging engine with conflict resolution
- [x] Per-cartridge theme switching
- [x] Cartridge creation UI (Cartridge Forge in-app editor)
- [x] Import/export cartridges as JSON files
- [x] Custom tool plugin system (Python handlers)

### Phase 2.5 — UX Polish ✅ *(added post-roadmap)*
- [x] Command palette (⌘K) with searchable actions
- [x] Welcome screen with per-cartridge example prompts
- [x] Inline file attachment chips
- [x] Chat sharing (copy conversation as Markdown)
- [x] Comprehensive keyboard shortcuts (Escape, ⌘N, ⌘E, ⌘⇧C, ⌘⇧F, ⌘/, ⌘.)
- [x] Mobile-responsive layout (phone → desktop)
- [x] Touch interactions (swipe carousel, swipe snake, active states)
- [x] Safe area insets for notched devices
- [x] Data persistence (last cartridge, mute state, snake high score)
- [x] Tutorial/help with mobile + shortcuts sections
- [x] Snake game easter egg (5 red LED clicks) with NSFW cartridge unlock

### Phase 3 — Store & Community
- [ ] Store browse UI (grid, categories, search)
- [ ] Git-backed store index
- [ ] Install/uninstall from store
- [ ] User profiles and published cartridges
- [ ] Ratings and reviews
- [ ] Featured collections

### Phase 4 — Advanced Features
- [x] Per-cartridge persistent memory
- [x] Sound design and audio toggle
- [ ] Workflow engine (multi-step sequences)
- [ ] Cartridge-specific hotkeys
- [ ] AI-generated cartridge creation ("make me a cartridge for...")
- [ ] Premium cartridges with revenue sharing
- [x] Mobile-responsive console layout
- [ ] Model swapping (different "processors" for the console)

---

## 10. Design Principles

1. **Tactile over flat.** Every element should feel like it has weight and physicality. Buttons press, cartridges click, screens glow.

2. **Modular over monolithic.** Capabilities are composed, not configured. Adding a skill = inserting a cartridge, not editing a settings page.

3. **Discoverable over documented.** Users should find new capabilities by browsing the store, not reading docs.

4. **Local-first.** Everything runs on your machine. Cartridges are files you own. The store is optional.

5. **Aesthetic is function.** The retro-futuristic design isn't decoration — it creates a mental model (console + cartridges) that makes AI interaction intuitive.

6. **Safe by default.** Tools are read-only, commands are whitelisted, paths are sandboxed. A cartridge cannot grant itself more permissions than the console allows.

7. **Responsive by nature.** Works on any screen size. The same console adapts from a phone to a 5K monitor. Touch and pointer interactions are both first-class.

8. **Persistent by default.** User preferences, chat history, memories, and state survive restarts. Data lives locally at `~/.qwen-studio/`.

---

*Working title. Final product name TBD.*
*This document is a living artifact — it evolves as we build.*
*Last updated: Phase 2.5 complete (UX polish, mobile, touch, shortcuts, persistence).*
