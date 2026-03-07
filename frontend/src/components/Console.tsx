"use client";

import React, { useState, useRef, useEffect, useMemo, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import FileExplorer from "./explorer/FileExplorer";
import ChatDrawer from "./ChatDrawer";
import CommandPalette from "./CommandPalette";
import Tutorial from "./Tutorial";
import { useCartridgeStore } from "@/stores/cartridgeStore";
import { useChatStore } from "@/stores/chatStore";
import { FolderOpen, X, Copy, Check, History, Plus, ChevronDown, ChevronRight, Wrench, Terminal, FileText, Clock, Play, Search, Calculator, Volume2, VolumeX, Square, RefreshCw, Pencil, Scissors, Trash2, CornerDownLeft, Paperclip, HelpCircle, Download, Command } from "lucide-react";
import { soundSend, soundThinkStart, soundThinkEnd, soundToolStart, soundToolDone, soundDone, soundError, soundNewChat, soundTick, soundCartridgeEject, isMuted, setMuted } from "@/lib/sounds";
import { getApiBase, isLocalClient } from "@/lib/api";
import SnakeGame from "./SnakeGame";
import dynamic from "next/dynamic";
const MermaidDiagram = dynamic(() => import("./MermaidDiagram"), { ssr: false });

// ═══════════════════════════════════════════
// TYPES — structured message segments
// ═══════════════════════════════════════════

interface ToolCallSegment {
  kind: "tool";
  name: string;
  args: Record<string, any>;
  result?: string;
  images?: string[];
  html?: string;
  consentId?: string;
  consentCommand?: string;
  status: "running" | "done" | "error" | "consent" | "preparing";
}

interface ThinkingSegment {
  kind: "thinking";
  content: string;
  durationMs?: number;
  collapsed: boolean;
}

interface TextSegment {
  kind: "text";
  content: string;
}

type Segment = ToolCallSegment | ThinkingSegment | TextSegment;

interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  segments?: Segment[];
}

// ═══════════════════════════════════════════
// TOOL ICONS & LABELS
// ═══════════════════════════════════════════

const TOOL_META: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  read_file:       { icon: <FileText size={13} />,   label: "Reading file",       color: "#60a5fa" },
  run_command:     { icon: <Terminal size={13} />,    label: "Running command",    color: "#a78bfa" },
  execute_python:  { icon: <Play size={13} />,        label: "Running Python",     color: "#34d399" },
  execute_cpp:     { icon: <Play size={13} />,        label: "Running C++",        color: "#38bdf8" },
  search_files:    { icon: <Search size={13} />,      label: "Searching files",    color: "#fbbf24" },
  list_directory:  { icon: <FolderOpen size={13} />,  label: "Listing directory",  color: "#fb923c" },
  calculate:       { icon: <Calculator size={13} />,  label: "Calculating",        color: "#f472b6" },
  get_current_time:{ icon: <Clock size={13} />,       label: "Getting time",       color: "#38bdf8" },
  get_system_info: { icon: <Terminal size={13} />,    label: "System info",        color: "#818cf8" },
};

function getToolMeta(name: string) {
  return TOOL_META[name] || { icon: <Wrench size={13} />, label: name, color: "#94a3b8" };
}

const TOOL_DISPLAY: Record<string, string> = {
  run_command: "Shell",
  execute_python: "Python",
  execute_cpp: "C++",
  read_file: "File Reader",
  search_files: "Search",
  list_directory: "Browse",
  calculate: "Math",
  get_current_time: "Clock",
  get_system_info: "System",
  search_web: "Web Search",
  read_url: "URL Reader",
};

const TOOL_EXAMPLES: Record<string, string> = {
  run_command: "Show my disk usage and top processes",
  execute_python: "Plot a sine wave using matplotlib",
  read_file: "Read my ~/.zshrc and explain what it does",
  search_files: "Find all Python files in my home directory",
  list_directory: "What's in my Downloads folder?",
  calculate: "What's the square root of 2048?",
  get_system_info: "What are my system specs?",
  get_current_time: "What time is it right now?",
  execute_cpp: "Write and run a C++ hello world program",
  search_web: "Search for the latest AI news",
  read_url: "Summarize the top story on Hacker News",
};

// ═══════════════════════════════════════════
// SUB-COMPONENTS
// ═══════════════════════════════════════════

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
      className="absolute top-2 right-2 p-1.5 rounded bg-white/5 hover:bg-white/10 text-white/40 hover:text-white/80 transition-all opacity-0 group-hover:opacity-100"
      title="Copy code"
    >
      {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
    </button>
  );
}

const ThinkingBlock = React.memo(function ThinkingBlock({ segment, onToggle }: { segment: ThinkingSegment; onToggle: () => void }) {
  const isStreaming = !segment.durationMs;
  const durationStr = segment.durationMs ? `${(segment.durationMs / 1000).toFixed(1)}s` : null;

  return (
    <div className="my-2">
      <button
        onClick={onToggle}
        className="flex items-center gap-2 text-[11px] font-mono text-white/30 hover:text-white/50 transition-colors group"
      >
        {segment.collapsed
          ? <ChevronRight size={12} className="text-white/20" />
          : <ChevronDown size={12} className="text-white/20" />
        }
        {isStreaming ? (
          <>
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-pulse" />
            <span className="text-[var(--accent)]/60">Thinking...</span>
          </>
        ) : (
          <>
            <Clock size={11} className="text-white/20" />
            <span>Thought for {durationStr}</span>
          </>
        )}
      </button>
      {!segment.collapsed && (
        <div className="ml-5 mt-1.5 pl-3 border-l border-white/5 text-[11px] text-white/25 font-mono leading-relaxed max-h-40 overflow-y-auto crt-scroll whitespace-pre-wrap">
          {segment.content}
        </div>
      )}
    </div>
  );
});

