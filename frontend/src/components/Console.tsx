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
import { ErrorBoundary } from "./ErrorBoundary";
import { showToast } from "./Toast";
import CommandPalette from "./CommandPalette";
import type { ToolCallSegment, ThinkingSegment, TextSegment, Segment, Message } from "./chat/types";
import { TOOL_META, getToolMeta, TOOL_DISPLAY, TOOL_EXAMPLES } from "./chat/toolMeta";
import ThinkingBlock from "./chat/ThinkingBlock";
import ToolCallCard from "./chat/ToolCallCard";
import WelcomeScreen from "./chat/WelcomeScreen";
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
// SUB-COMPONENTS (CopyButton stays here; others extracted to chat/)
// ═══════════════════════════════════════════

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
      className="absolute top-1 right-1 p-1 rounded bg-white/5 text-white/25 hover:text-white/60 hover:bg-white/10 transition-all opacity-0 group-hover/code:opacity-100"
    >
      {copied ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
    </button>
  );
}

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
  // Leaked JSON fragments from truncated tool calls (e.g. '"}> properly.' or '"}>  time.')
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
  // Trim anything from <tool_call> onward (both formats)
  const toolIdx = text.indexOf("<tool_call>");
  if (toolIdx >= 0) text = text.substring(0, toolIdx);
  const toolIdx2 = text.indexOf("<|tool_call|>");
  if (toolIdx2 >= 0) text = text.substring(0, toolIdx2);
  // Trim leaked JSON fragments like '"}> properly.'
  const jsonLeakIdx = text.search(/"\s*\}\s*>\s*[^<\n]{0,30}\.?\s*$/m);
  if (jsonLeakIdx >= 0) text = text.substring(0, jsonLeakIdx);
  // Trim raw JSON tool call objects
  const rawJsonIdx = text.indexOf('{"name"');
  if (rawJsonIdx >= 0) text = text.substring(0, rawJsonIdx);
  return text.trim();
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
    // Hydrate legacy messages: ensure assistant messages have segments for proper rendering
    const hydrated = loadedMessages.map((m: any) => {
      if (m.role === "assistant" && (!m.segments || m.segments.length === 0) && m.content) {
        return { ...m, segments: [{ kind: "text" as const, content: m.content }] };
      }
      return m;
    });
    setMessages(hydrated);
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
      const finalText = segments
        .filter((s) => s.kind === "text" && !(s as TextSegment).content.startsWith("⏳"))
        .map((s) => (s as TextSegment).content)
        .join("\n\n");
      setMessages((prev) => {
        const updated = [...prev, { role: "assistant" as const, content: finalText, segments: [...segments] }];
        // Auto-save chat after response completes — with retry + localStorage fallback
        const cid = chatIdRef.current;
        if (cid && activeConfig) {
          const saveable = updated.map(m => ({
            role: m.role,
            content: m.content,
            ...(m.segments && m.segments.length > 0 ? { segments: m.segments } : {}),
          }));
          const payload = { messages: saveable, cartridge_ids: activeConfig.active_cartridge_ids };
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
              updateLastSegment((s) => ({
                ...s,
                result: data.data.result,
                images: imgs.length > 0 ? [...((s as ToolCallSegment).images || []), ...imgs] : (s as ToolCallSegment).images,
                html: htmlArtifact || (s as ToolCallSegment).html,
                status: "done",
              } as ToolCallSegment), true);
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
          <div aria-label={isGenerating ? "Generating response" : "Idle"} className={`w-2.5 h-2.5 sm:w-3 sm:h-3 rounded-full ${isGenerating ? "bg-[var(--accent)] animate-pulse crt-glow" : "bg-white/20"}`} />
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
        <button onClick={handleNewChat} aria-label="New Chat" className="p-2 sm:p-1.5 rounded text-white/30 hover:text-[var(--accent)] hover:bg-white/5 active:bg-white/10 transition-all" title="New Chat (⌘N)">
          <Plus size={15} />
        </button>
        <button onClick={() => { setShowDrawer(true); soundTick(); }} aria-label="Chat History" className="p-2 sm:p-1.5 rounded text-white/30 hover:text-[var(--accent)] hover:bg-white/5 active:bg-white/10 transition-all" title="Chat History">
          <History size={15} />
        </button>
        <button onClick={() => { setShowPalette(true); soundTick(); }} aria-label="Command Palette" className="p-2 sm:p-1.5 rounded text-white/30 hover:text-[var(--accent)] hover:bg-white/5 active:bg-white/10 transition-all" title="Command Palette (⌘K)">
          <Command size={15} />
        </button>
        {onOpenForge && (
          <button onClick={onOpenForge} aria-label="Kasset Forge" className="p-2 sm:p-1.5 rounded text-white/30 hover:text-[var(--accent)] hover:bg-white/5 active:bg-white/10 transition-all" title="Kasset Forge (⌘⇧F)">
            <Wrench size={15} />
          </button>
        )}
        <button onClick={() => { setShowTutorial(true); soundTick(); }} aria-label="Quick Guide" className="p-2 sm:p-1.5 rounded text-white/30 hover:text-[var(--accent)] hover:bg-white/5 active:bg-white/10 transition-all" title="Quick Guide (⌘/)">
          <HelpCircle size={15} />
        </button>
        <button
          onClick={toggleMute}
          className={`hidden sm:block p-1.5 rounded transition-all ${muted ? "text-white/15" : "text-white/30 hover:text-[var(--accent)] hover:bg-white/5"}`}
          aria-label={muted ? "Unmute sounds" : "Mute sounds"}
          title={muted ? "Unmute sounds" : "Mute sounds"}
        >
          {muted ? <VolumeX size={15} /> : <Volume2 size={15} />}
        </button>
        <div className="hidden sm:block w-px h-4 bg-white/5 mx-1" />
        <div className="bg-black/40 border border-white/10 px-2 sm:px-3 py-1 rounded-lg text-[var(--accent)] font-bold text-[10px] sm:text-xs tracking-wider shadow-inner flex items-center gap-1.5 sm:gap-2 ml-0.5 sm:ml-1">
          {currentCartridge && <span className="text-sm sm:text-base leading-none">{currentCartridge.icon}</span>}
          <span className="max-w-[60px] sm:max-w-[120px] truncate text-glow">{currentCartridge?.name?.toUpperCase() || (activeConfig ? activeConfig.active_cartridge_ids[0].toUpperCase() : "NO KASSET")}</span>
          <button 
            onClick={() => {
              const cartridgeIds = activeConfig?.active_cartridge_ids;
              const name = currentCartridge?.name || "Kasset";
              soundCartridgeEject();
              ejectCartridge();
              onChangeCartridge();
              if (cartridgeIds?.length) {
                showToast(`Ejected ${name}`, () => {
                  useCartridgeStore.getState().loadActiveStack(cartridgeIds);
                }, 3000);
              }
            }}
            className="hover:text-white active:text-white transition-colors text-[var(--accent)]/50 hover:text-[var(--accent)]"
            title="Eject Kasset"
          >
            ⏏
          </button>
        </div>
      </div>

      {/* Screen Area */}
      <div className="flex-1 min-h-0 mt-8 sm:mt-10 rounded-xl sm:rounded-2xl border-2 sm:border-4 border-black/80 crt-screen p-3 sm:p-6 overflow-hidden flex flex-col relative">
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
            onEjectCartridge={() => {
              const cartridgeIds = activeConfig?.active_cartridge_ids;
              const name = currentCartridge?.name || "Kasset";
              soundCartridgeEject();
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
        <div ref={scrollRef} role="log" aria-live="polite" aria-label="Chat messages" className="flex-1 min-h-0 overflow-y-auto crt-scroll pr-2 sm:pr-4 space-y-3 sm:space-y-4">
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

                  {/* Hover action buttons */}
                  {!isGenerating && !isEditing && !isBoot && (
                    <div className={`absolute ${isUser ? "left-0 -translate-x-full pr-1.5" : "right-0 translate-x-full pl-1.5"} top-0 opacity-30 sm:opacity-0 sm:group-hover/msg:opacity-100 transition-opacity flex flex-col gap-0.5`}>
                      {/* Copy — assistant only */}
                      {isBot && (
                        <button
                          onClick={() => handleCopy(idx)}
                          className="p-2 sm:p-1 rounded text-white/20 hover:text-white/60 hover:bg-white/5 transition-all"
                          title="Copy response"
                        >
                          {copiedIdx === idx ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
                        </button>
                      )}
                      {/* Retry — last assistant only */}
                      {isBot && isLast && (
                        <button
                          onClick={() => handleRetry(idx)}
                          className="p-2 sm:p-1 rounded text-white/20 hover:text-white/60 hover:bg-white/5 transition-all"
                          title="Regenerate response"
                        >
                          <RefreshCw size={12} />
                        </button>
                      )}
                      {/* Edit — user only */}
                      {isUser && (
                        <button
                          onClick={() => handleStartEdit(idx)}
                          className="p-2 sm:p-1 rounded text-white/20 hover:text-white/60 hover:bg-white/5 transition-all"
                          title="Edit message"
                        >
                          <Pencil size={12} />
                        </button>
                      )}
                      {/* Revert — truncate to here */}
                      {!isLast && (
                        <button
                          onClick={() => handleRevert(idx)}
                          className="p-2 sm:p-1 rounded text-white/20 hover:text-white/60 hover:bg-white/5 transition-all"
                          title="Revert to here (delete everything after)"
                        >
                          <Scissors size={12} />
                        </button>
                      )}
                      {/* Delete single message */}
                      {isUser && (
                        <button
                          onClick={() => handleDeleteMessage(idx)}
                          className="p-2 sm:p-1 rounded text-white/20 hover:text-red-400/60 hover:bg-white/5 transition-all"
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
                <ErrorBoundary inline fallbackMessage="Stream render error">
                  {renderSegments(streamSegments, true)}
                </ErrorBoundary>
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
