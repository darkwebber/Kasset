# Frontend Reference

The frontend is a Next.js 14 (App Router) application in `frontend/`. It uses React, TypeScript, TailwindCSS, and Zustand for state management.

## Directory Structure

```
frontend/src/
├── app/                    # Next.js App Router pages
│   ├── page.tsx            # Main entry point
│   ├── layout.tsx          # Root layout with fonts + theme
│   ├── globals.css         # Tailwind + CRT theme CSS
│   └── canvas/             # Pop-out image canvas page
├── components/
│   ├── Console.tsx         # Main chat interface (SSE, segments, input)
│   ├── CartridgeCarousel.tsx  # Kasset selection UI
│   ├── ChatDrawer.tsx      # History, memory, context sidebar
│   ├── CommandPalette.tsx  # ⌘K command palette
│   ├── QuickSettings.tsx   # Model/sampling quick settings
│   ├── ErrorBoundary.tsx   # React error boundary
│   ├── Toast.tsx           # Toast notification system
│   ├── Tutorial.tsx        # Interactive onboarding guide
│   ├── chat/               # Chat-specific components
│   │   ├── ToolCallCard.tsx       # Tool execution display
│   │   ├── ThinkingBlock.tsx      # Chain-of-thought display
│   │   ├── InteractiveWidget.tsx  # Forms, editors, embeds
│   │   ├── DraftBlock.tsx         # Collaborative document editing
│   │   ├── WelcomeScreen.tsx      # Landing screen with suggestions
│   │   ├── MentalModelWidget.tsx  # Agent mental model visualization
│   │   ├── ErrorRecovery.tsx      # Error handling UI
│   │   ├── toolMeta.tsx           # Tool icons and labels
│   │   └── types.ts               # Segment type definitions
│   ├── console/            # Console sub-components
│   │   ├── ConsoleHeader.tsx      # Top bar with controls
│   │   ├── ConsoleFooter.tsx      # Input area
│   │   ├── MarkdownComponents.tsx # Custom markdown renderers
│   │   └── hooks/                 # Console-specific hooks
│   ├── image/              # Image editing components
│   │   └── ImagePanel.tsx         # Canvas panel with tools
│   ├── studio/             # Kasset Forge (creation studio)
│   └── effects/            # Visual effects (CRT scanlines, etc.)
├── stores/                 # Zustand state stores
│   ├── cartridgeStore.ts   # Active kasset config
│   ├── chatStore.ts        # Chat history state
│   ├── imageStore.ts       # Image canvas state (zoom, pan, history)
│   ├── settingsStore.ts    # User preferences
│   ├── uiStore.ts          # UI state (modals, palettes)
│   ├── kassetForgeStore.ts # Kasset creation state
│   ├── toolForgeStore.ts   # Tool creation state
│   └── inputTypeForgeStore.ts # Input type creation state
└── lib/                    # Shared utilities
    ├── api.ts              # API base URL helper
    ├── sounds.ts           # Sound effects
    ├── canvasChannel.ts    # Cross-tab canvas communication
    └── signalMetrics.ts    # Performance metrics
```

## Core Component: Console.tsx

`Console.tsx` is the main chat interface (~1900 lines). Key responsibilities:

- **SSE streaming**: Connects to `/api/chat`, processes events, builds segment arrays
- **Segment rendering**: Converts SSE events into typed segments (`TextSegment`, `ThinkingSegment`, `ToolCallSegment`, `InteractiveSegment`)
- **Input handling**: Text input with file attachment, paste-to-upload, edit/retry
- **State management**: Messages, streaming state, context info, cartridge config
- **Keyboard shortcuts**: ⌘K (palette), ⌘N (new chat), Esc (stop), etc.

### Segment Types

| Type | Component | Description |
|------|-----------|-------------|
| `text` | Markdown renderer | Assistant's text response |
| `thinking` | `ThinkingBlock` | Chain-of-thought (collapsible) |
| `tool` | `ToolCallCard` | Tool execution with result, images, HTML |
| `interactive` | `InteractiveWidget` | Forms, editors, embeds, choices |

### SSE Event Types

| Event | Action |
|-------|--------|
| `chat_id` | Store chat ID for cancel/save |
| `token` | Append to current text segment |
| `think_token` | Append to thinking segment |
| `think_end` | Collapse thinking, transition to answer |
| `status` | Show loading message (⏳) |
| `tool_call` | Create tool segment in "running" state |
| `tool_result` | Update tool segment with result/images/html |
| `interactive` | Create interactive widget segment |
| `done` | Finalize all segments, save chat |
| `error` | Display error message |
| `context_info` | Update token usage meter |

## State Stores (Zustand)

### cartridgeStore
- `activeConfig` — Currently loaded kasset stack config
- `loadActiveStack(ids)` — Load kassets from backend
- `ejectCartridge()` — Clear active config

### imageStore
- `currentImageUrl` / `originalImageUrl` — Active and original image URLs
- `zoomLevel`, `panOffset`, `activeTool` — Canvas viewport and tool state
- `selection` — Current rect/lasso/color selection (attached to next chat message)
- `editHistory` / `historyIndex` — Undo/redo stack
- `canvasActive` / `poppedOut` — Canvas visibility and pop-out state
- `showBeforeAfter` / `beforeAfterPosition` — Before/after comparison slider
- Tools: `pan`, `select`, `lasso` (freeform), `crop`, `eyedropper`
- `useCanvasSync()` hook — BroadcastChannel sync between main and pop-out windows, with `remoteUpdate` guard to prevent feedback loops
- `resetCanvas()` — Called on kasset eject, new chat, and chat switch

### uiStore
- Modal/drawer visibility flags
- `showPalette`, `showTutorial`, `showSnake`

## Theming

The app uses CSS custom properties for theming:
- `--accent` — Primary accent color (set per kasset)
- `--glow` — Glow color for highlights
- `--bg` — Background color

These are set dynamically when a kasset is loaded, based on its `theme` config.

## HTML Artifacts

When the agent produces HTML via `html_preview`, it renders in a sandboxed iframe inside `ToolCallCard`. The toolbar provides:
- **Copy HTML** — Copies raw HTML to clipboard
- **Download** — Downloads as `artifact.html`
