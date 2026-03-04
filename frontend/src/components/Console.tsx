"use client";

import { useCartridgeStore } from "@/stores/cartridgeStore";
import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import FileExplorer from "./explorer/FileExplorer";
import { FolderOpen, X } from "lucide-react";

interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  images?: string[]; // base64 sandbox plot images
}

export default function Console({ onChangeCartridge }: { onChangeCartridge: () => void }) {
  const { activeConfig } = useCartridgeStore();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [thinkingContent, setThinkingContent] = useState("");
  const [activeTool, setActiveTool] = useState<{name: string, args: any} | null>(null);
  const [showExplorer, setShowExplorer] = useState(false);
  const [attachedFile, setAttachedFile] = useState<string | null>(null);
  
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-add boot message
  useEffect(() => {
    if (activeConfig && messages.length === 0 && activeConfig.boot_messages.length > 0) {
      setMessages([{ role: "assistant", content: activeConfig.boot_messages[0] }]);
    }
  }, [activeConfig, messages.length]);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinkingContent, activeTool]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() && !attachedFile) return;
    if (isGenerating || !activeConfig) return;

    let userContent = input.trim();
    if (attachedFile) {
      // If it's an image, the backend needs it separately.
      // For now, we'll append a text note if it's a file, or if we build full vision we send it differently.
      // Let's assume the user just wants the model to know about the file for now.
      userContent = userContent ? `${userContent}\n[Attached file: ${attachedFile}]` : `[Attached file: ${attachedFile}]`;
    }

    const userMsg = { role: "user" as const, content: userContent };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    
    // We'll pass the image path directly to the backend if it's an image
    const isImage = attachedFile?.match(/\.(jpg|jpeg|png|webp)$/i);
    const imagePath = isImage ? attachedFile : undefined;
    
    setAttachedFile(null);
    setIsGenerating(true);
    setThinkingContent("");
    setActiveTool(null);

    try {
      const response = await fetch("http://127.0.0.1:7861/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cartridge_ids: activeConfig.active_cartridge_ids,
          messages: [...messages, userMsg],
          image_path: imagePath
        }),
      });

      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let currentAssistantMessage = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value);
        const lines = chunk.split("\n\n");
        
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          
          try {
            const data = JSON.parse(line.substring(6));
            
            if (data.type === "think_token") {
              setThinkingContent((prev) => prev + data.data);
            } else if (data.type === "token") {
              currentAssistantMessage += data.data;
              // Keep updating the last message
              setMessages((prev) => {
                const newMsgs = [...prev];
                if (newMsgs[newMsgs.length - 1].role === "assistant") {
                  newMsgs[newMsgs.length - 1].content = currentAssistantMessage;
                } else {
                  newMsgs.push({ role: "assistant", content: currentAssistantMessage });
                }
                return newMsgs;
              });
            } else if (data.type === "tool_start") {
              setActiveTool(data.data);
            } else if (data.type === "tool_result") {
              const resultText = data.data.result;
              const toolName = data.data.name;
              if (toolName === "execute_python") {
                currentAssistantMessage += `\n\n> **SANDBOX** \`${toolName}\`\n> ${resultText.split('\n').join('\n> ')}\n\n`;
              } else {
                currentAssistantMessage += `\n\n> 🔧 **${toolName}**\n> \`\`\`\n> ${resultText}\n> \`\`\`\n\n`;
              }
              setMessages((prev) => {
                const newMsgs = [...prev];
                if (newMsgs[newMsgs.length - 1].role === "assistant") {
                  newMsgs[newMsgs.length - 1].content = currentAssistantMessage;
                }
                return newMsgs;
              });
              setActiveTool(null);
            } else if (data.type === "sandbox_images") {
              // Append sandbox plot images to the current assistant message
              const imgs = data.data as string[];
              setMessages((prev) => {
                const newMsgs = [...prev];
                const lastMsg = newMsgs[newMsgs.length - 1];
                if (lastMsg && lastMsg.role === "assistant") {
                  lastMsg.images = [...(lastMsg.images || []), ...imgs];
                }
                return [...newMsgs];
              });
            } else if (data.type === "done") {
              setIsGenerating(false);
              setThinkingContent("");
            } else if (data.type === "error") {
              console.error(data.data);
              setIsGenerating(false);
            }
          } catch (e) {
            console.error("Failed to parse SSE line", line, e);
          }
        }
      }
    } catch (error) {
      console.error(error);
      setIsGenerating(false);
    }
  };

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

      {/* Hardware Accents */}
      <div className="absolute top-4 left-6 flex gap-2">
        <div className="w-3 h-3 rounded-full bg-red-500 opacity-80" />
        <div className={`w-3 h-3 rounded-full ${isGenerating ? "bg-[var(--accent)] animate-pulse crt-glow" : "bg-white/20"}`} />
        <div className={`w-3 h-3 rounded-full ${activeTool ? "bg-blue-400 animate-pulse crt-glow" : "bg-white/20"}`} />
      </div>
      
      {/* Cartridge Slot */}
      <div className="absolute top-4 right-8 flex items-center gap-3">
        <div className="text-xs uppercase tracking-widest text-white/40">Active Cartridge</div>
        <div className="bg-black/40 border border-white/10 px-4 py-1.5 rounded text-[var(--accent)] text-glow font-bold text-sm tracking-wider shadow-inner flex items-center gap-2">
          {activeConfig ? activeConfig.active_cartridge_ids[0].toUpperCase() : "NO CARTRIDGE"}
          <button 
            onClick={onChangeCartridge}
            className="ml-2 hover:text-white transition-colors"
            title="Eject Cartridge"
          >
            ⏏
          </button>
        </div>
      </div>

      {/* Screen Area */}
      <div className="flex-1 mt-6 rounded-2xl border-4 border-black/80 crt-screen p-6 overflow-hidden flex flex-col relative">
        <div className="flex-1 overflow-y-auto crt-scroll pr-4 space-y-6">
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
                ) : (
                  <>
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm, remarkMath]}
                      rehypePlugins={[rehypeKatex]}
                    >
                      {msg.content}
                    </ReactMarkdown>
                    {msg.images && msg.images.length > 0 && (
                      <div className="mt-3 space-y-3">
                        {msg.images.map((src, imgIdx) => (
                          <div key={imgIdx} className="border border-[var(--accent)]/20 rounded-lg overflow-hidden bg-black/60 p-1">
                            <img 
                              src={src} 
                              alt={`Sandbox plot ${imgIdx + 1}`}
                              className="w-full max-w-lg rounded"
                            />
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}

          {/* Thinking UI */}
          {thinkingContent && (
            <div className="flex justify-start">
              <div className="max-w-[85%] border border-[var(--accent)]/30 bg-black/40 rounded p-4 text-[var(--accent)]/70 text-sm font-mono opacity-80">
                <div className="font-bold mb-2 uppercase tracking-widest flex items-center gap-2">
                  <span className="animate-spin">◷</span> Processing...
                </div>
                <div className="whitespace-pre-wrap">{thinkingContent}</div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Tool overlay */}
        {activeTool && (
          <div className="absolute bottom-6 right-6 bg-black/90 border border-blue-500/50 p-3 rounded text-blue-400 text-xs font-mono shadow-[0_0_20px_rgba(59,130,246,0.2)] z-50">
            <div className="font-bold mb-1 flex items-center gap-2">
              <span className="w-2 h-2 bg-blue-500 rounded-full animate-ping" />
              EXECUTING: {activeTool.name}
            </div>
            <div className="opacity-70 truncate max-w-[200px]">
              {JSON.stringify(activeTool.args)}
            </div>
          </div>
        )}
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
