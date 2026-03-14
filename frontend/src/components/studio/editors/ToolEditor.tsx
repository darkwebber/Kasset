"use client";

import React, { useState } from "react";
import { Save, Play, Trash2, X } from "lucide-react";
import { soundError, soundNewChat } from "@/lib/sounds";
import { useToolForgeStore, ToolManifest } from "@/stores/toolForgeStore";
import { SectionHeader, Field, TextInput, TextArea, Toggle, TagInput } from "../ForgeUI";

interface ToolEditorProps {
  manifest: ToolManifest;
  handlerCode: string;
  onSave: (m: ToolManifest, code: string) => void;
  onDelete?: () => void;
  onCancel: () => void;
  isNew: boolean;
}

export function ToolEditor({ manifest: initManifest, handlerCode: initCode, onSave, onDelete, onCancel, isNew }: ToolEditorProps) {
  const [manifest, setManifest] = useState({ ...initManifest });
  const [code, setCode] = useState(initCode);
  const [showSandbox, setShowSandbox] = useState(false);
  const [showJson, setShowJson] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [showTest, setShowTest] = useState(false);
  const [testArgs, setTestArgs] = useState<Record<string, string>>({});
  const [depStatus, setDepStatus] = useState<Record<string, string> | null>(null);
  const [installingDeps, setInstallingDeps] = useState(false);

  const { testTool, checkDeps, installDeps } = useToolForgeStore();

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
      // Convert string inputs to proper types based on param definitions
      const typedArgs: Record<string, any> = {};
      for (const [k, v] of Object.entries(testArgs)) {
        if (!v && v !== "0") continue;
        const paramDef = manifest.parameters[k];
        if (paramDef?.type === "number") typedArgs[k] = Number(v);
        else if (paramDef?.type === "boolean") typedArgs[k] = v === "true";
        else typedArgs[k] = v;
      }
      const data = await testTool(manifest.id, typedArgs);
      const result = typeof data.result === "string" ? data.result : JSON.stringify(data.result, null, 2);
      setTestResult(result);
    } catch (err: any) {
      setTestResult(`Error: ${err.message}`);
    }
    setTesting(false);
  };

  const onCheckDeps = async () => {
    if (!manifest.id) return;
    try {
      const status = await checkDeps(manifest.id);
      setDepStatus(Object.fromEntries(
        Object.entries(status).map(([k, v]) => [k, v ? "installed" : "missing"])
      ));
    } catch {}
  };

  const onInstallDeps = async () => {
    if (!manifest.id) return;
    setInstallingDeps(true);
    try {
      const results = await installDeps(manifest.id);
      setDepStatus(results);
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

      {/* Code Editor */}
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
          <Field label="Dependencies" hint="Comma-separated pip packages (e.g. plotly>=5.0)">
            <TextInput value={(manifest.dependencies || []).join(", ")} onChange={v => set("dependencies", v.split(",").map((s: string) => s.trim()).filter(Boolean))} mono placeholder="plotly>=5.0" />
          </Field>
          {(manifest.dependencies || []).length > 0 && manifest.id && (
            <div className="flex items-center gap-2">
              <button onClick={onCheckDeps} className="text-[10px] text-white/30 hover:text-white/60 font-mono transition-colors">Check</button>
              <button onClick={onInstallDeps} disabled={installingDeps}
                className="text-[10px] text-[var(--accent)]/60 hover:text-[var(--accent)] font-mono transition-colors disabled:opacity-30">
                {installingDeps ? "Installing…" : "Install Missing"}
              </button>
              {depStatus && (
                <div className="flex gap-1.5 flex-wrap">
                  {Object.entries(depStatus).map(([pkg, status]) => (
                    <span key={pkg} className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${status === "installed" ? "bg-emerald-500/10 text-emerald-400/70" : "bg-red-500/10 text-red-400/70"}`}>
                      {pkg.split(">=")[0]}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
          <Field label="Pre-run Code" hint="Executed before handler loads">
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

      {/* Test Panel */}
      <SectionHeader title="Test Tool" open={showTest} onToggle={() => setShowTest(!showTest)} />
      {showTest && (
        <div className="space-y-2 pl-3 border-l border-emerald-500/10">
          {Object.keys(manifest.parameters).length > 0 ? (
            Object.entries(manifest.parameters).map(([key, val]: [string, any]) => (
              <div key={key} className="flex items-center gap-2">
                <label className="text-[10px] text-white/30 font-mono w-24 shrink-0 truncate" title={val.description || key}>{key}</label>
                <input
                  value={testArgs[key] || ""}
                  onChange={e => setTestArgs(prev => ({ ...prev, [key]: e.target.value }))}
                  placeholder={val.type === "boolean" ? "true / false" : val.type || "string"}
                  className="flex-1 bg-white/[0.035] border border-white/[0.06] rounded-md px-2.5 py-[5px] text-[11px] text-white/60 font-mono focus:outline-none focus:border-emerald-500/30 transition-all"
                />
              </div>
            ))
          ) : (
            <p className="text-[10px] text-white/20 italic">No parameters defined — test will run with empty args.</p>
          )}
          <button onClick={handleTest} disabled={testing || !manifest.id}
            className="flex items-center gap-1.5 px-3 py-[6px] bg-emerald-500/8 hover:bg-emerald-500/15 text-emerald-400 rounded-md text-[10px] font-medium transition-all disabled:opacity-25">
            <Play size={11} /> {testing ? "Running..." : "Run Test"}
          </button>
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
          placeholder="new_param" className="flex-1 bg-white/[0.035] border border-white/[0.06] rounded-md px-2.5 py-[5px] text-xs text-white/45 font-mono focus:outline-none focus:border-[var(--accent)]/30 transition-all" />
        <button onClick={addParam} className="px-2.5 py-[5px] bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] rounded-md text-[10px] text-white/35 hover:text-white/55 font-mono transition-all">+</button>
      </div>
    </div>
  );
}
