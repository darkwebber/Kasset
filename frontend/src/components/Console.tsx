"use client";

import { useCartridgeStore } from "@/stores/cartridgeStore";
import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

interface Message {
  role: "user" | "assistant" | "system";
  content: string;
}

export default function Console() {
  const { activeConfig } = useCartridgeStore();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [thinkingContent, setThinkingContent] = useState("");
  const [activeTool, setActiveTool] = useState<{name: string, args: any} | null>(null);
  
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
    if (!input.trim() || isGenerating || !activeConfig) return;

    const userMsg = { role: "user" as const, content: input.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
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
              // Add a visual marker in the chat for the tool execution
              currentAssistantMessage += `\n\n> 🔧 **${data.data.name}**\n> \`\`\`\n> ${data.data.result}\n> \`\`\`\n\n`;
              setMessages((prev) => {
                const newMsgs = [...prev];
                if (newMsgs[newMsgs.length - 1].role === "assistant") {
                  newMsgs[newMsgs.length - 1].content = currentAssistantMessage;
                }
                return newMsgs;
              });
              setActiveTool(null);
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

  // Apply theme variables
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
      {/* Hardware Accents */}
      <div className="absolute top-4 left-6 flex gap-2">
        <div className="w-3 h-3 rounded-full bg-red-500 opacity-80" />
        <div className={`w-3 h-3 rounded-full ${isGenerating ? "bg-[var(--accent)] animate-pulse crt-glow" : "bg-white/20"}`} />
        <div className={`w-3 h-3 rounded-full ${activeTool ? "bg-blue-400 animate-pulse crt-glow" : "bg-white/20"}`} />
      </div>
      
      {/* Cartridge Slot */}
      <div className="absolute top-4 right-8 flex items-center gap-3">
        <div className="text-xs uppercase tracking-widest text-white/40">Active Cartridge</div>
        <div className="bg-black/40 border border-white/10 px-4 py-1.5 rounded text-[var(--accent)] text-glow font-bold text-sm tracking-wider shadow-inner">
          {activeConfig ? activeConfig.active_cartridge_ids[0].toUpperCase() : "NO CARTRIDGE"}
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
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm, remarkMath]}
                    rehypePlugins={[rehypeKatex]}
                  >
                    {msg.content}
                  </ReactMarkdown>
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
      <div className="mt-6 bg-black/60 rounded-xl p-2 border border-white/10 shadow-inner">
        <form onSubmit={handleSubmit} className="flex items-center">
          <div className="text-[var(--accent)] px-3 text-xl font-bold">{">"}</div>
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
            disabled={isGenerating || !input.trim() || !activeConfig}
            className="px-6 py-2 bg-[var(--accent)] text-black font-bold uppercase tracking-widest rounded mx-1 hover:bg-white transition-colors disabled:opacity-30"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