const ToolCallCard = React.memo(function ToolCallCard({ segment, onConsent }: { segment: ToolCallSegment; onConsent?: (id: string, approved: boolean) => void }) {
  const [expanded, setExpanded] = useState(false);
  const meta = getToolMeta(segment.name);
  const isRunning = segment.status === "running";
  const isPreparing = segment.status === "preparing";
  const isConsent = segment.status === "consent";
  const hasImages = segment.images && segment.images.length > 0;
  const hasHtml = !!segment.html;

  const formatArgs = (args: Record<string, any>) => {
    const entries = Object.entries(args);
    if (entries.length === 0) return null;
    const [, firstVal] = entries[0];
    const valStr = typeof firstVal === "string" ? firstVal : JSON.stringify(firstVal);
    return { value: valStr, extra: entries.length > 1 ? entries.length - 1 : 0 };
  };

  const argInfo = formatArgs(segment.args);

  return (
    <div className="my-2 rounded-lg border overflow-hidden transition-all"
      style={{ borderColor: `${meta.color}20` }}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2.5 px-3 py-2 text-left transition-all hover:bg-white/[0.02]"
      >
        <div className="flex items-center justify-center w-6 h-6 rounded-md"
          style={{ background: `${meta.color}15`, color: meta.color }}
        >
          {isRunning || isPreparing ? <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" /> : meta.icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium" style={{ color: isConsent ? '#f59e0b' : meta.color }}>
              {isPreparing ? "Writing code…" : isRunning ? meta.label + "..." : isConsent ? "Approval Required" : meta.label}
            </span>
            {argInfo && (
              <span className="text-[10px] text-white/25 font-mono truncate max-w-[300px]">
                {argInfo.value.length > 60 ? argInfo.value.slice(0, 60) + "..." : argInfo.value}
              </span>
            )}
          </div>
        </div>
        {segment.result && (
          <ChevronDown size={12} className={`text-white/20 transition-transform ${expanded ? "rotate-0" : "-rotate-90"}`} />
        )}
      </button>

      {/* Live code preview during preparation */}
      {isPreparing && segment.args?.code && (
        <div className="px-3 pb-2.5">
          <div className="bg-black/40 rounded border border-white/5 p-2.5 text-[11px] text-[var(--accent)]/60 font-mono max-h-48 overflow-y-auto crt-scroll whitespace-pre-wrap leading-relaxed">
            {segment.args.code}
            <span className="inline-block w-[2px] h-[14px] bg-[var(--accent)] animate-blink ml-0.5 align-text-bottom" />
          </div>
        </div>
      )}

      {/* Expanded text result */}
      {expanded && segment.result && (
        <div className="px-3 pb-2.5 pt-0">
          <div className="bg-black/40 rounded border border-white/5 p-2.5 text-[11px] text-white/50 font-mono max-h-48 overflow-y-auto crt-scroll whitespace-pre-wrap leading-relaxed">
            {segment.result}
          </div>
        </div>
      )}

      {/* Consent approval buttons */}
      {isConsent && segment.consentId && (
        <div className="px-3 pb-3">
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
            <p className="text-[11px] text-white/60 mb-2">
              This command requires your approval:
            </p>
            <code className="block text-[11px] text-amber-400/90 font-mono bg-black/30 rounded px-2 py-1.5 mb-3">
              {segment.consentCommand || segment.args?.command || ''}
            </code>
            <div className="flex gap-2">
              <button
                onClick={() => onConsent?.(segment.consentId!, true)}
                className="px-3 py-1.5 rounded-md text-[11px] font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors"
              >
                Approve
              </button>
              <button
                onClick={() => onConsent?.(segment.consentId!, false)}
                className="px-3 py-1.5 rounded-md text-[11px] font-medium bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
              >
                Deny
              </button>
            </div>
          </div>
        </div>
      )}

      {/* HTML artifact (Plotly, custom tools) — rendered in sandboxed iframe */}
      {hasHtml && (
        <div className="px-3 pb-3">
          <div className="rounded-lg overflow-hidden border border-white/5" style={{ background: '#0d1117' }}>
            <iframe
              srcDoc={segment.html}
              sandbox="allow-scripts allow-same-origin"
              className="w-full rounded-lg"
              style={{ height: 500, border: 'none', background: '#0d1117' }}
              title="Interactive visualization"
            />
          </div>
        </div>
      )}

      {/* Images always visible inline — not hidden behind expand */}
      {hasImages && (
        <div className="px-3 pb-3 space-y-2">
          {segment.images!.map((src, i) => (
            <div key={i} className="rounded-lg overflow-hidden bg-black/60 border border-white/5">
              <img src={src} alt={`Plot ${i + 1}`} className="w-full max-h-[400px] object-contain rounded-lg" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
});

function WelcomeScreen({ cartridgeName, cartridgeIcon, bootMessage, tools, suggestedPrompts, onSendPrompt }: {
  cartridgeName: string;
  cartridgeIcon: string;
  bootMessage: string;
  tools: string[];
  suggestedPrompts: string[];
  onSendPrompt: (prompt: string) => void;
}) {
  const examples = useMemo(() => {
    // Prefer cartridge-defined prompts
    if (suggestedPrompts.length > 0) return suggestedPrompts.slice(0, 4);
    // Fallback to tool-based examples
    const picks: string[] = [];
    for (const toolId of tools) {
      if (TOOL_EXAMPLES[toolId] && picks.length < 4) {
        picks.push(TOOL_EXAMPLES[toolId]);
      }
    }
    if (picks.length === 0) {
      picks.push("Hello! What can you do?", "Tell me about yourself");
    }
    return picks;
  }, [tools, suggestedPrompts]);

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-3 sm:px-6 py-4 sm:py-8 min-h-0 select-none">
      <div className="text-4xl sm:text-5xl mb-2 sm:mb-3 drop-shadow-lg" style={{ filter: 'drop-shadow(0 0 12px var(--glow))' }}>{cartridgeIcon}</div>
      <div className="text-sm sm:text-base font-bold text-white/75 mb-0.5">
        {cartridgeName}
      </div>
      <div className="text-[11px] text-[var(--accent)]/50 font-mono text-center max-w-sm mb-5 sm:mb-8">
        {bootMessage}
      </div>

      {/* Example prompts — 2-col grid on desktop */}
      <div className="w-full max-w-lg mb-5 sm:mb-8">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 sm:gap-2">
          {examples.map((prompt, i) => (
            <button
              key={i}
              onClick={() => onSendPrompt(prompt)}
              className="text-left px-3 py-2.5 rounded-lg border border-white/[0.05] hover:border-[var(--accent)]/25 bg-white/[0.02] hover:bg-[var(--accent)]/[0.04] text-white/35 hover:text-white/70 text-[11px] sm:text-xs font-mono transition-all leading-relaxed group cursor-pointer active:scale-[0.99]"
            >
              <span className="opacity-40 group-hover:opacity-70 mr-1">›</span> {prompt}
            </button>
          ))}
        </div>
      </div>

      {/* Tool badges — compact */}
      {tools.length > 0 && (
        <div className="flex flex-wrap justify-center gap-1 mb-5 max-w-md">
          {tools.map(toolId => {
            const meta = getToolMeta(toolId);
            const display = TOOL_DISPLAY[toolId] || toolId.replace(/_/g, " ");
            return (
              <div key={toolId} className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-white/[0.02] border border-white/[0.04] text-[8px] font-mono">
                <span style={{ color: `${meta.color}66` }}>{meta.icon}</span>
                <span className="text-white/20">{display}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Keyboard hints */}
      <div className="hidden sm:flex items-center gap-4 text-[10px] text-white/25 font-mono">
        <span>⌘K commands</span>
        <span className="text-white/10">·</span>
        <span>⌘N new chat</span>
        <span className="text-white/10">·</span>
        <span>⌘/ tutorial</span>
      </div>
    </div>
  );
}

/** Strip raw tags from content for clean display */
function cleanContent(text: string): string {
  let c = text;
  c = c.replace(/<think>[\s\S]*?<\/think>/gi, "");
  c = c.replace(/<think>[\s\S]*$/gi, "");
  c = c.replace(/<\/think>/gi, "");
  c = c.replace(/<tool_call>[\s\S]*?<\/tool_call>/gi, "");
  c = c.replace(/<tool_call>[\s\S]*$/gi, "");
  c = c.replace(/<\/tool_call>/gi, "");
  return c.trim();
}

// ═══════════════════════════════════════════
// MAIN CONSOLE COMPONENT
// ═══════════════════════════════════════════

export default function Console({ onChangeCartridge, onOpenForge }: { onChangeCartridge: () => void; onOpenForge?: () => void }) {
  const { activeConfig, ejectCartridge, availableCartridges } = useCartridgeStore();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [showExplorer, setShowExplorer] = useState(false);
  const [showDrawer, setShowDrawer] = useState(false);
  const [attachments, setAttachments] = useState<{path: string, name: string}[]>([]);
  const [contextInfo, setContextInfo] = useState<{message_count: number, estimated_tokens: number, max_tokens: number} | null>(null);
  const [chatId, setChatId] = useState<string | null>(null);
  const chatIdRef = useRef<string | null>(null);
  // Streaming state — not part of messages until finalized
  const [streamSegments, setStreamSegments] = useState<Segment[]>([]);
  const [muted, setMutedState] = useState(false);
  const { setActiveChatId, loadChatList } = useChatStore();
  
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editingText, setEditingText] = useState("");
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const [showPalette, setShowPalette] = useState(false);
  const [showTutorial, setShowTutorial] = useState(false);
  const [showSnake, setShowSnake] = useState(false);
  const redDotClicks = useRef(0);
  const redDotTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const thinkStartRef = useRef<number>(0);
  const abortRef = useRef<AbortController | null>(null);
  const pinnedToBottom = useRef(true);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileUploadRef = useRef<HTMLInputElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);
  const isLocal = typeof window !== "undefined" ? isLocalClient() : true;

  // Derive cartridge info early (used by handlers below)
  const currentCartridge = activeConfig ? availableCartridges.find(c => c.id === activeConfig.active_cartridge_ids[0]) : null;
  const showWelcome = messages.length === 0 && !!activeConfig;

  // Sync mute state on mount
  useEffect(() => {
    setMutedState(isMuted());
  }, []);

  const toggleMute = () => {
    const next = !muted;
    setMutedState(next);
    setMuted(next);
    if (!next) soundTick();
  };

  const handleLoadChat = (loadedMessages: any[], _cartridgeIds: string[], loadedChatId?: string) => {
    setMessages(loadedMessages);
    if (loadedChatId) {
      setChatId(loadedChatId);
      chatIdRef.current = loadedChatId;
      setActiveChatId(loadedChatId);
    }
    setContextInfo(null);
    setStreamSegments([]);
    setEditingIdx(null);
  };

  const handleNewChat = () => {
    soundNewChat();
    setMessages([]);
    setChatId(null);
    chatIdRef.current = null;
    setActiveChatId(null);
    setContextInfo(null);
    setStreamSegments([]);
    setEditingIdx(null);
    setAttachments([]);
  };

  // ─── Render message to Markdown (for export/copy) ───
  const messageToMarkdown = (msg: Message): string => {
    if (msg.role === "user") return `**You:** ${msg.content}`;
    if (!msg.segments || msg.segments.length === 0) return msg.content;
    const parts: string[] = [];
    for (const seg of msg.segments) {
      if (seg.kind === "thinking") continue;
      if (seg.kind === "text" && seg.content.trim()) {
        parts.push(seg.content);
      } else if (seg.kind === "tool") {
        const tool = seg as ToolCallSegment;
        const toolLabel = TOOL_DISPLAY[tool.name] || tool.name;
        const code = tool.args?.code || tool.args?.command || tool.args?.query || tool.args?.expression || "";
        if (code) {
          const lang = tool.name === "execute_python" ? "python" : tool.name === "execute_cpp" ? "cpp" : tool.name === "run_command" ? "bash" : "";
          parts.push(`> **${toolLabel}**\n\n\`\`\`${lang}\n${code}\n\`\`\``);
        } else {
          parts.push(`> **${toolLabel}**: \`${JSON.stringify(tool.args)}\``);
        }
        if (tool.result && tool.result !== "Code executed successfully (no output).") {
          const preview = tool.result.length > 500 ? tool.result.slice(0, 500) + "\n..." : tool.result;
          parts.push(`<details><summary>Output</summary>\n\n\`\`\`\n${preview}\n\`\`\`\n</details>`);
        }
        if (tool.images && tool.images.length > 0) {
          parts.push(`*[${tool.images.length} visualization(s) generated]*`);
        }
      }
    }
    return parts.join("\n\n");
  };

  // ─── Export chat as Markdown ───
  const handleExportChat = () => {
    if (messages.length === 0) return;
    const cartName = currentCartridge?.name || activeConfig?.active_cartridge_ids[0] || "chat";
    const lines = messages.map(m => messageToMarkdown(m)).join("\n\n---\n\n");
    const md = `# ${cartName} — Chat Export\n\n${lines}\n`;
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${cartName.toLowerCase().replace(/\s+/g, "-")}-${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
    soundTick();
  };

  // ─── Copy full conversation to clipboard ───
  const handleCopyChat = () => {
    if (messages.length === 0) return;
    const text = messages.map(m => messageToMarkdown(m)).join("\n\n---\n\n");
    navigator.clipboard.writeText(text);
    soundTick();
  };

  // ─── Global keyboard shortcuts ───
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey;
      // ⌘K — toggle command palette
      if (meta && e.key === "k") { e.preventDefault(); setShowPalette(p => !p); return; }
      // ⌘N — new chat
      if (meta && e.key === "n") { e.preventDefault(); handleNewChat(); return; }
      // ⌘E — export chat
      if (meta && e.key === "e") { e.preventDefault(); handleExportChat(); return; }
      // ⌘⇧C — copy full conversation
      if (meta && e.shiftKey && e.key === "C") { e.preventDefault(); handleCopyChat(); return; }
      // ⌘⇧F — open forge
      if (meta && e.shiftKey && e.key === "F") { e.preventDefault(); onOpenForge?.(); return; }
      // ⌘/ — toggle help
      if (meta && e.key === "/") { e.preventDefault(); setShowTutorial(t => !t); return; }
      // ⌘. — focus input
      if (meta && e.key === ".") { e.preventDefault(); inputRef.current?.focus(); return; }
      // Escape — close overlays or stop generation
      if (e.key === "Escape") {
        if (showPalette) { setShowPalette(false); return; }
        if (showTutorial) { setShowTutorial(false); return; }
        if (showExplorer) { setShowExplorer(false); return; }
        if (showDrawer) { setShowDrawer(false); return; }
        if (isGenerating) { handleStop(); return; }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showPalette, showTutorial, showExplorer, showDrawer, isGenerating, messages]);

  // ─── Stop generation ───
  const handleStop = () => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
  };

  // ─── Retry last assistant response ───
  const handleRetry = (msgIdx: number) => {
    if (isGenerating) return;
    // Find the user message right before this assistant message
    const assistantIdx = msgIdx;
    if (assistantIdx < 1 || messages[assistantIdx]?.role !== "assistant") return;
    const userIdx = assistantIdx - 1;
    if (messages[userIdx]?.role !== "user") return;
    // Truncate to just before the assistant message, then re-submit
    const truncated = messages.slice(0, assistantIdx);
    setMessages(truncated);
    soundTick();
    // Re-submit via a delayed call so state settles
    setTimeout(() => {
      submitFromMessages(truncated, messages[userIdx].content);
    }, 50);
  };

  // ─── Edit a user message ───
  const handleStartEdit = (idx: number) => {
    if (isGenerating || messages[idx]?.role !== "user") return;
    setEditingIdx(idx);
    setEditingText(messages[idx].content);
  };

  const handleCancelEdit = () => {
    setEditingIdx(null);
    setEditingText("");
  };

  const handleConfirmEdit = () => {
    if (editingIdx === null || !editingText.trim()) return;
    // Truncate everything after the edited message and re-submit
    const truncated = messages.slice(0, editingIdx);
    const editedMsg: Message = { role: "user", content: editingText.trim() };
    setMessages([...truncated, editedMsg]);
    setEditingIdx(null);
    setEditingText("");
    soundTick();
    setTimeout(() => {
      submitFromMessages([...truncated, editedMsg], editedMsg.content);
    }, 50);
  };

  // ─── Revert conversation to a specific message ───
  const handleRevert = (idx: number) => {
    if (isGenerating) return;
    // Keep messages up to and including idx
    setMessages(messages.slice(0, idx + 1));
    setStreamSegments([]);
    soundTick();
  };

  // ─── Delete a single message ───
  const handleDeleteMessage = (idx: number) => {
    if (isGenerating) return;
    // Don't allow deleting if it's the boot message (idx 0, assistant)
    if (idx === 0 && messages[0]?.role === "assistant") return;
    setMessages((prev) => prev.filter((_, i) => i !== idx));
    soundTick();
  };

  // ─── Copy assistant message content ───
  const handleCopy = (idx: number) => {
    const msg = messages[idx];
    if (!msg) return;
    const text = msg.content || msg.segments?.filter(s => s.kind === "text").map(s => (s as TextSegment).content).join("\n\n") || "";
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    soundTick();
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const mdComponents = useMemo<Components>(() => ({
    code({ className, children, ...props }) {
      const match = /language-(\w+)/.exec(className || "");
      const codeStr = String(children).replace(/\n$/, "");
      if (match) {
        // Render mermaid diagrams as actual diagrams
        if (match[1] === "mermaid") {
          return <MermaidDiagram code={codeStr} />;
        }
        return (
          <div className="relative group my-3">
            <div className="flex items-center justify-between px-4 py-1.5 bg-white/5 border-b border-white/5 rounded-t-md">
              <span className="text-[10px] uppercase tracking-widest text-white/30 font-mono">{match[1]}</span>
            </div>
            <CopyButton text={codeStr} />
            <SyntaxHighlighter
              style={vscDarkPlus}
              language={match[1]}
              PreTag="div"
              customStyle={{
                margin: 0,
                borderRadius: "0 0 6px 6px",
                background: "rgba(0,0,0,0.6)",
                fontSize: "13px",
                border: "1px solid rgba(255,255,255,0.06)",
                borderTop: "none",
              }}
              codeTagProps={{ style: { fontFamily: "var(--font-mono), monospace" } }}
            >
              {codeStr}
            </SyntaxHighlighter>
          </div>
        );
      }
      return <code className={className} {...props}>{children}</code>;
    },
    table({ children }) {
      return <div className="overflow-x-auto my-4"><table>{children}</table></div>;
    },
    blockquote({ children }) {
      return (
        <blockquote className="border-l-2 border-[var(--accent)]/40 pl-4 my-3 text-white/60 italic">
          {children}
        </blockquote>
      );
    },
  }), []);

  // Handle clicking an example prompt from the welcome screen
  const handleWelcomePrompt = (prompt: string) => {
    if (isGenerating || !activeConfig) return;
    const msgs: Message[] = [];
    if (activeConfig.boot_messages.length > 0) {
      msgs.push({ role: "assistant", content: activeConfig.boot_messages[0] });
    }
    const userMsg: Message = { role: "user", content: prompt };
    msgs.push(userMsg);
    setMessages(msgs);
    submitFromMessages(msgs, prompt);
  };

  // Track user scroll position
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = el;
      pinnedToBottom.current = scrollHeight - scrollTop - clientHeight < 80;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  // Auto-scroll — only when pinned to bottom AND actively generating
  useEffect(() => {
    if (scrollRef.current && pinnedToBottom.current && isGenerating) {
      requestAnimationFrame(() => {
        // Re-check pinnedToBottom inside rAF to handle race with user scroll
        if (scrollRef.current && pinnedToBottom.current) {
          scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
      });
    }
  }, [streamSegments, isGenerating]);

  // Scroll once when new messages arrive (user send / finalize)
  useEffect(() => {
    if (scrollRef.current && pinnedToBottom.current) {
      requestAnimationFrame(() => {
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      });
    }
  }, [messages.length]);

  // Pin to bottom when generation starts
  useEffect(() => {
    if (isGenerating) {
      pinnedToBottom.current = true;
    }
  }, [isGenerating]);

  // Auto-resize textarea
  const adjustTextareaHeight = () => {
    const el = inputRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    }
  };

  // Insert text at cursor position in textarea
  const insertAtCursor = useCallback((text: string) => {
    const ta = inputRef.current;
    if (!ta) { setInput(prev => prev + text); return; }
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    setInput(prev => prev.slice(0, start) + text + prev.slice(end));
    setTimeout(() => {
      ta.selectionStart = ta.selectionEnd = start + text.length;
      ta.focus();
      adjustTextareaHeight();
    }, 0);
  }, []);

  // File selection from explorer (local clients)
  const handleFileSelect = (path: string) => {
    const name = path.split('/').pop() || path;
    if (!attachments.some(a => a.path === path)) {
      setAttachments(prev => [...prev, { path, name }]);
      insertAtCursor(`@${name} `);
    }
    setShowExplorer(false);
  };

  const removeAttachment = (idx: number) => {
    const att = attachments[idx];
    setAttachments(prev => prev.filter((_, i) => i !== idx));
    if (att) {
      setInput(prev => prev.replace(new RegExp(`@${att.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s?`, 'g'), ''));
    }
  };

  // Handle file upload from native file picker (network/mobile clients)
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const formData = new FormData();
      formData.append('file', file, file.name);
      try {
        const res = await fetch(`${getApiBase()}/api/fs/upload`, {
          method: 'POST', body: formData,
        });
        if (res.ok) {
          const data = await res.json();
          if (data.path) {
            const fname = data.filename || file.name;
            setAttachments(prev => [...prev, { path: data.path, name: fname }]);
            insertAtCursor(`@${fname} `);
          }
        }
      } catch (err) {
        console.error('Failed to upload file:', err);
      }
    }
    if (fileUploadRef.current) fileUploadRef.current.value = '';
  };

  // Handle paste — support pasting images
  const handlePaste = async (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.type.startsWith('image/')) {
        e.preventDefault();
        const blob = item.getAsFile();
        if (!blob) continue;
        const formData = new FormData();
        const fname = `paste_${Date.now()}.png`;
        formData.append('file', blob, fname);
        try {
          const res = await fetch(`${getApiBase()}/api/fs/upload`, {
            method: 'POST', body: formData,
          });
          if (res.ok) {
            const data = await res.json();
            if (data.path) {
              const pastedName = data.filename || fname;
              setAttachments(prev => [...prev, { path: data.path, name: pastedName }]);
              insertAtCursor(`@${pastedName} `);
            }
          }
        } catch (err) {
          console.error('Failed to upload pasted image:', err);
        }
        return;
      }
    }
  };

  // ─── Core streaming function (used by submit, retry, edit) ───
  const submitFromMessages = async (msgHistory: Message[], _userContent: string, imagePath?: string) => {
    if (!activeConfig) return;
    setIsGenerating(true);
    setStreamSegments([]);
    soundSend();

    const controller = new AbortController();
    abortRef.current = controller;

    let segments: Segment[] = [];
    let rawAccumulated = "";

    const pushSegment = (seg: Segment) => {
      segments = [...segments, seg];
      setStreamSegments([...segments]);
    };

    const updateLastSegment = (updater: (s: Segment) => Segment) => {
      if (segments.length === 0) return;
      segments = [...segments.slice(0, -1), updater(segments[segments.length - 1])];
      setStreamSegments([...segments]);
    };

    const finalizeSegments = () => {
      // Collapse any open thinking
      const lastIdx = segments.length - 1;
      if (lastIdx >= 0 && segments[lastIdx].kind === "thinking" && !(segments[lastIdx] as ThinkingSegment).durationMs) {
        const duration = Date.now() - thinkStartRef.current;
        segments = [...segments.slice(0, -1), { ...segments[lastIdx], durationMs: duration, collapsed: true }];
      }
      const finalText = segments
        .filter((s) => s.kind === "text" && !(s as TextSegment).content.startsWith("⏳"))
        .map((s) => (s as TextSegment).content)
        .join("\n\n");
      setMessages((prev) => {
        const updated = [...prev, { role: "assistant" as const, content: finalText, segments: [...segments] }];
        // Auto-save chat after response completes
        const cid = chatIdRef.current;
        if (cid && activeConfig) {
          const saveable = updated.map(m => ({ role: m.role, content: m.content }));
          fetch(`${getApiBase()}/api/chats/${cid}/save`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ messages: saveable, cartridge_ids: activeConfig.active_cartridge_ids }),
          }).catch(e => console.error("Auto-save failed:", e));
        }
        return updated;
      });
      setStreamSegments([]);
      setIsGenerating(false);
      abortRef.current = null;
    };

    try {
      const response = await fetch(`${getApiBase()}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          cartridge_ids: activeConfig.active_cartridge_ids,
          messages: msgHistory,
          image_path: imagePath,
          chat_id: chatId,
        }),
      });

      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let sseBuffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        sseBuffer += decoder.decode(value, { stream: true });
        const events = sseBuffer.split("\n\n");
        // Keep the last (potentially incomplete) chunk in the buffer
        sseBuffer = events.pop() || "";
        
        for (const line of events) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;
          
          try {
            const data = JSON.parse(trimmed.substring(6));
            
            if (data.type === "chat_id") {
              setChatId(data.data);
              chatIdRef.current = data.data;
              setActiveChatId(data.data);
            } else if (data.type === "context_info") {
              setContextInfo(data.data);
            } else if (data.type === "memory_update") {
              // Memory update received (silent)
            } else if (data.type === "status") {
              const statusText = String(data.data);
              if (statusText.length > 0) {
                const last = segments[segments.length - 1];
                if (!last || last.kind !== "text" || !(last as TextSegment).content.startsWith("⏳")) {
                  pushSegment({ kind: "text", content: `⏳ ${statusText}` });
                } else {
                  updateLastSegment(() => ({ kind: "text", content: `⏳ ${statusText}` }));
                }
              }
            } else if (data.type === "think_token") {
              // Remove any ⏳ status placeholder
              if (segments.length > 0 && segments[segments.length - 1].kind === "text" && (segments[segments.length - 1] as TextSegment).content.startsWith("⏳")) {
                segments = segments.slice(0, -1);
              }
              const last = segments[segments.length - 1];
              if (!last || last.kind !== "thinking") {
                thinkStartRef.current = Date.now();
                pushSegment({ kind: "thinking", content: data.data, collapsed: false });
                soundThinkStart();
              } else {
                updateLastSegment((s) => ({ ...s, content: (s as ThinkingSegment).content + data.data }));
              }
            } else if (data.type === "think_end") {
              const duration = Date.now() - thinkStartRef.current;
              updateLastSegment((s) => ({
                ...s,
                durationMs: duration,
                collapsed: true,
              }));
              soundThinkEnd();
            } else if (data.type === "token") {
              rawAccumulated += data.data;
              const cleanText = cleanContent(rawAccumulated);
              if (cleanText) {
                // Remove ⏳ status placeholder if present
                if (segments.length > 0 && segments[segments.length - 1].kind === "text" && (segments[segments.length - 1] as TextSegment).content.startsWith("⏳")) {
                  segments = segments.slice(0, -1);
                }
                const last = segments[segments.length - 1];
                if (last && last.kind === "text") {
                  updateLastSegment(() => ({ kind: "text", content: cleanText }));
                } else {
                  pushSegment({ kind: "text", content: cleanText });
                }
              } else if (rawAccumulated.includes("<tool_call>") || rawAccumulated.includes("<tool_call")) {
                // Extract partial tool call info for live code preview
                const tagIdx = rawAccumulated.indexOf('<tool_call>');
                const afterTag = tagIdx >= 0 ? rawAccumulated.substring(tagIdx + 11) : '';
                const nameMatch = afterTag.match(/"name"\s*:\s*"([^"]+)"/);
                const toolName = nameMatch ? nameMatch[1] : '';

                // Try to extract partial code for Python/C++ tools
                let partialCode = '';
                if (toolName === 'execute_python' || toolName === 'execute_cpp') {
                  const codeMatch = afterTag.match(/"code"\s*:\s*"([\s\S]*?)$/);
                  if (codeMatch) {
                    try {
                      partialCode = codeMatch[1]
                        .replace(/\\n/g, '\n').replace(/\\t/g, '\t')
                        .replace(/\\"/g, '"').replace(/\\\\/g, '\\');
                      if (partialCode.endsWith('\\')) partialCode = partialCode.slice(0, -1);
                    } catch { /* ignore partial parse */ }
                  }
                }

                const last = segments[segments.length - 1];
                if (last && last.kind === "tool" && (last as ToolCallSegment).status === "preparing") {
                  updateLastSegment((s) => ({
                    ...s,
                    name: toolName || (s as ToolCallSegment).name,
                    args: partialCode ? { code: partialCode } : (s as ToolCallSegment).args,
                  } as ToolCallSegment));
                } else {
                  // Remove ⏳ placeholders and short fragments
                  while (segments.length > 0) {
                    const l = segments[segments.length - 1];
                    if (l.kind === "text") {
                      const txt = (l as TextSegment).content;
                      if (txt.startsWith("⏳") || txt.length < 30) {
                        segments = segments.slice(0, -1);
                        continue;
                      }
                    }
                    break;
                  }
                  pushSegment({
                    kind: "tool",
                    name: toolName || "preparing",
                    args: partialCode ? { code: partialCode } : {},
                    status: "preparing",
                  });
                }
              }
            } else if (data.type === "tool_start") {
              // Check if last segment is a "preparing" tool — replace it seamlessly
              const lastSeg = segments[segments.length - 1];
              if (lastSeg && lastSeg.kind === "tool" && (lastSeg as ToolCallSegment).status === "preparing") {
                updateLastSegment(() => ({
                  kind: "tool" as const,
                  name: data.data.name,
                  args: data.data.args,
                  status: "running" as const,
                }));
              } else {
                // Remove transient segments: ⏳ placeholders or short text fragments (< 30 chars like "this.")
                while (segments.length > 0) {
                  const last = segments[segments.length - 1];
                  if (last.kind === "text") {
                    const txt = (last as TextSegment).content;
                    if (txt.startsWith("⏳") || txt.length < 30) {
                      segments = segments.slice(0, -1);
                      continue;
                    }
                  }
                  break;
                }
                if (segments.length > 0 && segments[segments.length - 1].kind === "thinking") {
                  const duration = Date.now() - thinkStartRef.current;
                  const thinkIdx = segments.length - 1;
                  segments = segments.map((s, j) => j === thinkIdx ? { ...s, durationMs: duration, collapsed: true } : s);
                }
                pushSegment({
                  kind: "tool",
                  name: data.data.name,
                  args: data.data.args,
                  status: "running",
                });
              }
              soundToolStart();
            } else if (data.type === "consent_required") {
              updateLastSegment((s) => ({
                ...s,
                consentId: data.data.id,
                consentCommand: data.data.command,
                status: "consent",
              } as ToolCallSegment));
            } else if (data.type === "tool_result") {
              const imgs = data.data.images || [];
              const htmlArtifact = data.data.html || "";
              updateLastSegment((s) => ({
                ...s,
                result: data.data.result,
                images: imgs.length > 0 ? [...((s as ToolCallSegment).images || []), ...imgs] : (s as ToolCallSegment).images,
                html: htmlArtifact || (s as ToolCallSegment).html,
                status: "done",
              } as ToolCallSegment));
              soundToolDone();
              rawAccumulated = "";
            } else if (data.type === "done") {
              finalizeSegments();
              loadChatList();
              soundDone();
            } else if (data.type === "error") {
              const errText = typeof data.data === "string" ? data.data : JSON.stringify(data.data);
              segments = [...segments, { kind: "text" as const, content: `⚠️ ${errText}` }];
              finalizeSegments();
              soundError();
            }
          } catch {
            // Skip unparseable SSE lines silently
          }
        }
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        // User stopped generation — finalize what we have so far
        if (segments.length > 0) {
          finalizeSegments();
        } else {
          setStreamSegments([]);
          setIsGenerating(false);
        }
        soundTick();
        return;
      }
      const errMsg = error instanceof Error ? error.message : "Connection failed";
      setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ ${errMsg}` }]);
      setStreamSegments([]);
      setIsGenerating(false);
      abortRef.current = null;
      soundError();
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() && attachments.length === 0) return;
    if (isGenerating || !activeConfig) return;

    // Build content: replace @filename references with [Attached file: path] tags
    let userContent = input.trim();
    for (const att of attachments) {
      const escaped = att.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      userContent = userContent.replace(new RegExp(`@${escaped}`, 'g'), `[Attached file: ${att.path}]`);
    }

    // If first message, inject boot message as first assistant message
    let history = [...messages];
    if (history.length === 0 && activeConfig.boot_messages.length > 0) {
      history.push({ role: "assistant", content: activeConfig.boot_messages[0] });
    }

    const userMsg: Message = { role: "user", content: userContent };
    const newMessages = [...history, userMsg];
    setMessages(newMessages);
    setInput("");
    setAttachments([]);
    if (inputRef.current) inputRef.current.style.height = 'auto';
    
    // Extract image path from attachments
    const imageAtt = attachments.find(a => /\.(jpg|jpeg|png|webp|gif|bmp|tiff|svg)$/i.test(a.path));
    const imagePath = imageAtt?.path;

    await submitFromMessages(newMessages, userContent, imagePath);
  };

  // ─── Render user message content with file attachment chips ───
  const IMAGE_EXTS = /\.(jpe?g|png|gif|webp|bmp|svg|tiff?|heic|heif)$/i;
  const renderUserContent = (content: string) => {
    const parts = content.split(/(\[Attached file: [^\]]+\])/g);
    if (parts.length === 1) return content;
    const textParts: React.ReactNode[] = [];
    const imagePaths: string[] = [];
    parts.forEach((part, i) => {
      const match = part.match(/^\[Attached file: (.+)\]$/);
      if (match) {
        const filePath = match[1];
        const fileName = filePath.split('/').pop() || filePath;
        if (IMAGE_EXTS.test(fileName)) {
          imagePaths.push(filePath);
        }
        textParts.push(
          <span key={i} className="inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 rounded bg-black/20 text-black/80 text-[11px] font-mono align-middle">
            <FileText size={11} className="shrink-0" />
            {fileName}
          </span>
        );
      } else if (part) {
        textParts.push(<span key={i}>{part}</span>);
      }
    });
    return (
      <div>
        <span>{textParts}</span>
        {imagePaths.length > 0 && (
          <div className="mt-2 space-y-2">
            {imagePaths.map((p, i) => (
              <div key={i} className="rounded-lg overflow-hidden border border-black/10 max-w-[280px]">
                <img
                  src={`${getApiBase()}/api/fs/read-image?path=${encodeURIComponent(p)}`}
                  alt={p.split('/').pop() || 'Attached image'}
                  className="w-full rounded-lg"
                  loading="lazy"
                />
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  // ─── Consent handler for approve/deny buttons ───
  const handleConsent = useCallback(async (consentId: string, approved: boolean) => {
    try {
      await fetch(`${getApiBase()}/api/tool/consent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: consentId, approved }),
      });
      // Update the segment to show it's been handled
      setStreamSegments((prev) =>
        prev.map((s) =>
          s.kind === "tool" && (s as ToolCallSegment).consentId === consentId
            ? { ...s, status: "running" as const, consentId: undefined } as ToolCallSegment
            : s
        )
      );
    } catch (e) {
      console.error("Consent request failed:", e);
    }
  }, []);

  // ─── Render helper for segments ───
  const renderSegments = (segs: Segment[], isLive: boolean) => (
    <div className="space-y-1">
      {segs.map((seg, i) => {
        if (seg.kind === "thinking") {
          return (
            <ThinkingBlock
              key={`think-${i}`}
              segment={seg}
              onToggle={() => {
                if (isLive) {
                  setStreamSegments((prev) => prev.map((s, j) =>
                    j === i && s.kind === "thinking" ? { ...s, collapsed: !s.collapsed } : s
                  ));
                } else {
                  setMessages((prev) => prev.map((msg) => {
                    if (!msg.segments) return msg;
                    return {
                      ...msg,
                      segments: msg.segments.map((s, j) =>
                        j === i && s.kind === "thinking" ? { ...s, collapsed: !s.collapsed } : s
                      ),
                    };
                  }));
                }
              }}
            />
          );
        }
        if (seg.kind === "tool") {
          return <ToolCallCard key={`tool-${i}`} segment={seg} onConsent={handleConsent} />;
        }
        if (seg.kind === "text" && (seg as TextSegment).content.startsWith("⏳")) {
          const statusText = (seg as TextSegment).content.replace(/^⏳\s*/, '');
          return (
            <div key={`status-${i}`} className="flex items-center gap-2.5 py-2 text-[11px] font-mono text-white/30">
              <div className="flex gap-1 items-center">
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] dot-pulse" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] dot-pulse" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] dot-pulse" style={{ animationDelay: '300ms' }} />
              </div>
              <span>{statusText}</span>
            </div>
          );
        }
        if (seg.kind === "text" && seg.content.trim()) {
          return (
            <ReactMarkdown
              key={`text-${i}`}
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeKatex]}
              components={mdComponents}
            >
              {seg.content}
            </ReactMarkdown>
          );
        }
        return null;
      })}
    </div>
  );

  const themeStyle = activeConfig ? {
    "--accent": activeConfig.theme.accent_color,
    "--tint": activeConfig.theme.screen_tint,
    "--scanline": activeConfig.theme.scanline_intensity,
    "--glow": activeConfig.theme.glow_color,
  } as React.CSSProperties : {};

  return (
    <div 
      className="w-full max-w-5xl h-[100dvh] sm:h-[90vh] bg-[var(--color-console-bezel)] rounded-none sm:rounded-3xl p-3 sm:p-6 md:p-10 shadow-2xl flex flex-col border-0 sm:border border-white/5 relative"
      style={themeStyle}
    >
      {showExplorer && (
        <FileExplorer 
          onSelect={handleFileSelect} 
          onClose={() => setShowExplorer(false)} 
        />
      )}

      {showDrawer && (
        <ChatDrawer
          onLoadChat={handleLoadChat}
          onNewChat={handleNewChat}
          onClose={() => { setShowDrawer(false); loadChatList(); }}
        />
      )}

      {showPalette && (
        <CommandPalette
          onClose={() => setShowPalette(false)}
          onNewChat={handleNewChat}
          onOpenHistory={() => { setShowDrawer(true); soundTick(); }}
          onExportChat={handleExportChat}
          onCopyChat={handleCopyChat}
          onOpenForge={onOpenForge}
          onOpenHelp={() => setShowTutorial(true)}
          onToggleMute={toggleMute}
          onEjectCartridge={() => { soundCartridgeEject(); ejectCartridge(); onChangeCartridge(); }}
          isMuted={muted}
          cartridgeName={currentCartridge?.name || "Kasset"}
          hasMessages={messages.length > 0}
        />
      )}

      {showTutorial && (
        <Tutorial onClose={() => setShowTutorial(false)} />
      )}

      {showSnake && (
        <SnakeGame
          onClose={() => setShowSnake(false)}
          onUnlock={() => {
            if (typeof window !== "undefined") localStorage.setItem("kasset-nsfw-unlocked", "true");
          }}
        />
      )}

      {/* Hardware Accents — LEDs + context meter */}
      <div className="absolute top-2 sm:top-4 left-3 sm:left-6 flex items-center gap-2 sm:gap-3">
        <div className="flex gap-1.5 sm:gap-2">
          <button
            className="w-2.5 h-2.5 sm:w-3 sm:h-3 rounded-full bg-red-500 opacity-80 cursor-default"
            onClick={() => {
              redDotClicks.current++;
              if (redDotTimer.current) clearTimeout(redDotTimer.current);
              redDotTimer.current = setTimeout(() => { redDotClicks.current = 0; }, 1500);
              if (redDotClicks.current >= 5) {
                redDotClicks.current = 0;
                setShowSnake(true);
              }
            }}
          />
          <div className={`w-2.5 h-2.5 sm:w-3 sm:h-3 rounded-full ${isGenerating ? "bg-[var(--accent)] animate-pulse crt-glow" : "bg-white/20"}`} />
        </div>
        {contextInfo && (
          <div className="hidden sm:flex items-center gap-2 ml-2" title={`${contextInfo.estimated_tokens} / ${contextInfo.max_tokens} tokens`}>
            <div className="w-24 h-1.5 bg-black/40 rounded-full overflow-hidden border border-white/5">
              <div 
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${Math.min(100, (contextInfo.estimated_tokens / contextInfo.max_tokens) * 100)}%`,
                  background: contextInfo.estimated_tokens / contextInfo.max_tokens > 0.8 ? '#ef4444' : 
                              contextInfo.estimated_tokens / contextInfo.max_tokens > 0.5 ? '#eab308' : 'var(--accent)',
                }}
              />
            </div>
            <span className="text-[9px] text-white/30 font-mono">{messages.length} msg</span>
          </div>
        )}
      </div>
      
      {/* Top Bar — controls */}
      <div className="absolute top-2 sm:top-4 right-3 sm:right-8 flex items-center gap-0.5 sm:gap-1 no-select">
        <button onClick={handleNewChat} className="p-2 sm:p-1.5 rounded text-white/30 hover:text-[var(--accent)] hover:bg-white/5 active:bg-white/10 transition-all" title="New Chat (⌘N)">
          <Plus size={15} />
        </button>
        <button onClick={() => { setShowDrawer(true); soundTick(); }} className="p-2 sm:p-1.5 rounded text-white/30 hover:text-[var(--accent)] hover:bg-white/5 active:bg-white/10 transition-all" title="Chat History">
          <History size={15} />
        </button>
        <button onClick={() => { setShowPalette(true); soundTick(); }} className="p-2 sm:p-1.5 rounded text-white/30 hover:text-[var(--accent)] hover:bg-white/5 active:bg-white/10 transition-all" title="Command Palette (⌘K)">
          <Command size={15} />
        </button>
        {onOpenForge && (
          <button onClick={onOpenForge} className="p-2 sm:p-1.5 rounded text-white/30 hover:text-[var(--accent)] hover:bg-white/5 active:bg-white/10 transition-all" title="Kasset Forge (⌘⇧F)">
            <Wrench size={15} />
          </button>
        )}
        <button onClick={() => { setShowTutorial(true); soundTick(); }} className="p-2 sm:p-1.5 rounded text-white/30 hover:text-[var(--accent)] hover:bg-white/5 active:bg-white/10 transition-all" title="Quick Guide (⌘/)">
          <HelpCircle size={15} />
        </button>
        <button
          onClick={toggleMute}
          className={`hidden sm:block p-1.5 rounded transition-all ${muted ? "text-white/15" : "text-white/30 hover:text-[var(--accent)] hover:bg-white/5"}`}
          title={muted ? "Unmute sounds" : "Mute sounds"}
        >
          {muted ? <VolumeX size={15} /> : <Volume2 size={15} />}
        </button>
        <div className="hidden sm:block w-px h-4 bg-white/5 mx-1" />
        <div className="bg-black/40 border border-white/10 px-2 sm:px-3 py-1 rounded-lg text-[var(--accent)] font-bold text-[10px] sm:text-xs tracking-wider shadow-inner flex items-center gap-1.5 sm:gap-2 ml-0.5 sm:ml-1">
          {currentCartridge && <span className="text-sm sm:text-base leading-none">{currentCartridge.icon}</span>}
          <span className="max-w-[60px] sm:max-w-[120px] truncate text-glow">{currentCartridge?.name?.toUpperCase() || (activeConfig ? activeConfig.active_cartridge_ids[0].toUpperCase() : "NO KASSET")}</span>
          <button 
            onClick={() => { soundCartridgeEject(); ejectCartridge(); onChangeCartridge(); }}
            className="hover:text-white active:text-white transition-colors text-[var(--accent)]/50 hover:text-[var(--accent)]"
            title="Eject Kasset"
          >
            ⏏
          </button>
        </div>
      </div>

      {/* Screen Area */}
      <div className="flex-1 min-h-0 mt-8 sm:mt-10 rounded-xl sm:rounded-2xl border-2 sm:border-4 border-black/80 crt-screen p-3 sm:p-6 overflow-hidden flex flex-col relative">
        {showWelcome ? (
          <WelcomeScreen
            cartridgeName={currentCartridge?.name || activeConfig!.active_cartridge_ids[0]}
            cartridgeIcon={currentCartridge?.icon || "🤖"}
            bootMessage={activeConfig!.boot_messages[0] || "Ready."}
            tools={activeConfig!.tools}
            suggestedPrompts={activeConfig!.suggested_prompts || []}
            onSendPrompt={handleWelcomePrompt}
          />
        ) : (
        <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto crt-scroll pr-2 sm:pr-4 space-y-3 sm:space-y-4">
          {/* Compact tool info strip — always visible at top of chat */}
          {activeConfig && activeConfig.tools.length > 0 && (
            <div className="flex flex-wrap items-center gap-1 pb-2 border-b border-white/[0.04] sticky top-0 z-10 bg-black/80 backdrop-blur-sm pt-1 -mt-1">
              <span className="text-[9px] text-white/20 font-mono mr-1">Tools:</span>
              {activeConfig.tools.map(toolId => {
                const meta = getToolMeta(toolId);
                const display = TOOL_DISPLAY[toolId] || toolId.replace(/_/g, " ");
                return (
                  <div key={toolId} className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-white/[0.02] border border-white/[0.04] text-[8px] font-mono">
                    <span style={{ color: `${meta.color}66` }}>{meta.icon}</span>
                    <span className="text-white/20">{display}</span>
                  </div>
                );
              })}
            </div>
          )}
          {messages.map((msg, idx) => {
            const isUser = msg.role === "user";
            const isBot = msg.role === "assistant";
            const isLast = idx === messages.length - 1;
            const isBoot = idx === 0 && isBot;
            const isEditing = editingIdx === idx;

            return (
              <div 
                key={idx} 
                className={`group/msg flex ${isUser ? "justify-end" : "justify-start"}`}
              >
                <div className="relative max-w-[85%]">
                  {/* Message bubble */}
                  <div 
                    className={
                      isUser 
                        ? "bg-[var(--accent)] text-black px-4 py-2 rounded-l-lg rounded-tr-lg font-medium shadow-[0_0_15px_var(--tint)]" 
                        : "prose-crt"
                    }
                  >
                    {isUser ? (
                      isEditing ? (
                        <div className="flex flex-col gap-2 min-w-[200px]">
                          <textarea
                            value={editingText}
                            onChange={(e) => setEditingText(e.target.value)}
                            className="w-full bg-black/20 text-black border border-black/20 rounded px-2 py-1.5 text-sm font-mono resize-none outline-none"
                            rows={Math.min(6, editingText.split("\n").length + 1)}
                            autoFocus
                            onKeyDown={(e) => {
                              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleConfirmEdit(); }
                              if (e.key === "Escape") handleCancelEdit();
                            }}
                          />
                          <div className="flex justify-end gap-1.5">
                            <button
                              onClick={handleCancelEdit}
                              className="px-2 py-0.5 text-[10px] text-black/60 hover:text-black font-bold uppercase"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={handleConfirmEdit}
                              className="px-2 py-0.5 text-[10px] bg-black/20 rounded text-black font-bold uppercase hover:bg-black/30"
                            >
                              <CornerDownLeft size={10} className="inline mr-1" />
                              Submit
                            </button>
                          </div>
                        </div>
                      ) : (
                        renderUserContent(msg.content)
                      )
                    ) : msg.segments && msg.segments.length > 0 ? (
                      renderSegments(msg.segments, false)
                    ) : (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm, remarkMath]}
                        rehypePlugins={[rehypeKatex]}
                        components={mdComponents}
                      >
                        {cleanContent(msg.content)}
                      </ReactMarkdown>
                    )}
                  </div>

                  {/* Hover action buttons */}
                  {!isGenerating && !isEditing && !isBoot && (
                    <div className={`absolute ${isUser ? "left-0 -translate-x-full pr-1.5" : "right-0 translate-x-full pl-1.5"} top-0 opacity-30 sm:opacity-0 sm:group-hover/msg:opacity-100 transition-opacity flex flex-col gap-0.5`}>
                      {/* Copy — assistant only */}
                      {isBot && (
                        <button
                          onClick={() => handleCopy(idx)}
                          className="p-1 rounded text-white/20 hover:text-white/60 hover:bg-white/5 transition-all"
                          title="Copy response"
                        >
                          {copiedIdx === idx ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
                        </button>
                      )}
                      {/* Retry — last assistant only */}
                      {isBot && isLast && (
                        <button
                          onClick={() => handleRetry(idx)}
                          className="p-1 rounded text-white/20 hover:text-white/60 hover:bg-white/5 transition-all"
                          title="Regenerate response"
                        >
                          <RefreshCw size={12} />
                        </button>
                      )}
                      {/* Edit — user only */}
                      {isUser && (
                        <button
                          onClick={() => handleStartEdit(idx)}
                          className="p-1 rounded text-white/20 hover:text-white/60 hover:bg-white/5 transition-all"
                          title="Edit message"
                        >
                          <Pencil size={12} />
                        </button>
                      )}
                      {/* Revert — truncate to here */}
                      {!isLast && (
                        <button
                          onClick={() => handleRevert(idx)}
                          className="p-1 rounded text-white/20 hover:text-white/60 hover:bg-white/5 transition-all"
                          title="Revert to here (delete everything after)"
                        >
                          <Scissors size={12} />
                        </button>
                      )}
                      {/* Delete single message */}
                      {isUser && (
                        <button
                          onClick={() => handleDeleteMessage(idx)}
                          className="p-1 rounded text-white/20 hover:text-red-400/60 hover:bg-white/5 transition-all"
                          title="Delete message"
                        >
                          <Trash2 size={12} />
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {/* Live streaming segments */}
          {streamSegments.length > 0 && (
            <div className="flex justify-start">
              <div className="max-w-[85%] prose-crt">
                {renderSegments(streamSegments, true)}
              </div>
            </div>
          )}
        </div>
        )}
      </div>

      {/* Input Area */}
      <div className="mt-1.5 sm:mt-4 shrink-0">
        <form onSubmit={handleSubmit} className="bg-white/[0.04] border border-white/[0.08] rounded-xl sm:rounded-2xl px-2 sm:px-3 py-1.5 sm:py-2 focus-within:border-[var(--accent)]/20 transition-colors">
          {/* Hidden file input for network/mobile clients */}
          <input
            ref={fileUploadRef}
            type="file"
            multiple
            className="hidden"
            onChange={handleFileUpload}
          />
          {/* Input row */}
          <div className="flex items-end gap-1.5 sm:gap-2">
            <button 
              type="button" 
              onClick={() => isLocal ? setShowExplorer(true) : fileUploadRef.current?.click()}
              className="p-1.5 rounded-lg text-white/30 hover:text-[var(--accent)] hover:bg-white/5 active:bg-white/10 transition-all shrink-0 mb-0.5"
              title={isLocal ? "Attach file or directory" : "Upload file"}
            >
              <Paperclip size={16} />
            </button>
            <div className="flex-1 min-w-0 relative">
              {/* Mirror overlay — renders styled @mentions */}
              <div
                ref={mirrorRef}
                aria-hidden
                className="absolute inset-0 pointer-events-none text-sm sm:text-base py-1.5 font-mono leading-relaxed whitespace-pre-wrap break-words overflow-hidden"
              >
                {attachments.length > 0 ? (() => {
                  const attNames = attachments.map(a => a.name);
                  const pattern = new RegExp(`(@(?:${attNames.map(n => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')}))`, 'g');
                  const parts = input.split(pattern);
                  return parts.map((part, i) =>
                    attNames.some(n => part === `@${n}`)
                      ? <span key={i} className="bg-[var(--accent)]/15 text-[var(--accent)] rounded-sm">{part}</span>
                      : <span key={i} className="text-white/90">{part}</span>
                  );
                })() : <span className="text-transparent">{input}</span>}
                {!input && <span className="text-transparent">.</span>}
              </div>
              {/* Actual textarea — text transparent where mirror renders, caret visible */}
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => { setInput(e.target.value); adjustTextareaHeight(); }}
                onScroll={() => { if (mirrorRef.current && inputRef.current) mirrorRef.current.scrollTop = inputRef.current.scrollTop; }}
                onPaste={handlePaste}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit(e);
                  }
                }}
                disabled={isGenerating || !activeConfig}
                className={`w-full bg-transparent border-none outline-none placeholder-white/20 text-sm sm:text-base py-1.5 font-mono resize-none min-h-[28px] sm:min-h-[32px] max-h-[100px] sm:max-h-[120px] leading-relaxed relative z-10 ${attachments.length > 0 ? 'text-white/90 caret-white/90' : 'text-white/90'}`}
                style={attachments.length > 0 ? { color: 'transparent', caretColor: 'rgba(255,255,255,0.9)' } : undefined}
                placeholder={activeConfig ? "Message..." : "Insert a kasset to begin..."}
                rows={1}
                autoFocus
              />
            </div>
            {isGenerating ? (
              <button 
                type="button"
                onClick={handleStop}
                className="p-2 rounded-xl bg-red-500/15 text-red-400 hover:bg-red-500/25 border border-red-500/20 transition-all shrink-0 mb-0.5"
                title="Stop generating"
              >
                <Square size={16} fill="currentColor" />
              </button>
            ) : (
              <button 
                type="submit"
                disabled={(!input.trim() && attachments.length === 0) || !activeConfig}
                className="p-2 rounded-xl bg-[var(--accent)]/15 text-[var(--accent)] hover:bg-[var(--accent)]/25 border border-[var(--accent)]/20 transition-all disabled:opacity-20 disabled:hover:bg-[var(--accent)]/15 shrink-0 mb-0.5"
                title="Send message"
              >
                <CornerDownLeft size={16} />
              </button>
            )}
          </div>
        </form>
        {/* Subtle action hints — desktop only */}
        <div className="hidden sm:flex items-center justify-center gap-4 mt-1.5 text-[10px] text-white/25 font-mono select-none">
          <span>⌘K commands</span>
          <span className="text-white/10">·</span>
          <span>⇧↵ newline</span>
          <span className="text-white/10">·</span>
          <span>⌘/ tutorial</span>
          <span className="text-white/10">·</span>
          <span>📎 attach files</span>
        </div>
      </div>
    </div>
  );
}
