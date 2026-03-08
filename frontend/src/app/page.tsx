"use client";

import { useEffect, useState } from "react";
import Console from "@/components/Console";
import CartridgeCarousel from "@/components/CartridgeCarousel";
import ForgeStudio from "@/components/studio/ForgeStudio";
import NetworkAuthModal from "@/components/NetworkAuthModal";
import ToastContainer from "@/components/Toast";
import Onboarding from "@/components/Onboarding";
import { useCartridgeStore } from "@/stores/cartridgeStore";
import { getApiBase, isLocalClient, onSessionExpired } from "@/lib/api";

export default function Home() {
  const { loadAvailableCartridges, loadActiveStack, activeConfig } = useCartridgeStore();
  const [isBooting, setIsBooting] = useState(true);
  const [showCarousel, setShowCarousel] = useState(true);
  const [showForge, setShowForge] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);

  // Auth state
  const [authChecked, setAuthChecked] = useState(false);
  const [authMode, setAuthMode] = useState<"setup" | "login" | null>(null);

  // Check auth status on mount
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const res = await fetch(`${getApiBase()}/api/auth/status`);
        const data = await res.json();

        if (data.is_local && !data.password_configured) {
          // Local user, first boot — prompt to set password
          setAuthMode("setup");
        } else if (!data.is_local && data.requires_auth) {
          // Network client, needs to login
          setAuthMode("login");
        } else {
          setAuthMode(null);
        }
      } catch {
        // If server is unreachable, skip auth check
        setAuthMode(null);
      }
      setAuthChecked(true);
    };
    checkAuth();

    // Register 401 interceptor — if a session expires mid-use, show login modal
    if (!isLocalClient()) {
      onSessionExpired(() => {
        setAuthMode("login");
      });
    }
  }, []);

  useEffect(() => {
    if (!authChecked) return;
    // Only init the app after auth is resolved
    if (authMode) return;
    const init = async () => {
      await loadAvailableCartridges();
      // Check if first launch
      if (typeof window !== "undefined" && !localStorage.getItem("kasset-onboarded")) {
        setShowOnboarding(true);
      }
      setTimeout(() => setIsBooting(false), 2000);
    };
    init();
  }, [authChecked, authMode, loadAvailableCartridges]);

  // Auth modal takes priority
  if (authMode) {
    return (
      <NetworkAuthModal
        mode={authMode}
        onAuthenticated={() => {
          setAuthMode(null);
        }}
      />
    );
  }

  if (!authChecked || isBooting) {
    return (
      <div className="w-full h-screen flex flex-col items-center justify-center bg-zinc-950 text-[#00ff88]">
        <div className="text-3xl sm:text-4xl mb-2 font-bold text-glow animate-pulse tracking-[0.3em]">
          KASSET
        </div>
        <div className="text-[10px] sm:text-xs text-[#00ff88]/40 font-mono tracking-[0.2em] mb-6">LOCAL AI CONSOLE</div>
        <div className="text-sm sm:text-base animate-blink font-mono">INITIALIZING...</div>
      </div>
    );
  }

  return (
    <main className="w-full h-screen flex items-center justify-center p-4 relative overflow-hidden">
      {showCarousel || !activeConfig ? (
        <CartridgeCarousel
          onSelect={() => setShowCarousel(false)}
          onOpenForge={() => setShowForge(true)}
        />
      ) : (
        <Console
          onChangeCartridge={() => setShowCarousel(true)}
          onOpenForge={() => setShowForge(true)}
        />
      )}

      {showForge && (
        <ForgeStudio onClose={() => { setShowForge(false); loadAvailableCartridges(); }} />
      )}

      {showOnboarding && (
        <Onboarding
          onComplete={() => setShowOnboarding(false)}
          onSelectCartridge={(id) => {
            loadActiveStack([id]);
            setShowCarousel(false);
          }}
        />
      )}

      <ToastContainer />
    </main>
  );
}
