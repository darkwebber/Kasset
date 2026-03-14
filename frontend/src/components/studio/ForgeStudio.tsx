"use client";

import { useState, useEffect, useCallback } from "react";
import { X, Plus, Trash2, Wrench, Cpu, Package, Code, Eye, Upload, Download, Info, ChevronRight, Sliders } from "lucide-react";
import { soundTick, soundNewChat, soundError } from "@/lib/sounds";
import { useCartridgeStore } from "@/stores/cartridgeStore";
import { useToolForgeStore, ToolInfo, ToolManifest } from "@/stores/toolForgeStore";
import { useKassetForgeStore, CartridgeData } from "@/stores/kassetForgeStore";
import { useInputTypeForgeStore, InputTypeManifest } from "@/stores/inputTypeForgeStore";

// Editors
import { KassetEditor } from "./editors/KassetEditor";
import { KassetWizard } from "./editors/KassetWizard";
import { ToolEditor } from "./editors/ToolEditor";
import { InputTypeEditor } from "./editors/InputTypeEditor";

const EMPTY_CARTRIDGE: CartridgeData = {
  id: "", name: "", description: "", icon: "🔧", author: "user", version: "1.0.0",
  tags: [], system_prompt: "", tools: [], input_methods: [],
  theme: { accent_color: "#60a5fa", screen_tint: "rgba(96, 165, 250, 0.02)", scanline_intensity: 0.12, glow_color: "#60a5fa", boot_animation: "fade" },
  boot_message: "", stacking: { stackable: true, priority: 50, role: "primary", conflicts_with: [], requires: [], merge_strategy: "append" },
  suggested_tokens: 4096, suggested_thinking: true, memory_enabled: false,
};

const EMPTY_TOOL: ToolManifest = {
  id: "", name: "", version: "1.0.0", description: "", author: "user",
  icon: "wrench", color: "#60a5fa", parameters: {},
  output_type: "text", handler: "handler.py", entry_point: "execute",
  sandbox: { timeout: 30, imports: [], pre_run: "" }, tags: [],
  dependencies: [],
};

const EMPTY_INPUT_TYPE: InputTypeManifest = {
  id: "", name: "", version: "1.0.0", description: "", author: "user",
  widget_type: "form", config_template: {}, icon: "sliders", tags: [],
};

const DEFAULT_HANDLER = `def execute(**kwargs):\n    return "Hello from custom tool!"\n`;

