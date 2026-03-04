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
import { FolderOpen, X, Copy, Check, History, Plus, ChevronDown, ChevronRight, Wrench, Terminal, FileText, Clock, Play, Search, Calculator, Volume2, VolumeX } from "lucide-react";
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

  const formatArgs = (args: Record<string, any>) => {
    const entries = Object.entries(args);
    if (entries.length === 0) return null;
    // Show the primary argument value inline
    const [firstKey, firstVal] = entries[0];
    const valStr = typeof firstVal === "string" ? firstVal : JSON.stringify(firstVal);
    return { key: firstKey, value: valStr, extra: entries.length > 1 ? entries.length - 1 : 0 };
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

      {/* Expanded result */}
      {expanded && segment.result && (
        <div className="px-3 pb-2.5 pt-0">
          <div className="bg-black/40 rounded border border-white/5 p-2.5 text-[11px] text-white/50 font-mono max-h-48 overflow-y-auto crt-scroll whitespace-pre-wrap leading-relaxed">
            {segment.result}
          </div>
          {segment.images && segment.images.length > 0 && (
            <div className="mt-2 space-y-2">
              {segment.images.map((src, i) => (
                <div key={i} className="border border-white/5 rounded overflow-hidden bg-black/60 p-1">
                  <img src={src} alt={`Output ${i + 1}`} className="w-full max-w-lg rounded" />
                </div>
              ))}
            </div>
          )}
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
  
  const scrollRef = useRef<HTMLDivElement>(null);
  const thinkStartRef = useRef<number>(0);

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
  };

  const handleNewChat = () => {
    soundNewChat();
    setMessages([]);
    setChatId(null);
    setActiveChatId(null);
    setContextInfo(null);
    setStreamSegments([]);
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() && !attachedFile) return;
    if (isGenerating || !activeConfig) return;

    let userContent = input.trim();
    if (attachedFile) {
      userContent = userContent ? `${userContent}\n[Attached file: ${attachedFile}]` : `[Attached file: ${attachedFile}]`;
    }

    const userMsg: Message = { role: "user", content: userContent };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    
    const isImage = attachedFile?.match(/\.(jpg|jpeg|png|webp)$/i);
    const imagePath = isImage ? attachedFile : undefined;
    
    setAttachedFile(null);
    setIsGenerating(true);
    setStreamSegments([]);
    soundSend();

    // Mutable ref for segments during streaming
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

    const getOrCreateTextSegment = (): number => {
      const last = segments[segments.length - 1];
      if (last && last.kind === "text") return segments.length - 1;
      pushSegment({ kind: "text", content: "" });
      return segments.length - 1;
    };

    try {
      const response = await fetch("http://127.0.0.1:7861/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cartridge_ids: activeConfig.active_cartridge_ids,
          messages: [...messages, userMsg],
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
              // Auto-collapse thinking when tool starts
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
              updateLastSegment((s) => ({
                ...s,
                result: data.data.result,
                status: "done",
              } as ToolCallSegment));
              soundToolDone();
              // Reset accumulated text for next round of generation
              rawAccumulated = "";
            } else if (data.type === "sandbox_images") {
              const imgs = data.data as string[];
              updateLastSegment((s) => ({
                ...s,
                images: [...((s as ToolCallSegment).images || []), ...imgs],
              } as ToolCallSegment));
            } else if (data.type === "done") {
              // Finalize: collapse any open thinking
              const lastIdx = segments.length - 1;
              if (lastIdx >= 0 && segments[lastIdx].kind === "thinking" && !(segments[lastIdx] as ThinkingSegment).durationMs) {
                const duration = Date.now() - thinkStartRef.current;
                updateLastSegment((s) => ({ ...s, durationMs: duration, collapsed: true }));
              }
              // Merge segments into a final assistant message
              const finalText = segments
                .filter((s) => s.kind === "text")
                .map((s) => (s as TextSegment).content)
                .join("\n\n");
              setMessages((prev) => [...prev, { role: "assistant", content: finalText, segments: [...segments] }]);
              setStreamSegments([]);
              setIsGenerating(false);
              loadChatList();
              soundDone();
            } else if (data.type === "error") {
              console.error(data.data);
              setIsGenerating(false);
              setStreamSegments([]);
              soundError();
            }
          } catch (e) {
            console.error("Failed to parse SSE line", line, e);
          }
        }
      }
    } catch (error) {
      console.error(error);
      setIsGenerating(false);
      setStreamSegments([]);
    }
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
          {messages.map((msg, idx) => (
            <div 
              key={idx} 
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div 
                className={`max-w-[85%] ${
                  msg.role === "user" 
                    ? "bg-[var(--accent)] text-black px-4 py-2 rounded-l-lg rounded-tr-lg font-medium shadow-[0_0_15px_var(--tint)]" 
                    : "prose-crt"
                }`}
              >
                {msg.role === "user" ? (
                  msg.content
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
            </div>
          ))}

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
          <button 
            type="submit"
            disabled={isGenerating || (!input.trim() && !attachedFile) || !activeConfig}
            className="px-6 py-2 bg-[var(--accent)] text-black font-bold uppercase tracking-widest rounded mx-1 hover:bg-white transition-colors disabled:opacity-30"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
