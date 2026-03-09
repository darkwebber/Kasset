import { create } from "zustand";
import { getApiBase } from "@/lib/api";

export interface CartridgeData {
  id: string;
  name: string;
  description: string;
  icon: string;
  author: string;
  version: string;
  tags: string[];
  system_prompt: string;
  tools: string[];
  input_methods?: Array<string | {
    id: string;
    name: string;
    description?: string;
    widget_type: string;
    example?: Record<string, any>;
  }>;
  theme: {
    accent_color: string;
    screen_tint: string;
    scanline_intensity: number;
    glow_color: string;
    boot_animation: string;
  };
  boot_message: string;
  stacking: {
    stackable: boolean;
    priority: number;
    role: string;
    conflicts_with: string[];
    requires: string[];
    merge_strategy: string;
  };
  suggested_tokens: number;
  suggested_thinking: boolean;
  memory_enabled: boolean;
  suggested_model?: string;
  suggested_temperature?: number;
  suggested_top_p?: number;
}

interface KassetForgeState {
  loading: boolean;
  error: string | null;

  getKasset: (id: string) => Promise<{ cartridge: CartridgeData; source: string }>;
  saveKasset: (cartridge: CartridgeData) => Promise<string>;
  deleteKasset: (id: string) => Promise<void>;
  exportKasset: (id: string, version: string) => Promise<void>;
  importKasset: (file: File) => Promise<any>;
}

export const useKassetForgeStore = create<KassetForgeState>((set) => ({
  loading: false,
  error: null,

  getKasset: async (id: string) => {
    const res = await fetch(`${getApiBase()}/api/forge/kassets/${id}`);
    if (!res.ok) throw new Error("Failed to fetch kasset");
    return res.json();
  },

  saveKasset: async (cartridge: CartridgeData) => {
    const res = await fetch(`${getApiBase()}/api/forge/kassets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cartridge),
    });
    const data = await res.json();
    if (!data.saved) throw new Error(data.error || "Failed to save kasset");
    return data.saved;
  },

  deleteKasset: async (id: string) => {
    const res = await fetch(`${getApiBase()}/api/forge/kassets/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete kasset");
  },

  exportKasset: async (id: string, version: string) => {
    const res = await fetch(`${getApiBase()}/api/forge/export/${id}`);
    if (!res.ok) throw new Error("Export failed");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${id}.kasset`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  importKasset: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${getApiBase()}/api/forge/import`, {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Import failed");
    return data;
  },
}));