export default function ForgeStudio({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<"cartridges" | "tools" | "input-types">("cartridges");
  
  const { availableCartridges, loadAvailableCartridges } = useCartridgeStore();
  const { tools, allToolIds, fetchTools, fetchToolIds, getTool, saveTool, deleteTool, exportTool, importTool } = useToolForgeStore();
  const { getKasset, saveKasset, deleteKasset, importKasset } = useKassetForgeStore();
  const { inputTypes, fetchInputTypes, getInputType, saveInputType, deleteInputType, exportWidget, importWidget } = useInputTypeForgeStore();

  // Editor states
  const [editingCartridge, setEditingCartridge] = useState<CartridgeData | null>(null);
  const [isNewCartridge, setIsNewCartridge] = useState(false);
  
  const [editingTool, setEditingTool] = useState<{ manifest: ToolManifest; code: string } | null>(null);
  const [isNewTool, setIsNewTool] = useState(false);
  
  const [editingInputType, setEditingInputType] = useState<InputTypeManifest | null>(null);
  const [isNewInputType, setIsNewInputType] = useState(false);

  useEffect(() => {
    loadAvailableCartridges();
    fetchTools();
    fetchToolIds();
    fetchInputTypes();
  }, []);

  // ─── Handlers ───────────────────────────
  
  const handleEditCartridge = async (id: string) => {
    try {
      const data = await getKasset(id);
      setEditingCartridge(data.cartridge);
      setIsNewCartridge(false);
      soundTick();
    } catch { soundError(); }
  };

  const handleEditTool = async (id: string) => {
    try {
      const data = await getTool(id);
      setEditingTool({ manifest: data.manifest, code: data.handler_code || DEFAULT_HANDLER });
      setIsNewTool(false);
      soundTick();
    } catch { soundError(); }
  };

  const handleEditInputType = async (id: string) => {
    try {
      const data = await getInputType(id);
      setEditingInputType(data.manifest);
      setIsNewInputType(false);
      soundTick();
    } catch { soundError(); }
  };

  const userCartridges = availableCartridges.filter((c: any) => c.source === "user");
  const builtinCartridges = availableCartridges.filter((c: any) => c.source !== "user");
  const userTools = tools.filter(t => t.source === "user");
  const builtinTools = tools.filter(t => t.source === "builtin");

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-xl p-0 sm:p-4">
      <div className="relative w-full max-w-3xl max-h-[100dvh] sm:max-h-[92vh] bg-[#09090f]/98 border-0 sm:border border-white/[0.07] rounded-none sm:rounded-2xl shadow-2xl overflow-hidden flex flex-col"
        style={{ "--accent": "#60a5fa" } as React.CSSProperties}>
        
        <div className="flex items-center justify-between px-5 sm:px-6 py-4 shrink-0 border-b border-white/[0.04]">
          <div className="flex items-center gap-3.5">
            <div className="p-2.5 rounded-xl border border-[var(--accent)]/15 bg-white/[0.02]">
              <Wrench size={17} className="text-[var(--accent)]" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-white/90 tracking-tight">Kasset Forge</h1>
              <p className="text-[10px] text-white/25 mt-0.5 font-medium">Modular Agent Design System</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-xl text-white/25 hover:text-white/60 hover:bg-white/[0.06] transition-all">
            <X size={16} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex mx-5 sm:mx-6 mt-4 mb-2 bg-white/[0.03] rounded-xl p-1 shrink-0 border border-white/[0.04]">
          {(["cartridges", "tools", "input-types"] as const).map(t => (
            <button key={t} onClick={() => { setTab(t); setEditingCartridge(null); setEditingTool(null); setEditingInputType(null); }}
              className={`flex-1 flex items-center justify-center gap-2 py-2 text-[12px] font-medium transition-all rounded-lg ${
                tab === t
                  ? "text-[var(--accent)] bg-[var(--accent)]/[0.08] border border-[var(--accent)]/10"
                  : "text-white/30 hover:text-white/50 border border-transparent"
              }`}>
              {t === "cartridges" && <><Cpu size={13} /> Kassets</>}
              {t === "tools" && <><Code size={13} /> Tools</>}
              {t === "input-types" && <><Sliders size={13} /> Widgets</>}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto subtle-scroll px-5 sm:px-6 py-4">
          
          {/* cartridges Tab */}
          {tab === "cartridges" && (
            editingCartridge ? (
              isNewCartridge ? (
                <KassetWizard
                  initial={editingCartridge}
                  onSave={async (c) => {
                    await saveKasset(c);
                    setEditingCartridge(null);
                    loadAvailableCartridges();
                    fetchToolIds();
                    soundNewChat();
                  }}
                  onCancel={() => setEditingCartridge(null)}
                />
              ) : (
              <KassetEditor 
                cartridge={editingCartridge} 
                onSave={async (c) => {
                  await saveKasset(c);
                  setEditingCartridge(null);
                  loadAvailableCartridges();
                  fetchToolIds();
                  soundNewChat();
                }}
                onDelete={() => { deleteKasset(editingCartridge.id).then(() => { setEditingCartridge(null); loadAvailableCartridges(); }); }}
                onCancel={() => setEditingCartridge(null)}
                isNew={isNewCartridge}
              />)
            ) : (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-[13px] text-white/50 font-semibold uppercase tracking-wider">Your Kassets</h2>
                  <div className="flex gap-2">
                    <label className="flex items-center gap-1.5 px-3 py-1.5 text-white/30 hover:text-white/55 hover:bg-white/[0.05] rounded-xl text-[11px] font-medium transition-all cursor-pointer">
                      <Upload size={12} /> Import
                      <input type="file" accept=".kasset,.zip,.json" className="sr-only" onChange={async (e) => {
                        const file = e.target.files?.[0]; if (!file) return;
                        await importKasset(file);
                        loadAvailableCartridges();
                        fetchTools();
                        fetchInputTypes();
                        soundNewChat();
                      }} />
                    </label>
                    <button onClick={() => { setEditingCartridge({...EMPTY_CARTRIDGE}); setIsNewCartridge(true); }} className="flex items-center gap-1.5 px-3.5 py-1.5 bg-[var(--accent)]/10 text-[var(--accent)] border border-[var(--accent)]/10 rounded-xl text-[11px] font-semibold">
                      <Plus size={13} /> New Kasset
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2.5">
                  {userCartridges.map((c: any) => (
                    <button key={c.id} onClick={() => handleEditCartridge(c.id)}
                      className="flex items-center gap-3 p-3.5 rounded-xl border border-white/[0.06] hover:border-[var(--accent)]/20 bg-white/[0.02] transition-all text-left group">
                      <span className="text-2xl group-hover:scale-110 transition-transform">{c.icon}</span>
                      <div className="min-w-0">
                        <div className="text-[13px] text-white/70 font-semibold truncate group-hover:text-white/90">{c.name}</div>
                        <div className="text-[10px] text-white/20 truncate mt-0.5">{c.description}</div>
                      </div>
                      <ChevronRight size={14} className="ml-auto text-white/0 group-hover:text-white/20 transition-all shrink-0" />
                    </button>
                  ))}
                </div>
                
                {builtinCartridges.length > 0 && (
                  <div className="pt-2">
                    <p className="text-[10px] text-white/20 font-semibold uppercase tracking-wider mb-2">Built-in</p>
                    <div className="grid grid-cols-2 gap-1.5">
                      {builtinCartridges.map((c: any) => (
                        <button key={c.id} onClick={() => handleEditCartridge(c.id)}
                          className="flex items-center gap-2.5 px-3 py-2.5 rounded-lg border border-white/[0.03] hover:border-white/[0.08] hover:bg-white/[0.02] transition-all text-left group">
                          <span className="text-base opacity-40 group-hover:opacity-70 transition-all">{c.icon}</span>
                          <span className="text-[11px] text-white/30 group-hover:text-white/50 font-medium truncate">{c.name}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )
          )}

          {/* tools Tab */}
          {tab === "tools" && (
            editingTool ? (
              <ToolEditor 
                manifest={editingTool.manifest} 
                handlerCode={editingTool.code}
                onSave={async (m, code) => {
                   await saveTool(m, code);
                   setEditingTool(null);
                   soundNewChat();
                }}
                onDelete={() => deleteTool(editingTool.manifest.id).then(() => setEditingTool(null))}
                onCancel={() => setEditingTool(null)}
                isNew={isNewTool}
              />
            ) : (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-[13px] text-white/50 font-semibold uppercase tracking-wider">Your Tools</h2>
                  <div className="flex gap-2">
                    <label className="flex items-center gap-1.5 px-3 py-1.5 text-white/30 hover:text-white/55 hover:bg-white/[0.05] rounded-xl text-[11px] font-medium transition-all cursor-pointer">
                      <Upload size={12} /> Import .ktool
                      <input type="file" accept=".ktool" className="sr-only" onChange={async (e) => {
                        const file = e.target.files?.[0]; if (!file) return;
                        try { await importTool(file); soundNewChat(); } catch { soundError(); }
                      }} />
                    </label>
                    <button onClick={() => { setEditingTool({ manifest: {...EMPTY_TOOL}, code: DEFAULT_HANDLER }); setIsNewTool(true); }} className="flex items-center gap-1.5 px-3.5 py-1.5 bg-[var(--accent)]/10 text-[var(--accent)] border border-[var(--accent)]/10 rounded-xl text-[11px] font-semibold">
                      <Plus size={13} /> New Tool
                    </button>
                  </div>
                </div>

                <div className="space-y-2">
                  {userTools.map(t => (
                    <div key={t.id} className="w-full flex items-center gap-3 p-3.5 rounded-xl border border-white/[0.06] hover:border-[var(--accent)]/20 bg-white/[0.02] transition-all text-left group">
                      <button onClick={() => handleEditTool(t.id)} className="flex items-center gap-3 flex-1 min-w-0">
                        <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 border border-white/[0.06]" style={{ background: `${t.color || "#60a5fa"}10` }}>
                          <Code size={15} style={{ color: t.color || "#60a5fa" }} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-[13px] text-white/70 font-semibold group-hover:text-white/90">{t.name}</div>
                          <div className="text-[10px] text-white/20 truncate mt-0.5">{t.description || t.id}</div>
                        </div>
                      </button>
                      <button onClick={(e) => { e.stopPropagation(); exportTool(t.id); soundTick(); }}
                        className="p-1.5 rounded-md text-white/0 group-hover:text-white/25 hover:!text-white/50 hover:bg-white/[0.05] transition-all shrink-0" title="Export .ktool">
                        <Download size={12} />
                      </button>
                      <ChevronRight size={14} className="text-white/0 group-hover:text-white/20 transition-all shrink-0" />
                    </div>
                  ))}
                </div>

                {builtinTools.length > 0 && (
                  <div className="pt-2">
                    <p className="text-[10px] text-white/20 font-semibold uppercase tracking-wider mb-2">Built-in</p>
                    <div className="grid grid-cols-3 gap-1.5">
                      {builtinTools.map(t => (
                        <div key={t.id} className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-white/[0.015] border border-white/[0.03] text-white/25">
                          <Code size={10} className="shrink-0" />
                          <span className="text-[9px] font-mono truncate">{t.id}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )
          )}

          {/* input-types (Widgets) Tab */}
          {tab === "input-types" && (
            editingInputType ? (
              <InputTypeEditor
                manifest={editingInputType}
                onSave={async (m) => {
                  await saveInputType(m);
                  setEditingInputType(null);
                  soundNewChat();
                }}
                onDelete={() => deleteInputType(editingInputType.id).then(() => setEditingInputType(null))}
                onCancel={() => setEditingInputType(null)}
                isNew={isNewInputType}
              />
            ) : (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-[13px] text-white/50 font-semibold uppercase tracking-wider">Your Widgets</h2>
                  <div className="flex gap-2">
                    <label className="flex items-center gap-1.5 px-3 py-1.5 text-white/30 hover:text-white/55 hover:bg-white/[0.05] rounded-xl text-[11px] font-medium transition-all cursor-pointer">
                      <Upload size={12} /> Import .kwid
                      <input type="file" accept=".kwid,.json" className="sr-only" onChange={async (e) => {
                        const file = e.target.files?.[0]; if (!file) return;
                        try { await importWidget(file); soundNewChat(); } catch { soundError(); }
                      }} />
                    </label>
                    <button onClick={() => { setEditingInputType({...EMPTY_INPUT_TYPE}); setIsNewInputType(true); }} className="flex items-center gap-1.5 px-3.5 py-1.5 bg-[var(--accent)]/10 text-[var(--accent)] border border-[var(--accent)]/10 rounded-xl text-[11px] font-semibold">
                      <Plus size={13} /> New Widget
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2.5">
                  {inputTypes.map(it => (
                    <div key={it.id}
                      className="flex items-center gap-3 p-3.5 rounded-xl border border-white/[0.06] hover:border-[var(--accent)]/20 bg-white/[0.02] transition-all text-left group">
                      <button onClick={() => handleEditInputType(it.id)} className="flex items-center gap-3 flex-1 min-w-0">
                        <div className="p-2 bg-white/[0.04] rounded-lg text-white/30 group-hover:text-white/60 transition-colors">
                          <Sliders size={14} />
                        </div>
                        <div className="min-w-0">
                          <div className="text-[13px] text-white/70 font-semibold truncate group-hover:text-white/90">{it.name}</div>
                          <div className="text-[10px] text-white/20 truncate mt-0.5">{it.description || it.id}</div>
                        </div>
                      </button>
                      <button onClick={(e) => { e.stopPropagation(); exportWidget(it.id); soundTick(); }}
                        className="p-1.5 rounded-md text-white/0 group-hover:text-white/25 hover:!text-white/50 hover:bg-white/[0.05] transition-all shrink-0" title="Export .kwid">
                        <Download size={12} />
                      </button>
                      <ChevronRight size={14} className="ml-auto text-white/0 group-hover:text-white/20 transition-all shrink-0" />
                    </div>
                  ))}
                  {inputTypes.length === 0 && (
                    <div className="col-span-2 text-center py-10 text-white/10 italic text-[11px]">No custom widgets created yet.</div>
                  )}
                </div>
              </div>
            )
          )}

        </div>

        {/* Global info */}
        <div className="px-5 py-3 border-t border-white/[0.04] bg-white/[0.01]">
          <div className="flex items-center gap-2 text-[9px] text-white/20 font-medium">
            <Info size={10} />
            <span>Share anything: <span className="text-white/40">.kasset</span> (bundles) · <span className="text-white/40">.ktool</span> (tools) · <span className="text-white/40">.kwid</span> (widgets) · <span className="text-white/40">.kchat</span> (chats)</span>
          </div>
        </div>
      </div>
    </div>
  );
}
