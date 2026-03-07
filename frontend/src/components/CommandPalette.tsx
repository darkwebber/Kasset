"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { Search, Plus, History, Download, Wrench, HelpCircle, Volume2, VolumeX, LogOut, Copy, Command } from "lucide-react";
import { soundTick } from "@/lib/sounds";

interface Action {
  id: string;
  label: string;
  description: string;
  icon: React.ReactNode;
  shortcut?: string;
  keywords: string[];
  action: () => void;
}

interface CommandPaletteProps {
  onClose: () => void;
  onNewChat: () => void;
  onOpenHistory: () => void;
  onExportChat: () => void;
  onCopyChat: () => void;
  onOpenForge?: () => void;
  onOpenHelp: () => void;
  onToggleMute: () => void;
  onEjectCartridge: () => void;
  isMuted: boolean;
  cartridgeName: string;
  hasMessages: boolean;
}

export default function CommandPalette({
  onClose, onNewChat, onOpenHistory, onExportChat, onCopyChat,
  onOpenForge, onOpenHelp, onToggleMute, onEjectCartridge,
  isMuted, cartridgeName, hasMessages,
}: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [selectedIdx, setSelectedIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const actions: Action[] = useMemo(() => [
    { id: "new", label: "New Chat", description: "Start a fresh conversation", icon: <Plus size={16} />, shortcut: "⌘N", keywords: ["new", "chat", "fresh", "clear", "reset"], action: onNewChat },
    { id: "history", label: "Chat History", description: "Browse previous conversations", icon: <History size={16} />, shortcut: "", keywords: ["history", "previous", "past", "browse", "memory"], action: onOpenHistory },
    { id: "export", label: "Export Chat", description: "Download as Markdown file", icon: <Download size={16} />, shortcut: "⌘E", keywords: ["export", "download", "save", "markdown"], action: onExportChat },
    { id: "copy", label: "Copy Conversation", description: "Copy full chat to clipboard", icon: <Copy size={16} />, shortcut: "⌘⇧C", keywords: ["copy", "clipboard", "share", "text"], action: onCopyChat },
    ...(onOpenForge ? [{ id: "forge", label: "Kasset Forge", description: "Create & edit kassets and tools", icon: <Wrench size={16} />, shortcut: "⌘⇧F", keywords: ["forge", "create", "edit", "kasset", "cartridge", "tool", "plugin", "studio"], action: onOpenForge }] : []),
    { id: "help", label: "Quick Guide", description: "Tips, shortcuts, and how-to", icon: <HelpCircle size={16} />, shortcut: "⌘/", keywords: ["help", "guide", "tutorial", "tips", "shortcuts", "how"], action: onOpenHelp },
    { id: "mute", label: isMuted ? "Unmute Sounds" : "Mute Sounds", description: isMuted ? "Turn sound effects back on" : "Silence all sound effects", icon: isMuted ? <VolumeX size={16} /> : <Volume2 size={16} />, shortcut: "", keywords: ["mute", "sound", "audio", "volume", "unmute"], action: onToggleMute },
    { id: "eject", label: "Switch Kasset", description: `Eject ${cartridgeName} and pick another`, icon: <LogOut size={16} />, shortcut: "", keywords: ["eject", "switch", "kasset", "cartridge", "change", "swap"], action: onEjectCartridge },
  ], [onNewChat, onOpenHistory, onExportChat, onCopyChat, onOpenForge, onOpenHelp, onToggleMute, onEjectCartridge, isMuted, cartridgeName]);

  const filtered = useMemo(() => {
    if (!query.trim()) return actions;
    const q = query.toLowerCase();
    return actions.filter(a =>
      a.label.toLowerCase().includes(q) ||
      a.description.toLowerCase().includes(q) ||
      a.keywords.some(k => k.includes(q))
    );
  }, [query, actions]);

  useEffect(() => { setSelectedIdx(0); }, [query]);

  useEffect(() => {
    inputRef.current?.focus();
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key === "ArrowDown") { e.preventDefault(); setSelectedIdx(i => Math.min(i + 1, filtered.length - 1)); }
      if (e.key === "ArrowUp") { e.preventDefault(); setSelectedIdx(i => Math.max(i - 1, 0)); }
      if (e.key === "Enter" && filtered.length > 0) {
        e.preventDefault();
        soundTick();
        filtered[selectedIdx]?.action();
        onClose();
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [filtered, selectedIdx, onClose]);

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center pt-[10vh] sm:pt-[15vh]" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-md mx-2 sm:mx-4 bg-[#0c0c10] border border-white/10 rounded-xl shadow-2xl overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-white/5">
          <Search size={16} className="text-white/30 shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Type a command..."
            className="flex-1 bg-transparent text-white/80 text-sm outline-none placeholder-white/20 font-mono"
            autoFocus
          />
          <kbd className="text-[9px] text-white/20 bg-white/5 px-1.5 py-0.5 rounded font-mono border border-white/5">ESC</kbd>
        </div>

        {/* Results */}
        <div className="max-h-[300px] overflow-y-auto py-1">
          {filtered.length === 0 ? (
            <div className="px-4 py-6 text-center text-white/20 text-xs font-mono">No matching commands</div>
          ) : (
            filtered.map((action, i) => (
              <button
                key={action.id}
                onClick={() => { soundTick(); action.action(); onClose(); }}
                onMouseEnter={() => setSelectedIdx(i)}
                className={`w-full flex items-center gap-3 px-4 py-3 sm:py-2.5 text-left transition-colors active:opacity-70 ${
                  i === selectedIdx ? "bg-[var(--accent,#00ff88)]/10 text-[var(--accent,#00ff88)]" : "text-white/50 hover:bg-white/5"
                }`}
              >
                <span className={i === selectedIdx ? "text-[var(--accent)]" : "text-white/30"}>{action.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium">{action.label}</div>
                  <div className="text-[10px] opacity-50 truncate">{action.description}</div>
                </div>
                {action.shortcut && (
                  <kbd className="text-[9px] text-white/15 bg-white/5 px-1.5 py-0.5 rounded font-mono border border-white/5">{action.shortcut}</kbd>
                )}
              </button>
            ))
          )}
        </div>

        {/* Footer hint */}
        <div className="hidden sm:flex px-4 py-2 border-t border-white/5 items-center gap-3 text-[9px] text-white/15 font-mono">
          <span className="flex items-center gap-1"><Command size={9} />K to toggle</span>
          <span>↑↓ navigate</span>
          <span>⏎ select</span>
        </div>
      </div>
    </div>
  );
}
