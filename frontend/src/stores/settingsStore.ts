import { create } from "zustand";

interface ContextSettings {
  use_session_summary: boolean;
  use_cartridge_context: boolean;
  use_global_profile: boolean;
}

interface SettingsState {
  context: ContextSettings;
  loaded: boolean;

  loadSettings: () => Promise<void>;
  updateContext: (key: keyof ContextSettings, value: boolean) => Promise<void>;
}

import { getApiBase } from "@/lib/api";

export const useSettingsStore = create<SettingsState>((set, get) => ({
  context: {
    use_session_summary: true,
    use_cartridge_context: true,
    use_global_profile: true,
  },
  loaded: false,

  loadSettings: async () => {
    try {
      const res = await fetch(`${getApiBase()}/api/settings`);
      const data = await res.json();
      if (data.settings?.context) {
        set({ context: data.settings.context, loaded: true });
      }
    } catch (e) {
      console.error("Failed to load settings", e);
    }
  },

  updateContext: async (key, value) => {
    const updated = { ...get().context, [key]: value };
    set({ context: updated });
    try {
      await fetch(`${getApiBase()}/api/settings/context`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updated),
      });
    } catch (e) {
      console.error("Failed to save settings", e);
    }
  },
}));
