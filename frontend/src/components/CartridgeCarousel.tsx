import { useState, useRef, useEffect } from "react";
import { useCartridgeStore } from "@/stores/cartridgeStore";
import { motion, AnimatePresence } from "framer-motion";

export default function CartridgeCarousel({ onSelect }: { onSelect: () => void }) {
  const { availableCartridges, loadActiveStack, isLoading } = useCartridgeStore();
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [isInserting, setIsInserting] = useState(false);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isInserting) return;
      if (e.key === "ArrowRight") {
        setSelectedIndex((i) => (i + 1) % availableCartridges.length);
      } else if (e.key === "ArrowLeft") {
        setSelectedIndex((i) => (i - 1 + availableCartridges.length) % availableCartridges.length);
      } else if (e.key === "Enter") {
        handleLoad();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedIndex, availableCartridges.length, isInserting]);

  const handleLoad = async () => {
    if (isInserting) return;
    setIsInserting(true);
    
    // SFX could go here (e.g. cartridge click sound)
    
    // Play insertion animation for 1s
    setTimeout(async () => {
      await loadActiveStack([availableCartridges[selectedIndex].id]);
      onSelect();
      setIsInserting(false);
    }, 1500);
  };

  if (availableCartridges.length === 0) return null;

  return (
    <div className="absolute inset-0 bg-black/90 z-50 flex flex-col items-center justify-center crt-screen overflow-hidden backdrop-blur-sm">
      <div className="text-[var(--accent)] font-bold tracking-widest uppercase mb-12 text-xl text-glow animate-pulse">
        Select Cartridge
      </div>

      <div className="relative w-full max-w-4xl h-64 flex items-center justify-center">
        <div className="flex gap-6 items-center">
          {availableCartridges.map((cart, idx) => {
            const isSelected = idx === selectedIndex;
            const diff = Math.abs(idx - selectedIndex);
            
            // Only show nearby cartridges
            if (diff > 2 && diff < availableCartridges.length - 2) return null;

            return (
              <motion.div
                key={cart.id}
                onClick={() => {
                  if (isSelected) handleLoad();
                  else setSelectedIndex(idx);
                }}
                animate={{
                  scale: isSelected ? 1 : 0.8,
                  opacity: isSelected ? 1 : 0.4,
                  y: isSelected ? (isInserting ? 100 : 0) : 0,
                  z: isSelected ? 10 : 0,
                }}
                transition={{ duration: 0.3 }}
                className={`relative w-48 h-64 rounded-t-xl rounded-b flex flex-col border-4 cursor-pointer transition-colors ${
                  isSelected 
                    ? "border-[var(--accent)] bg-zinc-900 shadow-[0_0_30px_var(--glow)] z-10" 
                    : "border-zinc-700 bg-zinc-950 hover:border-zinc-500"
                }`}
              >
                {/* Cartridge Label Sticker */}
                <div className="m-3 flex-1 bg-white rounded flex flex-col p-3 shadow-inner">
                  <div className="text-4xl text-center mb-2">{cart.icon}</div>
                  <div className="text-black font-bold font-sans text-center leading-tight tracking-tighter">
                    {cart.name.toUpperCase()}
                  </div>
                  <div className="text-zinc-600 text-[10px] text-center mt-2 font-mono leading-tight">
                    {cart.description}
                  </div>
                  <div className="mt-auto flex justify-between items-end border-t border-black/10 pt-1">
                    <span className="text-[8px] text-black/50 font-bold">{cart.role}</span>
                    <span className="text-[8px] text-black/50 font-mono">v{cart.version}</span>
                  </div>
                </div>
                
                {/* Cartridge PCB edge */}
                <div className="h-4 bg-[#b58840] w-2/3 mx-auto rounded-b-sm border-t-2 border-black flex justify-evenly px-2 items-center">
                  {[...Array(12)].map((_, i) => (
                    <div key={i} className="w-[2px] h-3 bg-yellow-300" />
                  ))}
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>

      <div className="mt-16 flex gap-8 items-center text-zinc-500 font-mono text-sm">
        <button onClick={() => setSelectedIndex((i) => (i - 1 + availableCartridges.length) % availableCartridges.length)} className="hover:text-white transition-colors">◀ PREV</button>
        <button 
          onClick={handleLoad}
          disabled={isInserting}
          className={`px-8 py-3 rounded uppercase font-bold tracking-widest transition-all ${
            isInserting 
              ? "bg-zinc-800 text-zinc-500 cursor-not-allowed" 
              : "bg-[var(--accent)] text-black hover:bg-white hover:shadow-[0_0_15px_var(--glow)]"
          }`}
        >
          {isInserting ? "Loading..." : "Insert [ENTER]"}
        </button>
        <button onClick={() => setSelectedIndex((i) => (i + 1) % availableCartridges.length)} className="hover:text-white transition-colors">NEXT ▶</button>
      </div>
    </div>
  );
}
