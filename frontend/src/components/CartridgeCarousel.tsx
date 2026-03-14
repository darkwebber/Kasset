"use client";

import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { useCartridgeStore, CartridgeConfig } from "@/stores/cartridgeStore";
import { motion, AnimatePresence } from "framer-motion";
import { soundCartridgeInsert, soundTick } from "@/lib/sounds";
import { Search, Grid3X3, Rows3, Upload, X } from "lucide-react";

type ViewMode = "carousel" | "grid";
type Category = "all" | "builtin" | "user" | "recent";

export default function CartridgeCarousel({ onSelect, onOpenForge }: { onSelect: () => void; onOpenForge?: () => void }) {
  const { availableCartridges, loadActiveStack, lastActiveCartridgeId } = useCartridgeStore();
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [isInserting, setIsInserting] = useState(false);
  const [direction, setDirection] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [category, setCategory] = useState<Category>("all");
  const [viewMode, setViewMode] = useState<ViewMode>("carousel");
  const wheelCooldown = useRef(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);

  // Auto-switch to grid if many cartridges
  useEffect(() => {
    if (availableCartridges.length > 12) setViewMode("grid");
  }, [availableCartridges.length]);

  // Filter cartridges
  const filteredCartridges = useMemo(() => {
    let list = availableCartridges;
    if (category === "builtin") list = list.filter(c => c.source === "builtin");
    else if (category === "user") list = list.filter(c => c.source === "user");
    else if (category === "recent" && lastActiveCartridgeId) {
      // Show recently used first (just move last active to front for now)
      const idx = list.findIndex(c => c.id === lastActiveCartridgeId);
      if (idx > 0) list = [list[idx], ...list.slice(0, idx), ...list.slice(idx + 1)];
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(c =>
        c.name.toLowerCase().includes(q) ||
        c.description.toLowerCase().includes(q) ||
        c.tags.some(t => t.toLowerCase().includes(q)) ||
        c.id.toLowerCase().includes(q)
      );
    }
    return list;
  }, [availableCartridges, category, searchQuery, lastActiveCartridgeId]);

  const total = filteredCartridges.length;

  // Clamp selectedIndex when filter changes
  useEffect(() => {
    setSelectedIndex(i => {
      if (total === 0) return 0;
      const desired = lastActiveCartridgeId
        ? Math.max(0, filteredCartridges.findIndex(c => c.id === lastActiveCartridgeId))
        : 0;
      return Math.min(desired >= 0 ? desired : i, total - 1);
    });
  }, [filteredCartridges, total, lastActiveCartridgeId]);

  const navigate = useCallback((dir: number) => {
    if (isInserting || total === 0) return;
    setDirection(dir);
    setSelectedIndex((i) => (i + dir + total) % total);
    soundTick();
  }, [isInserting, total]);

  const handleLoad = useCallback(async (cart?: CartridgeConfig) => {
    if (isInserting || total === 0) return;
    const target = cart || filteredCartridges[selectedIndex];
    if (!target) return;
    setIsInserting(true);
    soundCartridgeInsert();
    setTimeout(async () => {
      await loadActiveStack([target.id]);
      onSelect();
      setIsInserting(false);
    }, 1200);
  }, [isInserting, total, selectedIndex, filteredCartridges, loadActiveStack, onSelect]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isInserting) return;
      // Don't navigate if search focused
      if (document.activeElement === searchRef.current) {
        if (e.key === "Escape") searchRef.current?.blur();
        if (e.key === "Enter" && total > 0) { e.preventDefault(); handleLoad(); }
        return;
      }
      if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); navigate(1); }
      else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); navigate(-1); }
      else if (e.key === "Enter") { e.preventDefault(); handleLoad(); }
      else if (e.key === "/" || e.key === "f" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); searchRef.current?.focus(); }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [navigate, handleLoad, isInserting, total]);

  // Mouse wheel navigation with cooldown (carousel only)
  useEffect(() => {
    if (viewMode !== "carousel") return;
    const handleWheel = (e: WheelEvent) => {
      if (wheelCooldown.current || isInserting) return;
      const delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
      if (Math.abs(delta) < 20) return;
      wheelCooldown.current = true;
      navigate(delta > 0 ? 1 : -1);
      setTimeout(() => { wheelCooldown.current = false; }, 250);
    };
    window.addEventListener("wheel", handleWheel, { passive: true });
    return () => window.removeEventListener("wheel", handleWheel);
  }, [navigate, isInserting, viewMode]);

  // Touch swipe for carousel
  useEffect(() => {
    if (viewMode !== "carousel") return;
    const onTouchStart = (e: TouchEvent) => {
      touchStartRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    };
    const onTouchEnd = (e: TouchEvent) => {
      if (!touchStartRef.current) return;
      const dx = e.changedTouches[0].clientX - touchStartRef.current.x;
      const dy = e.changedTouches[0].clientY - touchStartRef.current.y;
      if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) {
        navigate(dx < 0 ? 1 : -1);
      }
      touchStartRef.current = null;
    };
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchend", onTouchEnd, { passive: true });
    return () => {
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchend", onTouchEnd);
    };
  }, [navigate, viewMode]);

  const selected = total > 0 ? filteredCartridges[Math.min(selectedIndex, total - 1)] : null;
  const accent = selected?.theme.accent_color || "#00ff88";
  const glow = selected?.theme.glow_color || "#00ff88";

  const getOffset = (idx: number) => {
    let diff = idx - selectedIndex;
    if (diff > total / 2) diff -= total;
    if (diff < -total / 2) diff += total;
    return diff;
  };

  const userCount = availableCartridges.filter(c => c.source === "user").length;

  return (
    <div
      className="absolute inset-0 z-50 flex flex-col items-center overflow-hidden"
      style={{ background: `radial-gradient(ellipse at center, ${accent}08 0%, #000 70%)` }}
    >
      {/* Scanline overlay */}
      <div className="absolute inset-0 pointer-events-none z-40 opacity-20"
        style={{ background: `repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.3) 2px, rgba(0,0,0,0.3) 4px)` }}
      />

      {/* Top controls: Search + View toggle */}
      <div className="z-10 w-full max-w-2xl px-3 sm:px-6 pt-3 sm:pt-6 pb-1 sm:pb-2 flex flex-col gap-1.5 sm:gap-3">
        {/* Title row */}
        <div className="flex items-center justify-between">
          <motion.div
            key={accent}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="font-bold tracking-[0.2em] sm:tracking-[0.3em] uppercase text-sm sm:text-base select-none"
            style={{ color: accent, textShadow: `0 0 20px ${glow}, 0 0 40px ${glow}40` }}
          >
            Select Kasset
          </motion.div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setViewMode("carousel")}
              className={`p-1.5 rounded transition-all ${viewMode === "carousel" ? "text-[var(--accent)] bg-white/5" : "text-white/20 hover:text-white/40"}`}
              title="Carousel view"
            >
              <Rows3 size={14} />
            </button>
            <button
              onClick={() => setViewMode("grid")}
              className={`p-1.5 rounded transition-all ${viewMode === "grid" ? "text-[var(--accent)] bg-white/5" : "text-white/20 hover:text-white/40"}`}
              title="Grid view"
            >
              <Grid3X3 size={14} />
            </button>
          </div>
        </div>

        {/* Search bar */}
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/20" />
          <input
            ref={searchRef}
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search kassets... (press /)"
            className="w-full pl-9 pr-8 py-1.5 sm:py-2 bg-white/[0.03] border border-white/5 rounded-lg text-xs text-white/60 placeholder-white/15 font-mono outline-none focus:border-[var(--accent)]/30 transition-colors"
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery("")} className="absolute right-2 top-1/2 -translate-y-1/2 text-white/20 hover:text-white/40">
              <X size={12} />
            </button>
          )}
        </div>

        {/* Category tabs */}
        <div className="flex gap-1 overflow-x-auto no-scrollbar">
          {([
            { key: "all" as Category, label: `All (${availableCartridges.length})` },
            { key: "builtin" as Category, label: "Built-in" },
            ...(userCount > 0 ? [{ key: "user" as Category, label: `My (${userCount})` }] : []),
            ...(lastActiveCartridgeId ? [{ key: "recent" as Category, label: "Recent" }] : []),
          ]).map(tab => (
            <button
              key={tab.key}
              onClick={() => setCategory(tab.key)}
              className={`px-2.5 sm:px-3 py-1 rounded-md text-[9px] sm:text-[10px] uppercase tracking-wider font-mono transition-all whitespace-nowrap shrink-0 active:scale-95 ${
                category === tab.key
                  ? "bg-[var(--accent)]/10 text-[var(--accent)] border border-[var(--accent)]/20"
                  : "text-white/20 hover:text-white/40 border border-transparent"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {total === 0 ? (
        <div className="flex-1 flex items-center justify-center z-10">
          <div className="text-center">
            <div className="text-white/20 text-sm font-mono mb-2">No kassets found</div>
            <div className="text-white/10 text-xs font-mono">Try a different search or category</div>
          </div>
        </div>
      ) : viewMode === "grid" ? (
        /* ═══ Grid View ═══ */
        <div className="flex-1 min-h-0 z-10 w-full max-w-4xl px-3 sm:px-6 py-2 sm:py-4 overflow-y-auto crt-scroll momentum-scroll">
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5 sm:gap-3">
            {filteredCartridges.map((cart) => {
              const cartAccent = cart.theme.accent_color;
              return (
                <button
                  key={cart.id}
                  onClick={() => handleLoad(cart)}
                  disabled={isInserting}
                  className="group text-left rounded-xl overflow-hidden border transition-all duration-200 hover:scale-[1.03] active:scale-[0.97] disabled:opacity-50 relative"
                  style={{
                    background: `linear-gradient(160deg, rgba(26,26,46,0.95) 0%, rgba(15,15,26,0.98) 100%)`,
                    borderColor: `${cartAccent}25`,
                    boxShadow: `0 2px 12px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.04)`,
                  }}
                  onMouseEnter={e => {
                    (e.currentTarget as HTMLElement).style.borderColor = `${cartAccent}60`;
                    (e.currentTarget as HTMLElement).style.boxShadow = `0 4px 24px ${cartAccent}20, 0 0 0 1px ${cartAccent}15, inset 0 1px 0 rgba(255,255,255,0.06)`;
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLElement).style.borderColor = `${cartAccent}25`;
                    (e.currentTarget as HTMLElement).style.boxShadow = `0 2px 12px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.04)`;
                  }}
                >
                  <div className="h-[3px] rounded-t-xl" style={{ background: `linear-gradient(90deg, ${cartAccent}, ${cartAccent}80)` }} />
                  <div className="p-3 sm:p-3.5">
                    <div className="flex items-start justify-between mb-1.5">
                      <div className="text-xl sm:text-2xl">{cart.icon}</div>
                      {cart.source === "user" && (
                        <span className="text-[6px] px-1.5 py-0.5 rounded-full font-mono uppercase bg-blue-500/15 text-blue-400 border border-blue-500/20">custom</span>
                      )}
                    </div>
                    <div className="text-[11px] sm:text-xs font-bold text-white/80 leading-tight mb-1">{cart.name}</div>
                    <div className="text-[8px] sm:text-[9px] text-white/30 font-mono line-clamp-2 leading-relaxed mb-2">{cart.description}</div>
                    <div className="flex gap-1 flex-wrap">
                      {cart.tags.slice(0, 2).map(tag => (
                        <span key={tag} className="text-[6px] sm:text-[7px] px-1.5 py-0.5 rounded font-mono uppercase tracking-wider" style={{ background: `${cartAccent}12`, color: `${cartAccent}cc`, border: `1px solid ${cartAccent}20` }}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      ) : (
        /* ═══ Carousel View ═══ */
        <>
          <div className="flex-1 flex flex-col items-center justify-center z-10" style={{ minHeight: 0 }}>
            <div className="relative w-full max-w-5xl h-44 sm:h-72 flex items-center justify-center" style={{ perspective: "1200px" }}>
              <AnimatePresence mode="popLayout">
                {filteredCartridges.map((cart, idx) => {
                  const offset = getOffset(idx);
                  if (Math.abs(offset) > 3) return null;
                  const isSelected = idx === selectedIndex;
                  const cartAccent = cart.theme.accent_color;
                  const absOffset = Math.abs(offset);

                  return (
                    <motion.div
                      key={cart.id}
                      layout
                      onClick={() => {
                        if (isSelected) handleLoad();
                        else { setDirection(offset > 0 ? 1 : -1); setSelectedIndex(idx); }
                      }}
                      initial={{ opacity: 0, scale: 0.6 }}
                      animate={{
                        x: offset * (typeof window !== 'undefined' && window.innerWidth < 400 ? 75 : typeof window !== 'undefined' && window.innerWidth < 640 ? 110 : 200),
                        scale: isSelected ? (isInserting ? 0.85 : 1.0) : Math.max(0.55, 0.85 - absOffset * 0.12),
                        rotateY: offset * -12,
                        z: isSelected ? 100 : -absOffset * 80,
                        opacity: isSelected ? (isInserting ? 0.3 : 1) : Math.max(0.15, 0.7 - absOffset * 0.2),
                        y: isSelected && isInserting ? 30 : 0,
                      }}
                      exit={{ opacity: 0, scale: 0.5 }}
                      transition={{ type: "spring", stiffness: 300, damping: 30 }}
                      className="absolute cursor-pointer select-none"
                      style={{ zIndex: 10 - absOffset, transformStyle: "preserve-3d" }}
                    >
                      <div
                        className="w-28 h-40 xs:w-32 xs:h-44 sm:w-48 sm:h-64 rounded-t-2xl rounded-b-md flex flex-col overflow-hidden"
                        style={{
                          background: `linear-gradient(145deg, #1a1a2e 0%, #0f0f1a 100%)`,
                          border: `3px solid ${isSelected ? cartAccent : "rgba(255,255,255,0.08)"}`,
                          boxShadow: isSelected
                            ? `0 0 40px ${cartAccent}50, 0 0 80px ${cartAccent}20, inset 0 1px 0 rgba(255,255,255,0.1)`
                            : `0 4px 20px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.05)`,
                          transition: "border-color 0.3s, box-shadow 0.3s",
                        }}
                      >
                        <div className="flex justify-center">
                          <div className="w-14 h-1.5 rounded-b-full" style={{ background: cartAccent, opacity: isSelected ? 1 : 0.3 }} />
                        </div>
                        <div className="mx-2.5 mt-1.5 flex-1 rounded-lg flex flex-col p-2.5 relative overflow-hidden"
                          style={{ background: `linear-gradient(180deg, #f5f5f0 0%, #e8e4db 100%)` }}
                        >
                          <div className="absolute top-0 left-0 right-0 h-1.5" style={{ background: cartAccent }} />
                          <div className="text-3xl text-center mb-1 mt-1.5 drop-shadow-sm">{cart.icon}</div>
                          <div className="font-bold font-sans text-center leading-tight text-xs tracking-tight" style={{ color: "#1a1a2e" }}>
                            {cart.name.toUpperCase()}
                          </div>
                          <div className="text-zinc-600 text-[9px] text-center mt-1 font-mono leading-snug line-clamp-2">
                            {cart.description}
                          </div>
                          <div className="mt-auto flex flex-wrap gap-1 justify-center pt-1.5">
                            {cart.tags.slice(0, 3).map(tag => (
                              <span key={tag} className="text-[7px] px-1.5 py-0.5 rounded-full font-mono uppercase tracking-wider font-semibold"
                                style={{ background: `${cartAccent}22`, color: '#1a1a2e', border: `1px solid ${cartAccent}40` }}>
                                {tag}
                              </span>
                            ))}
                          </div>
                          <div className="flex justify-between items-end border-t border-black/10 pt-1 mt-1.5">
                            <span className="text-[7px] text-black/50 font-bold uppercase">{cart.source === "user" ? "custom" : cart.role}</span>
                            <span className="text-[7px] text-black/50 font-mono">v{cart.version}</span>
                          </div>
                        </div>
                        <div className="h-4 mx-auto w-3/4 rounded-b-sm flex justify-evenly items-center px-1 mt-1 mb-1"
                          style={{ background: "linear-gradient(180deg, #c49a3c, #a07830)" }}>
                          {[...Array(12)].map((_, i) => (
                            <div key={i} className="w-[2px] h-2.5 rounded-sm" style={{ background: "#e8d574" }} />
                          ))}
                        </div>
                      </div>
                    </motion.div>
                  );
                })}
              </AnimatePresence>
            </div>

            {/* Info + Controls */}
            {selected && (
              <motion.div key={selected.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center select-none mt-1 sm:mt-3">
                <div className="text-white/40 text-[10px] sm:text-xs font-mono">{selectedIndex + 1} / {total}</div>
              </motion.div>
            )}

            <div className="mt-1.5 sm:mt-3 flex gap-3 sm:gap-4 items-center select-none">
              <button onClick={() => navigate(-1)} className="w-9 h-9 sm:w-10 sm:h-10 rounded-full border border-white/10 flex items-center justify-center text-white/40 hover:text-white active:text-white hover:border-white/30 transition-all hover:bg-white/5 active:bg-white/5 text-sm">◀</button>
              <button
                onClick={() => handleLoad()}
                disabled={isInserting || total === 0}
                className="px-5 sm:px-8 py-2 sm:py-2.5 rounded-lg uppercase font-bold tracking-[0.12em] sm:tracking-[0.2em] text-xs sm:text-sm transition-all disabled:cursor-not-allowed active:scale-95"
                style={{
                  background: isInserting ? "#333" : accent,
                  color: isInserting ? "#666" : "#000",
                  boxShadow: isInserting ? "none" : `0 0 20px ${accent}60, 0 4px 15px rgba(0,0,0,0.3)`,
                }}
              >
                {isInserting ? "LOADING..." : "INSERT  ⏎"}
              </button>
              <button onClick={() => navigate(1)} className="w-9 h-9 sm:w-10 sm:h-10 rounded-full border border-white/10 flex items-center justify-center text-white/40 hover:text-white active:text-white hover:border-white/30 transition-all hover:bg-white/5 active:bg-white/5 text-sm">▶</button>
            </div>
          </div>
        </>
      )}

      {/* Bottom: Forge button */}
      <div className="z-10 pb-3 sm:pb-6 pt-1 sm:pt-2 flex items-center gap-4 safe-bottom">
        {onOpenForge && (
          <button
            onClick={onOpenForge}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl border transition-all text-xs font-mono uppercase tracking-wider select-none active:scale-95"
            style={{
              borderColor: `${accent}30`,
              background: `linear-gradient(135deg, ${accent}10, ${accent}05)`,
              color: `${accent}cc`,
              boxShadow: `0 0 12px ${accent}10`,
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLElement).style.borderColor = `${accent}60`;
              (e.currentTarget as HTMLElement).style.background = `linear-gradient(135deg, ${accent}20, ${accent}10)`;
              (e.currentTarget as HTMLElement).style.boxShadow = `0 0 20px ${accent}25`;
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLElement).style.borderColor = `${accent}30`;
              (e.currentTarget as HTMLElement).style.background = `linear-gradient(135deg, ${accent}10, ${accent}05)`;
              (e.currentTarget as HTMLElement).style.boxShadow = `0 0 12px ${accent}10`;
            }}
          >
            <span className="text-sm">🔧</span> Kasset Forge
          </button>
        )}
      </div>
    </div>
  );
}
