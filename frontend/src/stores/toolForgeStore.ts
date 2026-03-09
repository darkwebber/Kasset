import { create } from "zustand";
import { getApiBase } from "@/lib/api";

export interface ToolManifest {
  id: string;
  name: string;
  version: string;
  description: string;
  author: string;
  icon: string;
  color: string;
  parameters: Record<string, any>;
  output_type: string;
  handler?: string;
  entry_point?: string;
  sandbox?: {
    timeout: number;
    imports: string[];
    pre_run: string;
  };
  tags: string[];
  dependencies: string[];
}

export interface ToolInfo {
  id: string;
  name: string;
  source: string;
  description?: string;
  icon?: string;
  color?: string;
}

interface ToolForgeState {
  tools: ToolInfo[];
  allToolIds: string[];
  loading: boolean;
  error: string | null;

  fetchTools: () => Promise<void>;
  fetchToolIds: () => Promise<void>;
  getTool: (id: string) => Promise<{ manifest: ToolManifest; handler_code: string }>;
  saveTool: (manifest: ToolManifest, handler_code: string) => Promise<void>;
  deleteTool: (id: string) => Promise<void>;
  testTool: (id: string, args: any) => Promise<any>;
  checkDeps: (id: string) => Promise<Record<string, boolean>>;
  installDeps: (id: string) => Promise<Record<string, string>>;
  exportTool: (id: string) => void;
  importTool: (file: File) => Promise<void>;
}

export const useToolForgeStore = create<ToolForgeState>((set, get) => ({
  tools: [],
  allToolIds: [],
  loading: false,
  error: null,

  fetchTools: async () => {
    set({ loading: true });
    try {
      const res = await fetch(`${getApiBase()}/api/forge/tools`);
      const data = await res.json();
      set({ tools: data.tools || [], loading: false });
    } catch (err: any) {
      set({ error: err.message, loading: false });
    }
  },

  fetchToolIds: async () => {
    try {
      const res = await fetch(`${getApiBase()}/api/forge/all-tool-ids`);
      const data = await res.json();
      set({ allToolIds: data.tool_ids || [] });
    } catch (err: any) {
      console.error("Failed to fetch tool IDs", err);
    }
  },

  getTool: async (id: string) => {
    const res = await fetch(`${getApiBase()}/api/forge/tools/${id}`);
    if (!res.ok) throw new Error("Failed to fetch tool");
    return res.json();
  },

  saveTool: async (manifest: ToolManifest, handler_code: string) => {
    const res = await fetch(`${getApiBase()}/api/forge/tools`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ manifest, handler_code }),
    });
    const data = await res.json();
    if (!data.saved) throw new Error(data.error || "Failed to save tool");
    await get().fetchTools();
    await get().fetchToolIds();
  },

  deleteTool: async (id: string) => {
    const res = await fetch(`${getApiBase()}/api/forge/tools/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete tool");
    await get().fetchTools();
    await get().fetchToolIds();
  },

  testTool: async (id: string, args: any) => {
    const res = await fetch(`${getApiBase()}/api/forge/tools/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool_id: id, args }),
    });
    return res.json();
  },

  checkDeps: async (id: string) => {
    const res = await fetch(`${getApiBase()}/api/forge/tools/${id}/deps`);
    const data = await res.json();
    return data.dependencies || {};
  },

  installDeps: async (id: string) => {
    const res = await fetch(`${getApiBase()}/api/forge/tools/${id}/deps/install`, { method: "POST" });
    const data = await res.json();
    return data.results || {};
  },

  exportTool: (id: string) => {
    const a = document.createElement("a");
    a.href = `${getApiBase()}/api/forge/tools/${id}/export`;
    a.download = `${id}.ktool`;
    a.click();
  },

  importTool: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${getApiBase()}/api/forge/tools/import`, { method: "POST", body: form });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || "Failed to import tool");
    await get().fetchTools();
    await get().fetchToolIds();
  },
}));
