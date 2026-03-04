"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useCartridgeStore } from "@/stores/cartridgeStore";
import { motion, AnimatePresence } from "framer-motion";
import { soundCartridgeInsert, soundTick } from "@/lib/sounds";

export default function CartridgeCarousel({ onSelect }: { onSelect: () => void }) {
  const { availableCartridges, loadActiveStack } = useCartridgeStore();
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [isInserting, setIsInserting] = useState(false);
  const [direction, setDirection] = useState(0); // -1 left, 1 right
  const wheelCooldown = useRef(false);

  const total = availableCartridges.length;

  const navigate = useCallback((dir: number) => {
    if (isInserting || total === 0) return;
    setDirection(dir);
    setSelectedIndex((i) => (i + dir + total) % total);
    soundTick();
  }, [isInserting, total]);

  const handleLoad = useCallback(async () => {
    if (isInserting || total === 0) return;
    setIsInserting(true);
    soundCartridgeInsert();
    setTimeout(async () => {
      await loadActiveStack([availableCartridges[selectedIndex].id]);
      onSelect();
      setIsInserting(false);
    }, 1200);
  }, [isInserting, total, selectedIndex, availableCartridges, loadActiveStack, onSelect]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isInserting) return;
      if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); navigate(1); }
      else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); navigate(-1); }
      else if (e.key === "Enter") { e.preventDefault(); handleLoad(); }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [navigate, handleLoad, isInserting]);

  // Mouse wheel navigation with cooldown
  useEffect(() => {
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
  }, [navigate, isInserting]);

  if (total === 0) return null;

  const selected = availableCartridges[selectedIndex];
  const accent = selected.theme.accent_color;
  const glow = selected.theme.glow_color;

  // Compute position offset for each card relative to selected
  const getOffset = (idx: number) => {
    let diff = idx - selectedIndex;
    if (diff > total / 2) diff -= total;
    if (diff < -total / 2) diff += total;
    return diff;
  };

  return (
    <div
      className="absolute inset-0 z-50 flex flex-col items-center justify-center overflow-hidden"
      style={{ background: `radial-gradient(ellipse at center, ${accent}08 0%, #000 70%)` }}
    >
      {/* Scanline overlay */}
      <div className="absolute inset-0 pointer-events-none z-40 opacity-20"
        style={{
          background: `repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.3) 2px, rgba(0,0,0,0.3) 4px)`,
        }}
      />

      {/* Title */}
      <motion.div
        key={accent}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="font-bold tracking-[0.3em] uppercase mb-16 text-lg z-10 select-none"
        style={{ color: accent, textShadow: `0 0 20px ${glow}, 0 0 40px ${glow}40` }}
      >
        Select Cartridge
      </motion.div>

      {/* Carousel Track */}
      <div className="relative w-full max-w-5xl h-80 flex items-center justify-center z-10" style={{ perspective: "1200px" }}>
        <AnimatePresence mode="popLayout">
          {availableCartridges.map((cart, idx) => {
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
                  else {
                    setDirection(offset > 0 ? 1 : -1);
                    setSelectedIndex(idx);
                  }
                }}
                initial={{ opacity: 0, scale: 0.6 }}
                animate={{
                  x: offset * 200,
                  scale: isSelected ? 1.05 : Math.max(0.55, 0.85 - absOffset * 0.12),
                  rotateY: offset * -12,
                  z: isSelected ? 100 : -absOffset * 80,
                  opacity: isSelected ? 1 : Math.max(0.15, 0.7 - absOffset * 0.2),
                  y: isSelected && isInserting ? 120 : 0,
                }}
                exit={{ opacity: 0, scale: 0.5 }}
                transition={{ type: "spring", stiffness: 300, damping: 30 }}
                className="absolute cursor-pointer select-none"
                style={{ zIndex: 10 - absOffset, transformStyle: "preserve-3d" }}
              >
                {/* Cartridge Body */}
                <div
                  className="w-52 h-72 rounded-t-2xl rounded-b-md flex flex-col overflow-hidden"
                  style={{
                    background: `linear-gradient(145deg, #1a1a2e 0%, #0f0f1a 100%)`,
                    border: `3px solid ${isSelected ? cartAccent : "rgba(255,255,255,0.08)"}`,
                    boxShadow: isSelected
                      ? `0 0 40px ${cartAccent}50, 0 0 80px ${cartAccent}20, inset 0 1px 0 rgba(255,255,255,0.1)`
                      : `0 4px 20px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.05)`,
                    transition: "border-color 0.3s, box-shadow 0.3s",
                  }}
                >
                  {/* Top edge notch */}
                  <div className="flex justify-center">
                    <div className="w-16 h-1.5 rounded-b-full" style={{ background: cartAccent, opacity: isSelected ? 1 : 0.3 }} />
                  </div>

                  {/* Label Area */}
                  <div className="mx-3 mt-2 flex-1 rounded-lg flex flex-col p-3 relative overflow-hidden"
                    style={{ background: `linear-gradient(180deg, #f5f5f0 0%, #e8e4db 100%)` }}
                  >
                    {/* Color stripe at top of label */}
                    <div className="absolute top-0 left-0 right-0 h-1.5" style={{ background: cartAccent }} />

                    <div className="text-4xl text-center mb-1 mt-2 drop-shadow-sm">{cart.icon}</div>
                    <div
                      className="font-bold font-sans text-center leading-tight text-sm tracking-tight"
                      style={{ color: "#1a1a2e" }}
                    >
                      {cart.name.toUpperCase()}
                    </div>
                    <div className="text-zinc-500 text-[9px] text-center mt-1.5 font-mono leading-snug line-clamp-3">
                      {cart.description}
                    </div>

                    {/* Tags */}
                    <div className="mt-auto flex flex-wrap gap-1 justify-center pt-2">
                      {cart.tags.slice(0, 3).map((tag) => (
                        <span
                          key={tag}
                          className="text-[7px] px-1.5 py-0.5 rounded-full font-mono uppercase tracking-wider"
                          style={{
                            background: `${cartAccent}18`,
                            color: cartAccent,
                            border: `1px solid ${cartAccent}30`,
                          }}
                        >
                          {tag}
                        </span>
                      ))}
                    </div>

                    <div className="flex justify-between items-end border-t border-black/10 pt-1 mt-2">
                      <span className="text-[8px] text-black/40 font-bold uppercase">{cart.role}</span>
                      <span className="text-[8px] text-black/40 font-mono">v{cart.version}</span>
                    </div>
                  </div>

                  {/* PCB Edge */}
                  <div className="h-5 mx-auto w-3/4 rounded-b-sm flex justify-evenly items-center px-1 mt-1 mb-1"
                    style={{ background: "linear-gradient(180deg, #c49a3c, #a07830)" }}
                  >
                    {[...Array(14)].map((_, i) => (
                      <div key={i} className="w-[2px] h-3 rounded-sm" style={{ background: "#e8d574" }} />
                    ))}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {/* Cartridge Info */}
      <motion.div
        key={selected.id}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="mt-10 text-center z-10 select-none"
      >
        <div className="text-white/60 text-xs font-mono mb-1">
          {selectedIndex + 1} / {total}
        </div>
        <div className="text-white/30 text-xs font-mono max-w-md">
          {selected.description}
        </div>
      </motion.div>

      {/* Controls */}
      <div className="mt-8 flex gap-6 items-center z-10 select-none">
        <button
          onClick={() => navigate(-1)}
          className="w-10 h-10 rounded-full border border-white/10 flex items-center justify-center text-white/40 hover:text-white hover:border-white/30 transition-all hover:bg-white/5"
        >
          ◀
        </button>
        <button
          onClick={handleLoad}
          disabled={isInserting}
          className="px-10 py-3 rounded-lg uppercase font-bold tracking-[0.2em] text-sm transition-all disabled:cursor-not-allowed"
          style={{
            background: isInserting ? "#333" : accent,
            color: isInserting ? "#666" : "#000",
            boxShadow: isInserting ? "none" : `0 0 20px ${accent}60, 0 4px 15px rgba(0,0,0,0.3)`,
          }}
        >
          {isInserting ? "LOADING..." : "INSERT  ⏎"}
        </button>
        <button
          onClick={() => navigate(1)}
          className="w-10 h-10 rounded-full border border-white/10 flex items-center justify-center text-white/40 hover:text-white hover:border-white/30 transition-all hover:bg-white/5"
        >
          ▶
        </button>
      </div>
    </div>
  );
}
