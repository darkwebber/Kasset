"use client";

import { useState, useEffect, useCallback } from "react";
import { X, Plus, Trash2, Save, ChevronDown, ChevronRight, Wrench, Cpu, Play, ArrowLeft, Package, Code, Palette, Eye, Copy, Upload, Download, Info } from "lucide-react";
import { soundTick, soundNewChat, soundError } from "@/lib/sounds";
import { useCartridgeStore } from "@/stores/cartridgeStore";

import { getApiBase } from "@/lib/api";

// ─── Types ───────────────────────────────────────────
interface ToolInfo {
  id: string; name: string; source: string; description?: string;
  version?: string; author?: string; icon?: string; color?: string;
  parameters?: Record<string, any>; output_type?: string;
  handler?: string; entry_point?: string; sandbox?: any; tags?: string[];
}

interface CartridgeData {
  id: string; name: string; description: string; icon: string;
  author: string; version: string; tags: string[];
  system_prompt: string; tools: string[];
  theme: { accent_color: string; screen_tint: string; scanline_intensity: number; glow_color: string; boot_animation: string };
  boot_message: string;
  stacking: { stackable: boolean; priority: number; role: string; conflicts_with: string[]; requires: string[]; merge_strategy: string };
  suggested_tokens: number; suggested_thinking: boolean; memory_enabled: boolean;
}

const EMPTY_CARTRIDGE: CartridgeData = {
  id: "", name: "", description: "", icon: "🔧", author: "user", version: "1.0.0",
  tags: [], system_prompt: "", tools: [],
  theme: { accent_color: "#60a5fa", screen_tint: "rgba(96, 165, 250, 0.02)", scanline_intensity: 0.12, glow_color: "#60a5fa", boot_animation: "fade" },
  boot_message: "", stacking: { stackable: true, priority: 50, role: "primary", conflicts_with: [], requires: [], merge_strategy: "append" },
  suggested_tokens: 4096, suggested_thinking: true, memory_enabled: false,
};

const EMPTY_MANIFEST = {
  id: "", name: "", version: "1.0.0", description: "", author: "user",
  icon: "wrench", color: "#60a5fa", parameters: {} as Record<string, any>,
  output_type: "text", handler: "handler.py", entry_point: "execute",
  sandbox: { timeout: 30, imports: [] as string[], pre_run: "" }, tags: [] as string[],
  dependencies: [] as string[],
};

const DEFAULT_HANDLER = `def execute(**kwargs):
    """Your tool's entry point. Receives parameters as keyword arguments.
    
    Return types:
        str         -> displayed as text
        dict        -> { "output": str, "images": [base64], "html": str }
    """
    return "Hello from custom tool!"
`;

// ─── Sub-Components ──────────────────────────────────

function SectionHeader({ title, open, onToggle }: { title: string; open: boolean; onToggle: () => void }) {
  return (
    <button onClick={onToggle} className="flex items-center gap-2 w-full text-left py-2.5 text-[10px] uppercase tracking-[0.15em] text-white/25 font-semibold hover:text-white/45 transition-colors group">
      <div className={`transition-transform duration-200 ${open ? "rotate-90" : ""}`}><ChevronRight size={11} /></div>
      {title}
      <div className="flex-1 h-px bg-white/5 group-hover:bg-white/8 transition-colors" />
    </button>
  );
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="space-y-1">
      <label className="text-[11px] text-white/30 font-medium">{label}</label>
      {children}
      {hint && <p className="text-[10px] text-white/15 mt-0.5">{hint}</p>}
    </div>
  );
}

function TextInput({ value, onChange, placeholder, mono }: { value: string; onChange: (v: string) => void; placeholder?: string; mono?: boolean }) {
  return (
    <input
      type="text" value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
      className={`w-full bg-white/[0.035] border border-white/[0.06] rounded-md px-2.5 py-[7px] text-[13px] text-white/75 placeholder-white/15 focus:border-[var(--accent)]/30 focus:bg-white/[0.05] focus:outline-none transition-all ${mono ? "font-mono text-xs" : ""}`}
    />
  );
}

function TextArea({ value, onChange, placeholder, rows, mono }: { value: string; onChange: (v: string) => void; placeholder?: string; rows?: number; mono?: boolean }) {
  return (
    <textarea
      value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} rows={rows || 4}
      className={`w-full bg-white/[0.035] border border-white/[0.06] rounded-md px-2.5 py-[7px] text-[13px] text-white/75 placeholder-white/15 focus:border-[var(--accent)]/30 focus:bg-white/[0.05] focus:outline-none transition-all resize-y subtle-scroll ${mono ? "font-mono text-xs leading-relaxed" : ""}`}
    />
  );
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer group">
      <div
        onClick={() => onChange(!checked)}
        className={`w-8 h-[18px] rounded-full transition-all relative ${checked ? "bg-[var(--accent)]/40" : "bg-white/[0.06]"}`}
      >
        <div className={`absolute top-[3px] w-3 h-3 rounded-full transition-all ${checked ? "left-[14px] bg-[var(--accent)]" : "left-[3px] bg-white/25"}`} />
      </div>
      <span className="text-[11px] text-white/40 group-hover:text-white/55 transition-colors">{label}</span>
    </label>
  );
}

function TagInput({ tags, onChange }: { tags: string[]; onChange: (t: string[]) => void }) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const t = draft.trim().toLowerCase();
    if (t && !tags.includes(t)) { onChange([...tags, t]); setDraft(""); }
  };
  return (
    <div className="space-y-1.5">
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {tags.map(t => (
            <span key={t} className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-[var(--accent)]/8 border border-[var(--accent)]/10 rounded text-[10px] text-[var(--accent)]/70 font-mono">
              {t}
              <button onClick={() => onChange(tags.filter(x => x !== t))} className="text-white/20 hover:text-red-400 transition-colors"><X size={8} /></button>
            </span>
          ))}
        </div>
      )}
      <div className="flex gap-1">
        <input value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={e => e.key === "Enter" && (e.preventDefault(), add())}
          placeholder="Add tag..." className="flex-1 bg-white/[0.035] border border-white/[0.06] rounded-md px-2.5 py-[5px] text-xs text-white/60 font-mono focus:outline-none focus:border-[var(--accent)]/30 transition-all" />
        <button onClick={add} className="px-2.5 py-[5px] bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] rounded-md text-[10px] text-white/35 hover:text-white/55 font-mono transition-all">+</button>
      </div>
    </div>
  );
}

