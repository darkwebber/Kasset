"use client";

import { useMemo } from "react";
import { Search } from "lucide-react";
import { getToolMeta, TOOL_DISPLAY, TOOL_EXAMPLES } from "./toolMeta";

interface WelcomeScreenProps {
  cartridgeName: string;
  cartridgeIcon: string;
  bootMessage: string;
  tools: string[];
  suggestedPrompts: string[];
  onSendPrompt: (prompt: string) => void;
  memoryCount?: number;
  modelName?: string;
  ctxActiveCount?: number;
  onOpenMemory?: () => void;
  onOpenContext?: () => void;
  onOpenSearch?: () => void;
}

export default function WelcomeScreen({ cartridgeName, cartridgeIcon, bootMessage, tools, suggestedPrompts, onSendPrompt, memoryCount, modelName, ctxActiveCount, onOpenMemory, onOpenContext, onOpenSearch }: WelcomeScreenProps) {
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

      {/* System info + keyboard hints */}
      <div className="hidden sm:flex items-center gap-2 text-[10px] text-white/25 font-mono">
        <span>⌘K commands</span>
        <span className="text-white/10">·</span>
        <span>⌘N new chat</span>
        {(memoryCount !== undefined || modelName) && (
          <>
            <span className="text-white/[0.06] mx-1">│</span>
            {onOpenMemory && memoryCount !== undefined && (
              <button onClick={onOpenMemory} className="px-1.5 py-0.5 rounded hover:bg-white/5 hover:text-[var(--accent)]/60 transition-all cursor-pointer">
                🧠 {memoryCount} memories
              </button>
            )}
            {onOpenContext && modelName && (
              <>
                <span className="text-white/10">·</span>
                <button onClick={onOpenContext} className="px-1.5 py-0.5 rounded hover:bg-white/5 hover:text-[var(--accent)]/60 transition-all cursor-pointer">
                  {modelName} <span className="text-white/15">({ctxActiveCount ?? 0}/3 ctx)</span>
                </button>
              </>
            )}
            {onOpenSearch && (
              <>
                <span className="text-white/10">·</span>
                <button onClick={onOpenSearch} className="flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-white/5 hover:text-[var(--accent)]/60 transition-all cursor-pointer">
                  <Search size={9} /> all chats
                </button>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
