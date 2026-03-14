"use client";

import React, { useState, useRef, useEffect, useMemo, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import FileExplorer from "./explorer/FileExplorer";
import ChatDrawer from "./ChatDrawer";
import { ErrorBoundary } from "./ErrorBoundary";
import { showToast } from "./Toast";
import CommandPalette from "./CommandPalette";
import type { ToolCallSegment, ThinkingSegment, TextSegment, InteractiveSegment, Segment, Message } from "./chat/types";
import { TOOL_META, getToolMeta, TOOL_DISPLAY, TOOL_EXAMPLES } from "./chat/toolMeta";
import ThinkingBlock from "./chat/ThinkingBlock";
import ToolCallCard from "./chat/ToolCallCard";
import InteractiveWidget from "./chat/InteractiveWidget";
import ErrorRecovery from "./chat/ErrorRecovery";
import DraftBlock, { DraftContext } from "./chat/DraftBlock";
import WelcomeScreen from "./chat/WelcomeScreen";
import MentalModelWidget from "./chat/MentalModelWidget";
import Tutorial from "./Tutorial";
import { useCartridgeStore } from "@/stores/cartridgeStore";
import { useChatStore } from "@/stores/chatStore";
import { useSettingsStore } from "@/stores/settingsStore";
import { useUIStore } from "@/stores/uiStore";
import { useAutoScroll } from "./console/hooks/useAutoScroll";
import { useAttachments } from "./console/hooks/useAttachments";
import { useMarkdownComponents } from "./console/MarkdownComponents";
import ConsoleHeader from "./console/ConsoleHeader";
import ConsoleFooter from "./console/ConsoleFooter";
import { X, Copy, Check, History, Square, RefreshCw, Pencil, Scissors, CornerDownLeft, Paperclip, Command, ThumbsUp, ThumbsDown, FileText } from "lucide-react";
import { soundSend, soundThinkStart, soundThinkEnd, soundToolStart, soundToolDone, soundDone, soundError, soundNewChat, soundTick, soundCartridgeEject, isMuted, setMuted } from "@/lib/sounds";
import { getApiBase, isLocalClient } from "@/lib/api";
import SignalProcessor from "./SignalProcessor";
import ImagePanel from "./image/ImagePanel";
import { useImageStore, useCanvasSync } from "@/stores/imageStore";

// ═══════════════════════════════════════════
// SUB-COMPONENTS (CopyButton + HtmlPreviewBlock extracted to console/MarkdownComponents.tsx)
// ═══════════════════════════════════════════

/** Strip raw tags and leaked JSON fragments from content for clean display */
const _cleanRegexes = [
  { re: /<think>[\s\S]*?<\/think>/gi },
  { re: /<think>[\s\S]*$/gi },
  { re: /<\/think>/gi },
  { re: /<tool_call>[\s\S]*?<\/tool_call>/gi },
  { re: /<tool_call>[\s\S]*$/gi },
  { re: /<\/tool_call>/gi },
  { re: /<\|tool_call\|>[\s\S]*?<\|\/tool_call\|>/gi },
  { re: /<\|tool_call\|>[\s\S]*$/gi },
  { re: /<\|\/tool_call\|>/gi },
  // Qwen3-Coder native XML tool call format
  { re: /<function=\w+>[\s\S]*?<\/function>/gi },
  { re: /<function=\w+>[\s\S]*$/gi },
  { re: /<\/function>/gi },
  // Leaked <answer> tags (Qwen3.5 sometimes wraps answers)
  { re: /<\/?answer>/gi },
  // Leaked JSON fragments from truncated tool calls (e.g. '"}> properly.' or '"}> time.')
  { re: /"\s*\}\s*>\s*[^<\n]{0,30}\.?\s*$/gm },
  // Raw JSON tool call objects that leaked through
  { re: /\{"name"\s*:\s*"[\w]+"\s*,\s*"arguments"\s*:\s*\{[\s\S]*?\}\s*\}/gi },
  // Backend placeholder text that can leak into output
  { re: /\(used tool\)/gi },
  { re: /\[Calling tool\.\.\.\]/gi },
];

function cleanContent(text: string): string {
  let c = text;
  for (const { re } of _cleanRegexes) {
    re.lastIndex = 0;
    c = c.replace(re, "");
  }
  // Clean up multiple blank lines left behind after stripping
  c = c.replace(/\n{3,}/g, "\n\n");
  return c.trim();
}

/**
 * Lightweight streaming extractor: instead of running full cleanContent on every token,
 * extract only the visible text after </think> (if present) and before <tool_call>.
 * O(1) string operations per token instead of 6 regex passes.
 */
function extractStreamText(accumulated: string): string {
  let start = 0;
  const thinkEnd = accumulated.lastIndexOf("</think>");
  if (thinkEnd >= 0) {
    start = thinkEnd + 8;
  } else if (accumulated.includes("<think>")) {
    return ""; // Still inside thinking block
  }
  let text = accumulated.substring(start);
  // Strip </tool_call> tags and anything after them
  text = text.replace(/<\/tool_call>[\s\S]*/gi, '');
  // Strip </think> tags that leak into visible text
  text = text.replace(/<\/think>/gi, '');
  // Trim anything from tool call tags onward (all formats)
  const toolIdx = text.indexOf("<tool_call>");
  if (toolIdx >= 0) text = text.substring(0, toolIdx);
  const toolIdx2 = text.indexOf("<|tool_call|>");
  if (toolIdx2 >= 0) text = text.substring(0, toolIdx2);
  // Qwen3-Coder XML format: <function=name>...
  const funcIdx = text.search(/<function=\w+>/);
  if (funcIdx >= 0) text = text.substring(0, funcIdx);
  // Strip leaked <answer> / </answer> tags
  text = text.replace(/<\/?answer>/gi, '');
  // Strip trailing JSON closers leaked from tool calls (e.g. '"}}' or '"}}  ')
  text = text.replace(/"\s*\}\s*\}\s*$/gm, '');
  // Trim leaked JSON fragments like '"}> properly.'
  const jsonLeakIdx = text.search(/"\s*\}\s*>\s*[^<\n]{0,30}\.?\s*$/m);
  if (jsonLeakIdx >= 0) text = text.substring(0, jsonLeakIdx);
  // Trim raw JSON tool call objects
  const rawJsonIdx = text.indexOf('{"name"');
  if (rawJsonIdx >= 0) text = text.substring(0, rawJsonIdx);
  // Strip backend placeholder text that can leak through
  text = text.replace(/\[Calling tool\.\.\.\]/gi, '');
  text = text.replace(/\(used tool\)/gi, '');
  return text.trim();
}

function collapseExactDouble(text: string): string {
  const t = text.trim();
  if (t.length < 300) return t;
  // 1. Exact-half dedup (original logic)
  const minChunk = Math.floor(t.length * 0.3);
  const maxChunk = Math.floor(t.length * 0.7);
  for (let cut = minChunk; cut <= maxChunk; cut++) {
    const a = t.slice(0, cut).trim();
    const b = t.slice(cut).trim();
    if (a.length > 100 && a === b) return a;
  }
  // 2. Paragraph-level dedup: remove duplicate paragraph blocks (≥3 lines)
  const paragraphs = t.split(/\n{2,}/);
  if (paragraphs.length >= 4) {
    const seen = new Set<string>();
    const unique: string[] = [];
    for (const p of paragraphs) {
      const key = p.trim().toLowerCase().replace(/\s+/g, " ");
      if (key.length > 80 && seen.has(key)) continue;
      if (key.length > 80) seen.add(key);
      unique.push(p);
    }
    if (unique.length < paragraphs.length) {
      return unique.join("\n\n");
    }
  }
  return t;
}

function mergeAssistantTextSegments(segs: Segment[]): string {
  const blocks = segs
    .filter((s) => s.kind === "text")
    .map((s) => {
      const raw = typeof (s as TextSegment).content === "string"
        ? (s as TextSegment).content
        : JSON.stringify((s as TextSegment).content ?? "");
      return cleanContent(raw);
    })
    .filter((t) => t && !t.startsWith("⏳"));

  let merged = "";
  for (const next of blocks) {
    if (!merged) {
      merged = next;
      continue;
    }

    const current = merged.trim();
    const candidate = next.trim();
    if (!candidate) continue;

    // If candidate is already contained, skip duplicate snapshot.
    if (current.includes(candidate)) continue;

    // If model re-emits the full answer as a longer snapshot, replace.
    if (candidate.includes(current) && current.length > 120) {
      merged = candidate;
      continue;
    }

    // Overlap-aware append (handles continuation across tool rounds).
    const maxOverlap = Math.min(current.length, candidate.length, 1200);
    let overlap = 0;
    for (let size = maxOverlap; size >= 40; size--) {
      if (current.slice(-size) === candidate.slice(0, size)) {
        overlap = size;
        break;
      }
    }

    merged = overlap > 0
      ? `${current}${candidate.slice(overlap)}`
      : `${current}\n\n${candidate}`;
  }

  return collapseExactDouble(merged);
}

// ═══════════════════════════════════════════
// MAIN CONSOLE COMPONENT
// ═══════════════════════════════════════════

export default function Console({ onChangeCartridge, onOpenForge }: { onChangeCartridge: () => void; onOpenForge?: () => void }) {
  const { activeConfig, ejectCartridge, availableCartridges, loadActiveStack, loadAvailableCartridges } = useCartridgeStore();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [modelName, setModelName] = useState("");
  const [attachments, setAttachments] = useState<{path: string, name: string}[]>([]);
  const [contextInfo, setContextInfo] = useState<{message_count: number, estimated_tokens: number, max_tokens: number} | null>(null);
  const [chatId, setChatId] = useState<string | null>(null);
  const chatIdRef = useRef<string | null>(null);
  // Streaming state — not part of messages until finalized
  const [streamSegments, setStreamSegments] = useState<Segment[]>([]);
  const [muted, setMutedState] = useState(false);
  const { setActiveChatId, loadChatList, memories, loadMemories } = useChatStore();
  const { context: ctxSettings, loadSettings: loadCtxSettings } = useSettingsStore();
  
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editingText, setEditingText] = useState("");
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const [messageFeedback, setMessageFeedback] = useState<Record<number, 'up' | 'down'>>({});

  // UI overlay state — extracted to Zustand store
  const {
    showExplorer, setShowExplorer,
    showDrawer, setShowDrawer,
    drawerTab, setDrawerTab,
    drawerFocusSearch, setDrawerFocusSearch,
    drawerAutoPreview, setDrawerAutoPreview,
    showPalette, setShowPalette,
    showTutorial, setShowTutorial,
    showSnake: showSignalDebug, setShowSnake: setShowSignalDebug,
    showQuickSettings, setShowQuickSettings,
    showMentalModel, setShowMentalModel,
    togglePalette, toggleTutorial,
  } = useUIStore();

  const redDotClicks = useRef(0);
  const redDotTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sessionStartRef = useRef(Date.now());

  // Auto-scroll management — extracted to hook
  const { scrollRef, pinnedToBottom } = useAutoScroll(isGenerating, streamSegments, messages.length);
  const thinkStartRef = useRef<number>(0);
  const abortRef = useRef<AbortController | null>(null);
  const rafIdRef = useRef<number | null>(null);        // 5.1: track RAF for cleanup on unmount
  const activeConfigRef = useRef(activeConfig);         // 5.2: always-current config for closures
  activeConfigRef.current = activeConfig;
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileUploadRef = useRef<HTMLInputElement>(null);
  const chatImportRef = useRef<HTMLInputElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);
  const qsAnchorDesktopRef = useRef<HTMLButtonElement>(null);
  const qsAnchorMobileRef = useRef<HTMLButtonElement>(null);
  const isLocal = typeof window !== "undefined" ? isLocalClient() : true;

  // Derive cartridge info early (used by handlers below)
  const currentCartridge = activeConfig ? availableCartridges.find(c => c.id === activeConfig.active_cartridge_ids[0]) : null;
  const showWelcome = messages.length === 0 && !!activeConfig;

  // Cleanup RAF on unmount (5.1)
  useEffect(() => {
    return () => {
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
    };
  }, []);

  // Sync mute state on mount
  useEffect(() => {
    setMutedState(isMuted());
  }, []);

  // Load system info on mount (memories, settings, model name)
  useEffect(() => {
    loadMemories();
    loadCtxSettings();
    fetch(`${getApiBase()}/api/models`).then(r => r.json()).then(d => {
      if (d.current) setModelName(d.current.split("/").pop() || "");
    }).catch(() => {});
  }, [loadMemories, loadCtxSettings]);

  const toggleMute = () => {
    const next = !muted;
    setMutedState(next);
    setMuted(next);
    if (!next) soundTick();
  };

  const handleLoadChat = (loadedMessages: any[], _cartridgeIds: string[], loadedChatId?: string) => {
    // Hydrate + normalize assistant messages for stable rendering/persistence
    const hydrated = loadedMessages.map((m: any) => {
      if (m.role === "assistant" && Array.isArray(m.segments) && m.segments.length > 0) {
        return { ...m, content: mergeAssistantTextSegments(m.segments) || m.content || "" };
      }
      if (m.role === "assistant" && (!m.segments || m.segments.length === 0) && m.content) {
        const normalized = collapseExactDouble(cleanContent(String(m.content)));
        return { ...m, content: normalized, segments: [{ kind: "text" as const, content: normalized }] };
      }
      return m;
    });
    setMessages(hydrated);
    resetCanvas();
    if (loadedChatId) {
      setChatId(loadedChatId);
      chatIdRef.current = loadedChatId;
      setActiveChatId(loadedChatId);
    }
    setContextInfo(null);
    setStreamSegments([]);
    setEditingIdx(null);

    // Auto-switch cartridge if the loaded chat belongs to a different one
    const currentIds = activeConfig?.active_cartridge_ids;
    if (_cartridgeIds?.length && (!currentIds || _cartridgeIds[0] !== currentIds[0])) {
      loadActiveStack(_cartridgeIds);
    }
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
    resetCanvas();
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
          if (seg.name === "request_user_input" || seg.name === "save_notes") continue;
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

  // ─── Export chat as structured JSON (lossless) ───
  const handleExportChatJSON = () => {
    if (messages.length === 0) return;
    const cartName = currentCartridge?.name || activeConfig?.active_cartridge_ids[0] || "chat";
    const exportData = {
      format: "kchat",
      version: 1,
      exported_at: new Date().toISOString(),
      cartridge_name: cartName,
      cartridge_ids: activeConfig?.active_cartridge_ids || [],
      chat_id: chatId,
      message_count: messages.length,
      messages: messages.map(m => ({
        role: m.role,
        content: m.content,
        ...(m.segments && m.segments.length > 0 ? { segments: m.segments } : {}),
      })),
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${cartName.toLowerCase().replace(/\s+/g, "-")}-${new Date().toISOString().slice(0, 10)}.kchat`;
    a.click();
    URL.revokeObjectURL(url);
    soundTick();
  };

  // ─── Import chat from .kchat JSON ───
  const handleImportChat = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = JSON.parse(e.target?.result as string);
        // Accept both new "kchat" and legacy "kasset-chat" format identifiers
        if ((data.format !== "kchat" && data.format !== "kasset-chat") || !Array.isArray(data.messages)) {
          console.error("Invalid .kchat format");
          return;
        }
        handleLoadChat(data.messages, data.cartridge_ids || [], data.chat_id);
        soundTick();
      } catch (err) {
        console.error("Failed to import chat:", err);
      }
    };
    reader.readAsText(file);
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
      if (meta && e.key === "k") { e.preventDefault(); togglePalette(); return; }
      // ⌘N — new chat
      if (meta && e.key === "n") { e.preventDefault(); handleNewChat(); return; }
      // ⌘E — export chat (lossless JSON)
      if (meta && e.key === "e") { e.preventDefault(); handleExportChatJSON(); return; }
      // ⌘⇧C — copy full conversation
      if (meta && e.shiftKey && e.key === "C") { e.preventDefault(); handleCopyChat(); return; }
      // ⌘⇧F — open forge
      if (meta && e.shiftKey && e.key === "F") { e.preventDefault(); onOpenForge?.(); return; }
      // ⌘/ — toggle help
      if (meta && e.key === "/") { e.preventDefault(); toggleTutorial(); return; }
      // ⌘. — focus input
      if (meta && e.key === ".") { e.preventDefault(); inputRef.current?.focus(); return; }
      // Escape — close overlays or stop generation
      if (e.key === "Escape") {
        if (showQuickSettings) { setShowQuickSettings(false); return; }
        if (showPalette) { setShowPalette(false); return; }
        if (showTutorial) { setShowTutorial(false); return; }
        if (showExplorer) { setShowExplorer(false); return; }
        if (showDrawer) { setShowDrawer(false); return; }
        if (showMentalModel) { setShowMentalModel(false); return; }
        if (isGenerating) { handleStop(); return; }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showPalette, showTutorial, showExplorer, showDrawer, showQuickSettings, isGenerating, messages]);

  // ─── Stop generation ───
  const handleStop = () => {
    // 1. Signal backend to cancel the agent loop + model inference
    if (chatId) {
      fetch(`${getApiBase()}/api/chat/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chatId }),
      }).catch(() => {}); // fire-and-forget
    }
    // 2. Abort the SSE fetch on the client side
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    // 3. Force generating state off
    setIsGenerating(false);
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

  // ─── Feedback (thumbs up/down) on assistant messages ───
  const handleFeedback = async (idx: number, rating: 'up' | 'down') => {
    if (!chatId) return;
    const current = messageFeedback[idx];
    const newRating = current === rating ? undefined : rating;
    setMessageFeedback(prev => {
      const next = { ...prev };
      if (newRating) next[idx] = newRating; else delete next[idx];
      return next;
    });
    if (!newRating) return;
    try {
      await fetch(`${getApiBase()}/api/chats/${chatId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message_index: idx, rating: newRating }),
      });
    } catch (e) {
      console.error("Feedback save failed:", e);
    }
  };

  const mdComponents = useMarkdownComponents();

  // DraftBlock "Refine" callback — sends the draft text back to the agent for improvement
  const handleDraftRefine = useCallback((draftText: string) => {
    if (isGenerating || !activeConfig) return;
    const userContent = `Please refine and improve this draft. Suggest specific changes and provide the improved version in a \`\`\`text code block:\n\n\`\`\`text\n${draftText}\n\`\`\``;
    let history = [...messages];
    if (history.length === 0 && activeConfig.boot_messages.length > 0) {
      history.push({ role: "assistant", content: activeConfig.boot_messages[0] });
    }
    const userMsg: Message = { role: "user", content: userContent };
    const newMessages = [...history, userMsg];
    setMessages(newMessages);
    submitFromMessages(newMessages, userContent);
  }, [isGenerating, activeConfig, messages]);

  const draftCtx = useMemo(() => ({ onRefine: handleDraftRefine }), [handleDraftRefine]);

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
    let rafPending = false;
    let rafId: number | null = null;

    const flushSegments = () => {
      setStreamSegments([...segments]);
      rafPending = false;
    };

    const scheduleRender = () => {
      if (!rafPending) {
        rafPending = true;
        rafId = requestAnimationFrame(flushSegments);
        rafIdRef.current = rafId;
      }
    };

    const pushSegment = (seg: Segment, immediate = false) => {
      segments = [...segments, seg];
      if (immediate) { flushSegments(); } else { scheduleRender(); }
    };

    const updateLastSegment = (updater: (s: Segment) => Segment, immediate = false) => {
      if (segments.length === 0) return;
      segments = [...segments.slice(0, -1), updater(segments[segments.length - 1])];
      if (immediate) { flushSegments(); } else { scheduleRender(); }
    };

    let finalized = false;
    const finalizeSegments = () => {
      if (finalized) return; // Guard against double-finalization
      finalized = true;
      // Cancel any pending RAF before finalizing
      if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; rafPending = false; }
      // Collapse any open thinking
      const lastIdx = segments.length - 1;
      if (lastIdx >= 0 && segments[lastIdx].kind === "thinking" && !(segments[lastIdx] as ThinkingSegment).durationMs) {
        const duration = Date.now() - thinkStartRef.current;
        segments = [...segments.slice(0, -1), { ...segments[lastIdx], durationMs: duration, collapsed: true }];
      }
      // Clean up stuck "preparing" tool segments (never resolved to running/done)
      segments = segments.filter(s => !(s.kind === "tool" && (s as ToolCallSegment).status === "preparing"));
      // Remove trailing ⏳ status placeholders
      while (segments.length > 0 && segments[segments.length - 1].kind === "text" && (segments[segments.length - 1] as TextSegment).content.startsWith("⏳")) {
        segments = segments.slice(0, -1);
      }
      const finalText = mergeAssistantTextSegments(segments);
      setMessages((prev) => {
        const assistantMessage: Message = { role: "assistant", content: finalText, segments: [...segments] };
        const last = prev[prev.length - 1];
        const updated = (
          last &&
          last.role === "assistant" &&
          cleanContent(last.content || "") === cleanContent(assistantMessage.content || "")
        )
          ? [...prev.slice(0, -1), assistantMessage]
          : [...prev, assistantMessage];
        // Auto-save chat after response completes — with retry + localStorage fallback
        const cid = chatIdRef.current;
        const currentConfig = activeConfigRef.current;
        if (cid && currentConfig) {
          const saveable = updated.map(m => ({
            role: m.role,
            content: m.content,
            ...(m.segments && m.segments.length > 0 ? { segments: m.segments } : {}),
          }));
          const payload = { messages: saveable, cartridge_ids: currentConfig.active_cartridge_ids };
          const saveToServer = async (retries = 2) => {
            for (let attempt = 0; attempt <= retries; attempt++) {
              try {
                const res = await fetch(`${getApiBase()}/api/chats/${cid}/save`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify(payload),
                });
                if (res.ok) {
                  // Clear localStorage fallback on success
                  try { localStorage.removeItem(`kasset-draft-${cid}`); } catch {}
                  return;
                }
              } catch {}
              if (attempt < retries) await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
            }
            // All retries failed — persist to localStorage as fallback
            try {
              localStorage.setItem(`kasset-draft-${cid}`, JSON.stringify(payload));
              console.warn(`Auto-save failed after retries. Draft saved to localStorage (${cid})`);
            } catch (e) { console.error("localStorage fallback also failed:", e); }
          };
          saveToServer();
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
          messages: msgHistory.map(m => ({ role: m.role, content: m.content })),
          image_path: imagePath,
          chat_id: chatId,
        }),
      });

      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let sseBuffer = "";
      const STALL_TIMEOUT_MS = 90_000; // 90s watchdog per chunk
      let stallTimer: ReturnType<typeof setTimeout> | null = null;
      let parseFailCount = 0;
      let parseWarned = false;

      while (true) {
        // Watchdog: if no data arrives within STALL_TIMEOUT_MS, abort
        const readPromise = reader.read();
        const timeoutPromise = new Promise<{ value: undefined; done: true }>((_, reject) => {
          stallTimer = setTimeout(() => reject(new Error("Stream stalled — no data received for 90 seconds")), STALL_TIMEOUT_MS);
        });
        const { value, done } = await Promise.race([readPromise, timeoutPromise]);
        if (stallTimer) { clearTimeout(stallTimer); stallTimer = null; }
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
              const cleanText = extractStreamText(rawAccumulated);
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
                        .replace(/\\r/g, '\r').replace(/\\b/g, '\b').replace(/\\f/g, '\f')
                        .replace(/\\u([0-9a-fA-F]{4})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)))
                        .replace(/\\"/g, '"').replace(/\\\\/g, '\\');
                      if (partialCode.endsWith('\\')) partialCode = partialCode.slice(0, -1);
                      // Strip trailing JSON/XML artifacts from partial code preview
                      partialCode = partialCode
                        .replace(/"\s*\}\s*\}\s*$/, '')         // trailing "}}
                        .replace(/<\/tool_call>\s*$/, '')        // trailing </tool_call>
                        .replace(/"\s*\}\s*$/, '')               // trailing "}
                        .trimEnd();
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
                }), true);
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
                }, true);
              }
              soundToolStart();
            } else if (data.type === "interactive") {
              pushSegment({
                kind: "interactive",
                widgetId: data.data.widget_id,
                widgetType: data.data.widget_type,
                config: data.data,
                status: "pending",
                persistentId: data.data.persistent_id || undefined,
                revision: 1,
              } as InteractiveSegment, true);
            } else if (data.type === "interactive_update") {
              // Update an existing persistent widget in-place
              const pid = data.data.persistent_id;
              const wid = data.data.widget_id;
              let found = false;
              segments = segments.map((s) => {
                if (s.kind === "interactive") {
                  const seg = s as InteractiveSegment;
                  if (seg.persistentId === pid || seg.widgetId === wid) {
                    found = true;
                    return {
                      ...seg,
                      widgetType: data.data.widget_type || seg.widgetType,
                      config: data.data,
                      status: "pending" as const,
                      revision: (seg.revision || 1) + 1,
                      response: undefined,
                    } as InteractiveSegment;
                  }
                }
                return s;
              });
              if (!found) {
                // Fallback: push as new if not found in current stream segments
                // Also check finalized messages
                setMessages((prev) => {
                  const updated = prev.map((msg) => {
                    if (!msg.segments) return msg;
                    let msgFound = false;
                    const newSegs = msg.segments.map((s) => {
                      if (s.kind === "interactive") {
                        const seg = s as InteractiveSegment;
                        if (seg.persistentId === pid || seg.widgetId === wid) {
                          msgFound = true;
                          return {
                            ...seg,
                            widgetType: data.data.widget_type || seg.widgetType,
                            config: data.data,
                            status: "pending" as const,
                            revision: (seg.revision || 1) + 1,
                            response: undefined,
                          } as InteractiveSegment;
                        }
                      }
                      return s;
                    });
                    return msgFound ? { ...msg, segments: newSegs } : msg;
                  });
                  return updated;
                });
              }
              flushSegments();
            } else if (data.type === "consent_required") {
              updateLastSegment((s) => ({
                ...s,
                consentId: data.data.id,
                consentCommand: data.data.command,
                status: "consent",
              } as ToolCallSegment), true);
            } else if (data.type === "tool_result") {
              const imgs = data.data.images || [];
              const htmlArtifact = data.data.html || "";
              // Find the last tool segment (may not be the absolute last segment
              // if an interactive widget was pushed after it)
              let toolIdx = -1;
              for (let si = segments.length - 1; si >= 0; si--) {
                if (segments[si].kind === "tool" && ((segments[si] as ToolCallSegment).status === "running" || (segments[si] as ToolCallSegment).status === "preparing")) {
                  toolIdx = si;
                  break;
                }
              }
              if (toolIdx >= 0) {
                const s = segments[toolIdx] as ToolCallSegment;
                segments = segments.map((seg, si) => {
                  if (si === toolIdx) {
                    return {
                      ...s,
                      result: data.data.result,
                      images: imgs.length > 0 ? [...(s.images || []), ...imgs] : s.images,
                      html: htmlArtifact || s.html,
                      status: "done" as const,
                    } as ToolCallSegment;
                  }
                  // Also mark any pending interactive segments as submitted
                  // (the local closure doesn't see handleInteractiveRespond's state update)
                  if (seg.kind === "interactive" && (seg as InteractiveSegment).status === "pending") {
                    return { ...seg, status: "submitted" as const } as InteractiveSegment;
                  }
                  return seg;
                });
                flushSegments();
              } else {
                // Fallback: update last segment (original behavior)
                updateLastSegment((s) => ({
                  ...s,
                  result: data.data.result,
                  images: imgs.length > 0 ? [...((s as ToolCallSegment).images || []), ...imgs] : (s as ToolCallSegment).images,
                  html: htmlArtifact || (s as ToolCallSegment).html,
                  status: "done",
                } as ToolCallSegment), true);
              }
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
            parseFailCount++;
            if (parseFailCount >= 5 && !parseWarned) {
              parseWarned = true;
              console.warn("Multiple SSE parse failures — stream may be corrupted");
            }
          }
        }
      }
      // Stream ended — ensure finalization even without explicit "done" event
      // (handles backend crashes, connection drops, and abnormal stream termination)
      if (!finalized) {
        finalizeSegments();
        loadChatList();
      }
    } catch (error) {
      const isAbort = (error instanceof DOMException && error.name === "AbortError")
        || (error instanceof Error && error.name === "AbortError")
        || controller.signal.aborted;
      if (isAbort) {
        // User stopped generation — finalize what we have so far
        if (!finalized) {
          if (segments.length > 0) {
            finalizeSegments();
          } else {
            finalized = true;
            setStreamSegments([]);
            setIsGenerating(false);
          }
        }
        soundTick();
        return;
      }
      // Abort the fetch and cancel the reader to prevent dangling connections
      if (abortRef.current) { try { abortRef.current.abort(); } catch {} }
      abortRef.current = null;
      const errMsg = error instanceof Error ? error.message : "Connection failed";
      if (!finalized) {
        segments = [...segments, { kind: "text" as const, content: `⚠️ ${errMsg}` }];
        finalizeSegments();
      } else {
        setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ ${errMsg}` }]);
        setStreamSegments([]);
        setIsGenerating(false);
      }
      soundError();
    } finally {
      // Absolute safety net — ensure isGenerating is ALWAYS reset
      // Use setTimeout to let React batched updates settle first
      setTimeout(() => {
        setIsGenerating((prev) => {
          if (prev) { abortRef.current = null; }
          return false;
        });
      }, 100);
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

    // Attach region selection from image canvas if present
    const imgSelection = useImageStore.getState().selection;
    if (imgSelection) {
      if (imgSelection.type === "rect") {
        const d = imgSelection.data;
        userContent += `\n[Selected region: rect x=${d.x} y=${d.y} w=${d.w} h=${d.h}${d.tool === "crop" ? " (crop)" : ""}]`;
      } else if (imgSelection.type === "lasso") {
        const pts = imgSelection.data.points;
        const xs = pts.map((p: {x:number}) => p.x);
        const ys = pts.map((p: {y:number}) => p.y);
        userContent += `\n[Selected region: freeform ${pts.length} points, bounds x=${Math.min(...xs)}-${Math.max(...xs)} y=${Math.min(...ys)}-${Math.max(...ys)}]`;
      }
      useImageStore.getState().setSelection(null);
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

  // ─── Interactive widget handler ───
  const handleInteractiveRespond = useCallback(async (widgetId: string, response: any, dismissed: boolean, finalize?: boolean) => {
    try {
      const endpoint = dismissed ? "/api/interactive/dismiss" : "/api/interactive/respond";
      const body: any = dismissed
        ? { widget_id: widgetId }
        : { widget_id: widgetId, response, ...(finalize ? { finalize: true } : {}) };
      await fetch(`${getApiBase()}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      // Update segment status — persistent widgets stay "active" unless finalized
      const updater = (segs: Segment[]) =>
        segs.map((s) => {
          if (s.kind !== "interactive") return s;
          const seg = s as InteractiveSegment;
          if (seg.widgetId !== widgetId) return s;
          if (dismissed) return { ...seg, status: "dismissed" as const, response };
          if (finalize) return { ...seg, status: "submitted" as const, response };
          // Persistent widget: stay active for further interaction
          if (seg.persistentId) return { ...seg, status: "active" as const, response };
          return { ...seg, status: "submitted" as const, response };
        });
      setStreamSegments(updater);
      setMessages((prev) =>
        prev.map((msg) => msg.segments ? { ...msg, segments: updater(msg.segments) } : msg)
      );
    } catch (e) {
      console.error("Interactive respond failed:", e);
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
          if (seg.name === "request_user_input" || seg.name === "save_notes") return null;
          return <ToolCallCard key={`tool-${i}`} segment={seg} onConsent={handleConsent} />;
        }
        if (seg.kind === "interactive") {
          return <InteractiveWidget key={`widget-${i}`} segment={seg as InteractiveSegment} onRespond={handleInteractiveRespond} />;
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
        if (seg.kind === "text") {
          const raw = typeof seg.content === "string"
            ? seg.content
            : (seg.content == null ? "" : JSON.stringify(seg.content));
          // Render error segments with recovery UX instead of plain markdown
          if (raw.startsWith("⚠️")) {
            const errText = raw.replace(/^⚠️\s*/, "");
            return <ErrorRecovery key={`err-${i}`} error={errText} onRetry={() => handleRetry(messages.length - 1)} onNewChat={handleNewChat} />;
          }
          const cleaned = cleanContent(raw);
          if (!cleaned) return null;
          return (
            <ReactMarkdown
              key={`text-${i}`}
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeKatex]}
              components={mdComponents}
            >
              {cleaned}
            </ReactMarkdown>
          );
        }
        return null;
      })}
    </div>
  );

  // Drawer tab helpers — open drawer to a specific tab
  const openDrawerTo = (tab: "history" | "memory" | "context", search = false, autoPreview = false) => {
    setDrawerTab(tab);
    setDrawerFocusSearch(search);
    setDrawerAutoPreview(autoPreview);
    setShowDrawer(true);
    setShowQuickSettings(false);
    soundTick();
  };

  const ctxActiveCount = [ctxSettings.use_session_summary, ctxSettings.use_cartridge_context, ctxSettings.use_global_profile].filter(Boolean).length;

  const themeStyle = activeConfig ? {
    "--accent": activeConfig.theme.accent_color,
    "--tint": activeConfig.theme.screen_tint,
    "--scanline": activeConfig.theme.scanline_intensity,
    "--glow": activeConfig.theme.glow_color,
  } as React.CSSProperties : {};

  const { canvasActive: imageCanvasVisible, poppedOut, setPoppedOut, hideCanvas, resetCanvas } = useImageStore();
  useCanvasSync(); // BroadcastChannel sync for pop-out canvas
  // Canvas shows inside CRT when active AND not in a pop-out window
  const canvasInsideCRT = imageCanvasVisible && !poppedOut;

  return (
    <div className="w-full max-w-5xl h-[100dvh] sm:h-[90vh]">
    <div 
      className="w-full h-full bg-[var(--color-console-bezel)] rounded-none sm:rounded-3xl p-2 sm:p-6 md:p-10 shadow-2xl flex flex-col border-0 sm:border border-white/5 relative transition-all"
      style={themeStyle}
    >
      <ConsoleHeader
        isGenerating={isGenerating}
        contextInfo={contextInfo}
        messageCount={messages.length}
        muted={muted}
        toggleMute={toggleMute}
        currentCartridge={currentCartridge}
        activeConfig={activeConfig}
        onNewChat={handleNewChat}
        onStop={handleStop}
        onOpenDrawerTo={openDrawerTo}
        onOpenForge={onOpenForge}
        onChangeCartridge={onChangeCartridge}
      />

      {/* Screen Area */}
      <div className={`flex-1 min-h-0 mt-7 sm:mt-10 rounded-lg sm:rounded-2xl border sm:border-4 border-black/80 crt-screen ${canvasInsideCRT ? 'p-0' : 'p-2 sm:p-6'} overflow-hidden flex flex-col relative`}>
        {/* Modals — rendered INSIDE crt-screen so ::before scanlines cover them */}
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
            onClose={() => { setShowDrawer(false); setDrawerFocusSearch(false); setDrawerAutoPreview(false); loadChatList(); loadMemories(); }}
            defaultTab={drawerTab}
            focusSearch={drawerFocusSearch}
            autoFetchPreview={drawerAutoPreview}
          />
        )}

        {showPalette && (
          <CommandPalette
            onClose={() => setShowPalette(false)}
            onNewChat={handleNewChat}
            onOpenHistory={() => openDrawerTo("history")}
            onSearchChats={() => openDrawerTo("history", true)}
            onOpenMemory={() => openDrawerTo("memory")}
            onOpenContext={() => openDrawerTo("context")}
            onExportChat={handleExportChatJSON}
            onImportChat={() => chatImportRef.current?.click()}
            onCopyChat={handleCopyChat}
            onOpenForge={onOpenForge}
            onOpenHelp={() => setShowTutorial(true)}
            onToggleMute={toggleMute}
            onEjectCartridge={() => {
              handleStop(); // Abort any in-progress SSE stream
              const cartridgeIds = activeConfig?.active_cartridge_ids;
              const name = currentCartridge?.name || "Kasset";
              soundCartridgeEject();
              resetCanvas();
              ejectCartridge();
              onChangeCartridge();
              if (cartridgeIds?.length) {
                showToast(`Ejected ${name}`, () => {
                  useCartridgeStore.getState().loadActiveStack(cartridgeIds);
                }, 3000);
              }
            }}
            isMuted={muted}
            cartridgeName={currentCartridge?.name || "Kasset"}
            hasMessages={messages.length > 0}
            memoryCount={memories.length}
            modelName={modelName}
          />
        )}

        {showTutorial && (
          <Tutorial onClose={() => setShowTutorial(false)} />
        )}

        {showMentalModel && (
          <MentalModelWidget chatId={chatId} onClose={() => setShowMentalModel(false)} />
        )}

        {showSignalDebug && (
          <SignalProcessor
            onClose={() => { setShowSignalDebug(false); loadAvailableCartridges(); }}
            onUnlock={async () => {
              if (typeof window !== "undefined") localStorage.setItem("kasset-nsfw-unlocked", "true");
              try {
                await fetch(`${getApiBase()}/api/forge/unlock-secret`, { method: "POST" });
                await loadAvailableCartridges();
              } catch (e) {
                console.error("Failed to unlock secret cartridge:", e);
              }
            }}
          />
        )}

        {/* ─── Canvas + Chat Split ─── */}
        {canvasInsideCRT && (
          <div className="flex-1 min-h-0 flex flex-col">
            {/* Image panel — ~55% */}
            <div className="h-[55%] min-h-0 relative">
              <ImagePanel
                showPopOut
                onPopOut={() => {
                  setPoppedOut(true);
                  window.open('/canvas', '_blank', 'width=900,height=700,menubar=no,toolbar=no');
                }}
                onClose={hideCanvas}
              />
            </div>
            {/* Divider */}
            <div className="h-px bg-white/[0.06] shrink-0" />
            {/* Chat area — ~45% */}
            <div className="flex-1 min-h-0 overflow-y-auto crt-scroll px-3 sm:px-5 py-2 space-y-2">
              <DraftContext.Provider value={draftCtx}>
                {messages.map((msg, idx) => {
                  const isUser = msg.role === "user";
                  const msgKey = `${msg.role}-${idx}-${msg.content.slice(0, 32).replace(/\s/g, '')}`;
                  return (
                    <div key={msgKey} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
                      <div className={`max-w-[95%] ${
                        isUser
                          ? "bg-[var(--accent)] text-black px-3 py-1.5 rounded-l-lg rounded-tr-lg font-medium text-[12px] shadow-[0_0_10px_var(--tint)]"
                          : "prose-crt text-[12px]"
                      }`}>
                        {isUser ? (
                          <span>{msg.content.length > 120 ? msg.content.slice(0, 120) + '…' : msg.content}</span>
                        ) : msg.segments && msg.segments.length > 0 ? (
                          <ErrorBoundary inline fallbackMessage="Render error">
                            {renderSegments(msg.segments, false)}
                          </ErrorBoundary>
                        ) : (
                          <ErrorBoundary inline fallbackMessage="Render error">
                            <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]} components={mdComponents}>
                              {cleanContent(msg.content)}
                            </ReactMarkdown>
                          </ErrorBoundary>
                        )}
                      </div>
                    </div>
                  );
                })}
                {streamSegments.length > 0 && (
                  <div className="flex justify-start">
                    <div className="max-w-[92%] prose-crt text-[12px]">
                      <ErrorBoundary inline fallbackMessage="Stream error">
                        {renderSegments(streamSegments, true)}
                      </ErrorBoundary>
                    </div>
                  </div>
                )}
              </DraftContext.Provider>
            </div>
          </div>
        )}

        {/* ─── Normal Chat Mode ─── */}
        {!canvasInsideCRT && showWelcome ? (
          <WelcomeScreen
            cartridgeId={activeConfig!.active_cartridge_ids[0]}
            cartridgeName={currentCartridge?.name || activeConfig!.active_cartridge_ids[0]}
            cartridgeIcon={currentCartridge?.icon || "🤖"}
            bootMessage={activeConfig!.boot_messages[0] || "Ready."}
            tools={activeConfig!.tools}
            suggestedPrompts={activeConfig!.suggested_prompts || []}
            onSendPrompt={handleWelcomePrompt}
            memoryCount={memories.length}
            modelName={modelName}
            ctxActiveCount={ctxActiveCount}
            onOpenMemory={() => openDrawerTo("memory")}
            onOpenContext={() => openDrawerTo("context")}
            onOpenSearch={() => openDrawerTo("history", true)}
          />
        ) : !canvasInsideCRT ? (
        <DraftContext.Provider value={draftCtx}>
        <div ref={scrollRef} role="log" aria-live="polite" aria-label="Chat messages" className="flex-1 min-h-0 overflow-y-auto crt-scroll pr-1 sm:pr-4 px-2 sm:px-6 pt-2 space-y-2.5 sm:space-y-4">
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
            const msgKey = `${msg.role}-${idx}-${msg.content.slice(0, 32).replace(/\s/g, '')}`;

            return (
              <div 
                key={msgKey} 
                className={`group/msg flex ${isUser ? "justify-end" : "justify-start"}`}
              >
                <div className="relative w-full max-w-full">
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
                      <ErrorBoundary inline fallbackMessage="Failed to render response">
                        {renderSegments(msg.segments, false)}
                      </ErrorBoundary>
                    ) : (
                      <ErrorBoundary inline fallbackMessage="Failed to render markdown">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm, remarkMath]}
                          rehypePlugins={[rehypeKatex]}
                          components={mdComponents}
                        >
                          {cleanContent(msg.content)}
                        </ReactMarkdown>
                      </ErrorBoundary>
                    )}
                  </div>

                  {/* Inline action bar — always visible */}
                  {!isGenerating && !isEditing && !isBoot && (
                    <div className={`flex items-center gap-0.5 mt-1 ${isUser ? "justify-end" : "justify-start"}`}>
                      {isBot && (
                        <button
                          onClick={() => handleCopy(idx)}
                          className="p-1.5 sm:p-1 rounded text-white/25 hover:text-white/70 hover:bg-white/5 transition-all"
                          title="Copy response"
                        >
                          {copiedIdx === idx ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
                        </button>
                      )}
                      {isBot && !isBoot && chatId && (
                        <>
                          <button
                            onClick={() => handleFeedback(idx, 'up')}
                            className={`p-1.5 sm:p-1 rounded transition-all ${
                              messageFeedback[idx] === 'up'
                                ? 'text-green-400 bg-green-400/10'
                                : 'text-white/25 hover:text-green-400 hover:bg-white/5'
                            }`}
                            title="Good response"
                          >
                            <ThumbsUp size={11} />
                          </button>
                          <button
                            onClick={() => handleFeedback(idx, 'down')}
                            className={`p-1.5 sm:p-1 rounded transition-all ${
                              messageFeedback[idx] === 'down'
                                ? 'text-red-400 bg-red-400/10'
                                : 'text-white/25 hover:text-red-400 hover:bg-white/5'
                            }`}
                            title="Poor response"
                          >
                            <ThumbsDown size={11} />
                          </button>
                        </>
                      )}
                      {isBot && isLast && (
                        <button
                          onClick={() => handleRetry(idx)}
                          className="p-1.5 sm:p-1 rounded text-white/25 hover:text-white/70 hover:bg-white/5 transition-all"
                          title="Regenerate response"
                        >
                          <RefreshCw size={12} />
                        </button>
                      )}
                      {isUser && (
                        <button
                          onClick={() => handleStartEdit(idx)}
                          className="p-1.5 sm:p-1 rounded text-white/25 hover:text-white/70 hover:bg-white/5 transition-all"
                          title="Edit & resend"
                        >
                          <Pencil size={12} />
                        </button>
                      )}
                      {!isLast && (
                        <button
                          onClick={() => handleRevert(idx)}
                          className="p-1.5 sm:p-1 rounded text-white/25 hover:text-white/70 hover:bg-white/5 transition-all"
                          title="Revert to here"
                        >
                          <Scissors size={12} />
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
              <div className="max-w-[92%] sm:max-w-[85%] prose-crt">
                <ErrorBoundary inline fallbackMessage="Stream render error">
                  {renderSegments(streamSegments, true)}
                </ErrorBoundary>
              </div>
            </div>
          )}
        </div>
        </DraftContext.Provider>
        ) : null}
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
          {/* Hidden file input for .kchat import */}
          <input
            ref={chatImportRef}
            type="file"
            accept=".kchat,.json"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleImportChat(file);
              if (chatImportRef.current) chatImportRef.current.value = '';
            }}
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
                aria-label="Stop generating"
                className="p-2 rounded-xl bg-red-500/15 text-red-400 hover:bg-red-500/25 border border-red-500/20 transition-all shrink-0 mb-0.5"
                title="Stop generating"
              >
                <Square size={16} fill="currentColor" />
              </button>
            ) : (
              <button 
                type="submit"
                disabled={(!input.trim() && attachments.length === 0) || !activeConfig}
                aria-label="Send message"
                className="p-2 rounded-xl bg-[var(--accent)]/15 text-[var(--accent)] hover:bg-[var(--accent)]/25 border border-[var(--accent)]/20 transition-all disabled:opacity-20 disabled:hover:bg-[var(--accent)]/15 shrink-0 mb-0.5"
                title="Send message"
              >
                <CornerDownLeft size={16} />
              </button>
            )}
          </div>
        </form>
        <ConsoleFooter
          memoryCount={memories.length}
          modelName={modelName}
          ctxActiveCount={ctxActiveCount}
          activeConfig={activeConfig}
          sessionStart={sessionStartRef.current}
          onModelChange={(name) => setModelName(name)}
          onOpenDrawerTo={openDrawerTo}
        />
      </div>
    </div>
    </div>
  );
}
