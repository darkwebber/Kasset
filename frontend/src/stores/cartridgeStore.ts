import { create } from "zustand";

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
  suggested_tokens: number;
  suggested_thinking: boolean;
}

interface CartridgeState {
  availableCartridges: CartridgeConfig[];
  activeConfig: LoadedConfig | null;
  isLoading: boolean;
  error: string | null;
  
  loadAvailableCartridges: () => Promise<void>;
  loadActiveStack: (cartridgeIds: string[]) => Promise<void>;
}

export const useCartridgeStore = create<CartridgeState>((set) => ({
  availableCartridges: [],
  activeConfig: null,
  isLoading: false,
  error: null,

  loadAvailableCartridges: async () => {
    try {
      const res = await fetch("http://127.0.0.1:7861/api/cartridges");
      const data = await res.json();
      set({ availableCartridges: data.cartridges });
    } catch (error: any) {
      set({ error: error.message });
    }
  },

  loadActiveStack: async (cartridgeIds: string[]) => {
    set({ isLoading: true, error: null });
    try {
      const res = await fetch("http://127.0.0.1:7861/api/cartridges/load", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cartridge_ids: cartridgeIds }),
      });
      
      if (!res.ok) throw new Error("Failed to load cartridge stack");
      
      const data = await res.json();
      set({ activeConfig: data.config, isLoading: false });
    } catch (error: any) {
      set({ error: error.message, isLoading: false });
    }
  },
}));
