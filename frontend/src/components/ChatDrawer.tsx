"use client";

import { useEffect, useState } from "react";
import { useCartridgeStore } from "@/stores/cartridgeStore";
import { useChatStore } from "@/stores/chatStore";
import { MessageSquare, Plus, Trash2, Brain, X, ChevronDown, ChevronRight, Filter } from "lucide-react";
import { soundTick, soundNewChat } from "@/lib/sounds";

interface ChatDrawerProps {
  onLoadChat: (messages: any[], cartridgeIds: string[]) => void;
  onNewChat: () => void;
  onClose: () => void;
}

export default function ChatDrawer({ onLoadChat, onNewChat, onClose }: ChatDrawerProps) {
  const { activeConfig } = useCartridgeStore();
  const {
    chatList, loadChatList, loadChat, deleteChat,
    memories, loadMemories, deleteMemory, addMemory,
  } = useChatStore();

  const [tab, setTab] = useState<"history" | "memory">("history");
  const [showAll, setShowAll] = useState(false);
  const [newMemContent, setNewMemContent] = useState("");
  const [newMemType, setNewMemType] = useState("fact");
  const [showAddMem, setShowAddMem] = useState(false);
  const [expandedType, setExpandedType] = useState<string | null>(null);

  const activeCartridgeId = activeConfig?.active_cartridge_ids?.[0] || "";

  useEffect(() => {
    loadChatList();
    loadMemories();
  }, [loadChatList, loadMemories]);

  // Filter chats by current cartridge
  const cartridgeChats = chatList.filter(
    (c) => c.cartridge_ids?.[0] === activeCartridgeId
  );
  const otherChats = chatList.filter(
    (c) => c.cartridge_ids?.[0] !== activeCartridgeId
  );
  const displayChats = showAll ? chatList : cartridgeChats;

  const handleLoadChat = async (chatId: string) => {
    const data = await loadChat(chatId);
    if (data) {
      onLoadChat(data.messages, data.cartridge_ids);
      onClose();
    }
  };

  const handleNewChat = () => {
    soundNewChat();
    onNewChat();
    onClose();
  };

  const handleAddMemory = () => {
    if (newMemContent.trim()) {
      addMemory(newMemContent.trim(), newMemType);
      setNewMemContent("");
      setShowAddMem(false);
      soundTick();
    }
  };

  const formatDate = (iso: string) => {
    if (!iso) return "";
    const d = new Date(iso);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    if (diff < 60000) return "just now";
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (diff < 604800000) return d.toLocaleDateString([], { weekday: "short" });
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  };

  // Group memories by type
  const memoryGroups: Record<string, typeof memories> = {};
  for (const m of memories) {
    if (!memoryGroups[m.type]) memoryGroups[m.type] = [];
    memoryGroups[m.type].push(m);
  }

  const typeLabels: Record<string, string> = {
    instruction: "Standing Instructions",
    preference: "Preferences",
    fact: "Known Facts",
    context: "Current Context",
  };

  const typeColors: Record<string, string> = {
    instruction: "#f59e0b",
    preference: "#a78bfa",
    fact: "#60a5fa",
    context: "#34d399",
  };

  return (
    <div className="absolute inset-0 z-50 flex">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      {/* Drawer Panel */}
      <div className="relative z-10 w-80 h-full bg-[#0d1117] border-r border-white/10 flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <div className="flex gap-1">
            <button
              onClick={() => { setTab("history"); soundTick(); }}
              className={`px-3 py-1.5 rounded text-xs font-bold uppercase tracking-wider transition-all ${
                tab === "history" ? "bg-[var(--accent)] text-black" : "text-white/40 hover:text-white/70"
              }`}
            >
              <MessageSquare size={12} className="inline mr-1.5 -mt-0.5" />
              Chats
            </button>
            <button
              onClick={() => { setTab("memory"); soundTick(); }}
              className={`px-3 py-1.5 rounded text-xs font-bold uppercase tracking-wider transition-all ${
                tab === "memory" ? "bg-[var(--accent)] text-black" : "text-white/40 hover:text-white/70"
              }`}
            >
              <Brain size={12} className="inline mr-1.5 -mt-0.5" />
              Memory
            </button>
          </div>
          <button onClick={onClose} className="text-white/30 hover:text-white/70 transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto crt-scroll min-h-0">
          {tab === "history" ? (
            <div className="p-2">
              {/* New Chat + Filter Row */}
              <div className="flex gap-1.5 mb-2">
                <button
                  onClick={handleNewChat}
                  className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-dashed border-white/10 text-white/50 hover:text-[var(--accent)] hover:border-[var(--accent)]/30 transition-all"
                >
                  <Plus size={14} />
                  <span className="font-mono text-[10px] uppercase tracking-wider">New Chat</span>
                </button>
                <button
                  onClick={() => { setShowAll(!showAll); soundTick(); }}
                  className={`flex items-center gap-1.5 px-2.5 py-2 rounded-lg border transition-all text-[10px] font-mono uppercase tracking-wider ${
                    showAll
                      ? "border-[var(--accent)]/30 text-[var(--accent)]"
                      : "border-white/10 text-white/30 hover:text-white/50"
                  }`}
                  title={showAll ? "Showing all cartridges" : "Showing current cartridge only"}
                >
                  <Filter size={12} />
                  {showAll ? "All" : activeCartridgeId.slice(0, 6).toUpperCase() || "ALL"}
                </button>
              </div>

              {/* Cartridge context label */}
              {!showAll && activeCartridgeId && (
                <div className="px-3 py-1.5 mb-1">
                  <span className="text-[9px] text-white/20 font-mono uppercase tracking-wider">
                    {cartridgeChats.length} conversation{cartridgeChats.length !== 1 ? "s" : ""} with {activeCartridgeId}
                    {otherChats.length > 0 && (
                      <button
                        onClick={() => setShowAll(true)}
                        className="ml-2 text-[var(--accent)]/40 hover:text-[var(--accent)]/70 transition-colors"
                      >
                        +{otherChats.length} others
                      </button>
                    )}
                  </span>
                </div>
              )}

              {/* Chat List */}
              {displayChats.length === 0 ? (
                <div className="text-white/20 text-xs text-center py-8 font-mono space-y-2">
                  <div>No conversations{!showAll ? ` with ${activeCartridgeId}` : ""}</div>
                  {!showAll && otherChats.length > 0 && (
                    <button
                      onClick={() => setShowAll(true)}
                      className="text-[var(--accent)]/40 hover:text-[var(--accent)] transition-colors text-[10px]"
                    >
                      Show all cartridges ({otherChats.length})
                    </button>
                  )}
                </div>
              ) : (
                <div className="space-y-0.5">
                  {displayChats.map((chat) => {
                    const isCurrentCartridge = chat.cartridge_ids?.[0] === activeCartridgeId;
                    return (
                      <div
                        key={chat.id}
                        className={`group flex items-start gap-2 px-3 py-2.5 rounded-lg cursor-pointer transition-all ${
                          isCurrentCartridge
                            ? "hover:bg-[var(--accent)]/5"
                            : "hover:bg-white/5 opacity-60"
                        }`}
                        onClick={() => handleLoadChat(chat.id)}
                      >
                        <MessageSquare size={14} className={`mt-0.5 shrink-0 ${isCurrentCartridge ? "text-[var(--accent)]/30" : "text-white/15"}`} />
                        <div className="flex-1 min-w-0">
                          <div className="text-white/70 text-xs font-medium truncate">
                            {chat.title}
                          </div>
                          <div className="flex items-center gap-2 mt-0.5">
                            <span className="text-[9px] text-white/20 font-mono">
                              {chat.message_count} msg
                            </span>
                            <span className="text-[9px] text-white/20 font-mono">
                              {formatDate(chat.updated_at)}
                            </span>
                            {showAll && chat.cartridge_ids?.[0] && (
                              <span className={`text-[8px] font-mono uppercase ${
                                isCurrentCartridge ? "text-[var(--accent)]/40" : "text-white/20"
                              }`}>
                                {chat.cartridge_ids[0]}
                              </span>
                            )}
                          </div>
                        </div>
                        <button
                          onClick={(e) => { e.stopPropagation(); deleteChat(chat.id); soundTick(); }}
                          className="opacity-0 group-hover:opacity-100 text-white/20 hover:text-red-400 transition-all p-1"
                          title="Delete chat"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ) : (
            <div className="p-2">
              {/* Memory Stats */}
              <div className="flex items-center justify-between px-3 py-2 mb-2">
                <span className="text-[10px] text-white/30 font-mono uppercase tracking-wider">
                  {memories.length} memories
                </span>
                <button
                  onClick={() => { setShowAddMem(!showAddMem); soundTick(); }}
                  className="text-[10px] text-[var(--accent)]/60 hover:text-[var(--accent)] font-mono uppercase tracking-wider transition-colors"
                >
                  {showAddMem ? "Cancel" : "+ Add"}
                </button>
              </div>

              {/* Add Memory Form */}
              {showAddMem && (
                <div className="mx-2 mb-3 p-3 rounded-lg bg-white/5 border border-white/10 space-y-2">
                  <textarea
                    value={newMemContent}
                    onChange={(e) => setNewMemContent(e.target.value)}
                    placeholder="e.g. I prefer Python, I work on ML projects..."
                    className="w-full bg-black/40 border border-white/10 rounded px-2 py-1.5 text-xs text-white/80 placeholder-white/20 font-mono resize-none outline-none focus:border-[var(--accent)]/30"
                    rows={2}
                  />
                  <div className="flex gap-2">
                    <select
                      value={newMemType}
                      onChange={(e) => setNewMemType(e.target.value)}
                      className="flex-1 bg-black/40 border border-white/10 rounded px-2 py-1 text-[10px] text-white/60 font-mono outline-none"
                    >
                      <option value="fact">Fact</option>
                      <option value="preference">Preference</option>
                      <option value="instruction">Instruction</option>
                      <option value="context">Context</option>
                    </select>
                    <button
                      onClick={handleAddMemory}
                      disabled={!newMemContent.trim()}
                      className="px-3 py-1 bg-[var(--accent)] text-black text-[10px] font-bold uppercase rounded disabled:opacity-30 transition-all"
                    >
                      Save
                    </button>
                  </div>
                </div>
              )}

              {/* Memory Groups */}
              {Object.entries(memoryGroups).length === 0 ? (
                <div className="text-white/20 text-xs text-center py-8 font-mono">
                  No memories yet. The system learns from your conversations automatically.
                </div>
              ) : (
                <div className="space-y-1">
                  {Object.entries(typeLabels).map(([type, label]) => {
                    const items = memoryGroups[type];
                    if (!items || items.length === 0) return null;
                    const isExpanded = expandedType === type;
                    const color = typeColors[type] || "#888";
                    return (
                      <div key={type}>
                        <button
                          onClick={() => { setExpandedType(isExpanded ? null : type); soundTick(); }}
                          className="w-full flex items-center gap-2 px-3 py-2 rounded hover:bg-white/5 transition-all"
                        >
                          {isExpanded ? <ChevronDown size={12} className="text-white/30" /> : <ChevronRight size={12} className="text-white/30" />}
                          <div className="w-2 h-2 rounded-full" style={{ background: color }} />
                          <span className="text-xs text-white/50 font-mono flex-1 text-left">{label}</span>
                          <span className="text-[9px] text-white/20 font-mono">{items.length}</span>
                        </button>
                        {isExpanded && (
                          <div className="ml-7 space-y-1 mb-2">
                            {items.map((mem) => (
                              <div key={mem.id} className="group flex items-start gap-2 px-2 py-1.5 rounded hover:bg-white/5">
                                <div className="flex-1 text-[11px] text-white/60 font-mono leading-relaxed">
                                  {mem.content}
                                </div>
                                <button
                                  onClick={() => { deleteMemory(mem.id); soundTick(); }}
                                  className="opacity-0 group-hover:opacity-100 text-white/20 hover:text-red-400 transition-all p-0.5 shrink-0"
                                >
                                  <X size={10} />
                                </button>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-white/5 text-center">
          <span className="text-[8px] text-white/15 font-mono uppercase tracking-widest">
            ~/.qwen-studio
          </span>
        </div>
      </div>
    </div>
  );
}
