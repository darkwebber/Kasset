import { create } from "zustand";
import { getApiBase } from "@/lib/api";

export interface Theme {
  accent_color: string;
  screen_tint: string;
  scanline_intensity: number;
  glow_color: string;
  boot_animation: string;
}

export interface CartridgeConfig {
  id: string;
  name: string;
  description: string;
  icon: string;
  author: string;
  version: string;
  tags: string[];
  role: string;
  source: string;
  tools: string[];
  theme: {
    accent_color: string;
    glow_color: string;
  };
}

export interface LoadedConfig {
  merged_prompt: string;
  tools: string[];
  theme: Theme;
  boot_messages: string[];
  active_cartridge_ids: string[];
  suggested_prompts: string[];
  suggested_tokens: number;
  suggested_thinking: boolean;
}

interface CartridgeState {
  availableCartridges: CartridgeConfig[];
  activeConfig: LoadedConfig | null;
  lastActiveCartridgeId: string | null;
  isLoading: boolean;
  error: string | null;
  
  loadAvailableCartridges: () => Promise<void>;
  loadActiveStack: (cartridgeIds: string[]) => Promise<void>;
  ejectCartridge: () => void;
}

export const useCartridgeStore = create<CartridgeState>((set, get) => ({
  availableCartridges: [],
  activeConfig: null,
  lastActiveCartridgeId: typeof window !== "undefined" ? localStorage.getItem("kasset-last-cartridge") : null,
  isLoading: false,
  error: null,

  loadAvailableCartridges: async () => {
    try {
      const res = await fetch(`${getApiBase()}/api/cartridges`);
      const data = await res.json();
      set({ availableCartridges: data.cartridges });
    } catch (error: any) {
      set({ error: error.message });
    }
  },

  loadActiveStack: async (cartridgeIds: string[]) => {
    set({ isLoading: true, error: null });
    try {
      const res = await fetch(`${getApiBase()}/api/cartridges/load`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cartridge_ids: cartridgeIds }),
      });
      
      if (!res.ok) throw new Error("Failed to load cartridge stack");
      
      const data = await res.json();
      if (typeof window !== "undefined") localStorage.setItem("kasset-last-cartridge", cartridgeIds[0]);
      set({ activeConfig: data.config, lastActiveCartridgeId: cartridgeIds[0], isLoading: false });
    } catch (error: any) {
      set({ error: error.message, isLoading: false });
    }
  },

  ejectCartridge: () => {
    const current = get().activeConfig;
    set({
      activeConfig: null,
      lastActiveCartridgeId: current?.active_cartridge_ids?.[0] ?? get().lastActiveCartridgeId,
    });
    // Keep localStorage updated even on eject
    const lastId = current?.active_cartridge_ids?.[0] ?? get().lastActiveCartridgeId;
    if (lastId && typeof window !== "undefined") {
      localStorage.setItem("kasset-last-cartridge", lastId);
    }
  },
}));
