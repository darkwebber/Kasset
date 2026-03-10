import React from "react";
import { ChevronRight, X } from "lucide-react";

export function SectionHeader({ title, open, onToggle }: { title: string; open: boolean; onToggle: () => void }) {
  return (
    <button onClick={onToggle} className="flex items-center gap-2 w-full text-left py-2.5 text-[10px] uppercase tracking-[0.15em] text-white/25 font-semibold hover:text-white/45 transition-colors group">
      <div className={`transition-transform duration-200 ${open ? "rotate-90" : ""}`}><ChevronRight size={11} /></div>
      {title}
      <div className="flex-1 h-px bg-white/5 group-hover:bg-white/8 transition-colors" />
    </button>
  );
}

export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="space-y-1">
      <label className="text-[11px] text-white/30 font-medium">{label}</label>
      {children}
      {hint && <p className="text-[10px] text-white/15 mt-0.5">{hint}</p>}
    </div>
  );
}

export function TextInput({ value, onChange, placeholder, mono }: { value: string; onChange: (v: string) => void; placeholder?: string; mono?: boolean }) {
  return (
    <input
      type="text" value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
      className={`w-full bg-white/[0.035] border border-white/[0.06] rounded-md px-2.5 py-[7px] text-[13px] text-white/75 placeholder-white/15 focus:border-[var(--accent)]/30 focus:bg-white/[0.05] focus:outline-none transition-all ${mono ? "font-mono text-xs" : ""}`}
    />
  );
}

export function TextArea({ value, onChange, placeholder, rows, mono }: { value: string; onChange: (v: string) => void; placeholder?: string; rows?: number; mono?: boolean }) {
  return (
    <textarea
      value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} rows={rows || 4}
      className={`w-full bg-white/[0.035] border border-white/[0.06] rounded-md px-2.5 py-[7px] text-[13px] text-white/75 placeholder-white/15 focus:border-[var(--accent)]/30 focus:bg-white/[0.05] focus:outline-none transition-all resize-y subtle-scroll ${mono ? "font-mono text-xs leading-relaxed" : ""}`}
    />
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
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

export function TagInput({ tags, onChange }: { tags: string[]; onChange: (t: string[]) => void }) {
  const [draft, setReactDraft] = React.useState("");
  const add = () => {
    const t = draft.trim().toLowerCase();
    if (t && !tags.includes(t)) { onChange([...tags, t]); setReactDraft(""); }
  };
  return (
    <div className="space-y-1.5">
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {tags.map(t => (
            <span key={t} className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-[var(--accent)]/8 border border-[var(--accent)]/10 rounded text-[10px] text-[var(--accent)]/70 font-mono">
              {t}
              <button 
                onClick={(e) => { e.preventDefault(); onChange(tags.filter(x => x !== t)); }} 
                className="text-white/20 hover:text-red-400 transition-colors"
                type="button"
              >
                <X size={8} />
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex gap-1">
        <input value={draft} onChange={e => setReactDraft(e.target.value)} onKeyDown={e => e.key === "Enter" && (e.preventDefault(), add())}
          placeholder="Add tag..." className="flex-1 bg-white/[0.035] border border-white/[0.06] rounded-md px-2.5 py-[5px] text-xs text-white/60 font-mono focus:outline-none focus:border-[var(--accent)]/30 transition-all" />
        <button onClick={add} type="button" className="px-2.5 py-[5px] bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] rounded-md text-[10px] text-white/35 hover:text-white/55 font-mono transition-all">+</button>
      </div>
    </div>
  );
}
