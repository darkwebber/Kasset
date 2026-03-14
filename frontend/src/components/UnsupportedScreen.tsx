"use client";

import { useEffect, useState } from "react";

/**
 * Detects unsupported screen conditions:
 * - Too narrow (< 320px)
 * - Too short (< 480px)
 * - Extreme aspect ratios (> 3:1 landscape without enough height, or > 4:1 portrait)
 * Shows a blocking overlay advising the user.
 */
export default function UnsupportedScreen({ children }: { children: React.ReactNode }) {
  const [unsupported, setUnsupported] = useState<string | null>(null);

  useEffect(() => {
    const check = () => {
      const w = window.innerWidth;
      const h = window.innerHeight;
      const ratio = w / h;

      if (w < 320) {
        setUnsupported("Screen too narrow. Kasset requires at least 320px width.");
        return;
      }
      if (h < 400) {
        setUnsupported("Screen too short. Kasset requires at least 400px height.");
        return;
      }
      // Ultra-wide with insufficient height (e.g. 21:9 split, car displays)
      if (ratio > 3 && h < 500) {
        setUnsupported("This ultra-wide aspect ratio is not supported. Please resize your window or use a different display.");
        return;
      }
      // Extreme portrait (e.g. very tall narrow widget)
      if (ratio < 0.25) {
        setUnsupported("This aspect ratio is not supported. Please resize your window.");
        return;
      }
      setUnsupported(null);
    };

    check();
    window.addEventListener("resize", check);
    // Also check on orientation change (mobile)
    window.addEventListener("orientationchange", () => setTimeout(check, 200));
    return () => {
      window.removeEventListener("resize", check);
      window.removeEventListener("orientationchange", () => {});
    };
  }, []);

  if (unsupported) {
    return (
      <div className="fixed inset-0 z-[200] bg-zinc-950 flex flex-col items-center justify-center p-6 text-center">
        <div className="text-4xl mb-4">🖥️</div>
        <div className="text-white/80 text-lg font-bold mb-2 font-sans">
          Display Not Supported
        </div>
        <div className="text-white/40 text-sm font-mono max-w-xs leading-relaxed mb-6">
          {unsupported}
        </div>
        <div className="text-white/20 text-xs font-mono">
          Min: 320×400 &nbsp;·&nbsp; Recommended: 375×667+
        </div>
        <div className="mt-6 text-[10px] text-white/15 font-mono tracking-wider uppercase">
          Kasset — Local AI Console
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