function ToolMultiSelect({ selected, onChange, allTools }: { selected: string[]; onChange: (t: string[]) => void; allTools: string[] }) {
  const toggle = (id: string) => {
    if (selected.includes(id)) onChange(selected.filter(x => x !== id));
    else onChange([...selected, id]);
  };
  return (
    <div className="grid grid-cols-2 gap-px bg-white/[0.02] rounded-md border border-white/[0.06] overflow-hidden max-h-36 overflow-y-auto subtle-scroll">
      {allTools.map(id => (
        <label key={id} className={`flex items-center gap-2 px-2.5 py-[6px] cursor-pointer text-[11px] font-mono transition-all ${selected.includes(id) ? "bg-[var(--accent)]/8 text-[var(--accent)]/80" : "text-white/30 hover:bg-white/[0.03] hover:text-white/45"}`}>
          <input type="checkbox" checked={selected.includes(id)} onChange={() => toggle(id)} className="sr-only" />
          <div className={`w-3 h-3 rounded-sm border transition-all flex items-center justify-center ${selected.includes(id) ? "bg-[var(--accent)]/80 border-[var(--accent)]/60" : "border-white/15"}`}>
            {selected.includes(id) && <svg width="8" height="8" viewBox="0 0 12 12"><path d="M2.5 6l2.5 2.5 5-5" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" className="text-white"/></svg>}
          </div>
          {id}
        </label>
      ))}
    </div>
  );
}

// ─── Param Editor ────────────────────────────────────
function ParamEditor({ params, onChange }: { params: Record<string, any>; onChange: (p: Record<string, any>) => void }) {
  const [newName, setNewName] = useState("");
  const addParam = () => {
    const name = newName.trim().replace(/\s/g, "_").toLowerCase();
    if (name && !(name in params)) {
      onChange({ ...params, [name]: { type: "string", description: "", required: true } });
      setNewName("");
    }
  };
  const removeParam = (key: string) => {
    const next = { ...params };
    delete next[key];
    onChange(next);
  };
  const updateParam = (key: string, field: string, value: any) => {
    onChange({ ...params, [key]: { ...params[key], [field]: value } });
  };
  return (
    <div className="space-y-1.5">
      {Object.entries(params).map(([key, val]: [string, any]) => (
        <div key={key} className="flex items-start gap-2 bg-white/[0.02] rounded-md p-2 border border-white/[0.05]">
          <div className="flex-1 space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-[var(--accent)]/70 font-mono font-medium">{key}</span>
              <select value={val.type || "string"} onChange={e => updateParam(key, "type", e.target.value)}
                className="bg-white/[0.04] border border-white/[0.06] rounded px-1.5 py-0.5 text-[10px] text-white/40 font-mono focus:outline-none">
                <option value="string">string</option>
                <option value="number">number</option>
                <option value="boolean">boolean</option>
              </select>
              <Toggle checked={val.required !== false} onChange={v => updateParam(key, "required", v)} label="req" />
            </div>
            <input value={val.description || ""} onChange={e => updateParam(key, "description", e.target.value)}
              placeholder="Description..." className="w-full bg-white/[0.025] border border-white/[0.04] rounded px-2 py-[3px] text-[10px] text-white/45 font-mono focus:outline-none focus:border-white/10 transition-all" />
          </div>
          <button onClick={() => removeParam(key)} className="p-1 text-white/15 hover:text-red-400 transition-colors"><Trash2 size={11} /></button>
        </div>
      ))}
      <div className="flex gap-1">
        <input value={newName} onChange={e => setNewName(e.target.value)} onKeyDown={e => e.key === "Enter" && (e.preventDefault(), addParam())}
          placeholder="new_param_name" className="flex-1 bg-white/[0.035] border border-white/[0.06] rounded-md px-2.5 py-[5px] text-xs text-white/45 font-mono focus:outline-none focus:border-[var(--accent)]/30 transition-all" />
        <button onClick={addParam} className="px-2.5 py-[5px] bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] rounded-md text-[10px] text-white/35 hover:text-white/55 font-mono transition-all">+ Add</button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════
// CARTRIDGE EDITOR
// ═══════════════════════════════════════════════════════
function CartridgeEditor({ cartridge, allTools, onSave, onDelete, onCancel, isNew }: {
  cartridge: CartridgeData; allTools: string[];
  onSave: (c: CartridgeData) => void; onDelete?: () => void;
  onCancel: () => void; isNew: boolean;
}) {
  const [data, setData] = useState<CartridgeData>({ ...cartridge });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showJson, setShowJson] = useState(false);
  const [saving, setSaving] = useState(false);

  const set = <K extends keyof CartridgeData>(key: K, value: CartridgeData[K]) => setData(d => ({ ...d, [key]: value }));
  const setTheme = (key: string, value: any) => setData(d => ({ ...d, theme: { ...d.theme, [key]: value } }));

  const autoId = (name: string) => name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  const handleSave = async () => {
    if (!data.name.trim()) { soundError(); return; }
    const toSave = { ...data };
    if (isNew || !toSave.id) toSave.id = autoId(toSave.name);
    setSaving(true);
    try { await onSave(toSave); } finally { setSaving(false); }
  };

  return (
    <div className="space-y-3 max-h-[70vh] overflow-y-auto subtle-scroll pr-1">
      {/* Core Fields */}
      <div className="grid grid-cols-[1fr_80px] gap-2">
        <Field label="Name">
          <TextInput value={data.name} onChange={v => { set("name", v); if (isNew) set("id", autoId(v)); }} placeholder="My Custom Bot" />
        </Field>
        <Field label="Icon">
          <TextInput value={data.icon} onChange={v => set("icon", v)} placeholder="🤖" />
        </Field>
      </div>
      {isNew && data.id && <p className="text-[8px] text-white/15 font-mono -mt-1.5">ID: {data.id}</p>}

      <Field label="Description" hint="One-line summary (max 120 chars)">
        <TextInput value={data.description} onChange={v => set("description", v)} placeholder="What does this kasset do?" />
      </Field>

      <Field label="System Prompt" hint="The core instruction that defines this agent's behavior">
        <TextArea value={data.system_prompt} onChange={v => set("system_prompt", v)} rows={8} mono placeholder="You are a specialist in..." />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Tools">
          <ToolMultiSelect selected={data.tools} onChange={v => set("tools", v)} allTools={allTools} />
        </Field>
        <div className="space-y-3">
          <Field label="Boot Message" hint="First message on load">
            <TextInput value={data.boot_message || ""} onChange={v => set("boot_message", v)} placeholder="Systems online." />
          </Field>
          <Field label="Tags">
            <TagInput tags={data.tags} onChange={v => set("tags", v)} />
          </Field>
        </div>
      </div>

      {/* Theme */}
      <SectionHeader title="Theme & Config" open={showAdvanced} onToggle={() => setShowAdvanced(!showAdvanced)} />
      {showAdvanced && (
        <div className="space-y-2.5 pl-3 border-l border-white/[0.04]">
          <div className="grid grid-cols-[1fr_1fr] gap-2">
            <Field label="Accent Color">
              <div className="flex gap-1.5 items-center">
                <input type="color" value={data.theme.accent_color} onChange={e => { setTheme("accent_color", e.target.value); setTheme("glow_color", e.target.value); }}
                  className="w-7 h-7 rounded-md border border-white/[0.06] bg-transparent cursor-pointer shrink-0" />
                <TextInput value={data.theme.accent_color} onChange={v => { setTheme("accent_color", v); setTheme("glow_color", v); }} mono />
              </div>
            </Field>
            <Field label="Boot Animation">
              <select value={data.theme.boot_animation} onChange={e => setTheme("boot_animation", e.target.value)}
                className="w-full bg-white/[0.035] border border-white/[0.06] rounded-md px-2.5 py-[7px] text-[13px] text-white/60 focus:outline-none focus:border-[var(--accent)]/30 transition-all">
                {["fade", "terminal", "glitch", "matrix", "scan"].map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Max Tokens">
              <TextInput value={String(data.suggested_tokens)} onChange={v => set("suggested_tokens", parseInt(v) || 4096)} mono />
            </Field>
            <Field label="Stacking Role">
              <select value={data.stacking.role} onChange={e => setData(d => ({ ...d, stacking: { ...d.stacking, role: e.target.value } }))}
                className="w-full bg-white/[0.035] border border-white/[0.06] rounded-md px-2.5 py-[7px] text-[13px] text-white/60 focus:outline-none focus:border-[var(--accent)]/30 transition-all">
                <option value="primary">primary</option>
                <option value="auxiliary">auxiliary</option>
              </select>
            </Field>
          </div>
          <div className="flex items-center gap-4 pt-0.5">
            <Toggle checked={data.suggested_thinking} onChange={v => set("suggested_thinking", v)} label="Thinking" />
            <Toggle checked={data.memory_enabled} onChange={v => set("memory_enabled", v)} label="Memory" />
          </div>
          <Field label="Suggested Model" hint="Preferred model for this kasset (optional)">
            <TextInput value={(data as any).suggested_model || ""} onChange={v => setData(d => ({ ...d, suggested_model: v || undefined } as any))} mono placeholder="mlx-community/Qwen3.5-9B-MLX-4bit" />
          </Field>
        </div>
      )}

      {/* JSON Preview */}
      <SectionHeader title="JSON Preview" open={showJson} onToggle={() => setShowJson(!showJson)} />
      {showJson && (
        <pre className="bg-black/40 border border-white/[0.05] rounded-md p-3 text-[10px] text-white/30 font-mono max-h-48 overflow-auto subtle-scroll whitespace-pre-wrap">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}

      {/* Actions */}
      <div className="flex items-center gap-1.5 pt-3 border-t border-white/[0.04]">
        <button onClick={handleSave} disabled={saving || !data.name.trim()}
          className="flex items-center gap-1.5 px-3.5 py-[7px] bg-[var(--accent)]/12 hover:bg-[var(--accent)]/20 text-[var(--accent)] rounded-md text-[11px] font-medium transition-all disabled:opacity-25">
          <Save size={13} /> {saving ? "Saving..." : "Save"}
        </button>
        <button onClick={async () => {
          if (!isNew && data.id) {
            // Export as .kasset zip bundle via API (includes tools)
            try {
              const res = await fetch(`${getApiBase()}/api/forge/export/${data.id}`);
              if (!res.ok) throw new Error("Export failed");
              const blob = await res.blob();
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a"); a.href = url; a.download = `kasset-${data.id}-v${data.version || "1.0.0"}.zip`;
              document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
            } catch { /* Fallback to JSON */
              const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a"); a.href = url; a.download = `${data.id || "kasset"}.json`;
              document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
            }
          } else {
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a"); a.href = url; a.download = `${data.id || "kasset"}.json`;
            document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
          }
        }} className="flex items-center gap-1 px-3 py-[7px] text-white/25 hover:text-white/50 hover:bg-white/[0.04] rounded-md text-[11px] font-medium transition-all" title="Export as .kasset bundle">
          <Download size={12} /> Export
        </button>
        <button onClick={() => { if (JSON.stringify(data) !== JSON.stringify(cartridge)) { if (!confirm("Discard unsaved changes?")) return; } onCancel(); }} className="px-3 py-[7px] text-white/25 hover:text-white/45 rounded-md text-[11px] font-medium transition-all hover:bg-white/[0.04]">Cancel</button>
        {onDelete && <button onClick={onDelete} className="ml-auto p-1.5 text-red-400/25 hover:text-red-400 hover:bg-red-400/10 rounded-md transition-all"><Trash2 size={13} /></button>}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════
// TOOL EDITOR
// ═══════════════════════════════════════════════════════
function ToolEditor({ manifest: initManifest, handlerCode: initCode, onSave, onDelete, onCancel, isNew }: {
  manifest: typeof EMPTY_MANIFEST; handlerCode: string;
  onSave: (m: typeof EMPTY_MANIFEST, code: string) => void;
  onDelete?: () => void; onCancel: () => void; isNew: boolean;
}) {
  const [manifest, setManifest] = useState({ ...initManifest });
  const [code, setCode] = useState(initCode);
  const [showSandbox, setShowSandbox] = useState(false);
  const [showJson, setShowJson] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [depStatus, setDepStatus] = useState<Record<string, string> | null>(null);
  const [installingDeps, setInstallingDeps] = useState(false);

  const set = (key: string, value: any) => setManifest((m: any) => ({ ...m, [key]: value }));
  const autoId = (name: string) => name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");

  const handleSave = async () => {
    if (!manifest.name.trim()) { soundError(); return; }
    const toSave = { ...manifest };
    if (isNew || !toSave.id) toSave.id = autoId(toSave.name);
    setSaving(true);
    try { await onSave(toSave, code); } finally { setSaving(false); }
  };

  const handleTest = async () => {
    if (!manifest.id) return;
    setTesting(true);
    try {
      // First save, then test
      const toSave = { ...manifest };
      if (!toSave.id) toSave.id = autoId(toSave.name);
      await fetch(`${getApiBase()}/api/forge/tools`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ manifest: toSave, handler_code: code }),
      });
      const res = await fetch(`${getApiBase()}/api/forge/tools/test`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool_id: toSave.id, args: {} }),
      });
      const data = await res.json();
      const result = typeof data.result === "string" ? data.result : JSON.stringify(data.result, null, 2);
      setTestResult(result);
    } catch (err: any) {
      setTestResult(`Error: ${err.message}`);
    }
    setTesting(false);
  };

  const checkDeps = async () => {
    if (!manifest.id) return;
    try {
      const res = await fetch(`${getApiBase()}/api/forge/tools/${manifest.id}/deps`);
      if (res.ok) {
        const data = await res.json();
        setDepStatus(Object.fromEntries(
          Object.entries(data.dependencies || {}).map(([k, v]) => [k, v ? "installed" : "missing"])
        ));
      }
    } catch {}
  };

  const installDeps = async () => {
    if (!manifest.id) return;
    setInstallingDeps(true);
    try {
      const res = await fetch(`${getApiBase()}/api/forge/tools/${manifest.id}/deps/install`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setDepStatus(data.results || {});
      }
    } catch {} finally { setInstallingDeps(false); }
  };

  return (
    <div className="space-y-3 max-h-[70vh] overflow-y-auto subtle-scroll pr-1">
      <div className="grid grid-cols-[1fr_100px_36px] gap-2 items-end">
        <Field label="Name">
          <TextInput value={manifest.name} onChange={v => { set("name", v); if (isNew) set("id", autoId(v)); }} placeholder="My Custom Tool" />
        </Field>
        <Field label="Icon">
          <TextInput value={manifest.icon} onChange={v => set("icon", v)} placeholder="wrench" />
        </Field>
        <div className="pb-px">
          <input type="color" value={manifest.color} onChange={e => set("color", e.target.value)}
            className="w-full h-[33px] rounded-md border border-white/[0.06] bg-transparent cursor-pointer" title="Color" />
        </div>
      </div>
      {isNew && manifest.id && <p className="text-[8px] text-white/15 font-mono -mt-1.5">ID: {manifest.id}</p>}

      <Field label="Description" hint="What the model sees — be specific">
        <TextArea value={manifest.description} onChange={v => set("description", v)} rows={2} placeholder="Creates interactive 3D visualizations..." />
      </Field>

      <div className="grid grid-cols-2 gap-2">
        <Field label="Output Type">
          <select value={manifest.output_type} onChange={e => set("output_type", e.target.value)}
            className="w-full bg-white/[0.035] border border-white/[0.06] rounded-md px-2.5 py-[7px] text-[13px] text-white/60 focus:outline-none focus:border-[var(--accent)]/30 transition-all">
            <option value="text">text — Plain text</option>
            <option value="html">html — Artifact</option>
            <option value="image">image — Base64</option>
            <option value="mixed">mixed — Dict</option>
          </select>
        </Field>
        <Field label="Parameters" hint="Arguments the model can pass">
          <ParamEditor params={manifest.parameters} onChange={v => set("parameters", v)} />
        </Field>
      </div>

      {/* Code Editor with header */}
      <div>
        <div className="flex items-center justify-between px-3 py-1.5 bg-[#161b22] border border-white/[0.06] border-b-0 rounded-t-md">
          <span className="text-[10px] text-white/25 font-mono">handler.py</span>
          <span className="text-[9px] text-white/15 font-mono">export "{manifest.entry_point || "execute"}(**kwargs)"</span>
        </div>
        <textarea
          value={code} onChange={e => setCode(e.target.value)} rows={14}
          spellCheck={false}
          className="w-full bg-[#0d1117] border border-white/[0.06] border-t-0 rounded-b-md px-3 py-2.5 text-[12px] text-[#e6edf3] font-mono leading-relaxed focus:outline-none resize-y subtle-scroll"
          style={{ tabSize: 4 }}
        />
      </div>

      {/* Sandbox Config */}
      <SectionHeader title="Sandbox Settings" open={showSandbox} onToggle={() => setShowSandbox(!showSandbox)} />
      {showSandbox && (
        <div className="space-y-2.5 pl-3 border-l border-white/[0.04]">
          <Field label="Dependencies" hint="Comma-separated pip packages (e.g. plotly>=5.0, librosa)">
            <TextInput value={(manifest.dependencies || []).join(", ")} onChange={v => set("dependencies", v.split(",").map((s: string) => s.trim()).filter(Boolean))} mono placeholder="plotly>=5.0, librosa" />
          </Field>
          {(manifest.dependencies || []).length > 0 && manifest.id && (
            <div className="flex items-center gap-2">
              <button onClick={checkDeps} className="text-[10px] text-white/30 hover:text-white/60 font-mono transition-colors">Check</button>
              <button onClick={installDeps} disabled={installingDeps}
                className="text-[10px] text-[var(--accent)]/60 hover:text-[var(--accent)] font-mono transition-colors disabled:opacity-30">
                {installingDeps ? "Installing…" : "Install Missing"}
              </button>
              {depStatus && (
                <div className="flex gap-1.5 flex-wrap">
                  {Object.entries(depStatus).map(([pkg, status]) => (
                    <span key={pkg} className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${
                      status === "installed" || status === "already_installed"
                        ? "bg-emerald-500/10 text-emerald-400/70"
                        : status === "missing"
                        ? "bg-red-500/10 text-red-400/70"
                        : "bg-yellow-500/10 text-yellow-400/70"
                    }`}>
                      {pkg.split(">=")[0].split("==")[0]}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
          <Field label="Pre-run Code" hint="Executed before handler loads (for imports)">
            <TextInput value={manifest.sandbox?.pre_run || ""} onChange={v => set("sandbox", { ...manifest.sandbox, pre_run: v })} mono placeholder="import plotly.graph_objects as go" />
          </Field>
          <Field label="Timeout (seconds)">
            <TextInput value={String(manifest.sandbox?.timeout || 30)} onChange={v => set("sandbox", { ...manifest.sandbox, timeout: parseInt(v) || 30 })} mono />
          </Field>
          <Field label="Tags">
            <TagInput tags={manifest.tags || []} onChange={v => set("tags", v)} />
          </Field>
        </div>
      )}

      {/* JSON Preview */}
      <SectionHeader title="Manifest Preview" open={showJson} onToggle={() => setShowJson(!showJson)} />
      {showJson && (
        <pre className="bg-black/40 border border-white/[0.05] rounded-md p-3 text-[10px] text-white/30 font-mono max-h-48 overflow-auto subtle-scroll whitespace-pre-wrap">
          {JSON.stringify(manifest, null, 2)}
        </pre>
      )}

      {/* Test Result */}
      {testResult !== null && (
        <div className="bg-white/[0.02] border border-white/[0.05] rounded-md overflow-hidden">
          <div className="flex items-center justify-between px-3 py-1.5 bg-white/[0.02] border-b border-white/[0.04]">
            <span className="text-[10px] text-white/25 font-mono">Test Result</span>
            <button onClick={() => setTestResult(null)} className="text-white/15 hover:text-white/40 transition-colors"><X size={10} /></button>
          </div>
          <pre className="px-3 py-2 text-[11px] text-white/50 font-mono whitespace-pre-wrap max-h-32 overflow-auto subtle-scroll">{testResult}</pre>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-1.5 pt-3 border-t border-white/[0.04]">
        <button onClick={handleSave} disabled={saving || !manifest.name.trim()}
          className="flex items-center gap-1.5 px-3.5 py-[7px] bg-[var(--accent)]/12 hover:bg-[var(--accent)]/20 text-[var(--accent)] rounded-md text-[11px] font-medium transition-all disabled:opacity-25">
          <Save size={13} /> {saving ? "Saving..." : "Save"}
        </button>
        <button onClick={handleTest} disabled={testing || !manifest.name.trim()}
          className="flex items-center gap-1.5 px-3 py-[7px] bg-emerald-500/8 hover:bg-emerald-500/15 text-emerald-400 rounded-md text-[11px] font-medium transition-all disabled:opacity-25">
          <Play size={13} /> {testing ? "Testing..." : "Test"}
        </button>
        <button onClick={() => { if (JSON.stringify(manifest) !== JSON.stringify(initManifest) || code !== initCode) { if (!confirm("Discard unsaved changes?")) return; } onCancel(); }} className="px-3 py-[7px] text-white/25 hover:text-white/45 rounded-md text-[11px] font-medium transition-all hover:bg-white/[0.04]">Cancel</button>
        {onDelete && <button onClick={onDelete} className="ml-auto p-1.5 text-red-400/25 hover:text-red-400 hover:bg-red-400/10 rounded-md transition-all"><Trash2 size={13} /></button>}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════
// MAIN KASSET FORGE
// ═══════════════════════════════════════════════════════
export default function ForgeStudio({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<"cartridges" | "tools">("cartridges");
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [allToolIds, setAllToolIds] = useState<string[]>([]);
  const { availableCartridges, loadAvailableCartridges } = useCartridgeStore();

  // Editor state
  const [editingCartridge, setEditingCartridge] = useState<CartridgeData | null>(null);
  const [isNewCartridge, setIsNewCartridge] = useState(false);
  const [editingTool, setEditingTool] = useState<{ manifest: typeof EMPTY_MANIFEST; code: string } | null>(null);
  const [isNewTool, setIsNewTool] = useState(false);

  const fetchTools = useCallback(async () => {
    try {
      const res = await fetch(`${getApiBase()}/api/forge/tools`);
      const data = await res.json();
      setTools(data.tools || []);
    } catch { /* ignore */ }
  }, []);

  const fetchToolIds = useCallback(async () => {
    try {
      const res = await fetch(`${getApiBase()}/api/forge/all-tool-ids`);
      const data = await res.json();
      setAllToolIds(data.tool_ids || []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchTools();
    fetchToolIds();
    loadAvailableCartridges();
  }, [fetchTools, fetchToolIds, loadAvailableCartridges]);

  // ─── Cartridge Handlers ──────────────────
  const handleNewCartridge = () => {
    setEditingCartridge({ ...EMPTY_CARTRIDGE });
    setIsNewCartridge(true);
    soundTick();
  };

  const handleEditCartridge = async (id: string) => {
    try {
      const res = await fetch(`${getApiBase()}/api/forge/kassets/${id}`);
      const data = await res.json();
      if (data.cartridge) {
        setEditingCartridge(data.cartridge);
        setIsNewCartridge(false);
        soundTick();
      }
    } catch { soundError(); }
  };

  const handleSaveCartridge = async (c: CartridgeData) => {
    try {
      const res = await fetch(`${getApiBase()}/api/forge/kassets`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(c),
      });
      const data = await res.json();
      if (data.saved) {
        soundNewChat();
        setEditingCartridge(null);
        loadAvailableCartridges();
        fetchToolIds();
      } else {
        soundError();
        alert(data.error || "Failed to save");
      }
    } catch { soundError(); }
  };

  const handleDeleteCartridge = async (id: string) => {
    if (!confirm(`Delete kasset "${id}"?`)) return;
    try {
      await fetch(`${getApiBase()}/api/forge/kassets/${id}`, { method: "DELETE" });
      soundTick();
      setEditingCartridge(null);
      loadAvailableCartridges();
    } catch { soundError(); }
  };

  // ─── Tool Handlers ──────────────────────
  const handleNewTool = () => {
    setEditingTool({ manifest: { ...EMPTY_MANIFEST }, code: DEFAULT_HANDLER });
    setIsNewTool(true);
    soundTick();
  };

  const handleEditTool = async (id: string) => {
    try {
      const res = await fetch(`${getApiBase()}/api/forge/tools/${id}`);
      const data = await res.json();
      if (data.manifest) {
        setEditingTool({ manifest: data.manifest, code: data.handler_code || DEFAULT_HANDLER });
        setIsNewTool(false);
        soundTick();
      }
    } catch { soundError(); }
  };

  const handleSaveTool = async (m: typeof EMPTY_MANIFEST, code: string) => {
    try {
      const res = await fetch(`${getApiBase()}/api/forge/tools`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ manifest: m, handler_code: code }),
      });
      const data = await res.json();
      if (data.saved) {
        soundNewChat();
        setEditingTool(null);
        fetchTools();
        fetchToolIds();
      } else {
        soundError();
        alert(data.error ? `${data.error}: ${JSON.stringify(data.details)}` : "Failed to save");
      }
    } catch { soundError(); }
  };

  const handleDeleteTool = async (id: string) => {
    if (!confirm(`Delete tool "${id}"?`)) return;
    try {
      await fetch(`${getApiBase()}/api/forge/tools/${id}`, { method: "DELETE" });
      soundTick();
      setEditingTool(null);
      fetchTools();
      fetchToolIds();
    } catch { soundError(); }
  };

  const userCartridges = availableCartridges.filter((c: any) => c.source === "user");
  const builtinCartridges = availableCartridges.filter((c: any) => c.source !== "user");
  const userTools = tools.filter(t => t.source === "user");
  const builtinTools = tools.filter(t => t.source === "builtin");

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-xl">
      {/* Ambient glow behind modal */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[400px] rounded-full opacity-[0.03]"
          style={{ background: "radial-gradient(ellipse, var(--accent), transparent 70%)" }} />
      </div>

      <div className="relative w-full max-w-3xl mx-0 sm:mx-4 max-h-[100dvh] sm:max-h-[92vh] bg-[#09090f]/98 border-0 sm:border border-white/[0.07] rounded-none sm:rounded-2xl shadow-[0_0_0_1px_rgba(255,255,255,0.03),0_32px_80px_-16px_rgba(0,0,0,0.8)] overflow-hidden flex flex-col"
        style={{ "--accent": "#60a5fa" } as React.CSSProperties}>

        {/* Top accent line */}
        <div className="h-px w-full shrink-0" style={{ background: "linear-gradient(90deg, transparent 10%, var(--accent) 50%, transparent 90%)", opacity: 0.3 }} />

        {/* Header */}
        <div className="flex items-center justify-between px-5 sm:px-6 py-4 shrink-0 border-b border-white/[0.04]">
          <div className="flex items-center gap-3.5">
            <div className="relative">
              <div className="p-2.5 rounded-xl border border-[var(--accent)]/15" style={{ background: "linear-gradient(135deg, rgba(96,165,250,0.08), rgba(96,165,250,0.02))" }}>
                <Wrench size={17} className="text-[var(--accent)]" style={{ filter: "drop-shadow(0 0 6px rgba(96,165,250,0.4))" }} />
              </div>
            </div>
            <div>
              <h1 className="text-base font-semibold text-white/90 tracking-tight">Kasset Forge</h1>
              <p className="text-[10px] text-white/25 mt-0.5 font-medium">Design agents & tools</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-xl text-white/25 hover:text-white/60 hover:bg-white/[0.06] transition-all duration-200">
            <X size={16} />
          </button>
        </div>

        {/* Onboarding banner */}
        {userCartridges.length === 0 && userTools.length === 0 && !editingCartridge && !editingTool && (
          <div className="mx-5 sm:mx-6 mt-4 mb-1 shrink-0">
            <div className="relative overflow-hidden rounded-xl border border-[var(--accent)]/12 p-4"
              style={{ background: "linear-gradient(135deg, rgba(96,165,250,0.04) 0%, rgba(96,165,250,0.01) 50%, transparent 100%)" }}>
              <div className="flex gap-3.5 items-start">
                <div className="p-1.5 rounded-lg bg-[var(--accent)]/8 shrink-0 mt-0.5">
                  <Info size={14} className="text-[var(--accent)]/80" />
                </div>
                <div>
                  <p className="text-[12px] text-white/55 leading-relaxed">
                    <strong className="text-[var(--accent)]/90 font-semibold">Get started</strong> — Build custom AI agents by combining a system prompt, tools, and a visual theme.
                  </p>
                  <div className="mt-3 flex gap-2">
                    <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.05]">
                      <Cpu size={12} className="text-[var(--accent)]/60 shrink-0" />
                      <span className="text-[10px] text-white/40 font-medium">Kasset = persona + tools + theme</span>
                    </div>
                    <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.05]">
                      <Code size={12} className="text-[var(--accent)]/60 shrink-0" />
                      <span className="text-[10px] text-white/40 font-medium">Tool = Python function the AI calls</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex mx-5 sm:mx-6 mt-3 mb-2 bg-white/[0.03] rounded-xl p-1 shrink-0 border border-white/[0.04]">
          {(["cartridges", "tools"] as const).map(t => (
            <button key={t} onClick={() => { setTab(t); setEditingCartridge(null); setEditingTool(null); }}
              className={`flex-1 flex items-center justify-center gap-2 py-2 text-[12px] font-medium transition-all duration-200 rounded-lg ${
                tab === t
                  ? "text-[var(--accent)] bg-[var(--accent)]/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.2),inset_0_1px_0_rgba(255,255,255,0.04)] border border-[var(--accent)]/10"
                  : "text-white/30 hover:text-white/50 border border-transparent"
              }`}>
              {t === "cartridges" ? <><Cpu size={13} /> Kassets</> : <><Code size={13} /> Tools</>}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto subtle-scroll px-5 sm:px-6 py-4">
          {/* ─── Cartridges Tab ─── */}
          {tab === "cartridges" && !editingCartridge && (
            <div className="space-y-4">
              {/* Section header */}
              <div className="flex items-center justify-between">
                <h2 className="text-[13px] text-white/50 font-semibold tracking-tight">Your Kassets</h2>
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-1.5 px-3 py-1.5 text-white/30 hover:text-white/55 hover:bg-white/[0.05] rounded-lg text-[11px] font-medium transition-all duration-200 cursor-pointer border border-transparent hover:border-white/[0.06]">
                    <Upload size={12} /> Import
                    <input type="file" accept=".json,.zip" className="sr-only" onChange={async (e) => {
                      const file = e.target.files?.[0]; if (!file) return;
                      try {
                        if (file.name.endsWith(".zip") || file.type === "application/zip") {
                          const form = new FormData();
                          form.append("file", file);
                          const res = await fetch(`${getApiBase()}/api/forge/import`, { method: "POST", body: form });
                          const data = await res.json();
                          if (data.imported) {
                            soundNewChat();
                            loadAvailableCartridges();
                            fetchToolIds();
                          } else { soundError(); alert(data.error || "Import failed"); }
                        } else {
                          const text = await file.text();
                          const data = JSON.parse(text);
                          await handleSaveCartridge(data);
                        }
                      } catch { soundError(); alert("Invalid kasset file"); }
                      e.target.value = "";
                    }} />
                  </label>
                  <button onClick={handleNewCartridge}
                    className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-[11px] font-semibold transition-all duration-200 border border-[var(--accent)]/20 hover:border-[var(--accent)]/35"
                    style={{ background: "linear-gradient(135deg, rgba(96,165,250,0.12), rgba(96,165,250,0.06))", color: "var(--accent)" }}>
                    <Plus size={13} /> New
                  </button>
                </div>
              </div>

              {/* Empty state */}
              {userCartridges.length === 0 && (
                <div className="text-center py-14">
                  <div className="w-14 h-14 mx-auto mb-4 rounded-2xl flex items-center justify-center border border-white/[0.06]"
                    style={{ background: "linear-gradient(135deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01))" }}>
                    <Package size={24} className="text-white/15" />
                  </div>
                  <p className="text-[14px] text-white/30 font-medium">No custom kassets yet</p>
                  <p className="text-[11px] mt-1.5 text-white/18">Click <strong className="text-[var(--accent)]/60">+ New</strong> to create your first agent</p>
                </div>
              )}

              {/* User kassets grid */}
              {userCartridges.length > 0 && (
                <div className="grid grid-cols-2 gap-2.5">
                  {userCartridges.map((c: any) => (
                    <button key={c.id} onClick={() => handleEditCartridge(c.id)}
                      className="relative flex items-center gap-3 p-3.5 rounded-xl border border-white/[0.06] hover:border-[var(--accent)]/20 transition-all duration-200 text-left group overflow-hidden"
                      style={{ background: "linear-gradient(135deg, rgba(255,255,255,0.025), rgba(255,255,255,0.01))" }}>
                      <div className="absolute inset-0 bg-[var(--accent)]/[0.02] opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                      <span className="text-2xl group-hover:scale-110 transition-transform duration-200 relative z-10">{c.icon}</span>
                      <div className="min-w-0 relative z-10">
                        <div className="text-[13px] text-white/70 font-semibold truncate group-hover:text-white/90 transition-colors duration-200">{c.name}</div>
                        <div className="text-[10px] text-white/20 truncate mt-0.5 group-hover:text-white/30 transition-colors">{c.description}</div>
                      </div>
                      <ChevronRight size={14} className="ml-auto text-white/0 group-hover:text-white/20 transition-all duration-200 shrink-0 relative z-10" />
                    </button>
                  ))}
                </div>
              )}

              {/* Built-in kassets */}
              {builtinCartridges.length > 0 && (
                <div className="pt-2">
                  <div className="flex items-center gap-3 mb-3">
                    <span className="text-[10px] text-white/20 font-semibold uppercase tracking-wider">Built-in</span>
                    <div className="flex-1 h-px bg-gradient-to-r from-white/[0.05] to-transparent" />
                  </div>
                  <div className="grid grid-cols-2 gap-1.5">
                    {builtinCartridges.map((c: any) => (
                      <button key={c.id} onClick={() => handleEditCartridge(c.id)}
                        className="flex items-center gap-2.5 px-3 py-2.5 rounded-lg border border-white/[0.03] hover:border-white/[0.08] hover:bg-white/[0.02] transition-all duration-200 text-left group">
                        <span className="text-base opacity-50 group-hover:opacity-80 transition-all duration-200 group-hover:scale-105">{c.icon}</span>
                        <div className="min-w-0 flex-1">
                          <div className="text-[11px] text-white/35 group-hover:text-white/55 font-medium truncate transition-colors duration-200">{c.name}</div>
                        </div>
                        <Eye size={10} className="text-white/0 group-hover:text-white/20 transition-all shrink-0" />
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {tab === "cartridges" && editingCartridge && (
            <CartridgeEditor
              cartridge={editingCartridge}
              allTools={allToolIds}
              onSave={handleSaveCartridge}
              onDelete={!isNewCartridge && (availableCartridges.find((c: any) => c.id === editingCartridge.id) as any)?.source === "user" ? () => handleDeleteCartridge(editingCartridge.id) : undefined}
              onCancel={() => setEditingCartridge(null)}
              isNew={isNewCartridge}
            />
          )}

          {/* ─── Tools Tab ─── */}
          {tab === "tools" && !editingTool && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-[13px] text-white/50 font-semibold tracking-tight">Your Tools</h2>
                <button onClick={handleNewTool}
                  className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-[11px] font-semibold transition-all duration-200 border border-[var(--accent)]/20 hover:border-[var(--accent)]/35"
                  style={{ background: "linear-gradient(135deg, rgba(96,165,250,0.12), rgba(96,165,250,0.06))", color: "var(--accent)" }}>
                  <Plus size={13} /> New Tool
                </button>
              </div>

              {/* Empty state */}
              {userTools.length === 0 && (
                <div className="text-center py-14">
                  <div className="w-14 h-14 mx-auto mb-4 rounded-2xl flex items-center justify-center border border-white/[0.06]"
                    style={{ background: "linear-gradient(135deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01))" }}>
                    <Code size={24} className="text-white/15" />
                  </div>
                  <p className="text-[14px] text-white/30 font-medium">No custom tools yet</p>
                  <p className="text-[11px] mt-1.5 text-white/18 max-w-xs mx-auto">Tools are Python functions your AI agents can call</p>
                </div>
              )}

              {/* User tools list */}
              {userTools.length > 0 && (
                <div className="space-y-2">
                  {userTools.map(t => (
                    <button key={t.id} onClick={() => handleEditTool(t.id)}
                      className="w-full relative flex items-center gap-3 p-3.5 rounded-xl border border-white/[0.06] hover:border-[var(--accent)]/20 transition-all duration-200 text-left group overflow-hidden"
                      style={{ background: "linear-gradient(135deg, rgba(255,255,255,0.025), rgba(255,255,255,0.01))" }}>
                      <div className="absolute inset-0 bg-[var(--accent)]/[0.02] opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                      <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 relative z-10 border border-white/[0.06]"
                        style={{ background: `linear-gradient(135deg, ${t.color || "#60a5fa"}15, ${t.color || "#60a5fa"}05)` }}>
                        <Wrench size={15} style={{ color: t.color || "#60a5fa" }} />
                      </div>
                      <div className="flex-1 min-w-0 relative z-10">
                        <div className="text-[13px] text-white/70 font-semibold group-hover:text-white/90 transition-colors duration-200">{t.name}</div>
                        <div className="text-[10px] text-white/20 truncate mt-0.5 group-hover:text-white/30 transition-colors">{t.description || t.id}</div>
                      </div>
                      <span className="text-[9px] text-white/15 font-mono px-2 py-1 bg-white/[0.03] rounded-md border border-white/[0.04] relative z-10">{t.output_type || "text"}</span>
                      <ChevronRight size={14} className="text-white/0 group-hover:text-white/20 transition-all duration-200 shrink-0 relative z-10" />
                    </button>
                  ))}
                </div>
              )}

              {/* Built-in tools */}
              {builtinTools.length > 0 && (
                <div className="pt-2">
                  <div className="flex items-center gap-3 mb-3">
                    <span className="text-[10px] text-white/20 font-semibold uppercase tracking-wider">Built-in</span>
                    <div className="flex-1 h-px bg-gradient-to-r from-white/[0.05] to-transparent" />
                  </div>
                  <div className="grid grid-cols-3 gap-1.5">
                    {builtinTools.map(t => (
                      <div key={t.id} className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-white/[0.015] border border-white/[0.03] hover:border-white/[0.06] hover:bg-white/[0.03] transition-all duration-200">
                        <Wrench size={10} className="text-white/15 shrink-0" />
                        <span className="text-[9px] text-white/25 font-mono truncate">{t.id}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {tab === "tools" && editingTool && (
            <ToolEditor
              manifest={editingTool.manifest}
              handlerCode={editingTool.code}
              onSave={handleSaveTool}
              onDelete={!isNewTool ? () => handleDeleteTool(editingTool.manifest.id) : undefined}
              onCancel={() => setEditingTool(null)}
              isNew={isNewTool}
            />
          )}
        </div>

        {/* Bottom fade */}
        <div className="h-px w-full shrink-0 bg-gradient-to-r from-transparent via-white/[0.04] to-transparent" />
      </div>
    </div>
  );
}
