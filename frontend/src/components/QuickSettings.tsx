"use client";

import { useState, useEffect, useRef, useLayoutEffect } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronRight, Rss, Plus, Trash2, Loader2 } from "lucide-react";
import { getApiBase } from "@/lib/api";
import { useSettingsStore } from "@/stores/settingsStore";
import { showToast } from "./Toast";
import { soundTick } from "@/lib/sounds";

interface QuickSettingsProps {
  onClose: () => void;
  hasRssTool: boolean;
  onOpenFullPreview: () => void;
  onModelChange: (name: string) => void;
  anchorRef?: React.RefObject<HTMLElement | null>;
}

export default function QuickSettings({ onClose, hasRssTool, onOpenFullPreview, onModelChange, anchorRef }: QuickSettingsProps) {
  const { context: ctxSettings, updateContext } = useSettingsStore();
  const [models, setModels] = useState<any[]>([]);
  const [currentModel, setCurrentModel] = useState("");
  const [modelStatus, setModelStatus] = useState("");
  const [modelSwitching, setModelSwitching] = useState(false);
  const [rssFeeds, setRssFeeds] = useState<{name: string; url: string}[]>([]);
  const [showAddRss, setShowAddRss] = useState(false);
  const [newRssName, setNewRssName] = useState("");
  const [newRssUrl, setNewRssUrl] = useState("");
  const popoverRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{bottom: number; right: number} | null>(null);

  // Compute fixed position from anchor button
  useLayoutEffect(() => {
    if (anchorRef?.current) {
      const rect = anchorRef.current.getBoundingClientRect();
      setPos({
        bottom: window.innerHeight - rect.top + 8,
        right: window.innerWidth - rect.right,
      });
    }
  }, [anchorRef]);

  // Fetch models + poll status while open
  useEffect(() => {
    const fetchStatus = () => {
      fetch(`${getApiBase()}/api/models`).then(r => r.json()).then(d => {
        setModels(d.models || []);
        setCurrentModel(d.current || "");
        setModelStatus(d.status?.status || "");
      }).catch(() => {});
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 4000);
    return () => clearInterval(interval);
  }, []);

  // Fetch RSS if relevant
  useEffect(() => {
    if (hasRssTool) {
      fetch(`${getApiBase()}/api/rss-feeds`).then(r => r.json()).then(d => {
        setRssFeeds(d.feeds || []);
      }).catch(() => {});
    }
  }, [hasRssTool]);

  // Close on click outside or Escape
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); onClose(); }
    };
    setTimeout(() => document.addEventListener("mousedown", handleClick), 10);
    document.addEventListener("keydown", handleEsc, true);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleEsc, true);
    };
  }, [onClose]);

  const switchModel = async (modelId: string) => {
    if (modelId === currentModel) return;
    setModelSwitching(true);
    try {
      const res = await fetch(`${getApiBase()}/api/model/switch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_path: modelId, force: true }),
      });
      if (res.ok) {
        setCurrentModel(modelId);
        setModelStatus("loading");
        const shortName = modelId.split("/").pop() || modelId;
        onModelChange(shortName);
        showToast(`Switching to ${shortName}…`);
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.error || "Switch failed");
      }
    } catch {} finally { setModelSwitching(false); }
  };

  const addRssFeed = async () => {
    if (!newRssUrl.trim()) return;
    try {
      const res = await fetch(`${getApiBase()}/api/rss-feeds`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newRssName.trim() || new URL(newRssUrl).hostname, url: newRssUrl.trim() }),
      });
      if (res.ok) { const d = await res.json(); setRssFeeds(d.feeds || []); }
    } catch {}
    setNewRssName(""); setNewRssUrl(""); setShowAddRss(false); soundTick();
  };

  const deleteRssFeed = async (index: number) => {
    try {
      const res = await fetch(`${getApiBase()}/api/rss-feeds/${index}`, { method: "DELETE" });
      if (res.ok) { const d = await res.json(); setRssFeeds(d.feeds || []); }
    } catch {}
    soundTick();
  };

  const ctxLayers: { key: keyof typeof ctxSettings; label: string }[] = [
    { key: "use_session_summary", label: "Session Summary" },
    { key: "use_cartridge_context", label: "Kasset Context" },
    { key: "use_global_profile", label: "Global Profile" },
  ];

  const popover = (
    <div
      ref={popoverRef}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
      className="fixed w-full sm:w-72 max-h-[80dvh] sm:max-h-[70vh] bg-[#0c0c10] border border-white/10 rounded-xl shadow-2xl overflow-y-auto animate-in fade-in slide-in-from-bottom-2 duration-150"
      style={{
        zIndex: 9999,
        ...(pos
          ? { bottom: pos.bottom, right: pos.right, left: 'auto', top: 'auto' }
          : { bottom: 0, left: 0, right: 0, borderRadius: '0.75rem 0.75rem 0 0' })
      }}
    >
      {/* Models */}
      <div className="p-3 border-b border-white/5">
        <div className="text-[10px] text-white/30 font-mono uppercase tracking-wider mb-2">Model</div>
        <div className="space-y-0.5 max-h-36 overflow-y-auto crt-scroll">
          {models.map((m: any) => {
            const isCurrent = m.id === currentModel;
            const shortName = m.id.split("/").pop() || m.id;
            return (
              <button
                key={m.id}
                onClick={() => switchModel(m.id)}
                disabled={modelSwitching && !isCurrent}
                className={`w-full flex items-center justify-between px-2 py-1.5 rounded text-[11px] font-mono transition-all ${
                  isCurrent
                    ? "bg-[var(--accent)]/10 text-[var(--accent)]"
                    : "text-white/50 hover:bg-white/5 hover:text-white/70"
                } ${modelSwitching && !isCurrent ? "opacity-30" : ""}`}
              >
                <span className="truncate">{shortName}</span>
                {isCurrent && (
                  modelStatus === "loading"
                    ? <Loader2 size={10} className="animate-spin text-[var(--accent)]/50 shrink-0" />
                    : <Check size={10} className="shrink-0" />
                )}
              </button>
            );
          })}
          {models.length === 0 && (
            <p className="text-[10px] text-white/20 px-2 py-1">No cached models found.</p>
          )}
        </div>
      </div>

      {/* Context Layers */}
      <div className="p-3 border-b border-white/5">
        <div className="text-[10px] text-white/30 font-mono uppercase tracking-wider mb-2">Context Layers</div>
        <div className="space-y-0.5">
          {ctxLayers.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => { updateContext(key, !ctxSettings[key]); soundTick(); }}
              className="w-full flex items-center justify-between px-2 py-1.5 rounded text-[11px] font-mono text-white/50 hover:bg-white/5 transition-all"
            >
              <span>{label}</span>
              <div className={`w-7 h-[16px] rounded-full transition-colors relative ${ctxSettings[key] ? "bg-[var(--accent)]/40" : "bg-white/10"}`}>
                <div className={`w-3 h-3 rounded-full absolute top-0.5 transition-all ${ctxSettings[key] ? "left-3.5 bg-[var(--accent)]" : "left-0.5 bg-white/30"}`} />
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* RSS Feeds — conditional on cartridge having read_rss */}
      {hasRssTool && (
        <div className="p-3 border-b border-white/5">
          <div className="flex items-center justify-between mb-2">
            <div className="text-[10px] text-white/30 font-mono uppercase tracking-wider flex items-center gap-1">
              <Rss size={9} /> RSS Feeds
            </div>
            <button
              onClick={() => { setShowAddRss(!showAddRss); soundTick(); }}
              className="text-[9px] text-[var(--accent)]/50 hover:text-[var(--accent)] font-mono transition-colors"
            >
              {showAddRss ? "Cancel" : "+ Add"}
            </button>
          </div>
          {showAddRss && (
            <div className="space-y-1 mb-2">
              <input
                type="text" placeholder="Feed name"
                value={newRssName} onChange={e => setNewRssName(e.target.value)}
                className="w-full bg-black/30 border border-white/10 rounded px-2 py-1 text-[10px] text-white/70 font-mono placeholder:text-white/20 focus:outline-none focus:border-[var(--accent)]/30"
              />
              <div className="flex gap-1">
                <input
                  type="url" placeholder="Feed URL"
                  value={newRssUrl} onChange={e => setNewRssUrl(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && addRssFeed()}
                  className="flex-1 bg-black/30 border border-white/10 rounded px-2 py-1 text-[10px] text-white/70 font-mono placeholder:text-white/20 focus:outline-none focus:border-[var(--accent)]/30"
                />
                <button onClick={addRssFeed} className="px-2 py-1 rounded text-[10px] font-mono bg-[var(--accent)]/10 text-[var(--accent)]/70 hover:bg-[var(--accent)]/20 transition-colors">
                  Add
                </button>
              </div>
            </div>
          )}
          <div className="space-y-0.5 max-h-24 overflow-y-auto crt-scroll">
            {rssFeeds.map((feed, i) => (
              <div key={i} className="flex items-center justify-between px-2 py-1 rounded bg-black/20 group">
                <span className="text-[10px] text-white/40 font-mono truncate">{feed.name || feed.url}</span>
                <button
                  onClick={() => deleteRssFeed(i)}
                  className="opacity-0 group-hover:opacity-100 text-white/20 hover:text-red-400 transition-all p-0.5 shrink-0 ml-1"
                >
                  <Trash2 size={9} />
                </button>
              </div>
            ))}
            {rssFeeds.length === 0 && <p className="text-[9px] text-white/20 px-1">No custom feeds. Defaults used.</p>}
          </div>
        </div>
      )}

      {/* Preview injected context link */}
      <button
        onClick={() => { onOpenFullPreview(); onClose(); }}
        className="w-full flex items-center justify-between px-3 py-2.5 text-[10px] font-mono text-white/30 hover:text-[var(--accent)]/60 hover:bg-white/5 transition-all"
      >
        <span>Preview injected context</span>
        <ChevronRight size={10} />
      </button>
    </div>
  );

  if (typeof document === 'undefined') return popover;
  return createPortal(popover, document.body);
}
