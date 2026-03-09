import { create } from "zustand";
import { getApiBase } from "@/lib/api";

export interface InputTypeManifest {
  id: string;
  name: string;
  version: string;
  description: string;
  author: string;
  widget_type: string;
  config_template?: Record<string, any>;
  icon?: string;
  tags?: string[];
}

interface InputTypeForgeState {
  inputTypes: InputTypeManifest[];
  loading: boolean;
  error: string | null;

  fetchInputTypes: () => Promise<void>;
  getInputType: (id: string) => Promise<{ manifest: InputTypeManifest }>;
  saveInputType: (manifest: InputTypeManifest) => Promise<string>;
  deleteInputType: (id: string) => Promise<void>;
  exportWidget: (id: string) => void;
  importWidget: (file: File) => Promise<void>;
}

export const useInputTypeForgeStore = create<InputTypeForgeState>((set, get) => ({
  inputTypes: [],
  loading: false,
  error: null,

  fetchInputTypes: async () => {
    set({ loading: true });
    try {
      const res = await fetch(`${getApiBase()}/api/forge/input-types`);
      const data = await res.json();
      set({ inputTypes: data.input_types || [], loading: false });
    } catch (err: any) {
      set({ error: err.message, loading: false });
    }
  },

  getInputType: async (id: string) => {
    const res = await fetch(`${getApiBase()}/api/forge/input-types/${id}`);
    if (!res.ok) throw new Error("Failed to fetch input type");
    return res.json();
  },

  saveInputType: async (manifest: InputTypeManifest) => {
    const res = await fetch(`${getApiBase()}/api/forge/input-types`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(manifest),
    });
    const data = await res.json();
    if (!data.saved) throw new Error(data.error || "Failed to save input type");
    await get().fetchInputTypes();
    return data.saved;
  },

  deleteInputType: async (id: string) => {
    const res = await fetch(`${getApiBase()}/api/forge/input-types/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete input type");
    await get().fetchInputTypes();
  },

  exportWidget: (id: string) => {
    const a = document.createElement("a");
    a.href = `${getApiBase()}/api/forge/input-types/${id}/export`;
    a.download = `${id}.kwid`;
    a.click();
  },

  importWidget: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${getApiBase()}/api/forge/input-types/import`, { method: "POST", body: form });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || "Failed to import widget");
    await get().fetchInputTypes();
  },
}));
