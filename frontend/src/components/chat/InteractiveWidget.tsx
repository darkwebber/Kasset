"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import { Check, X, ChevronDown, Send, Sliders, ListChecks, FileEdit, FormInput, ExternalLink, Copy, Download } from "lucide-react";
import { getApiBase } from "@/lib/api";
import type { InteractiveSegment } from "./types";

// ═══════════════════════════════════════════
// CHOICE WIDGET — single/multi select options
// ═══════════════════════════════════════════

function ChoiceWidget({ segment, onSubmit, onDismiss }: WidgetProps) {
  const { config } = segment;
  const options: { label: string; value: string; description?: string }[] = config.options || [];
  const multiple = config.multiple || false;
  const [selected, setSelected] = useState<string[]>([]);

  const toggle = (val: string) => {
    if (multiple) {
      setSelected((prev) => prev.includes(val) ? prev.filter((v) => v !== val) : [...prev, val]);
    } else {
      setSelected([val]);
    }
  };

  const submit = () => {
    if (selected.length === 0) return;
    onSubmit(multiple ? selected : selected[0]);
  };

  return (
    <div className="space-y-3">
      {config.prompt && (
        <p className="text-[13px] text-white/80 font-medium">{config.prompt}</p>
      )}
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
      {config.prompt && (
        <p className="text-[12px] text-white/70 leading-relaxed">{config.prompt}</p>
      )}
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
      {config.prompt && (
        <p className="text-[13px] text-white/80 font-medium">{config.prompt}</p>
      )}
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
// EDITOR WIDGET — text/code editing
// ═══════════════════════════════════════════

function EditorWidget({ segment, onSubmit, onDismiss }: WidgetProps) {
  const { config } = segment;
  const [content, setContent] = useState(config.content || "");
  const [copied, setCopied] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 400) + "px";
    }
  }, [content]);

  const submit = () => {
    const original = config.content || "";
    onSubmit({ edited_content: content, changed: content !== original });
  };

  const isCode = config.language && config.language !== "text";
  const fileBase = String(config.filename || config.title || "draft")
    .toLowerCase()
    .replace(/[^a-z0-9-_]+/g, "-")
    .replace(/^-+|-+$/g, "") || "draft";

  const escapeHtml = (s: string) =>
    s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const download = (kind: "txt" | "html") => {
    const body = kind === "html"
      ? `<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>${fileBase}</title><style>body{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:24px;line-height:1.6;color:#111;background:#fff}pre{white-space:pre-wrap;background:#f6f8fa;border:1px solid #e5e7eb;border-radius:10px;padding:16px;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace}</style></head><body><pre>${escapeHtml(content)}</pre></body></html>`
      : content;
    const blob = new Blob([body], { type: kind === "html" ? "text/html" : "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${fileBase}.${kind}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const copyAll = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      // no-op
    }
  };

  return (
    <div className="space-y-3">
      {config.prompt && (
        <p className="text-[12px] text-white/70 font-medium leading-relaxed">{config.prompt}</p>
      )}
      <div className="rounded-xl border border-white/10 overflow-hidden bg-[#0b1220]/80 shadow-[0_0_0_1px_rgba(255,255,255,0.02)]">
        {config.language && (
          <div className="px-3 py-2 bg-white/[0.03] border-b border-white/10 flex items-center justify-between gap-2">
            <span className="text-[10px] text-white/45 font-mono tracking-wide">{config.language}</span>
            <div className="flex items-center gap-1.5">
              <button
                onClick={copyAll}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-white/[0.04] hover:bg-white/[0.08] text-white/60 text-[10px] font-medium transition-colors"
                title="Copy all"
              >
                {copied ? <Check size={10} /> : <Copy size={10} />} {copied ? "Copied" : "Copy"}
              </button>
              <button
                onClick={() => download("txt")}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-white/[0.04] hover:bg-white/[0.08] text-white/60 text-[10px] font-medium transition-colors"
                title="Download as text"
              >
                <Download size={10} /> .txt
              </button>
              <button
                onClick={() => download("html")}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-white/[0.04] hover:bg-white/[0.08] text-white/60 text-[10px] font-medium transition-colors"
                title="Download as HTML"
              >
                <Download size={10} /> .html
              </button>
            </div>
          </div>
        )}
        <textarea
          ref={textareaRef}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          disabled={segment.status !== "pending"}
          className={`w-full bg-black/35 p-4 text-[13px] leading-relaxed resize-none outline-none crt-scroll ${
            isCode ? "font-mono text-[var(--accent)]/80" : "text-white/80"
          } ${segment.status !== "pending" ? "opacity-60" : ""}`}
          style={{ minHeight: "140px" }}
          spellCheck={!isCode}
        />
        <div className="px-3 py-1.5 border-t border-white/10 bg-white/[0.02] text-[10px] text-white/35 font-mono flex items-center justify-between">
          <span>{content.length.toLocaleString()} chars</span>
          <span>{content.split(/\s+/).filter(Boolean).length.toLocaleString()} words</span>
        </div>
      </div>
      {segment.status === "pending" && (
        <div className="flex gap-2 pt-1">
          <button onClick={submit}
            className="px-3.5 py-1.5 rounded-md text-[11px] font-medium bg-[var(--accent)]/20 text-[var(--accent)] hover:bg-[var(--accent)]/30 transition-colors flex items-center gap-1.5">
            <Send size={10} /> Submit Edits
          </button>
          <button onClick={onDismiss}
            className="px-3.5 py-1.5 rounded-md text-[11px] font-medium bg-white/5 text-white/40 hover:bg-white/8 transition-colors">
            Use Original
          </button>
        </div>
      )}
      {segment.status === "submitted" && (
        <div className="text-[11px] text-[var(--accent)]/60 font-mono flex items-center gap-1.5">
          <Check size={10} /> {segment.response?.changed
            ? `Edits applied (${segment.response?.edited_content?.length?.toLocaleString() || "?"} chars)`
            : "Submitted original — no edits were made in the editor"}
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
  type: "text" | "number" | "select" | "toggle";
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

function FormWidget({ segment, onSubmit, onDismiss }: WidgetProps) {
  const { config } = segment;
  const fields: FormField[] = config.fields || [];
  const [values, setValues] = useState<Record<string, any>>(() => {
    const init: Record<string, any> = {};
    fields.forEach((f) => {
      if (f.default !== undefined && f.default !== null) {
        init[f.name] = f.default;
      } else if (f.type === "toggle") {
        init[f.name] = false;
      } else if (f.type === "number") {
        init[f.name] = 0;
      } else if (f.type === "select" && f.options && f.options.length > 0) {
        // Default to first option's value so the visual matches the state
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

  return (
    <div className="space-y-3">
      {config.prompt && (
        <p className="text-[13px] text-white/80 font-medium">{config.prompt}</p>
      )}
      <div className="space-y-2.5">
        {fields.map((f) => (
          <div key={f.name} className="space-y-1">
            <label className="text-[11px] text-white/50 font-medium">{f.label}</label>
            {f.type === "text" && (
              <input
                type="text"
                value={values[f.name] || ""}
                onChange={(e) => updateField(f.name, e.target.value)}
                disabled={segment.status !== "pending"}
                className="w-full bg-black/30 border border-white/8 rounded-md px-2.5 py-1.5 text-[12px] text-white/70 outline-none focus:border-[var(--accent)]/30 transition-colors"
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
        <div className="text-[11px] text-[var(--accent)]/60 font-mono flex items-center gap-1.5">
          <Check size={10} /> Form submitted
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
  const embedType = config.embed_type || "iframe";

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
// MAIN COMPONENT
// ═══════════════════════════════════════════

interface WidgetProps {
  segment: InteractiveSegment;
  onSubmit: (response: any) => void;
  onDismiss: () => void;
}

const WIDGET_META: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  choice: { icon: <ListChecks size={14} />, label: "Choose", color: "#8b5cf6" },
  slider: { icon: <Sliders size={14} />, label: "Adjust", color: "#f59e0b" },
  editor: { icon: <FileEdit size={14} />, label: "Edit", color: "#38bdf8" },
  form: { icon: <FormInput size={14} />, label: "Form", color: "#10b981" },
  embed: { icon: <ExternalLink size={14} />, label: "Embed", color: "#e879f9" },
  custom: { icon: <FormInput size={14} />, label: "Custom Input", color: "#60a5fa" },
};

const InteractiveWidget = React.memo(function InteractiveWidget({
  segment,
  onRespond,
}: {
  segment: InteractiveSegment;
  onRespond: (widgetId: string, response: any, dismissed: boolean) => void;
}) {
  const meta = WIDGET_META[segment.widgetType] || WIDGET_META.custom;

  const handleSubmit = useCallback((response: any) => {
    onRespond(segment.widgetId, response, false);
  }, [segment.widgetId, onRespond]);

  const handleDismiss = useCallback(() => {
    onRespond(segment.widgetId, null, true);
  }, [segment.widgetId, onRespond]);

  const widgetProps: WidgetProps = { segment, onSubmit: handleSubmit, onDismiss: handleDismiss };

  return (
    <div className="my-2 rounded-lg border overflow-hidden transition-all"
      style={{ borderColor: `${meta.color}20` }}
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
          {segment.status === "pending" ? `${meta.label} — Waiting for your input` : meta.label}
        </span>
        {segment.status === "dismissed" && (
          <span className="text-[10px] text-white/30 ml-auto">Skipped</span>
        )}
      </div>

      {/* Widget body */}
      <div className="px-3 pb-3 pt-2">
        {segment.widgetType === "choice" && <ChoiceWidget {...widgetProps} />}
        {segment.widgetType === "slider" && <SliderWidget {...widgetProps} />}
        {segment.widgetType === "editor" && <EditorWidget {...widgetProps} />}
        {segment.widgetType === "form" && <FormWidget {...widgetProps} />}
        {segment.widgetType === "embed" && <EmbedWidget {...widgetProps} />}
        {!(["choice", "slider", "editor", "form", "embed"].includes(segment.widgetType)) && <CustomWidget {...widgetProps} />}
      </div>
    </div>
  );
});

export default InteractiveWidget;
