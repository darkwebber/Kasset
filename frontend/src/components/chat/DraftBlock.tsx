"use client";

import React, { useState, useRef, useEffect, useCallback, createContext, useContext } from "react";
import { Pencil, Copy, Check, Download, Sparkles, X, FileText } from "lucide-react";

// ═══════════════════════════════════════════════════════════
// DRAFT CONTEXT — provides callbacks from Console to DraftBlock
// ═══════════════════════════════════════════════════════════

interface DraftContextType {
  onRefine: (text: string) => void;
}

export const DraftContext = createContext<DraftContextType | null>(null);

// ═══════════════════════════════════════════════════════════
// DRAFT BLOCK — interactive editable document in chat
// ═══════════════════════════════════════════════════════════

interface DraftBlockProps {
  content: string;
  language?: string;
}

export default function DraftBlock({ content, language }: DraftBlockProps) {
  const ctx = useContext(DraftContext);
  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState(content);
  const [copied, setCopied] = useState(false);
  const [hasEdits, setHasEdits] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Sync content when a new draft arrives
  useEffect(() => {
    setEditText(content);
    setHasEdits(false);
    setIsEditing(false);
  }, [content]);

  // Auto-resize textarea
  useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 500) + "px";
      textareaRef.current.focus();
    }
  }, [isEditing, editText]);

  const handleEdit = useCallback(() => {
    if (isEditing) {
      // Exiting edit mode — check for changes
      setHasEdits(editText !== content);
      setIsEditing(false);
    } else {
      setIsEditing(true);
    }
  }, [isEditing, editText, content]);

  const handleDiscard = useCallback(() => {
    setEditText(content);
    setHasEdits(false);
    setIsEditing(false);
  }, [content]);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(editText);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* no-op */ }
  }, [editText]);

  const handleDownload = useCallback(() => {
    const blob = new Blob([editText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "draft.txt";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [editText]);

  const handleRefine = useCallback(() => {
    if (!ctx) return;
    ctx.onRefine(editText);
    setHasEdits(false);
  }, [ctx, editText]);

  const wordCount = editText.split(/\s+/).filter(Boolean).length;
  const charCount = editText.length;
  const lang = language || "text";

  return (
    <div className="my-3 rounded-xl border border-white/8 overflow-hidden bg-[#080c14]/80 shadow-[0_2px_12px_rgba(0,0,0,0.3)]">
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-white/[0.025] border-b border-white/6">
        <div className="flex items-center gap-2">
          <FileText size={12} className="text-white/30" />
          <span className="text-[10px] uppercase tracking-wider text-white/30 font-mono">{lang}</span>
          {hasEdits && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-400/80 font-medium">
              edited
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {/* Edit toggle */}
          <button
            onClick={handleEdit}
            className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium transition-all ${
              isEditing
                ? "bg-[var(--accent)]/15 text-[var(--accent)]"
                : "bg-white/[0.04] hover:bg-white/[0.08] text-white/50"
            }`}
            title={isEditing ? "Done editing" : "Edit draft"}
          >
            {isEditing ? <><Check size={10} /> Done</> : <><Pencil size={10} /> Edit</>}
          </button>

          {/* Discard edits — only show when editing and text changed */}
          {isEditing && editText !== content && (
            <button
              onClick={handleDiscard}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-white/[0.04] hover:bg-red-500/10 text-white/40 hover:text-red-400 text-[10px] font-medium transition-all"
              title="Discard edits"
            >
              <X size={10} /> Discard
            </button>
          )}

          {/* Copy */}
          <button
            onClick={handleCopy}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-white/[0.04] hover:bg-white/[0.08] text-white/50 text-[10px] font-medium transition-colors"
            title="Copy to clipboard"
          >
            {copied ? <><Check size={10} /> Copied</> : <><Copy size={10} /> Copy</>}
          </button>

          {/* Download */}
          <button
            onClick={handleDownload}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-white/[0.04] hover:bg-white/[0.08] text-white/50 text-[10px] font-medium transition-colors"
            title="Download as .txt"
          >
            <Download size={10} />
          </button>
        </div>
      </div>

      {/* Content area */}
      {isEditing ? (
        <textarea
          ref={textareaRef}
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          className="w-full bg-black/40 px-4 py-3 text-[13px] text-white/85 leading-[1.7] resize-none outline-none crt-scroll"
          style={{ minHeight: "120px", fontFamily: "ui-sans-serif, system-ui, -apple-system, sans-serif" }}
          spellCheck
        />
      ) : (
        <div
          className="px-4 py-3 text-[13px] text-white/80 leading-[1.7] whitespace-pre-wrap max-h-[500px] overflow-y-auto crt-scroll cursor-text select-text"
          style={{ fontFamily: "ui-sans-serif, system-ui, -apple-system, sans-serif" }}
          onClick={() => setIsEditing(true)}
        >
          {editText}
        </div>
      )}

      {/* Footer — stats + refine button */}
      <div className="flex items-center justify-between px-4 py-2 border-t border-white/6 bg-white/[0.015]">
        <div className="text-[10px] text-white/25 font-mono flex gap-3">
          <span>{charCount.toLocaleString()} chars</span>
          <span>{wordCount.toLocaleString()} words</span>
        </div>
        {ctx && (
          <button
            onClick={handleRefine}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium bg-[var(--accent)]/10 text-[var(--accent)]/90 hover:bg-[var(--accent)]/20 transition-all border border-[var(--accent)]/15 hover:border-[var(--accent)]/30"
            title="Send to agent for refinement"
          >
            <Sparkles size={11} />
            Refine with AI
          </button>
        )}
      </div>
    </div>
  );
}
