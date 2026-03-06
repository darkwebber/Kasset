"use client";

import { useCartridgeStore } from "@/stores/cartridgeStore";
import { useState, useRef, useEffect, useMemo } from "react";
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
import { useChatStore } from "@/stores/chatStore";
import { FolderOpen, X, Copy, Check, History, Plus, ChevronDown, ChevronRight, Wrench, Terminal, FileText, Clock, Play, Search, Calculator, Volume2, VolumeX, Square, RefreshCw, Pencil, Scissors, Trash2, CornerDownLeft } from "lucide-react";
import { soundSend, soundThinkStart, soundThinkEnd, soundToolStart, soundToolDone, soundDone, soundError, soundNewChat, soundTick, soundCartridgeEject, isMuted, setMuted } from "@/lib/sounds";

// ═══════════════════════════════════════════
// TYPES — structured message segments
// ═══════════════════════════════════════════

interface ToolCallSegment {
  kind: "tool";
  name: string;
  args: Record<string, any>;
  result?: string;
  images?: string[];
  status: "running" | "done" | "error";
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

function ThinkingBlock({ segment, onToggle }: { segment: ThinkingSegment; onToggle: () => void }) {
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
}

function ToolCallCard({ segment }: { segment: ToolCallSegment }) {
  const [expanded, setExpanded] = useState(false);
  const meta = getToolMeta(segment.name);
  const isRunning = segment.status === "running";
  const hasImages = segment.images && segment.images.length > 0;

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
          {isRunning ? <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" /> : meta.icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium" style={{ color: meta.color }}>
              {isRunning ? meta.label + "..." : meta.label}
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

      {/* Expanded text result */}
      {expanded && segment.result && (
        <div className="px-3 pb-2.5 pt-0">
          <div className="bg-black/40 rounded border border-white/5 p-2.5 text-[11px] text-white/50 font-mono max-h-48 overflow-y-auto crt-scroll whitespace-pre-wrap leading-relaxed">
            {segment.result}
          </div>
        </div>
      )}

      {/* Images always visible inline — not hidden behind expand */}
      {hasImages && (
        <div className="px-3 pb-3 space-y-2">
          {segment.images!.map((src, i) => (
            <div key={i} className="rounded-lg overflow-hidden bg-black/60 border border-white/5">
              <img src={src} alt={`Plot ${i + 1}`} className="w-full rounded-lg" />
            </div>
          ))}
        </div>
      )}
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

export default function Console({ onChangeCartridge }: { onChangeCartridge: () => void }) {
  const { activeConfig } = useCartridgeStore();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [showExplorer, setShowExplorer] = useState(false);
  const [showDrawer, setShowDrawer] = useState(false);
  const [attachedFile, setAttachedFile] = useState<string | null>(null);
  const [contextInfo, setContextInfo] = useState<{message_count: number, estimated_tokens: number, max_tokens: number} | null>(null);
  const [chatId, setChatId] = useState<string | null>(null);
  // Streaming state — not part of messages until finalized
  const [streamSegments, setStreamSegments] = useState<Segment[]>([]);
  const [muted, setMutedState] = useState(false);
  const { setActiveChatId, loadChatList } = useChatStore();
  
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editingText, setEditingText] = useState("");
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const thinkStartRef = useRef<number>(0);
  const abortRef = useRef<AbortController | null>(null);

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

  const handleLoadChat = (loadedMessages: any[], _cartridgeIds: string[]) => {
    setMessages(loadedMessages);
    setContextInfo(null);
    setStreamSegments([]);
    setEditingIdx(null);
  };

  const handleNewChat = () => {
    soundNewChat();
    setMessages([]);
    setChatId(null);
    setActiveChatId(null);
    setContextInfo(null);
    setStreamSegments([]);
    setEditingIdx(null);
  };

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

  // Auto-add boot message
  useEffect(() => {
    if (activeConfig && messages.length === 0 && activeConfig.boot_messages.length > 0) {
      setMessages([{ role: "assistant", content: activeConfig.boot_messages[0] }]);
    }
  }, [activeConfig, messages.length]);

  // Auto-scroll
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streamSegments]);

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
        .filter((s) => s.kind === "text")
        .map((s) => (s as TextSegment).content)
        .join("\n\n");
      setMessages((prev) => [...prev, { role: "assistant", content: finalText, segments: [...segments] }]);
      setStreamSegments([]);
      setIsGenerating(false);
      abortRef.current = null;
    };

    try {
      const response = await fetch("http://127.0.0.1:7861/api/chat", {
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

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value);
        const lines = chunk.split("\n\n");
        
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          
          try {
            const data = JSON.parse(line.substring(6));
            
            if (data.type === "chat_id") {
              setChatId(data.data);
              setActiveChatId(data.data);
            } else if (data.type === "context_info") {
              setContextInfo(data.data);
            } else if (data.type === "memory_update") {
              console.log("New memories learned:", data.data);
            } else if (data.type === "think_token") {
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
                const last = segments[segments.length - 1];
                if (last && last.kind === "text") {
                  updateLastSegment(() => ({ kind: "text", content: cleanText }));
                } else {
                  pushSegment({ kind: "text", content: cleanText });
                }
              }
            } else if (data.type === "tool_start") {
              const lastIdx = segments.length - 1;
              if (lastIdx >= 0 && segments[lastIdx].kind === "thinking") {
                const duration = Date.now() - thinkStartRef.current;
                updateLastSegment((s) => ({ ...s, durationMs: duration, collapsed: true }));
              }
              pushSegment({
                kind: "tool",
                name: data.data.name,
                args: data.data.args,
                status: "running",
              });
              soundToolStart();
            } else if (data.type === "tool_result") {
              const imgs = data.data.images || [];
              updateLastSegment((s) => ({
                ...s,
                result: data.data.result,
                images: imgs.length > 0 ? [...((s as ToolCallSegment).images || []), ...imgs] : (s as ToolCallSegment).images,
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
    if (!input.trim() && !attachedFile) return;
    if (isGenerating || !activeConfig) return;

    let userContent = input.trim();
    if (attachedFile) {
      userContent = userContent ? `${userContent}\n[Attached file: ${attachedFile}]` : `[Attached file: ${attachedFile}]`;
    }

    const userMsg: Message = { role: "user", content: userContent };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput("");
    
    const isImage = attachedFile?.match(/\.(jpg|jpeg|png|webp)$/i);
    const imagePath = isImage ? attachedFile ?? undefined : undefined;
    setAttachedFile(null);

    await submitFromMessages(newMessages, userContent, imagePath);
  };

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
          return <ToolCallCard key={`tool-${i}`} segment={seg} />;
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
      className="w-full max-w-5xl h-[90vh] bg-[var(--color-console-bezel)] rounded-3xl p-6 md:p-10 shadow-2xl flex flex-col border border-white/5 relative"
      style={themeStyle}
    >
      {showExplorer && (
        <FileExplorer 
          onSelect={(path) => { setAttachedFile(path); setShowExplorer(false); }} 
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

      {/* Hardware Accents */}
      <div className="absolute top-4 left-6 flex items-center gap-3">
        <div className="flex gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500 opacity-80" />
          <div className={`w-3 h-3 rounded-full ${isGenerating ? "bg-[var(--accent)] animate-pulse crt-glow" : "bg-white/20"}`} />
        </div>
        {contextInfo && (
          <div className="flex items-center gap-2 ml-2" title={`${contextInfo.estimated_tokens} / ${contextInfo.max_tokens} tokens`}>
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
      
      {/* Cartridge Slot + Chat Controls */}
      <div className="absolute top-4 right-8 flex items-center gap-2">
        <button
          onClick={toggleMute}
          className={`p-1.5 rounded transition-all ${muted ? "text-white/15" : "text-white/30 hover:text-[var(--accent)] hover:bg-white/5"}`}
          title={muted ? "Unmute sounds" : "Mute sounds"}
        >
          {muted ? <VolumeX size={15} /> : <Volume2 size={15} />}
        </button>
        <button
          onClick={handleNewChat}
          className="p-1.5 rounded text-white/30 hover:text-[var(--accent)] hover:bg-white/5 transition-all"
          title="New Chat"
        >
          <Plus size={16} />
        </button>
        <button
          onClick={() => { setShowDrawer(true); soundTick(); }}
          className="p-1.5 rounded text-white/30 hover:text-[var(--accent)] hover:bg-white/5 transition-all"
          title="Chat History & Memory"
        >
          <History size={16} />
        </button>
        <div className="bg-black/40 border border-white/10 px-4 py-1.5 rounded text-[var(--accent)] text-glow font-bold text-sm tracking-wider shadow-inner flex items-center gap-2">
          {activeConfig ? activeConfig.active_cartridge_ids[0].toUpperCase() : "NO CARTRIDGE"}
          <button 
            onClick={() => { soundCartridgeEject(); onChangeCartridge(); }}
            className="ml-2 hover:text-white transition-colors"
            title="Eject Cartridge"
          >
            ⏏
          </button>
        </div>
      </div>

      {/* Screen Area */}
      <div className="flex-1 min-h-0 mt-6 rounded-2xl border-4 border-black/80 crt-screen p-6 overflow-hidden flex flex-col relative">
        <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto crt-scroll pr-4 space-y-4">
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
                        msg.content
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
                    <div className={`absolute ${isUser ? "left-0 -translate-x-full pr-1.5" : "right-0 translate-x-full pl-1.5"} top-0 opacity-0 group-hover/msg:opacity-100 transition-opacity flex flex-col gap-0.5`}>
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
      </div>

      {/* Input Area */}
      <div className="mt-6 bg-black/60 rounded-xl p-2 border border-white/10 shadow-inner flex flex-col gap-2">
        {attachedFile && (
          <div className="flex items-center gap-2 px-3 py-1 bg-white/5 w-fit rounded border border-white/10 text-xs text-white/70">
            <span className="truncate max-w-xs">{attachedFile}</span>
            <button onClick={() => setAttachedFile(null)} className="hover:text-red-400">
              <X size={14} />
            </button>
          </div>
        )}
        <form onSubmit={handleSubmit} className="flex items-center">
          <button 
            type="button" 
            onClick={() => setShowExplorer(true)}
            className="p-2 text-white/50 hover:text-[var(--accent)] transition-colors"
            title="Browse File System"
          >
            <FolderOpen size={20} />
          </button>
          <div className="text-[var(--accent)] px-2 text-xl font-bold">{">"}</div>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isGenerating || !activeConfig}
            className="flex-1 bg-transparent border-none outline-none text-[var(--accent)] placeholder-[var(--accent)]/30 text-lg py-2 font-mono"
            placeholder={activeConfig ? "Enter command..." : "Insert cartridge to begin..."}
            autoFocus
          />
          {isGenerating ? (
            <button 
              type="button"
              onClick={handleStop}
              className="px-5 py-2 bg-red-500/80 text-white font-bold uppercase tracking-widest rounded mx-1 hover:bg-red-500 transition-colors flex items-center gap-2"
            >
              <Square size={14} fill="currentColor" />
              Stop
            </button>
          ) : (
            <button 
              type="submit"
              disabled={(!input.trim() && !attachedFile) || !activeConfig}
              className="px-6 py-2 bg-[var(--accent)] text-black font-bold uppercase tracking-widest rounded mx-1 hover:bg-white transition-colors disabled:opacity-30"
            >
              Send
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
