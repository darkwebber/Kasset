"use client";

import React, { useState } from "react";
import { ChevronLeft, ChevronRight, Sparkles, Save } from "lucide-react";
import { soundTick, soundError } from "@/lib/sounds";
import { CartridgeData } from "@/stores/kassetForgeStore";
import { useToolForgeStore } from "@/stores/toolForgeStore";
import { Field, TextInput, TextArea, Toggle } from "../ForgeUI";

interface KassetWizardProps {
  initial: CartridgeData;
  onSave: (c: CartridgeData) => void;
  onCancel: () => void;
}

const STEPS = ["Identity", "Personality", "Tools", "Theme"] as const;
type Step = typeof STEPS[number];

export function KassetWizard({ initial, onSave, onCancel }: KassetWizardProps) {
  const [step, setStep] = useState(0);
  const [data, setData] = useState<CartridgeData>({ ...initial });
  const [saving, setSaving] = useState(false);
  const { allToolIds } = useToolForgeStore();

  const set = <K extends keyof CartridgeData>(key: K, value: CartridgeData[K]) => setData(d => ({ ...d, [key]: value }));
  const setTheme = (key: string, value: any) => setData(d => ({ ...d, theme: { ...d.theme, [key]: value } }));
  const autoId = (name: string) => name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  const canNext = () => {
    if (step === 0) return data.name.trim().length > 0;
    return true;
  };

  const handleSave = async () => {
    if (!data.name.trim()) { soundError(); return; }
    const toSave = { ...data };
    if (!toSave.id) toSave.id = autoId(toSave.name);
    setSaving(true);
    try { await onSave(toSave); } finally { setSaving(false); }
  };

  return (
    <div className="space-y-4">
      {/* Step indicator */}
      <div className="flex items-center gap-1 px-1">
        {STEPS.map((s, i) => (
          <React.Fragment key={s}>
            <button
              onClick={() => i <= step && setStep(i)}
              className={`text-[10px] font-medium px-2 py-1 rounded-md transition-all ${
                i === step
                  ? "bg-[var(--accent)]/15 text-[var(--accent)]"
                  : i < step
                  ? "text-[var(--accent)]/40 hover:text-[var(--accent)]/60 cursor-pointer"
                  : "text-white/15 cursor-default"
              }`}
            >
              {s}
            </button>
            {i < STEPS.length - 1 && (
              <div className={`flex-1 h-px ${i < step ? "bg-[var(--accent)]/20" : "bg-white/5"}`} />
            )}
          </React.Fragment>
        ))}
      </div>

      {/* Step content */}
      <div className="min-h-[240px]">
        {step === 0 && (
          <div className="space-y-3">
            <p className="text-[11px] text-white/30 leading-relaxed">Give your kasset an identity. The name and icon are what users see when selecting it.</p>
            <div className="grid grid-cols-[1fr_80px] gap-2">
              <Field label="Name">
                <TextInput value={data.name} onChange={v => { set("name", v); set("id", autoId(v)); }} placeholder="My Custom Bot" />
              </Field>
              <Field label="Icon">
                <TextInput value={data.icon} onChange={v => set("icon", v)} placeholder="🤖" />
              </Field>
            </div>
            {data.id && <p className="text-[8px] text-white/15 font-mono -mt-1">ID: {data.id}</p>}
            <Field label="Description" hint="One-line summary shown in the kasset picker">
              <TextInput value={data.description} onChange={v => set("description", v)} placeholder="What does this kasset do?" />
            </Field>
            <Field label="Boot Message" hint="First message shown when loaded">
              <TextInput value={data.boot_message || ""} onChange={v => set("boot_message", v)} placeholder="Systems online. How can I help?" />
            </Field>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-3">
            <p className="text-[11px] text-white/30 leading-relaxed">Define the agent's personality and behavior. This is the core instruction the model follows.</p>
            <Field label="System Prompt" hint="Be specific about tone, expertise, and constraints">
              <TextArea value={data.system_prompt} onChange={v => set("system_prompt", v)} rows={10} mono placeholder="You are a specialist in..." />
            </Field>
            <div className="flex items-center gap-4">
              <Toggle checked={data.suggested_thinking} onChange={v => set("suggested_thinking", v)} label="Enable Thinking" />
              <Toggle checked={data.memory_enabled} onChange={v => set("memory_enabled", v)} label="Enable Memory" />
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-3">
            <p className="text-[11px] text-white/30 leading-relaxed">Select which tools this kasset can use. The model will only have access to checked tools.</p>
            <div className="grid grid-cols-2 gap-px bg-white/[0.02] rounded-md border border-white/[0.06] overflow-hidden max-h-64 overflow-y-auto subtle-scroll">
              {allToolIds.map((id: string) => {
                const checked = data.tools.includes(id);
                return (
                  <label key={id} className={`flex items-center gap-2 px-2.5 py-[6px] cursor-pointer text-[11px] font-mono transition-all ${checked ? "bg-[var(--accent)]/8 text-[var(--accent)]/80" : "text-white/30 hover:bg-white/[0.03] hover:text-white/45"}`}>
                    <input type="checkbox" checked={checked} onChange={() => {
                      if (checked) set("tools", data.tools.filter(t => t !== id));
                      else set("tools", [...data.tools, id]);
                    }} className="sr-only" />
                    <div className={`w-3 h-3 rounded-sm border transition-all flex items-center justify-center ${checked ? "bg-[var(--accent)]/80 border-[var(--accent)]/60" : "border-white/15"}`}>
                      {checked && <svg width="8" height="8" viewBox="0 0 12 12"><path d="M2.5 6l2.5 2.5 5-5" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" className="text-white"/></svg>}
                    </div>
                    {id}
                  </label>
                );
              })}
            </div>
            <p className="text-[9px] text-white/15">{data.tools.length} tool{data.tools.length !== 1 ? "s" : ""} selected</p>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-3">
            <p className="text-[11px] text-white/30 leading-relaxed">Customize the visual theme. These settings control the console appearance when this kasset is active.</p>
            <div className="grid grid-cols-2 gap-2">
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
            <Field label="Tags">
              <div className="flex flex-wrap gap-1.5">
                {data.tags.map(t => (
                  <span key={t} className="text-[10px] font-mono px-1.5 py-0.5 bg-[var(--accent)]/8 border border-[var(--accent)]/10 rounded text-[var(--accent)]/70">
                    {t}
                    <button onClick={() => set("tags", data.tags.filter(x => x !== t))} className="ml-1 text-white/20 hover:text-red-400">&times;</button>
                  </span>
                ))}
                <input
                  placeholder="Add tag..."
                  className="bg-white/[0.035] border border-white/[0.06] rounded-md px-2 py-[3px] text-[10px] text-white/50 font-mono w-24 focus:outline-none focus:border-[var(--accent)]/30 transition-all"
                  onKeyDown={e => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      const v = (e.target as HTMLInputElement).value.trim().toLowerCase();
                      if (v && !data.tags.includes(v)) { set("tags", [...data.tags, v]); (e.target as HTMLInputElement).value = ""; }
                    }
                  }}
                />
              </div>
            </Field>

            {/* Preview card */}
            <div className="mt-2 p-3 rounded-xl border border-white/[0.06] bg-white/[0.02]">
              <p className="text-[9px] text-white/20 uppercase tracking-wider mb-2 font-semibold">Preview</p>
              <div className="flex items-center gap-3">
                <span className="text-2xl">{data.icon}</span>
                <div>
                  <p className="text-[13px] text-white/80 font-semibold">{data.name || "Untitled"}</p>
                  <p className="text-[10px] text-white/30">{data.description || "No description"}</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <div className="flex items-center gap-2 pt-3 border-t border-white/[0.04]">
        {step > 0 && (
          <button onClick={() => { setStep(s => s - 1); soundTick(); }}
            className="flex items-center gap-1 px-3 py-[7px] text-white/30 hover:text-white/55 rounded-md text-[11px] font-medium transition-all hover:bg-white/[0.04]">
            <ChevronLeft size={13} /> Back
          </button>
        )}
        <div className="flex-1" />
        <button onClick={onCancel} className="px-3 py-[7px] text-white/20 hover:text-white/40 rounded-md text-[11px] font-medium transition-all">
          Cancel
        </button>
        {step < STEPS.length - 1 ? (
          <button onClick={() => { if (canNext()) { setStep(s => s + 1); soundTick(); } else soundError(); }}
            className="flex items-center gap-1 px-3.5 py-[7px] bg-[var(--accent)]/12 hover:bg-[var(--accent)]/20 text-[var(--accent)] rounded-md text-[11px] font-medium transition-all disabled:opacity-25"
            disabled={!canNext()}>
            Next <ChevronRight size={13} />
          </button>
        ) : (
          <button onClick={handleSave} disabled={saving || !data.name.trim()}
            className="flex items-center gap-1.5 px-3.5 py-[7px] bg-[var(--accent)]/12 hover:bg-[var(--accent)]/20 text-[var(--accent)] rounded-md text-[11px] font-medium transition-all disabled:opacity-25">
            <Sparkles size={12} /> {saving ? "Creating..." : "Create Kasset"}
          </button>
        )}
      </div>
    </div>
  );
}
