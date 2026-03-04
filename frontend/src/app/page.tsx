"use client";

import { useEffect, useState } from "react";
import Console from "@/components/Console";
import CartridgeCarousel from "@/components/CartridgeCarousel";
import { useCartridgeStore } from "@/stores/cartridgeStore";

export default function Home() {
  const { loadAvailableCartridges, activeConfig } = useCartridgeStore();
  const [isBooting, setIsBooting] = useState(true);
  const [showCarousel, setShowCarousel] = useState(true);

  useEffect(() => {
    const init = async () => {
      await loadAvailableCartridges();
      setTimeout(() => setIsBooting(false), 2000);
    };
    init();
  }, [loadAvailableCartridges]);

  if (isBooting) {
    return (
      <div className="w-full h-screen flex flex-col items-center justify-center bg-zinc-950 text-[#00ff88]">
        <div className="text-4xl mb-4 font-bold text-glow animate-pulse">
          QWEN OS v3.5
        </div>
        <div className="text-xl animate-blink">INITIALIZING MEMORY...</div>
      </div>
    );
  }

  return (
    <main className="w-full h-screen flex items-center justify-center p-4 relative overflow-hidden">
      {showCarousel || !activeConfig ? (
        <CartridgeCarousel onSelect={() => setShowCarousel(false)} />
      ) : (
        <Console onChangeCartridge={() => setShowCarousel(true)} />
      )}
    </main>
  );
}
