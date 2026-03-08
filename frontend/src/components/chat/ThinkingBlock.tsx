"use client";

import React, { useState } from "react";
import { ChevronDown, ChevronRight, Clock } from "lucide-react";
import type { ThinkingSegment } from "./types";

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

export default ThinkingBlock;
