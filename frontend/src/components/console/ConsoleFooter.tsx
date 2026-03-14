"use client";

import React, { useRef, useState, useEffect } from "react";
import { Brain, ChevronDown, Search, Clock } from "lucide-react";
import { soundTick } from "@/lib/sounds";
import QuickSettings from "../QuickSettings";
import { useUIStore } from "@/stores/uiStore";

interface ConsoleFooterProps {
  memoryCount: number;
  modelName: string;
  ctxActiveCount: number;
  activeConfig: any;
  sessionStart: number;
  onModelChange: (name: string) => void;
  onOpenDrawerTo: (tab: "history" | "memory" | "context", search?: boolean, autoPreview?: boolean) => void;
}

function formatDuration(ms: number): string {
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export default function ConsoleFooter({
  memoryCount,
  modelName,
  ctxActiveCount,
  activeConfig,
  sessionStart,
  onModelChange,
  onOpenDrawerTo,
}: ConsoleFooterProps) {
  const { showMentalModel, setShowMentalModel, showQuickSettings, setShowQuickSettings } = useUIStore();
  const qsAnchorDesktopRef = useRef<HTMLButtonElement>(null);
  const qsAnchorMobileRef = useRef<HTMLButtonElement>(null);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setElapsed(Date.now() - sessionStart), 30_000);
    setElapsed(Date.now() - sessionStart);
    return () => clearInterval(id);
  }, [sessionStart]);

  const isLongSession = elapsed > 2 * 60 * 60 * 1000; // 2 hours

  return (
    <>
      {/* Mobile info strip — compact icon buttons */}
      <div className="flex sm:hidden items-center justify-center gap-1 mt-1 text-[10px] text-white/25 font-mono select-none px-1 safe-bottom">
        <button
          onClick={() => { setShowMentalModel(!showMentalModel); soundTick(); }}
          className={`p-2 rounded-lg transition-all ${showMentalModel ? "text-[var(--accent)] bg-white/5" : "text-white/30 active:bg-white/5"}`}
          aria-label="Mental Model"
        >
          <Brain size={16} />
        </button>
        <button
          onClick={() => onOpenDrawerTo("memory")}
          className="p-2 rounded-lg text-white/30 active:bg-white/5 transition-all"
          aria-label="Memories"
        >
          <span className="text-sm">🧠</span>
        </button>
        <div className="relative">
          <button
            ref={qsAnchorMobileRef}
            onClick={() => { setShowQuickSettings(!showQuickSettings); soundTick(); }}
            className={`p-2 rounded-lg transition-all ${showQuickSettings ? "text-[var(--accent)] bg-white/5" : "text-white/30 active:bg-white/5"}`}
            aria-label="Settings"
          >
            <ChevronDown size={16} />
          </button>
          {showQuickSettings && (
            <QuickSettings
              onClose={() => setShowQuickSettings(false)}
              hasRssTool={activeConfig?.tools?.includes("read_rss") || false}
              onOpenFullPreview={() => onOpenDrawerTo("context", false, true)}
              onModelChange={onModelChange}
              anchorRef={qsAnchorMobileRef}
            />
          )}
        </div>
        <button
          onClick={() => onOpenDrawerTo("history", true)}
          className="p-2 rounded-lg text-white/30 active:bg-white/5 transition-all"
          aria-label="Search chats"
        >
          <Search size={16} />
        </button>
      </div>
      {/* Desktop info strip — keyboard hints + interactive system indicators */}
      <div className="hidden sm:flex items-center justify-between mt-1.5 text-[10px] text-white/25 font-mono select-none px-1">
        <div className="flex items-center gap-3">
          <span>⌘K commands</span>
          <span className="text-white/10">·</span>
          <span>⇧↵ newline</span>
          {elapsed > 60_000 && (
            <>
              <span className="text-white/10">·</span>
              <span className={`flex items-center gap-1 ${isLongSession ? "text-amber-400/50" : ""}`} title={isLongSession ? "You've been going for a while — consider a break!" : "Session duration"}>
                <Clock size={9} />
                {formatDuration(elapsed)}
              </span>
            </>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => { setShowMentalModel(!showMentalModel); soundTick(); }}
            className={`flex items-center gap-1 px-1.5 py-0.5 rounded transition-all cursor-pointer ${showMentalModel ? "text-[var(--accent)] bg-white/5" : "hover:bg-white/5 hover:text-[var(--accent)]/60"}`}
            title="View Agent's Mental Model"
          >
            <Brain size={11} />
            <span>mental model</span>
          </button>
          <span className="text-white/10">·</span>
          <button
            onClick={() => onOpenDrawerTo("memory")}
            className="flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-white/5 hover:text-[var(--accent)]/60 transition-all cursor-pointer"
            title="View learned memories"
          >
            <span className="text-[9px]">🧠</span>
            <span>{memoryCount} memories</span>
          </button>
          <span className="text-white/10">·</span>
          {/* Model & context — opens QuickSettings popover */}
          <div className="relative">
            <button
              ref={qsAnchorDesktopRef}
              onClick={() => { setShowQuickSettings(!showQuickSettings); soundTick(); }}
              className={`flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-white/5 transition-all cursor-pointer ${showQuickSettings ? "text-[var(--accent)]/60 bg-white/5" : "hover:text-[var(--accent)]/60"}`}
              title="Model, context layers & RSS settings"
            >
              <span>{modelName || "model"}</span>
              <span className="text-white/15">({ctxActiveCount}/3 ctx)</span>
            </button>
            {showQuickSettings && (
              <QuickSettings
                onClose={() => setShowQuickSettings(false)}
                hasRssTool={activeConfig?.tools?.includes("read_rss") || false}
                onOpenFullPreview={() => onOpenDrawerTo("context", false, true)}
                onModelChange={onModelChange}
                anchorRef={qsAnchorDesktopRef}
              />
            )}
          </div>
          <span className="text-white/10">·</span>
          <button
            onClick={() => onOpenDrawerTo("history", true)}
            className="flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-white/5 hover:text-[var(--accent)]/60 transition-all cursor-pointer"
            title="Search across all conversations"
          >
            <Search size={9} />
            <span>all chats</span>
          </button>
        </div>
      </div>
    </>
  );
}
