import { create } from "zustand";

export interface ChatMeta {
  id: string;
  title: string;
  summary: string;
  cartridge_ids: string[];
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface UserMemory {
  id: string;
  content: string;
  type: string;
  source: string;
  created_at: string;
  hits: number;
  active: boolean;
}

interface ChatState {
  // Chat history
  chatList: ChatMeta[];
  activeChatId: string | null;

  // User memories
  memories: UserMemory[];

  // Actions
  loadChatList: () => Promise<void>;
  loadChat: (chatId: string) => Promise<{ messages: any[]; cartridge_ids: string[] } | null>;
  deleteChat: (chatId: string) => Promise<void>;
  setActiveChatId: (id: string | null) => void;
  startNewChat: () => void;

  // Memory actions
  loadMemories: () => Promise<void>;
  addMemory: (content: string, type: string) => Promise<void>;
  deleteMemory: (memoryId: string) => Promise<void>;
  updateMemory: (memoryId: string, content: string) => Promise<void>;
}

import { getApiBase } from "@/lib/api";

export const useChatStore = create<ChatState>((set, get) => ({
  chatList: [],
  activeChatId: null,
  memories: [],

  loadChatList: async () => {
    try {
      const res = await fetch(`${getApiBase()}/api/chats`);
      if (!res.ok) throw new Error(`Failed to load chats (${res.status})`);
      const data = await res.json();
      set({ chatList: data.chats || [] });
    } catch (e) {
      console.error("Failed to load chat list", e);
      set({ chatList: [] });
    }
  },

  loadChat: async (chatId: string) => {
    try {
      const res = await fetch(`${getApiBase()}/api/chats/${chatId}`);
      if (!res.ok) throw new Error(`Failed to load chat (${res.status})`);
      const data = await res.json();
      if (data.chat) {
        const rawMessages = data.chat.messages;
        if (!Array.isArray(rawMessages)) {
          console.warn(`Chat ${chatId} has invalid messages (not an array)`);
          return null;
        }
        const validMessages = rawMessages.filter(
          (m: any) => m && typeof m === "object" && typeof m.role === "string" && m.content !== undefined
        );
        set({ activeChatId: chatId });
        return { messages: validMessages, cartridge_ids: data.chat.cartridge_ids || [] };
      }
    } catch (e) {
      console.error("Failed to load chat", e);
    }
    return null;
  },

  deleteChat: async (chatId: string) => {
    try {
      await fetch(`${getApiBase()}/api/chats/${chatId}`, { method: "DELETE" });
      set((s) => ({
        chatList: s.chatList.filter((c) => c.id !== chatId),
        activeChatId: s.activeChatId === chatId ? null : s.activeChatId,
      }));
    } catch (e) {
      console.error("Failed to delete chat", e);
    }
  },

  setActiveChatId: (id) => set({ activeChatId: id }),

  startNewChat: () => set({ activeChatId: null }),

  loadMemories: async () => {
    try {
      const res = await fetch(`${getApiBase()}/api/memory`);
      const data = await res.json();
      set({ memories: data.memories || [] });
    } catch (e) {
      console.error("Failed to load memories", e);
    }
  },

  addMemory: async (content: string, type: string) => {
    try {
      await fetch(`${getApiBase()}/api/memory`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, memory_type: type }),
      });
      get().loadMemories();
    } catch (e) {
      console.error("Failed to add memory", e);
    }
  },

  deleteMemory: async (memoryId: string) => {
    try {
      await fetch(`${getApiBase()}/api/memory/${memoryId}`, { method: "DELETE" });
      set((s) => ({ memories: s.memories.filter((m) => m.id !== memoryId) }));
    } catch (e) {
      console.error("Failed to delete memory", e);
    }
  },

  updateMemory: async (memoryId: string, content: string) => {
    try {
      await fetch(`${getApiBase()}/api/memory/${memoryId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      get().loadMemories();
    } catch (e) {
      console.error("Failed to update memory", e);
    }
  },
}));
