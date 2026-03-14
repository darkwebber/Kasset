"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import { Check, X, ChevronDown, Send, Sliders, ListChecks, FileEdit, FormInput, ExternalLink, Copy, Download, GitBranch, Edit3, CheckCircle, XCircle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getApiBase } from "@/lib/api";
import type { InteractiveSegment } from "./types";
import ProgressWidget from "./ProgressWidget";
import DraftBlock, { DraftContext } from "./DraftBlock";

// ═══════════════════════════════════════════
// SHARED — Markdown prompt renderer
// ═══════════════════════════════════════════

function WidgetPrompt({ text, className }: { text: string; className?: string }) {
  return (
    <div className={className || "text-[13px] text-white/80 font-medium leading-relaxed [&_p]:m-0 [&_strong]:text-white/90 [&_em]:text-white/70 [&_a]:text-[var(--accent)] [&_a]:underline [&_code]:text-[var(--accent)]/80 [&_code]:text-[11px] [&_code]:bg-white/5 [&_code]:px-1 [&_code]:rounded"}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}

// ═══════════════════════════════════════════
// CHOICE WIDGET — single/multi select options
// ═══════════════════════════════════════════

function ChoiceWidget({ segment, onSubmit, onDismiss }: WidgetProps) {
  const { config } = segment;
  const options: { label: string; value: string; description?: string }[] = config.options || [];
  const multiple = config.multiple || false;
  const [selected, setSelected] = useState<string[]>(() => {
    // Restore selection from response when widget is already finalized
    if (segment.status === "submitted" && segment.response) {
      return Array.isArray(segment.response) ? segment.response : [String(segment.response)];
    }
    return [];
  });

  const submitRef = useRef<(() => void) | null>(null);

  const toggle = (val: string) => {
    if (multiple) {
      setSelected((prev) => prev.includes(val) ? prev.filter((v) => v !== val) : [...prev, val]);
    } else {
      // Single-select: auto-submit after a short delay so user sees the selection
      setSelected([val]);
      setTimeout(() => submitRef.current?.(), 150);
    }
  };

  const submit = () => {
    if (selected.length === 0) return;
    onSubmit(multiple ? selected : selected[0]);
  };
  submitRef.current = submit;

  // Enter key submits
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" && selected.length > 0 && segment.status === "pending") {
      e.preventDefault();
      submit();
    }
  }, [selected, segment.status]);

  return (
    <div className="space-y-3" tabIndex={0} onKeyDown={handleKeyDown}>
      {config.prompt && <WidgetPrompt text={config.prompt} />}
      <div className="space-y-1.5">
        {options.map((opt, i) => {
          const active = selected.includes(opt.value);
          return (
            <button
              key={i}
              onClick={() => toggle(opt.value)}
              disabled={segment.status !== "pending"}
              className={`w-full text-left px-3 py-2.5 rounded-lg border transition-all text-[12px] ${
                active
                  ? "border-[var(--accent)]/40 bg-[var(--accent)]/10 text-white/90"
                  : "border-white/8 bg-white/[0.02] text-white/60 hover:bg-white/[0.04] hover:border-white/12"
              } ${segment.status !== "pending" ? "opacity-60 cursor-default" : "cursor-pointer"}`}
            >
              <div className="flex items-center gap-2.5">
                <div className={`w-4 h-4 rounded-${multiple ? "sm" : "full"} border-2 flex items-center justify-center flex-shrink-0 transition-all ${
                  active ? "border-[var(--accent)] bg-[var(--accent)]" : "border-white/20"
                }`}>
                  {active && <Check size={10} className="text-black" />}
                </div>
                <div className="flex-1 min-w-0">
                  <span className="font-medium">{opt.label}</span>
                  {opt.description && (
                    <p className="text-[11px] text-white/40 mt-0.5">{opt.description}</p>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>
      {segment.status === "pending" && (
        <div className="flex gap-2 pt-1">
          <button onClick={submit} disabled={selected.length === 0}
            className="px-3.5 py-1.5 rounded-md text-[11px] font-medium bg-[var(--accent)]/20 text-[var(--accent)] hover:bg-[var(--accent)]/30 transition-colors disabled:opacity-30 disabled:cursor-default">
            Submit
          </button>
          <button onClick={onDismiss}
            className="px-3.5 py-1.5 rounded-md text-[11px] font-medium bg-white/5 text-white/40 hover:bg-white/8 transition-colors">
            Skip
          </button>
        </div>
      )}
      {segment.status === "submitted" && segment.response && (
        <div className="text-[11px] text-[var(--accent)]/60 font-mono flex items-center gap-1.5">
          <Check size={10} /> Answered: {Array.isArray(segment.response) ? segment.response.join(", ") : String(segment.response)}
        </div>
      )}
    </div>
  );
}

function CustomWidget({ segment, onSubmit, onDismiss }: WidgetProps) {
  const { config } = segment;
  const [raw, setRaw] = useState(
    typeof config.default_response === "string"
      ? config.default_response
      : JSON.stringify(config.default_response ?? {}, null, 2)
  );

  const submit = () => {
    const text = raw.trim();
    if (!text) {
      onSubmit("");
      return;
    }
    try {
      onSubmit(JSON.parse(text));
    } catch {
      onSubmit(text);
    }
  };

  if (Array.isArray(config.fields) && config.fields.length > 0) {
    // If custom widget provides form-like fields, reuse FormWidget rendering pipeline.
    return <FormWidget segment={{ ...segment, widgetType: "form" }} onSubmit={onSubmit} onDismiss={onDismiss} />;
  }

  return (
    <div className="space-y-3">
      {config.prompt && <WidgetPrompt text={config.prompt} className="text-[12px] text-white/70 leading-relaxed [&_p]:m-0 [&_strong]:text-white/80" />}
      <div className="rounded-lg border border-white/10 bg-black/30 overflow-hidden">
        <div className="px-3 py-1.5 border-b border-white/10 bg-white/[0.03] text-[10px] text-white/35 font-mono">
          Custom input payload (JSON or plain text)
        </div>
        <textarea
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          disabled={segment.status !== "pending"}
          className="w-full min-h-[120px] bg-black/35 px-3 py-2.5 text-[12px] text-white/75 font-mono outline-none resize-y"
          spellCheck={false}
        />
      </div>
      {segment.status === "pending" && (
        <div className="flex gap-2 pt-1">
          <button onClick={submit}
            className="px-3.5 py-1.5 rounded-md text-[11px] font-medium bg-[var(--accent)]/20 text-[var(--accent)] hover:bg-[var(--accent)]/30 transition-colors">
            Submit
          </button>
          <button onClick={onDismiss}
            className="px-3.5 py-1.5 rounded-md text-[11px] font-medium bg-white/5 text-white/40 hover:bg-white/8 transition-colors">
            Skip
          </button>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// SLIDER WIDGET — numeric adjustments
// ═══════════════════════════════════════════

interface SliderConfig {
  name: string;
  label: string;
  min: number;
  max: number;
  step: number;
  default: number;
  unit?: string;
}

function SliderWidget({ segment, onSubmit, onDismiss }: WidgetProps) {
  const { config } = segment;
  // Handle both array format {sliders: [...]} and flat format {min, max, step, default, label}
  const sliders: SliderConfig[] = config.sliders && Array.isArray(config.sliders) ? config.sliders
    : (typeof config.min === "number" && typeof config.max === "number")
      ? [{ name: config.name || "value", label: config.label || "Value", min: config.min, max: config.max, step: config.step ?? 1, default: config.default ?? config.min, unit: config.unit }]
      : [];
  const [values, setValues] = useState<Record<string, number>>(() => {
    const init: Record<string, number> = {};
    sliders.forEach((s) => { init[s.name] = s.default; });
    return init;
  });
  const [previewImg, setPreviewImg] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const previewTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const hasPreview = !!config.preview_code;

  const runPreview = useCallback(async (vals: Record<string, number>) => {
    if (!config.preview_code) return;
    setPreviewing(true);
    try {
      let code = config.preview_code as string;
      for (const [k, v] of Object.entries(vals)) {
        code = code.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
      }
      const resp = await fetch(`${getApiBase()}/api/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const data = await resp.json();
      if (data.images && data.images.length > 0) {
        setPreviewImg(data.images[0]);
      }
    } catch {
      // Preview failed silently
    } finally {
      setPreviewing(false);
    }
  }, [config.preview_code]);

  const updateVal = (name: string, val: number) => {
    setValues((prev) => {
      const next = { ...prev, [name]: val };
      // Debounced auto-preview on slider change
      if (hasPreview) {
        if (previewTimerRef.current) clearTimeout(previewTimerRef.current);
        previewTimerRef.current = setTimeout(() => runPreview(next), 400);
      }
      return next;
    });
  };

  return (
    <div className="space-y-3">
      {config.prompt && <WidgetPrompt text={config.prompt} />}
      {/* Preview image display */}
      {previewImg && (
        <div className="rounded-lg overflow-hidden border border-white/8 bg-black/30">
          <img src={previewImg} alt="Preview" className="w-full max-h-[300px] object-contain" />
          <div className="px-2 py-1 text-[9px] text-white/30 font-mono text-center">
            {previewing ? "Updating preview…" : "Preview — adjust sliders to update"}
          </div>
        </div>
      )}
      <div className="space-y-3">
        {sliders.map((s) => (
          <div key={s.name} className="space-y-1">
            <div className="flex items-center justify-between">
              <label className="text-[11px] text-white/50 font-medium">{s.label}</label>
              <span className="text-[11px] font-mono text-[var(--accent)]/70">
                {values[s.name]}{s.unit || ""}
              </span>
            </div>
            <input
              type="range"
              min={s.min}
              max={s.max}
              step={s.step}
              value={values[s.name]}
              onChange={(e) => updateVal(s.name, parseFloat(e.target.value))}
              disabled={segment.status !== "pending"}
              className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-slider"
              style={{
                background: segment.status === "pending"
                  ? `linear-gradient(to right, var(--accent) ${((values[s.name] - s.min) / (s.max - s.min)) * 100}%, rgba(255,255,255,0.08) ${((values[s.name] - s.min) / (s.max - s.min)) * 100}%)`
                  : "rgba(255,255,255,0.08)",
              }}
            />
            <div className="flex justify-between text-[9px] text-white/25 font-mono">
              <span>{s.min}{s.unit || ""}</span>
              <span>{s.max}{s.unit || ""}</span>
            </div>
          </div>
        ))}
      </div>
      {segment.status === "pending" && (
        <div className="flex gap-2 pt-1">
          {hasPreview && !previewImg && (
            <button onClick={() => runPreview(values)} disabled={previewing}
              className="px-3.5 py-1.5 rounded-md text-[11px] font-medium bg-white/5 text-white/50 hover:bg-white/8 transition-colors disabled:opacity-30">
              {previewing ? "Loading…" : "Preview"}
            </button>
          )}
          <button onClick={() => onSubmit(values)}
            className="px-3.5 py-1.5 rounded-md text-[11px] font-medium bg-[var(--accent)]/20 text-[var(--accent)] hover:bg-[var(--accent)]/30 transition-colors">
            Apply
          </button>
          <button onClick={onDismiss}
            className="px-3.5 py-1.5 rounded-md text-[11px] font-medium bg-white/5 text-white/40 hover:bg-white/8 transition-colors">
            Skip
          </button>
        </div>
      )}
      {segment.status === "submitted" && (
        <div className="text-[11px] text-[var(--accent)]/60 font-mono flex items-center gap-1.5">
          <Check size={10} /> Applied: {Object.entries(segment.response || values).map(([k, v]) => `${k}=${v}`).join(", ")}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// EDITOR WIDGET — split-pane markdown editor + preview
// ═══════════════════════════════════════════

interface InlineComment {
  id: string;
  selectedText: string;
  startOffset: number;
  endOffset: number;
  comment: string;
}

type EditorView = "edit" | "preview" | "split";

function EditorWidget({ segment, onSubmit, onDismiss, onFinalize }: WidgetProps) {
  const { config } = segment;
  const content = config.content || "";
  const language = config.language || "text";
  const title = config.title || config.filename || "Untitled Draft";

  const handleRefine = (payload: string) => {
    onSubmit({ edited_content: payload, changed: payload !== content });
  };

  const handleFinalize = () => {
    onFinalize?.({ finalized: true });
  };

  return (
    <div className="space-y-3">
      {config.prompt && <WidgetPrompt text={config.prompt} className="text-[12px] text-white/70 font-medium leading-relaxed [&_p]:m-0 [&_strong]:text-white/80" />}
      
      <DraftContext.Provider value={{ onRefine: handleRefine, onFinalize: handleFinalize }}>
        <DraftBlock content={content} language={language} draftId={segment.persistentId} />
      </DraftContext.Provider>

      {segment.status === "pending" && (
        <div className="flex gap-2 justify-end mt-2">
          <button onClick={onDismiss}
            className="px-3.5 py-1.5 rounded-md text-[11px] font-medium bg-white/5 text-white/40 hover:bg-white/8 transition-colors">
            Skip
          </button>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// OUTLINE WIDGET — Notion-style sortable blocks
// ═══════════════════════════════════════════

interface OutlineBlock {
  id: string;
  text: string;
  description?: string;
}

function OutlineWidget({ segment, onSubmit, onDismiss }: WidgetProps) {
  const { config } = segment;
  const [blocks, setBlocks] = useState<OutlineBlock[]>(() => {
    const items = config.items || config.blocks || config.sections || [];
    return items.map((item: any, i: number) => ({
      id: `block_${i}`,
      text: typeof item === "string" ? item : (item.title || item.label || item.text || ""),
      description: typeof item === "string" ? undefined : (item.description || item.desc),
    }));
  });
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);
  const [newBlockText, setNewBlockText] = useState("");

  const isEditable = segment.status === "pending" || segment.status === "active";

  const startEdit = (block: OutlineBlock) => {
    setEditingId(block.id);
    setEditText(block.text);
    setEditDesc(block.description || "");
  };

  const confirmEdit = () => {
    if (!editingId || !editText.trim()) return;
    setBlocks(prev => prev.map(b => b.id === editingId ? { ...b, text: editText.trim(), description: editDesc.trim() || undefined } : b));
    setEditingId(null);
  };

  const deleteBlock = (id: string) => {
    setBlocks(prev => prev.filter(b => b.id !== id));
  };

  const addBlock = () => {
    if (!newBlockText.trim()) return;
    setBlocks(prev => [...prev, { id: `block_${Date.now()}`, text: newBlockText.trim() }]);
    setNewBlockText("");
  };

  // Drag and drop reordering
  const handleDragStart = (idx: number) => {
    setDragIdx(idx);
  };

  const handleDragOver = (e: React.DragEvent, idx: number) => {
    e.preventDefault();
    setDragOverIdx(idx);
  };

  const handleDrop = (idx: number) => {
    if (dragIdx === null || dragIdx === idx) {
      setDragIdx(null);
      setDragOverIdx(null);
      return;
    }
    setBlocks(prev => {
      const next = [...prev];
      const [moved] = next.splice(dragIdx, 1);
      next.splice(idx, 0, moved);
      return next;
    });
    setDragIdx(null);
    setDragOverIdx(null);
  };

  const moveBlock = (idx: number, dir: -1 | 1) => {
    const target = idx + dir;
    if (target < 0 || target >= blocks.length) return;
    setBlocks(prev => {
      const next = [...prev];
      [next[idx], next[target]] = [next[target], next[idx]];
      return next;
    });
  };

  const submit = () => {
    onSubmit({
      blocks: blocks.map((b, i) => ({ index: i, title: b.text, description: b.description })),
      action: "approve",
    });
  };

  return (
    <div className="space-y-3">
      {config.prompt && <WidgetPrompt text={config.prompt} />}
      <div className="space-y-1">
        {blocks.map((block, idx) => (
          <div
            key={block.id}
            draggable={isEditable && editingId !== block.id}
            onDragStart={() => handleDragStart(idx)}
            onDragOver={(e) => handleDragOver(e, idx)}
            onDragEnd={() => { setDragIdx(null); setDragOverIdx(null); }}
            onDrop={() => handleDrop(idx)}
            className={`group rounded-lg border transition-all ${
              dragOverIdx === idx && dragIdx !== idx
                ? "border-[var(--accent)]/40 bg-[var(--accent)]/5"
                : dragIdx === idx
                  ? "border-white/20 opacity-50"
                  : "border-white/8 bg-white/[0.02] hover:border-white/12"
            }`}
          >
            {editingId === block.id ? (
              <div className="p-2.5 space-y-2">
                <input
                  type="text"
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") confirmEdit(); if (e.key === "Escape") setEditingId(null); }}
                  className="w-full bg-black/30 border border-white/10 rounded-md px-2.5 py-1.5 text-[12px] text-white/80 outline-none focus:border-[var(--accent)]/30"
                  autoFocus
                  placeholder="Section title"
                />
                <input
                  type="text"
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") confirmEdit(); if (e.key === "Escape") setEditingId(null); }}
                  className="w-full bg-black/30 border border-white/10 rounded-md px-2.5 py-1.5 text-[11px] text-white/50 outline-none focus:border-[var(--accent)]/30"
                  placeholder="Description (optional)"
                />
                <div className="flex gap-1.5">
                  <button onClick={confirmEdit}
                    className="px-2.5 py-1 rounded-md text-[10px] font-medium bg-[var(--accent)]/20 text-[var(--accent)] hover:bg-[var(--accent)]/30 transition-colors">
                    Save
                  </button>
                  <button onClick={() => setEditingId(null)}
                    className="px-2.5 py-1 rounded-md text-[10px] font-medium bg-white/5 text-white/40 hover:bg-white/8 transition-colors">
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2 px-2.5 py-2">
                {/* Drag handle */}
                {isEditable && (
                  <div className="cursor-grab active:cursor-grabbing text-white/15 group-hover:text-white/30 transition-colors select-none shrink-0"
                    title="Drag to reorder">
                    <svg width="10" height="14" viewBox="0 0 10 14" fill="currentColor">
                      <circle cx="2" cy="2" r="1.5" /><circle cx="8" cy="2" r="1.5" />
                      <circle cx="2" cy="7" r="1.5" /><circle cx="8" cy="7" r="1.5" />
                      <circle cx="2" cy="12" r="1.5" /><circle cx="8" cy="12" r="1.5" />
                    </svg>
                  </div>
                )}
                {/* Number */}
                <span className="text-[11px] font-mono text-[var(--accent)]/50 w-5 text-center shrink-0">{idx + 1}</span>
                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="text-[12px] text-white/80 font-medium">{block.text}</div>
                  {block.description && (
                    <div className="text-[11px] text-white/40 mt-0.5">{block.description}</div>
                  )}
                </div>
                {/* Actions */}
                {isEditable && (
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                    {idx > 0 && (
                      <button onClick={() => moveBlock(idx, -1)} title="Move up"
                        className="p-1 rounded text-white/25 hover:text-white/60 hover:bg-white/5 transition-colors">
                        <ChevronDown size={10} className="rotate-180" />
                      </button>
                    )}
                    {idx < blocks.length - 1 && (
                      <button onClick={() => moveBlock(idx, 1)} title="Move down"
                        className="p-1 rounded text-white/25 hover:text-white/60 hover:bg-white/5 transition-colors">
                        <ChevronDown size={10} />
                      </button>
                    )}
                    <button onClick={() => startEdit(block)} title="Edit"
                      className="p-1 rounded text-white/25 hover:text-[var(--accent)] hover:bg-[var(--accent)]/10 transition-colors">
                      <Edit3 size={10} />
                    </button>
                    <button onClick={() => deleteBlock(block.id)} title="Remove"
                      className="p-1 rounded text-white/25 hover:text-red-400 hover:bg-red-500/10 transition-colors">
                      <X size={10} />
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Add new block */}
      {isEditable && (
        <div className="flex gap-1.5">
          <input
            type="text"
            value={newBlockText}
            onChange={(e) => setNewBlockText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") addBlock(); }}
            placeholder="Add a section…"
            className="flex-1 bg-black/20 border border-white/8 border-dashed rounded-lg px-2.5 py-1.5 text-[12px] text-white/60 placeholder:text-white/20 outline-none focus:border-[var(--accent)]/30 transition-colors"
          />
          <button onClick={addBlock} disabled={!newBlockText.trim()}
            className="px-2.5 py-1.5 rounded-lg text-[10px] font-medium bg-white/5 text-white/40 hover:bg-white/8 disabled:opacity-30 transition-colors shrink-0">
            + Add
          </button>
        </div>
      )}

      {/* Submit / Skip */}
      {isEditable && (
        <div className="flex gap-2 pt-1">
          <button onClick={submit} disabled={blocks.length === 0}
            className="px-3.5 py-1.5 rounded-md text-[11px] font-medium bg-[var(--accent)]/20 text-[var(--accent)] hover:bg-[var(--accent)]/30 transition-colors disabled:opacity-30 flex items-center gap-1.5">
            <Check size={10} /> Approve Outline
          </button>
          <button onClick={() => onSubmit({ blocks: blocks.map((b, i) => ({ index: i, title: b.text, description: b.description })), action: "revise" })}
            className="px-3.5 py-1.5 rounded-md text-[11px] font-medium bg-white/5 text-white/40 hover:bg-white/8 transition-colors">
            Request Revisions
          </button>
          <button onClick={onDismiss}
            className="px-3.5 py-1.5 rounded-md text-[11px] font-medium bg-white/5 text-white/30 hover:bg-white/8 transition-colors">
            Skip
          </button>
        </div>
      )}
      {segment.status === "submitted" && (
        <div className="text-[11px] text-[var(--accent)]/60 font-mono flex items-center gap-1.5">
          <Check size={10} /> Outline {segment.response?.action === "approve" ? "approved" : "submitted"} — {blocks.length} sections
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// FORM WIDGET — structured fields
// ═══════════════════════════════════════════

interface FormField {
  name: string;
  label: string;
  type: "text" | "number" | "select" | "toggle" | "textarea" | string; // Catch-all for unknown types from model
  options?: Array<string | number | { label?: string; value?: string | number }>;
  default?: any;
}

function normalizeSelectOption(opt: string | number | { label?: string; value?: string | number }, index: number) {
  if (typeof opt === "object" && opt !== null) {
    const valueRaw = opt.value ?? opt.label ?? "";
    const labelRaw = opt.label ?? opt.value ?? "";
    const value = String(valueRaw);
    const label = String(labelRaw);
    return {
      key: `${value}-${index}`,
      value,
      label,
    };
  }
  const value = String(opt);
  return {
    key: `${value}-${index}`,
    value,
    label: value,
  };
}

// Normalize raw model fields into well-formed FormFields with guaranteed
// unique names, labels, and types.  This is the ROOT fix for:
//  - shared-state bug (model omits `name` → all fields map to values[undefined])
//  - duplicate React key warning (all keys were undefined)
function normalizeFormFields(rawFields: any[]): FormField[] {
  const valid = rawFields.filter(
    (f) => f && typeof f === "object" && Object.keys(f).length > 0
  );
  const seen = new Map<string, number>();
  return valid.map((f, idx) => {
    // Derive name: prefer explicit name/id/key/field, else slugify label, else index
    let name: string =
      f.name || f.id || f.key || f.field || "";
    if (!name && f.label) {
      name = String(f.label)
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_|_$/g, "");
    }
    if (!name) {
      name = `field_${idx}`;
    }
    // Ensure uniqueness
    const count = seen.get(name) || 0;
    seen.set(name, count + 1);
    if (count > 0) name = `${name}_${count}`;

    return {
      name,
      label: f.label || f.name || `Field ${idx + 1}`,
      type: f.type || "text",
      options: f.options,
      default: f.default ?? f.defaultValue ?? f.value,
    };
  });
}

function FormWidget({ segment, onSubmit, onDismiss }: WidgetProps) {
  const { config } = segment;
  const rawFields: any[] = Array.isArray(config.fields) ? config.fields : [];

  // Stable normalized fields — computed once from config, never changes.
  // useMemo avoids re-normalizing on every render (which would lose state).
  const fields = React.useMemo<FormField[]>(() => {
    const normalized = normalizeFormFields(rawFields);
    if (normalized.length > 0) return normalized;
    // Graceful fallback: model called "form" but provided no valid fields
    return [{
      name: "response",
      label: config.prompt || "Input required (model provided no fields)",
      type: "textarea",
    }];
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [segment.widgetId]);

  const [values, setValues] = useState<Record<string, any>>(() => {
    // Restore submitted values when widget is already finalized (e.g. chat reload)
    if (segment.status === "submitted" && segment.response && typeof segment.response === "object") {
      const restored: Record<string, any> = {};
      fields.forEach((f) => {
        restored[f.name] = (segment.response as Record<string, any>)[f.name] ?? "";
      });
      return restored;
    }
    const init: Record<string, any> = {};
    fields.forEach((f) => {
      if (f.default !== undefined && f.default !== null) {
        init[f.name] = f.default;
      } else if (f.type === "toggle") {
        init[f.name] = false;
      } else if (f.type === "number") {
        init[f.name] = 0;
      } else if (f.type === "select" && f.options && f.options.length > 0) {
        const first = f.options[0];
        init[f.name] = typeof first === "object" && first !== null
          ? String((first as any).value ?? (first as any).label ?? "")
          : String(first);
      } else {
        init[f.name] = "";
      }
    });
    return init;
  });

  const updateField = (name: string, val: any) => {
    setValues((prev) => ({ ...prev, [name]: val }));
  };

  // Suppress verbose markdown prompt when fields already describe the same info.
  const hasRealFields = rawFields.length > 0;
  const promptTitle = React.useMemo(() => {
    if (!config.prompt) return null;
    if (!hasRealFields) return config.prompt;
    const firstLine = config.prompt.split('\n')[0].replace(/[:：]\s*$/, '').trim();
    if (config.prompt.length < 80) return config.prompt;
    return firstLine || null;
  }, [config.prompt, hasRealFields]);

  return (
    <div className="space-y-3">
      {promptTitle && <WidgetPrompt text={promptTitle} />}
      <div className="space-y-2.5">
        {fields.map((f) => (
          <div key={f.name} className="space-y-1">
            <label className="text-[11px] text-white/50 font-medium">{f.label}</label>
            {(f.type === "text" || (f.type !== "number" && f.type !== "select" && f.type !== "toggle" && f.type !== "textarea")) && (
              <input
                type="text"
                value={values[f.name] || ""}
                onChange={(e) => updateField(f.name, e.target.value)}
                disabled={segment.status !== "pending"}
                className="w-full bg-black/30 border border-white/8 rounded-md px-2.5 py-1.5 text-[12px] text-white/70 outline-none focus:border-[var(--accent)]/30 transition-colors"
              />
            )}
            {f.type === "textarea" && (
              <textarea
                value={values[f.name] || ""}
                onChange={(e) => updateField(f.name, e.target.value)}
                disabled={segment.status !== "pending"}
                className="w-full bg-black/30 border border-white/8 rounded-md px-2.5 py-1.5 text-[12px] text-white/70 outline-none focus:border-[var(--accent)]/30 transition-colors resize-y min-h-[60px]"
                rows={3}
              />
            )}
            {f.type === "number" && (
              <input
                type="number"
                value={values[f.name] || 0}
                onChange={(e) => updateField(f.name, parseFloat(e.target.value) || 0)}
                disabled={segment.status !== "pending"}
                className="w-full bg-black/30 border border-white/8 rounded-md px-2.5 py-1.5 text-[12px] text-white/70 font-mono outline-none focus:border-[var(--accent)]/30 transition-colors"
              />
            )}
            {f.type === "select" && f.options && (
              <div className="relative">
                <select
                  value={String(values[f.name] ?? "")}
                  onChange={(e) => updateField(f.name, e.target.value)}
                  disabled={segment.status !== "pending"}
                  className="w-full bg-black/30 border border-white/8 rounded-md px-2.5 py-1.5 text-[12px] text-white/70 outline-none appearance-none focus:border-[var(--accent)]/30 transition-colors"
                >
                  {f.options.map((o, idx) => {
                    const normalized = normalizeSelectOption(o, idx);
                    return (
                      <option key={normalized.key} value={normalized.value} className="bg-[#1a1a2e] text-white">
                        {normalized.label}
                      </option>
                    );
                  })}
                </select>
                <ChevronDown size={10} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-white/25 pointer-events-none" />
              </div>
            )}
            {f.type === "toggle" && (
              <button
                onClick={() => updateField(f.name, !values[f.name])}
                disabled={segment.status !== "pending"}
                className={`w-10 h-5 rounded-full transition-all relative ${
                  values[f.name] ? "bg-[var(--accent)]/30" : "bg-white/8"
                }`}
              >
                <div className={`w-4 h-4 rounded-full absolute top-0.5 transition-all ${
                  values[f.name] ? "left-5 bg-[var(--accent)]" : "left-0.5 bg-white/30"
                }`} />
              </button>
            )}
          </div>
        ))}
      </div>
      {segment.status === "pending" && (
        <div className="flex gap-2 pt-1">
          <button onClick={() => onSubmit(values)}
            className="px-3.5 py-1.5 rounded-md text-[11px] font-medium bg-[var(--accent)]/20 text-[var(--accent)] hover:bg-[var(--accent)]/30 transition-colors">
            Submit
          </button>
          <button onClick={onDismiss}
            className="px-3.5 py-1.5 rounded-md text-[11px] font-medium bg-white/5 text-white/40 hover:bg-white/8 transition-colors">
            Skip
          </button>
        </div>
      )}
      {segment.status === "submitted" && (
        <div className="space-y-1.5 pt-1">
          <div className="text-[11px] text-[var(--accent)]/60 font-mono flex items-center gap-1.5 mb-1.5">
            <Check size={10} /> Form submitted
          </div>
          {fields.map((f) => {
            const val = values[f.name];
            if (val === undefined || val === null || val === "") return null;
            return (
              <div key={f.name} className="flex items-baseline gap-2 text-[11px]">
                <span className="text-white/35 font-medium shrink-0">{f.label}:</span>
                <span className="text-white/70">{f.type === "toggle" ? (val ? "Yes" : "No") : String(val)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// EMBED WIDGET — YouTube, iframes
// ═══════════════════════════════════════════

function EmbedWidget({ segment }: WidgetProps) {
  const { config } = segment;
  const url = config.url || "";
  const title = config.title || "Embedded Content";
  const embedType = config.embed_type || config.type || "iframe";

  if (embedType === "progress") {
    return <ProgressWidget config={config as any} />;
  }

  // Convert YouTube URLs to embed URLs
  const getEmbedUrl = (rawUrl: string): string => {
    const ytMatch = rawUrl.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]+)/);
    if (ytMatch) return `https://www.youtube.com/embed/${ytMatch[1]}`;
    return rawUrl;
  };

  const isYouTube = embedType === "youtube" || /youtube\.com|youtu\.be/.test(url);
  const embedUrl = getEmbedUrl(url);

  return (
    <div className="space-y-2">
      {title && (
        <div className="flex items-center gap-2">
          <ExternalLink size={12} className="text-white/30" />
          <span className="text-[12px] text-white/60 font-medium">{title}</span>
        </div>
      )}
      <div className="rounded-lg overflow-hidden border border-white/8" style={{ background: "#0d1117" }}>
        <iframe
          src={embedUrl}
          className="w-full rounded-lg"
          style={{ height: isYouTube ? 315 : 400, border: "none" }}
          title={title}
          allow={isYouTube ? "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" : ""}
          allowFullScreen={isYouTube}
          sandbox={isYouTube ? "allow-scripts allow-same-origin allow-popups" : "allow-scripts"}
        />
      </div>
      {url && (
        <a href={url} target="_blank" rel="noopener noreferrer"
          className="text-[10px] text-white/25 hover:text-white/40 transition-colors font-mono truncate block">
          {url}
        </a>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// DIFF WIDGET — code review with accept/reject per change
// ═══════════════════════════════════════════

interface DiffChange {
  id: string;
  label: string;
  original: string;
  proposed: string;
}

function DiffWidget({ segment, onSubmit, onDismiss, onFinalize }: WidgetProps) {
  const { config } = segment;
  const changes: DiffChange[] = config.changes || [];
  const [decisions, setDecisions] = useState<Record<string, { action: string; edited_text?: string; comment?: string }>>({});
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [commentingId, setCommentingId] = useState<string | null>(null);
  const [commentText, setCommentText] = useState("");
  const commentInputRef = useRef<HTMLInputElement>(null);
  const prevRevisionRef = useRef(segment.revision || 1);
  const isPersistent = !!segment.persistentId;

  // Reset decisions when the agent updates the diff (new revision via persistent widget)
  useEffect(() => {
    const newRev = segment.revision || 1;
    if (newRev > prevRevisionRef.current) {
      setDecisions({});
      setEditingId(null);
      setCommentingId(null);
      prevRevisionRef.current = newRev;
    }
  }, [segment.revision]);

  const allDecided = changes.length > 0 && changes.every(c => decisions[c.id]);

  const decide = (id: string, action: "accepted" | "rejected") => {
    setDecisions(prev => ({ ...prev, [id]: { ...prev[id], action } }));
    if (editingId === id) setEditingId(null);
  };

  const startEdit = (c: DiffChange) => {
    setEditingId(c.id);
    setEditText(c.proposed);
    setCommentingId(null);
  };

  const confirmEdit = (id: string) => {
    setDecisions(prev => ({ ...prev, [id]: { ...prev[id], action: "edited", edited_text: editText } }));
    setEditingId(null);
  };

  const startComment = (c: DiffChange) => {
    setCommentingId(c.id);
    setCommentText(decisions[c.id]?.comment || "");
    setEditingId(null);
    setTimeout(() => commentInputRef.current?.focus(), 50);
  };

  const confirmComment = (id: string) => {
    if (commentText.trim()) {
      setDecisions(prev => {
        const existing = prev[id] || { action: "rejected" };
        return { ...prev, [id]: { ...existing, comment: commentText.trim() } };
      });
    }
    setCommentingId(null);
    setCommentText("");
  };

  const acceptAll = () => {
    const all: typeof decisions = {};
    changes.forEach(c => { all[c.id] = { action: "accepted" }; });
    setDecisions(all);
  };

  const rejectAll = () => {
    const all: typeof decisions = {};
    changes.forEach(c => { all[c.id] = { action: "rejected" }; });
    setDecisions(all);
  };

  const submit = () => {
    onSubmit({ decisions });
  };

  const renderDiffLines = (original: string, proposed: string) => {
    const origLines = original.split("\n");
    const propLines = proposed.split("\n");
    const lines: { text: string; type: "remove" | "add" | "same" }[] = [];
    const maxLen = Math.max(origLines.length, propLines.length);
    // Simple line-by-line diff
    let oi = 0, pi = 0;
    while (oi < origLines.length || pi < propLines.length) {
      if (oi < origLines.length && pi < propLines.length && origLines[oi] === propLines[pi]) {
        lines.push({ text: origLines[oi], type: "same" });
        oi++; pi++;
      } else {
        if (oi < origLines.length) {
          lines.push({ text: origLines[oi], type: "remove" });
          oi++;
        }
        if (pi < propLines.length) {
          lines.push({ text: propLines[pi], type: "add" });
          pi++;
        }
      }
    }
    return lines;
  };

  const isPending = segment.status === "pending" || segment.status === "active";

  return (
    <div className="space-y-3">
      {config.prompt && <WidgetPrompt text={config.prompt} className="text-[12px] text-white/70 font-medium leading-relaxed [&_p]:m-0 [&_strong]:text-white/80" />}
      {config.file_path && (
        <div className="text-[10px] font-mono text-white/40 flex items-center gap-1.5">
          <FileEdit size={10} /> {config.file_path}
        </div>
      )}

      {/* Context before */}
      {config.context_before && (
        <pre className="text-[11px] font-mono text-white/25 bg-black/20 px-3 py-1.5 rounded-md overflow-x-auto">{config.context_before}</pre>
      )}

      {/* Empty changes fallback */}
      {changes.length === 0 && (
        <div className="rounded-lg border border-white/10 bg-black/20 px-4 py-6 text-center">
          <p className="text-[12px] text-white/40">No changes proposed yet.</p>
          <p className="text-[10px] text-white/25 mt-1">The agent will update this widget with specific changes to review.</p>
        </div>
      )}

      {/* Changes */}
      {changes.map((c) => {
        const decision = decisions[c.id];
        const diffLines = renderDiffLines(c.original, c.proposed);
        const isEditing = editingId === c.id;

        return (
          <div key={c.id} className={`rounded-lg border overflow-hidden transition-all ${
            decision?.action === "accepted" ? "border-emerald-500/30 bg-emerald-500/5"
            : decision?.action === "rejected" ? "border-red-500/20 bg-red-500/5 opacity-60"
            : decision?.action === "edited" ? "border-blue-400/30 bg-blue-400/5"
            : "border-white/10 bg-black/30"
          }`}>
            {/* Change header */}
            <div className="px-3 py-1.5 border-b border-white/8 bg-white/[0.02] flex items-center justify-between">
              <span className="text-[10px] font-mono text-white/45">{c.label}</span>
              {decision && (
                <span className={`text-[10px] font-medium ${
                  decision.action === "accepted" ? "text-emerald-400" : decision.action === "rejected" ? "text-red-400" : "text-blue-400"
                }`}>
                  {decision.action === "accepted" ? "✓ Accepted" : decision.action === "rejected" ? "✗ Rejected" : "✎ Edited"}
                </span>
              )}
            </div>

            {/* Diff view */}
            <div className="px-3 py-2 font-mono text-[11px] overflow-x-auto whitespace-pre-wrap">
              {diffLines.map((line, i) => (
                <div key={i} className={`leading-[1.6] ${
                  line.type === "remove" ? "text-red-400/70 bg-red-500/5" :
                  line.type === "add" ? "text-emerald-400/80 bg-emerald-500/5" :
                  "text-white/35"
                }`}>
                  <span className="inline-block w-4 text-right mr-2 text-white/15 select-none shrink-0">
                    {line.type === "remove" ? "-" : line.type === "add" ? "+" : " "}
                  </span>
                  <span className="break-words">{line.text || " "}</span>
                </div>
              ))}
            </div>

            {/* Edit mode */}
            {isEditing && (
              <div className="px-3 pb-2">
                <textarea
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  className="w-full bg-black/40 border border-blue-400/20 rounded-md px-3 py-2 text-[11px] font-mono text-blue-300/80 outline-none resize-y min-h-[80px]"
                  spellCheck={false}
                />
                <div className="flex gap-2 pt-1.5">
                  <button onClick={() => confirmEdit(c.id)}
                    className="px-2.5 py-1 rounded-md text-[10px] font-medium bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 transition-colors">
                    Confirm Edit
                  </button>
                  <button onClick={() => setEditingId(null)}
                    className="px-2.5 py-1 rounded-md text-[10px] font-medium bg-white/5 text-white/40 hover:bg-white/8 transition-colors">
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {/* Comment mode */}
            {commentingId === c.id && (
              <div className="px-3 pb-2">
                <div className="flex gap-1.5">
                  <input
                    ref={commentInputRef}
                    type="text"
                    value={commentText}
                    onChange={(e) => setCommentText(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") confirmComment(c.id); if (e.key === "Escape") setCommentingId(null); }}
                    placeholder="What should change here instead?"
                    className="flex-1 bg-black/40 border border-[var(--accent)]/20 rounded-md px-2.5 py-1.5 text-[11px] text-white/80 placeholder:text-white/25 outline-none focus:border-[var(--accent)]/30 font-mono"
                  />
                  <button onClick={() => confirmComment(c.id)}
                    disabled={!commentText.trim()}
                    className="px-2.5 py-1.5 rounded-md text-[10px] font-medium bg-[var(--accent)]/20 text-[var(--accent)] hover:bg-[var(--accent)]/30 disabled:opacity-30 transition-colors shrink-0">
                    Add
                  </button>
                  <button onClick={() => setCommentingId(null)}
                    className="px-1.5 py-1.5 rounded-md text-white/30 hover:text-white/60 hover:bg-white/5 transition-colors shrink-0">
                    <X size={12} />
                  </button>
                </div>
              </div>
            )}

            {/* Show existing comment on a change */}
            {decision?.comment && commentingId !== c.id && (
              <div className="px-3 pb-2">
                <div className="text-[10px] text-[var(--accent)]/70 bg-[var(--accent)]/5 border border-[var(--accent)]/10 rounded-md px-2.5 py-1.5 flex items-start gap-1.5">
                  <Edit3 size={9} className="shrink-0 mt-0.5" />
                  <span>{decision.comment}</span>
                </div>
              </div>
            )}

            {/* Per-change actions */}
            {isPending && !decision && !isEditing && commentingId !== c.id && (
              <div className="px-3 py-1.5 border-t border-white/5 flex gap-1.5">
                <button onClick={() => decide(c.id, "accepted")}
                  className="px-2.5 py-1 rounded-md text-[10px] font-medium bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 transition-colors flex items-center gap-1">
                  <CheckCircle size={10} /> Accept
                </button>
                <button onClick={() => decide(c.id, "rejected")}
                  className="px-2.5 py-1 rounded-md text-[10px] font-medium bg-red-500/10 text-red-400/80 hover:bg-red-500/20 transition-colors flex items-center gap-1">
                  <XCircle size={10} /> Reject
                </button>
                <button onClick={() => startEdit(c)}
                  className="px-2.5 py-1 rounded-md text-[10px] font-medium bg-white/5 text-white/50 hover:bg-white/8 transition-colors flex items-center gap-1">
                  <Edit3 size={10} /> Edit
                </button>
                <button onClick={() => startComment(c)}
                  className="px-2.5 py-1 rounded-md text-[10px] font-medium bg-[var(--accent)]/10 text-[var(--accent)]/80 hover:bg-[var(--accent)]/20 transition-colors flex items-center gap-1">
                  <Edit3 size={10} /> Comment
                </button>
              </div>
            )}
          </div>
        );
      })}

      {/* Context after */}
      {config.context_after && (
        <pre className="text-[11px] font-mono text-white/25 bg-black/20 px-3 py-1.5 rounded-md overflow-x-auto">{config.context_after}</pre>
      )}

      {/* Bulk actions and submit */}
      {isPending && (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <button onClick={acceptAll}
            className="px-3 py-1.5 rounded-md text-[10px] font-medium bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 active:bg-emerald-500/30 transition-colors">
            Accept All
          </button>
          <button onClick={rejectAll}
            className="px-3 py-1.5 rounded-md text-[10px] font-medium bg-red-500/10 text-red-400/80 hover:bg-red-500/20 active:bg-red-500/25 transition-colors">
            Reject All
          </button>
          <div className="flex-1 min-w-[20px]" />
          {allDecided && (
            <>
              <button onClick={submit}
                className="px-3.5 py-1.5 rounded-md text-[11px] font-medium bg-[var(--accent)]/20 text-[var(--accent)] hover:bg-[var(--accent)]/30 transition-colors flex items-center gap-1.5">
                <Send size={10} /> {isPersistent ? "Submit Review" : "Submit Review"}
              </button>
              {isPersistent && onFinalize && (
                <button onClick={() => onFinalize({ decisions })}
                  className="px-3.5 py-1.5 rounded-md text-[11px] font-medium bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 transition-colors flex items-center gap-1.5">
                  <CheckCircle size={10} /> Accept & Finalize
                </button>
              )}
            </>
          )}
          <button onClick={onDismiss}
            className="px-3 py-1.5 rounded-md text-[10px] font-medium bg-white/5 text-white/40 hover:bg-white/8 transition-colors">
            Skip
          </button>
        </div>
      )}
      {segment.status === "active" && isPersistent && (
        <div className="text-[11px] text-[var(--accent)]/60 font-mono flex items-center gap-1.5 animate-pulse">
          <Check size={10} /> Review sent — awaiting agent&apos;s updated proposal…
        </div>
      )}
      {segment.status === "submitted" && segment.response && (
        <div className="text-[11px] text-[var(--accent)]/60 font-mono flex items-center gap-1.5">
          <Check size={10} /> Review finalized — {Object.values(segment.response.decisions || {}).filter((d: any) => d.action === "accepted").length} accepted, {Object.values(segment.response.decisions || {}).filter((d: any) => d.action === "rejected").length} rejected
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// CROP WIDGET — visual crop region selector
// ═══════════════════════════════════════════

function CropWidget({ segment, onSubmit, onDismiss }: WidgetProps) {
  const { config } = segment;
  const imageUrl = config.image_url || "";
  const ratios: string[] = config.aspect_ratios || ["free", "1:1", "4:3", "16:9"];
  const [selectedRatio, setSelectedRatio] = useState(config.default_ratio || "free");
  const [crop, setCrop] = useState({ left: 10, top: 10, right: 90, bottom: 90 }); // percentages
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef<string | null>(null);
  const startPos = useRef({ x: 0, y: 0 });
  const startCrop = useRef(crop);

  const handlePointerDown = useCallback((edge: string, e: React.PointerEvent) => {
    dragging.current = edge;
    startPos.current = { x: e.clientX, y: e.clientY };
    startCrop.current = { ...crop };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }, [crop]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const dx = ((e.clientX - startPos.current.x) / rect.width) * 100;
    const dy = ((e.clientY - startPos.current.y) / rect.height) * 100;
    const s = startCrop.current;
    const next = { ...s };
    const edge = dragging.current;
    if (edge.includes("l")) next.left = Math.max(0, Math.min(s.left + dx, next.right - 5));
    if (edge.includes("r")) next.right = Math.max(next.left + 5, Math.min(100, s.right + dx));
    if (edge.includes("t")) next.top = Math.max(0, Math.min(s.top + dy, next.bottom - 5));
    if (edge.includes("b")) next.bottom = Math.max(next.top + 5, Math.min(100, s.bottom + dy));
    if (edge === "move") {
      const w = s.right - s.left, h = s.bottom - s.top;
      let nl = s.left + dx, nt = s.top + dy;
      nl = Math.max(0, Math.min(100 - w, nl));
      nt = Math.max(0, Math.min(100 - h, nt));
      next.left = nl; next.top = nt; next.right = nl + w; next.bottom = nt + h;
    }
    setCrop(next);
  }, []);

  const handlePointerUp = useCallback(() => { dragging.current = null; }, []);

  return (
    <div className="space-y-3">
      {config.prompt && <WidgetPrompt text={config.prompt} />}
      {/* Aspect ratio selector */}
      <div className="flex gap-1.5">
        {ratios.map((r) => (
          <button key={r} onClick={() => setSelectedRatio(r)}
            className={`px-2 py-1 rounded text-[10px] font-mono transition-colors ${selectedRatio === r ? "bg-[var(--accent)]/20 text-[var(--accent)]" : "bg-white/5 text-white/40 hover:text-white/60"}`}
          >{r}</button>
        ))}
      </div>
      {/* Image with crop overlay */}
      {imageUrl && (
        <div ref={containerRef} className="relative rounded-lg overflow-hidden border border-white/10"
          onPointerMove={handlePointerMove} onPointerUp={handlePointerUp}
        >
          <img src={imageUrl} alt="Crop" className="w-full" draggable={false} />
          {/* Dim outside crop */}
          <div className="absolute inset-0 pointer-events-none" style={{
            background: `linear-gradient(to right, rgba(0,0,0,0.6) ${crop.left}%, transparent ${crop.left}%, transparent ${crop.right}%, rgba(0,0,0,0.6) ${crop.right}%)`
          }} />
          {/* Crop handles */}
          <div className="absolute border-2 border-dashed border-white/60 cursor-move"
            style={{ left: `${crop.left}%`, top: `${crop.top}%`, width: `${crop.right - crop.left}%`, height: `${crop.bottom - crop.top}%` }}
            onPointerDown={(e) => handlePointerDown("move", e)}
          >
            {/* Corner handles */}
            {[["tl","top-0 left-0 cursor-nwse-resize"], ["tr","top-0 right-0 cursor-nesw-resize"], ["bl","bottom-0 left-0 cursor-nesw-resize"], ["br","bottom-0 right-0 cursor-nwse-resize"]].map(([id, cls]) => (
              <div key={id} className={`absolute w-3 h-3 bg-white rounded-sm -translate-x-1/2 -translate-y-1/2 ${cls}`}
                onPointerDown={(e) => { e.stopPropagation(); handlePointerDown(id, e); }} />
            ))}
          </div>
          {/* Dimension readout */}
          <div className="absolute bottom-2 right-2 px-2 py-1 bg-black/70 rounded text-[10px] text-white/70 font-mono">
            {Math.round(crop.right - crop.left)}% × {Math.round(crop.bottom - crop.top)}%
          </div>
        </div>
      )}
      {/* Action buttons */}
      {segment.status === "pending" && (
        <div className="flex gap-2">
          <button onClick={() => onSubmit({ left: crop.left, top: crop.top, right: crop.right, bottom: crop.bottom, ratio: selectedRatio })}
            className="flex-1 px-3 py-2 rounded-lg bg-[var(--accent)]/15 text-[var(--accent)] text-[12px] font-medium hover:bg-[var(--accent)]/25 transition-colors flex items-center justify-center gap-1.5">
            <Check size={13} /> Apply Crop
          </button>
          <button onClick={onDismiss} className="px-3 py-2 rounded-lg bg-white/5 text-white/40 text-[12px] hover:bg-white/10 transition-colors">
            <X size={13} />
          </button>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// COLOR PICKER WIDGET
// ═══════════════════════════════════════════

function ColorPickerWidget({ segment, onSubmit, onDismiss }: WidgetProps) {
  const { config } = segment;
  const [color, setColor] = useState(config.default_color || "#ffffff");
  const [hexInput, setHexInput] = useState(color);

  const hexToRgb = (hex: string) => {
    const h = hex.replace("#", "");
    return { r: parseInt(h.substring(0, 2), 16) || 0, g: parseInt(h.substring(2, 4), 16) || 0, b: parseInt(h.substring(4, 6), 16) || 0 };
  };

  const handleHexChange = (val: string) => {
    setHexInput(val);
    if (/^#[0-9a-fA-F]{6}$/.test(val)) setColor(val);
  };

  const rgb = hexToRgb(color);

  return (
    <div className="space-y-3">
      {config.prompt && <WidgetPrompt text={config.prompt} />}
      <div className="flex items-start gap-3">
        {/* Native color input as a large swatch */}
        <div className="relative">
          <input type="color" value={color}
            onChange={(e) => { setColor(e.target.value); setHexInput(e.target.value); }}
            className="w-16 h-16 rounded-lg border border-white/10 cursor-pointer bg-transparent"
          />
        </div>
        {/* Color details */}
        <div className="flex-1 space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-white/40 font-mono w-8">HEX</span>
            <input type="text" value={hexInput} onChange={(e) => handleHexChange(e.target.value)}
              className="flex-1 bg-black/30 border border-white/8 rounded px-2 py-1 text-[11px] text-white/70 font-mono outline-none focus:border-[var(--accent)]/30"
            />
          </div>
          <div className="flex gap-2 text-[10px] font-mono text-white/50">
            <span>R: {rgb.r}</span>
            <span>G: {rgb.g}</span>
            <span>B: {rgb.b}</span>
          </div>
          {/* Preview swatch */}
          <div className="w-full h-6 rounded" style={{ backgroundColor: color }} />
        </div>
      </div>
      {/* Preset colors */}
      <div className="flex gap-1 flex-wrap">
        {["#ffffff","#000000","#ff0000","#00ff00","#0000ff","#ffff00","#ff00ff","#00ffff","#ff6b35","#8b5cf6","#10b981","#f59e0b"].map(c => (
          <button key={c} onClick={() => { setColor(c); setHexInput(c); }}
            className={`w-6 h-6 rounded border ${color === c ? "border-white/60 ring-1 ring-white/30" : "border-white/10"} transition-all`}
            style={{ backgroundColor: c }}
          />
        ))}
      </div>
      {segment.status === "pending" && (
        <div className="flex gap-2">
          <button onClick={() => onSubmit({ hex: color, ...rgb })}
            className="flex-1 px-3 py-2 rounded-lg bg-[var(--accent)]/15 text-[var(--accent)] text-[12px] font-medium hover:bg-[var(--accent)]/25 transition-colors flex items-center justify-center gap-1.5">
            <Check size={13} /> Select Color
          </button>
          <button onClick={onDismiss} className="px-3 py-2 rounded-lg bg-white/5 text-white/40 text-[12px] hover:bg-white/10 transition-colors">
            <X size={13} />
          </button>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// REGION SELECT WIDGET — paint a mask on image
// ═══════════════════════════════════════════

function RegionSelectWidget({ segment, onSubmit, onDismiss }: WidgetProps) {
  const { config } = segment;
  const imageUrl = config.image_url || "";
  const [brushSize, setBrushSize] = useState(config.brush_size || 20);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const maskCanvasRef = useRef<HTMLCanvasElement>(null);
  const painting = useRef(false);
  const imgRef = useRef<HTMLImageElement | null>(null);

  // Initialize canvas when image loads
  useEffect(() => {
    if (!imageUrl) return;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      imgRef.current = img;
      const canvas = canvasRef.current;
      const maskCanvas = maskCanvasRef.current;
      if (!canvas || !maskCanvas) return;
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      maskCanvas.width = img.naturalWidth;
      maskCanvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d");
      if (ctx) { ctx.drawImage(img, 0, 0); }
      const mctx = maskCanvas.getContext("2d");
      if (mctx) { mctx.fillStyle = "#000000"; mctx.fillRect(0, 0, maskCanvas.width, maskCanvas.height); }
    };
    img.src = imageUrl;
  }, [imageUrl]);

  const getCanvasCoords = useCallback((e: React.PointerEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left) * (canvas.width / rect.width),
      y: (e.clientY - rect.top) * (canvas.height / rect.height),
    };
  }, []);

  const paint = useCallback((x: number, y: number) => {
    const canvas = canvasRef.current;
    const maskCanvas = maskCanvasRef.current;
    if (!canvas || !maskCanvas) return;
    // Draw on visible canvas (semi-transparent red)
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.fillStyle = "rgba(255, 80, 80, 0.4)";
      ctx.beginPath();
      ctx.arc(x, y, brushSize, 0, Math.PI * 2);
      ctx.fill();
    }
    // Draw on mask canvas (white = selected)
    const mctx = maskCanvas.getContext("2d");
    if (mctx) {
      mctx.fillStyle = "#ffffff";
      mctx.beginPath();
      mctx.arc(x, y, brushSize, 0, Math.PI * 2);
      mctx.fill();
    }
  }, [brushSize]);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    painting.current = true;
    const { x, y } = getCanvasCoords(e);
    paint(x, y);
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }, [getCanvasCoords, paint]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!painting.current) return;
    const { x, y } = getCanvasCoords(e);
    paint(x, y);
  }, [getCanvasCoords, paint]);

  const onPointerUp = useCallback(() => { painting.current = false; }, []);

  const handleClear = useCallback(() => {
    const canvas = canvasRef.current;
    const maskCanvas = maskCanvasRef.current;
    if (!canvas || !maskCanvas || !imgRef.current) return;
    const ctx = canvas.getContext("2d");
    if (ctx) { ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.drawImage(imgRef.current, 0, 0); }
    const mctx = maskCanvas.getContext("2d");
    if (mctx) { mctx.fillStyle = "#000000"; mctx.fillRect(0, 0, maskCanvas.width, maskCanvas.height); }
  }, []);

  const handleSubmitMask = useCallback(() => {
    const maskCanvas = maskCanvasRef.current;
    if (!maskCanvas) return;
    const dataUrl = maskCanvas.toDataURL("image/png");
    onSubmit({ mask_base64: dataUrl, width: maskCanvas.width, height: maskCanvas.height });
  }, [onSubmit]);

  return (
    <div className="space-y-3">
      {config.prompt && <WidgetPrompt text={config.prompt} />}
      {/* Brush size control */}
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-white/40 font-mono">Brush</span>
        <input type="range" min={5} max={80} step={1} value={brushSize}
          onChange={(e) => setBrushSize(parseInt(e.target.value))}
          className="flex-1 accent-[var(--accent)]"
        />
        <span className="text-[10px] text-white/50 font-mono w-6">{brushSize}</span>
        <button onClick={handleClear} className="px-2 py-1 text-[10px] text-white/40 bg-white/5 rounded hover:bg-white/10">Clear</button>
      </div>
      {/* Canvas */}
      <div className="rounded-lg overflow-hidden border border-white/10 relative">
        <canvas ref={canvasRef} className="w-full cursor-crosshair"
          onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp}
        />
        <canvas ref={maskCanvasRef} className="hidden" />
      </div>
      {segment.status === "pending" && (
        <div className="flex gap-2">
          <button onClick={handleSubmitMask}
            className="flex-1 px-3 py-2 rounded-lg bg-[var(--accent)]/15 text-[var(--accent)] text-[12px] font-medium hover:bg-[var(--accent)]/25 transition-colors flex items-center justify-center gap-1.5">
            <Check size={13} /> Apply Selection
          </button>
          <button onClick={onDismiss} className="px-3 py-2 rounded-lg bg-white/5 text-white/40 text-[12px] hover:bg-white/10 transition-colors">
            <X size={13} />
          </button>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// BEFORE/AFTER WIDGET — compare two images
// ═══════════════════════════════════════════

function BeforeAfterWidget({ segment, onSubmit, onDismiss }: WidgetProps) {
  const { config } = segment;
  const beforeUrl = config.before_url || "";
  const afterUrl = config.after_url || "";
  const [position, setPosition] = useState(50);
  const containerRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);

  const handleMove = useCallback((clientX: number) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setPosition(Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100)));
  }, []);

  return (
    <div className="space-y-3">
      {config.prompt && <WidgetPrompt text={config.prompt} />}
      <div ref={containerRef} className="relative rounded-lg overflow-hidden border border-white/10 cursor-col-resize select-none"
        onPointerDown={(e) => { isDragging.current = true; handleMove(e.clientX); (e.target as HTMLElement).setPointerCapture(e.pointerId); }}
        onPointerMove={(e) => { if (isDragging.current) handleMove(e.clientX); }}
        onPointerUp={() => { isDragging.current = false; }}
      >
        {afterUrl && <img src={afterUrl} alt="After" className="w-full" draggable={false} />}
        {beforeUrl && (
          <div className="absolute inset-0 overflow-hidden" style={{ width: `${position}%` }}>
            <img src={beforeUrl} alt="Before" className="h-full object-cover" style={{ minWidth: containerRef.current?.offsetWidth || "100%" }} draggable={false} />
          </div>
        )}
        <div className="absolute top-0 bottom-0 w-0.5 bg-white/80" style={{ left: `${position}%` }}>
          <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-5 h-5 rounded-full bg-white/90 shadow" />
        </div>
        <span className="absolute top-2 left-2 px-1.5 py-0.5 bg-black/60 rounded text-[9px] text-white/60 font-mono">Before</span>
        <span className="absolute top-2 right-2 px-1.5 py-0.5 bg-black/60 rounded text-[9px] text-white/60 font-mono">After</span>
      </div>
      {segment.status === "pending" && (
        <div className="flex gap-2">
          <button onClick={() => onSubmit({ accepted: true })}
            className="flex-1 px-3 py-2 rounded-lg bg-emerald-500/15 text-emerald-400 text-[12px] font-medium hover:bg-emerald-500/25 transition-colors flex items-center justify-center gap-1.5">
            <Check size={13} /> Looks Good
          </button>
          <button onClick={onDismiss} className="px-3 py-2 rounded-lg bg-white/5 text-white/40 text-[12px] hover:bg-white/10 transition-colors">
            <X size={13} /> Undo
          </button>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════

interface WidgetProps {
  segment: InteractiveSegment;
  onSubmit: (response: any) => void;
  onDismiss: () => void;
  onFinalize?: (response: any) => void;
}

const WIDGET_META: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  choice: { icon: <ListChecks size={14} />, label: "Choose", color: "#8b5cf6" },
  slider: { icon: <Sliders size={14} />, label: "Adjust", color: "#f59e0b" },
  editor: { icon: <FileEdit size={14} />, label: "Edit", color: "#38bdf8" },
  outline: { icon: <ListChecks size={14} />, label: "Outline", color: "#f59e0b" },
  form: { icon: <FormInput size={14} />, label: "Form", color: "#10b981" },
  embed: { icon: <ExternalLink size={14} />, label: "Embed", color: "#e879f9" },
  diff: { icon: <GitBranch size={14} />, label: "Review Changes", color: "#34d399" },
  crop: { icon: <FormInput size={14} />, label: "Crop", color: "#f59e0b" },
  color_picker: { icon: <FormInput size={14} />, label: "Color Picker", color: "#e879f9" },
  region_select: { icon: <FormInput size={14} />, label: "Select Region", color: "#38bdf8" },
  before_after: { icon: <FormInput size={14} />, label: "Compare", color: "#10b981" },
  custom: { icon: <FormInput size={14} />, label: "Custom Input", color: "#60a5fa" },
};

const InteractiveWidget = React.memo(function InteractiveWidget({
  segment,
  onRespond,
}: {
  segment: InteractiveSegment;
  onRespond: (widgetId: string, response: any, dismissed: boolean, finalize?: boolean) => void;
}) {
  const meta = WIDGET_META[segment.widgetType] || WIDGET_META.custom;
  const isPersistent = !!segment.persistentId;
  const revision = segment.revision || 1;

  const handleSubmit = useCallback((response: any) => {
    onRespond(segment.widgetId, response, false);
  }, [segment.widgetId, onRespond]);

  const handleDismiss = useCallback(() => {
    onRespond(segment.widgetId, null, true);
  }, [segment.widgetId, onRespond]);

  const handleFinalize = useCallback((response: any) => {
    onRespond(segment.widgetId, response, false, true);
  }, [segment.widgetId, onRespond]);

  const widgetProps: WidgetProps = { segment, onSubmit: handleSubmit, onDismiss: handleDismiss, onFinalize: handleFinalize };

  const statusLabel = (() => {
    if (segment.status === "pending") return `${meta.label} — Waiting for your input`;
    if (segment.status === "active") return isPersistent ? `${meta.label} — Collaborative Session` : `${meta.label} — Awaiting response`;
    if (segment.status === "submitted") return `${meta.label} — Finalized`;
    if (segment.status === "dismissed") return `${meta.label} — Skipped`;
    return meta.label;
  })();

  return (
    <div className="my-2 rounded-lg border overflow-hidden transition-all"
      style={{ borderColor: `${meta.color}${isPersistent && segment.status !== "submitted" ? "35" : "20"}` }}
    >
      {/* Header */}
      <div className="flex items-center gap-2.5 px-3 py-2"
        style={{ background: `${meta.color}05` }}
      >
        <div className="flex items-center justify-center w-6 h-6 rounded-md"
          style={{ background: `${meta.color}15`, color: meta.color }}
        >
          {meta.icon}
        </div>
        <span className="text-xs font-medium" style={{ color: meta.color }}>
          {statusLabel}
        </span>
        {isPersistent && revision > 1 && segment.status !== "submitted" && (
          <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-white/35 font-mono ml-1">
            rev {revision}
          </span>
        )}
        <div className="flex items-center gap-2 ml-auto">
          {segment.status === "active" && (
            <span className="text-[9px] text-white/25 animate-pulse">● Live</span>
          )}
          {segment.status === "dismissed" && (
            <span className="text-[10px] text-white/30">Skipped</span>
          )}
          {isPersistent && segment.status === "submitted" && (
            <span className="text-[9px] text-emerald-400/60 font-mono flex items-center gap-1">
              <CheckCircle size={9} /> Done
            </span>
          )}
        </div>
      </div>

      {/* Widget body */}
      <div className="px-3 pb-3 pt-2">
        {segment.widgetType === "choice" && <ChoiceWidget {...widgetProps} />}
        {segment.widgetType === "slider" && <SliderWidget {...widgetProps} />}
        {segment.widgetType === "editor" && <EditorWidget {...widgetProps} />}
        {segment.widgetType === "outline" && <OutlineWidget {...widgetProps} />}
        {segment.widgetType === "form" && <FormWidget {...widgetProps} />}
        {segment.widgetType === "embed" && <EmbedWidget {...widgetProps} />}
        {segment.widgetType === "diff" && <DiffWidget {...widgetProps} />}
        {segment.widgetType === "crop" && <CropWidget {...widgetProps} />}
        {segment.widgetType === "color_picker" && <ColorPickerWidget {...widgetProps} />}
        {segment.widgetType === "region_select" && <RegionSelectWidget {...widgetProps} />}
        {segment.widgetType === "before_after" && <BeforeAfterWidget {...widgetProps} />}
        {!(["choice", "slider", "editor", "outline", "form", "embed", "diff", "crop", "color_picker", "region_select", "before_after"].includes(segment.widgetType)) && <CustomWidget {...widgetProps} />}
      </div>
    </div>
  );
});

export default InteractiveWidget;
