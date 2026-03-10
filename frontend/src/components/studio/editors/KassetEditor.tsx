"use client";

import React, { useState } from "react";
import { Save, Download, Trash2, Code } from "lucide-react";
import { soundError, soundTick } from "@/lib/sounds";
import { CartridgeData, useKassetForgeStore } from "@/stores/kassetForgeStore";
import { useToolForgeStore } from "@/stores/toolForgeStore";
import { useInputTypeForgeStore } from "@/stores/inputTypeForgeStore";
import { 
  SectionHeader, Field, TextInput, TextArea, 
  Toggle, TagInput 
} from "../ForgeUI";

interface KassetEditorProps {
  cartridge: CartridgeData;
  onSave: (c: CartridgeData) => void;
  onDelete?: () => void;
  onCancel: () => void;
  isNew: boolean;
}

export function KassetEditor({ cartridge, onSave, onDelete, onCancel, isNew }: KassetEditorProps) {
  const [data, setData] = useState<CartridgeData>({ ...cartridge });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showJson, setShowJson] = useState(false);
  const [saving, setSaving] = useState(false);
  
  const { exportKasset } = useKassetForgeStore();
  const { allToolIds } = useToolForgeStore();

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
          <ToolMultiSelect selected={data.tools} onChange={v => set("tools", v)} allTools={allToolIds} />
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

      <Field
        label="Input Methods"
        hint="Reusable request_user_input templates this kasset can use. Surfaced in model system prompt."
      >
        <InputMethodsEditor
          methods={data.input_methods || []}
          onChange={(v) => setData(d => ({ ...d, input_methods: v }))}
        />
      </Field>

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
          <div className="grid grid-cols-2 gap-2">
            <Field label="Temperature">
              <TextInput value={String(data.suggested_temperature || "")} onChange={v => set("suggested_temperature", parseFloat(v) || undefined)} mono placeholder="0.7" />
            </Field>
            <Field label="Top P">
              <TextInput value={String(data.suggested_top_p || "")} onChange={v => set("suggested_top_p", parseFloat(v) || undefined)} mono placeholder="0.8" />
            </Field>
          </div>
          <Field label="Suggested Model" hint="Preferred model for this kasset (optional)">
            <TextInput value={data.suggested_model || ""} onChange={v => setData(d => ({ ...d, suggested_model: v || undefined }))} mono placeholder="mlx-community/Qwen3.5-9B-MLX-4bit" />
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
        {!isNew && data.id && (
          <button onClick={() => exportKasset(data.id, data.version)} className="flex items-center gap-1 px-3 py-[7px] text-white/25 hover:text-white/50 hover:bg-white/[0.04] rounded-md text-[11px] font-medium transition-all" title="Export as .kasset bundle">
            <Download size={12} /> Export .kasset
          </button>
        )}
        <button onClick={() => { if (JSON.stringify(data) !== JSON.stringify(cartridge)) { if (!confirm("Discard unsaved changes?")) return; } onCancel(); }} className="px-3 py-[7px] text-white/25 hover:text-white/45 rounded-md text-[11px] font-medium transition-all hover:bg-white/[0.04]">Cancel</button>
        {onDelete && <button onClick={onDelete} className="ml-auto p-1.5 text-red-400/25 hover:text-red-400 hover:bg-red-400/10 rounded-md transition-all"><Trash2 size={13} /></button>}
      </div>
    </div>
  );
}

// ─── Internal Sub-components ──────────────────────────

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

function InputMethodsEditor({ methods, onChange }: {
  methods: CartridgeData["input_methods"];
  onChange: (methods: CartridgeData["input_methods"]) => void;
}) {
  const { inputTypes, fetchInputTypes } = useInputTypeForgeStore();
  const [showAddInline, setShowAddInline] = React.useState(false);

  React.useEffect(() => {
    fetchInputTypes();
  }, []);

  const update = (idx: number, patch: any) => {
    const next = (methods || []).map((m, i) => i === idx ? (typeof m === 'string' ? m : { ...m, ...patch }) : m);
    onChange(next);
  };

  const remove = (idx: number) => onChange((methods || []).filter((_, i) => i !== idx));

  const addStandalone = (id: string) => {
    onChange([...(methods || []), id]);
  };

  const addInline = () => {
    const n = (methods || []).length + 1;
    onChange([
      ...(methods || []),
      {
        id: `method_${n}`,
        name: `Method ${n}`,
        description: "",
        widget_type: "form",
        example: { widget_type: "form", config: { prompt: "Collect details", fields: [{ name: "field1", label: "Field 1", type: "text" }] } },
      },
    ]);
  };

  return (
    <div className="space-y-2">
      {(methods || []).map((m, i) => {
        if (typeof m === "string") {
          const manifest = inputTypes.find((it: any) => it.id === m);
          return (
            <div key={`${m}-${i}`} className="flex items-center gap-2 p-2 rounded-lg border border-[var(--accent)]/10 bg-[var(--accent)]/5">
              <div className="p-1.5 bg-[var(--accent)]/10 rounded-md text-[var(--accent)]">
                <Code size={12} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[11px] font-medium text-white/70 truncate">{manifest?.name || m}</p>
                <p className="text-[9px] text-white/30 font-mono truncate">Standalone: {m}</p>
              </div>
              <button onClick={() => remove(i)} className="p-1.5 text-white/20 hover:text-red-400 transition-colors">
                <Trash2 size={12} />
              </button>
            </div>
          );
        }

        return (
          <div key={`${m.id}-${i}`} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5 space-y-2">
            <div className="grid grid-cols-[1fr_1fr_110px_28px] gap-2 items-end">
              <Field label="Method ID">
                <TextInput value={m.id} onChange={v => update(i, { id: v })} mono />
              </Field>
              <Field label="Name">
                <TextInput value={m.name} onChange={v => update(i, { name: v })} />
              </Field>
              <Field label="Widget">
                <select
                  value={m.widget_type || "form"}
                  onChange={e => update(i, { widget_type: e.target.value })}
                  className="w-full bg-white/[0.035] border border-white/[0.06] rounded-md px-2.5 py-[7px] text-[12px] text-white/60 focus:outline-none focus:border-[var(--accent)]/30 transition-all"
                >
                  {['choice', 'form', 'slider', 'editor', 'embed', 'custom'].map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </Field>
              <button onClick={() => remove(i)} className="p-1.5 text-red-400/30 hover:text-red-400 transition-colors rounded-md hover:bg-red-400/10">
                <Trash2 size={12} />
              </button>
            </div>
            <TextArea
              value={JSON.stringify(m.example || {}, null, 2)}
              onChange={(v) => { try { update(i, { example: JSON.parse(v) }); } catch {} }}
              rows={3}
              mono
            />
          </div>
        );
      })}

      <div className="flex flex-wrap gap-1.5">
        <select 
          onChange={(e) => { if (e.target.value) addStandalone(e.target.value); e.target.value = ""; }}
          className="px-3 py-[7px] bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] rounded-md text-[11px] text-white/40 hover:text-white/60 font-medium transition-all focus:outline-none"
        >
          <option value="">+ Add Standalone Type...</option>
          {inputTypes.filter(it => !(methods || []).includes(it.id)).map((it: any) => (
            <option key={it.id} value={it.id}>{it.name} ({it.id})</option>
          ))}
        </select>
        <button onClick={addInline} className="px-3 py-[7px] bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] rounded-md text-[11px] text-white/40 hover:text-white/60 font-medium transition-all">
          + Add Inline Method
        </button>
      </div>
    </div>
  );
}
