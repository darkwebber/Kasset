"use client";

import React, { useRef } from "react";
import {
  Plus, History, Command, Wrench, HelpCircle, Volume2, VolumeX,
} from "lucide-react";
import { soundTick, soundCartridgeEject } from "@/lib/sounds";
import { showToast } from "../Toast";
import { useCartridgeStore } from "@/stores/cartridgeStore";
import { useUIStore } from "@/stores/uiStore";

interface ConsoleHeaderProps {
  isGenerating: boolean;
  contextInfo: { message_count: number; estimated_tokens: number; max_tokens: number } | null;
  messageCount: number;
  muted: boolean;
  toggleMute: () => void;
  currentCartridge: { id: string; name: string; icon?: string } | null | undefined;
  activeConfig: any;
  onNewChat: () => void;
  onStop: () => void;
  onOpenDrawerTo: (tab: "history" | "memory" | "context") => void;
  onOpenForge?: () => void;
  onChangeCartridge: () => void;
}

export default function ConsoleHeader({
  isGenerating,
  contextInfo,
  messageCount,
  muted,
  toggleMute,
  currentCartridge,
  activeConfig,
  onNewChat,
  onStop,
  onOpenDrawerTo,
  onOpenForge,
  onChangeCartridge,
}: ConsoleHeaderProps) {
  const { ejectCartridge } = useCartridgeStore();
  const { setShowSnake: setShowSignalDebug, setShowPalette, setShowTutorial } = useUIStore();
  const redDotClicks = useRef(0);
  const redDotTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  return (
    <>
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
                setShowSignalDebug(true);
              }
            }}
          />
          <div aria-label={isGenerating ? "Generating response" : "Idle"} className={`w-2.5 h-2.5 sm:w-3 sm:h-3 rounded-full ${isGenerating ? "bg-[var(--accent)] animate-pulse crt-glow" : "bg-white/20"}`} />
        </div>
        {contextInfo && (
          <button
            onClick={() => onOpenDrawerTo("context")}
            className="hidden sm:flex items-center gap-2 ml-2 hover:opacity-80 transition-opacity cursor-pointer"
            title={`${contextInfo.estimated_tokens} / ${contextInfo.max_tokens} tokens · Click for context settings`}
          >
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
            <span className="text-[9px] text-white/30 font-mono">{messageCount} msg</span>
          </button>
        )}
      </div>

      {/* Top Bar — controls */}
      <div className="absolute top-2 sm:top-4 right-3 sm:right-8 flex items-center gap-0.5 sm:gap-1 no-select">
        <button onClick={onNewChat} aria-label="New Chat" className="p-2 sm:p-1.5 rounded text-white/30 hover:text-[var(--accent)] hover:bg-white/5 active:bg-white/10 transition-all" title="New Chat (⌘N)">
          <Plus size={15} />
        </button>
        <button onClick={() => onOpenDrawerTo("history")} aria-label="Chat History" className="p-2 sm:p-1.5 rounded text-white/30 hover:text-[var(--accent)] hover:bg-white/5 active:bg-white/10 transition-all" title="Chat History">
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
              onStop();
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
    </>
  );
}
