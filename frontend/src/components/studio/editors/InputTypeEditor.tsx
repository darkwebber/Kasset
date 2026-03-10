"use client";

import React, { useState } from "react";
import { Save, Trash2, Code } from "lucide-react";
import { soundError } from "@/lib/sounds";
import { InputTypeManifest } from "@/stores/inputTypeForgeStore";
import { SectionHeader, Field, TextInput, TextArea, TagInput } from "../ForgeUI";

interface InputTypeEditorProps {
  manifest: InputTypeManifest;
  onSave: (m: InputTypeManifest) => void;
  onDelete?: () => void;
  onCancel: () => void;
  isNew: boolean;
}

export function InputTypeEditor({ manifest: initManifest, onSave, onDelete, onCancel, isNew }: InputTypeEditorProps) {
  const [manifest, setManifest] = useState<InputTypeManifest>({ ...initManifest });
  const [showJson, setShowJson] = useState(false);
  const [saving, setSaving] = useState(false);

  const set = (key: string, value: any) => setManifest(m => ({ ...m, [key]: value }));
  const autoId = (name: string) => name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  const handleSave = async () => {
    if (!manifest.id && !manifest.name.trim()) { soundError(); return; }
    const toSave = { ...manifest };
    if (!toSave.id) toSave.id = autoId(toSave.name);
    setSaving(true);
    try { await onSave(toSave); } finally { setSaving(false); }
  };

  return (
    <div className="space-y-3 max-h-[70vh] overflow-y-auto subtle-scroll pr-1">
      <div className="grid grid-cols-[1fr_80px] gap-2">
        <Field label="Name">
          <TextInput value={manifest.name} onChange={v => { set("name", v); if (isNew && !manifest.id) set("id", autoId(v)); }} placeholder="Number Slider" />
        </Field>
        <Field label="Icon">
          <TextInput value={manifest.icon || ""} onChange={v => set("icon", v)} placeholder="sliders" />
        </Field>
      </div>
      {(isNew || manifest.id) && <p className="text-[8px] text-white/15 font-mono -mt-1.5">ID: {manifest.id}</p>}

      <Field label="Description" hint="Describe the widget's purpose">
        <TextInput value={manifest.description} onChange={v => set("description", v)} placeholder="A range slider for selecting numeric values" />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Widget Type">
          <select value={manifest.widget_type} onChange={e => set("widget_type", e.target.value)}
            className="w-full bg-white/[0.035] border border-white/[0.06] rounded-md px-2.5 py-[7px] text-[13px] text-white/60 focus:outline-none focus:border-[var(--accent)]/30 transition-all">
            {['form', 'choice', 'slider', 'editor', 'embed', 'custom'].map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </Field>
        <Field label="Tags">
          <TagInput tags={manifest.tags || []} onChange={v => set("tags", v)} />
        </Field>
      </div>

      <Field label="Configuration Template" hint="The JSON payload structure for request_user_input using this type">
        <TextArea
          value={JSON.stringify(manifest.config_template || {}, null, 2)}
          onChange={(v) => {
            try { set("config_template", JSON.parse(v)); } catch {}
          }}
          rows={8}
          mono
          placeholder='{ "min": 0, "max": 100 }'
        />
      </Field>

      {/* JSON Preview */}
      <SectionHeader title="Manifest Preview" open={showJson} onToggle={() => setShowJson(!showJson)} />
      {showJson && (
        <pre className="bg-black/40 border border-white/[0.05] rounded-md p-3 text-[10px] text-white/30 font-mono max-h-48 overflow-auto subtle-scroll whitespace-pre-wrap">
          {JSON.stringify(manifest, null, 2)}
        </pre>
      )}

      {/* Actions */}
      <div className="flex items-center gap-1.5 pt-3 border-t border-white/[0.04]">
        <button onClick={handleSave} disabled={saving || (!manifest.id && !manifest.name.trim())}
          className="flex items-center gap-1.5 px-3.5 py-[7px] bg-[var(--accent)]/12 hover:bg-[var(--accent)]/20 text-[var(--accent)] rounded-md text-[11px] font-medium transition-all disabled:opacity-25">
          <Save size={13} /> {saving ? "Saving..." : "Save"}
        </button>
        <button onClick={() => { if (JSON.stringify(manifest) !== JSON.stringify(initManifest)) { if (!confirm("Discard unsaved changes?")) return; } onCancel(); }} className="px-3 py-[7px] text-white/25 hover:text-white/45 rounded-md text-[11px] font-medium transition-all hover:bg-white/[0.04]">Cancel</button>
        {onDelete && <button onClick={onDelete} className="ml-auto p-1.5 text-red-400/25 hover:text-red-400 hover:bg-red-400/10 rounded-md transition-all"><Trash2 size={13} /></button>}
      </div>
    </div>
  );
}
