"use client";

import React, { useState, useRef, useEffect, useCallback, useMemo, createContext, useContext } from "react";
import { createPortal } from "react-dom";
import {
  Pencil, Copy, Check, Download, Sparkles, X, FileText,
  MessageSquare, ChevronLeft, ChevronRight, Diff, CheckCircle2,
  ExternalLink, Loader2, Trash2, ChevronDown, Clock, GitCompare,
} from "lucide-react";
import { getApiBase } from "@/lib/api";

// ═══════════════════════════════════════════════════════════
// DRAFT CONTEXT — Console provides callbacks + API base
// ═══════════════════════════════════════════════════════════

interface DraftContextType {
  onRefine: (text: string) => void;
  onFinalize?: () => void;
}

export const DraftContext = createContext<DraftContextType | null>(null);

// ═══════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════

interface DraftBlockProps {
  content: string;
  language?: string;
  draftId?: string; // Optional: reuse existing backend draft for continuity
}

interface DraftState {
  id: string;
  title: string;
  language: string;
  content: string;
  current_version: number;
  viewing_version: number;
  version_count: number;
  versions: VersionMeta[];
  comments: DraftComment[];
  all_comments: DraftComment[];
  finalized: boolean;
  finalized_path: string | null;
  char_count: number;
  word_count: number;
}

interface VersionMeta {
  number: number;
  author: "ai" | "user";
  timestamp: number;
  char_count: number;
  word_count: number;
}

interface DraftComment {
  id: string;
  selection: string;
  start_offset: number;
  end_offset: number;
  text: string;
  author: string;
  version: number;
  timestamp: number;
  resolved: boolean;
}

interface DiffOp {
  op: "equal" | "insert" | "delete";
  text: string;
}

interface DiffStats {
  additions: number;
  deletions: number;
  chars_added: number;
  chars_removed: number;
}

function timeAgo(ts: number): string {
  const sec = Math.floor((Date.now() / 1000) - ts);
  if (sec < 60) return "just now";
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

// ═══════════════════════════════════════════════════════════
// API HELPERS
// ═══════════════════════════════════════════════════════════

async function draftApi(path: string, opts?: RequestInit) {
  const res = await fetch(`${getApiBase()}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  return res.json();
}

// ═══════════════════════════════════════════════════════════
// DRAFT BLOCK — backend-synced collaborative document
// ═══════════════════════════════════════════════════════════

export default function DraftBlock({ content, language, draftId: externalDraftId }: DraftBlockProps) {
  const ctx = useContext(DraftContext);

  // ── Core state ──
  const [draft, setDraft] = useState<DraftState | null>(null);
  const [loading, setLoading] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState(content);
  const [copied, setCopied] = useState(false);
  const [viewMode, setViewMode] = useState<"content" | "diff">("content");
  const [diffOps, setDiffOps] = useState<DiffOp[]>([]);
  const [diffStats, setDiffStats] = useState<DiffStats | null>(null);
  const [diffFrom, setDiffFrom] = useState(0);
  const [diffTo, setDiffTo] = useState(0);
  const [diffLoading, setDiffLoading] = useState(false);
  const [showTimeline, setShowTimeline] = useState(false);
  const [justSubmitted, setJustSubmitted] = useState(false);
  const [finalizing, setFinalizing] = useState(false);

  // ── Comment state ──
  const [pendingSel, setPendingSel] = useState<{
    rect: DOMRect; text: string; start: number; end: number;
  } | null>(null);
  const [isCommenting, setIsCommenting] = useState(false);
  const [commentInput, setCommentInput] = useState("");
  const savedRangeRef = useRef<Range | null>(null);
  const commentInputRef = useRef<HTMLTextAreaElement>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const draftIdRef = useRef<string | null>(null);
  const contentSeenRef = useRef<string>(content);

  // ── Create or load draft on mount ──
  useEffect(() => {
    if (draftIdRef.current) return;
    let cancelled = false;
    setLoading(true);

    // If an external draftId is provided, try to load it first
    const initDraft = externalDraftId
      ? draftApi(`/api/drafts/${externalDraftId}`).then((data) => {
          if (data.draft) return data;
          // Draft doesn't exist yet — create it with the given ID
          return draftApi("/api/drafts", {
            method: "POST",
            body: JSON.stringify({
              content,
              title: content.substring(0, 60).split("\n")[0] || "Untitled Draft",
              author: "ai",
              language: language || "text",
            }),
          });
        })
      : draftApi("/api/drafts", {
          method: "POST",
          body: JSON.stringify({
            content,
            title: content.substring(0, 60).split("\n")[0] || "Untitled Draft",
            author: "ai",
            language: language || "text",
          }),
        });

    initDraft.then((data) => {
      if (cancelled || !data.draft) return;
      draftIdRef.current = data.draft.id;
      setDraft(data.draft);
      setEditText(data.draft.content);
      contentSeenRef.current = content;
    }).finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── When content prop changes (new AI revision) add version ──
  useEffect(() => {
    if (!draftIdRef.current || content === contentSeenRef.current) return;
    contentSeenRef.current = content;
    draftApi(`/api/drafts/${draftIdRef.current}/versions`, {
      method: "POST",
      body: JSON.stringify({ content, author: "ai" }),
    }).then((data) => {
      if (data.draft) {
        setDraft(data.draft);
        setEditText(data.draft.content);
        setViewMode("content");
      }
    });
  }, [content]);

  // ── Auto-resize textarea ──
  useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 500) + "px";
      textareaRef.current.focus();
    }
  }, [isEditing, editText]);

  // ── Focus comment input ──
  useEffect(() => {
    if (isCommenting && commentInputRef.current) commentInputRef.current.focus();
  }, [isCommenting]);

  // ── Restore browser selection when commenting ──
  useEffect(() => {
    if (isCommenting && savedRangeRef.current) {
      try {
        const sel = window.getSelection();
        if (sel) { sel.removeAllRanges(); sel.addRange(savedRangeRef.current); }
      } catch { /* range may be stale */ }
    }
  }, [isCommenting]);

  // ── Handlers ──

  const clearPending = useCallback(() => {
    setPendingSel(null);
    setIsCommenting(false);
    setCommentInput("");
    savedRangeRef.current = null;
  }, []);

  const handleEditDone = useCallback(async () => {
    if (!isEditing) { setIsEditing(true); return; }
    setIsEditing(false);
    if (!draftIdRef.current || editText === draft?.content) return;
    const data = await draftApi(`/api/drafts/${draftIdRef.current}/versions`, {
      method: "POST",
      body: JSON.stringify({ content: editText, author: "user" }),
    });
    if (data.draft) setDraft(data.draft);
  }, [isEditing, editText, draft?.content]);

  const handleDiscard = useCallback(() => {
    setEditText(draft?.content || content);
    setIsEditing(false);
    clearPending();
  }, [draft?.content, content]);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(editText);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard blocked */ }
  }, [editText]);

  const handleDownload = useCallback(() => {
    const blob = new Blob([editText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${draft?.title || "draft"}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [editText, draft?.title]);

  const handleRefine = useCallback(() => {
    if (!ctx || !draft) return;
    let payload = editText;
    const activeComments = draft.comments.filter((c: DraftComment) => !c.resolved);
    if (activeComments.length > 0) {
      payload += "\n\n### User Comments/Annotations:\n";
      activeComments.forEach((c: DraftComment) => {
        payload += `- On "${c.selection}": ${c.text}\n`;
      });
    }
    ctx.onRefine(payload);
  }, [ctx, editText, draft]);

  const handleFinalize = useCallback(async () => {
    if (!draftIdRef.current || finalizing) return;
    setFinalizing(true);
    try {
      const data = await draftApi(`/api/drafts/${draftIdRef.current}/finalize`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      if (data.draft) {
        setDraft(data.draft);
        // Clear any pending comments/selection
        clearPending();
        if (ctx?.onFinalize) {
          ctx.onFinalize();
        }
      }
    } finally {
      setFinalizing(false);
    }
  }, [ctx, finalizing, clearPending]);

  // ── Version navigation ──

  const navigateVersion = useCallback(async (version: number) => {
    if (!draftIdRef.current) return;
    const data = await draftApi(`/api/drafts/${draftIdRef.current}/navigate`, {
      method: "POST",
      body: JSON.stringify({ version }),
    });
    if (data.draft) {
      setDraft(data.draft);
      setEditText(data.draft.content);
      setViewMode("content");
    }
  }, []);

  const showDiff = useCallback(async (v1: number, v2: number) => {
    if (!draftIdRef.current) return;
    setDiffLoading(true);
    const data = await draftApi(`/api/drafts/${draftIdRef.current}/diff?v1=${v1}&v2=${v2}`);
    setDiffLoading(false);
    if (data.diff) {
      setDiffOps(data.diff.ops);
      setDiffStats(data.diff.stats || null);
      setDiffFrom(v1);
      setDiffTo(v2);
      setViewMode("diff");
    }
  }, []);

  // ── Selection / Comment ──

  const getTextOffset = useCallback((container: HTMLElement, node: Node, offset: number): number => {
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    let count = 0;
    while (walker.nextNode()) {
      if (walker.currentNode === node) return count + offset;
      count += (walker.currentNode.textContent?.length || 0);
    }
    return count + offset;
  }, []);

  const handleMouseUp = useCallback(() => {
    if (isEditing || viewMode !== "content") return;
    // Block all commenting on finalized drafts
    if (draft?.finalized) return;
    // Don't disrupt highlight while user is actively commenting
    if (isCommenting) return;
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !contentRef.current?.contains(sel.anchorNode)) {
      // Only clear if not in a comment flow
      if (!pendingSel || !isCommenting) clearPending();
      return;
    }
    const text = sel.toString().trim();
    if (!text || !contentRef.current) return;
    const range = sel.getRangeAt(0);
    const endRange = range.cloneRange();
    endRange.collapse(false);
    const endRects = endRange.getClientRects();
    const fallbackRects = range.getClientRects();
    const rect = endRects.length > 0
      ? endRects[endRects.length - 1]
      : (fallbackRects.length > 0 ? fallbackRects[fallbackRects.length - 1] : range.getBoundingClientRect());
    const start = getTextOffset(contentRef.current, range.startContainer, range.startOffset);
    const end = getTextOffset(contentRef.current, range.endContainer, range.endOffset);
    setPendingSel({ rect, text, start, end });
    setIsCommenting(false);
    setCommentInput("");
  }, [isEditing, viewMode, isCommenting, pendingSel, clearPending, getTextOffset]);

  const openCommentBox = useCallback(() => {
    const sel = window.getSelection();
    if (sel && sel.rangeCount > 0) savedRangeRef.current = sel.getRangeAt(0).cloneRange();
    setIsCommenting(true);
  }, []);

  const submitComment = useCallback(async () => {
    if (!commentInput.trim() || !pendingSel || !draftIdRef.current) return;
    const data = await draftApi(`/api/drafts/${draftIdRef.current}/comments`, {
      method: "POST",
      body: JSON.stringify({
        selection: pendingSel.text,
        start_offset: pendingSel.start,
        end_offset: pendingSel.end,
        text: commentInput.trim(),
        author: "user",
      }),
    });
    if (data.draft) {
      setDraft(data.draft);
      // Briefly show amber→green transition before clearing pending
      setJustSubmitted(true);
      setTimeout(() => {
        clearPending();
        setJustSubmitted(false);
        window.getSelection()?.removeAllRanges();
      }, 350);
    } else {
      clearPending();
      window.getSelection()?.removeAllRanges();
    }
  }, [commentInput, pendingSel, clearPending]);

  const deleteComment = useCallback(async (commentId: string) => {
    if (!draftIdRef.current) return;
    const data = await draftApi(`/api/drafts/${draftIdRef.current}/comments/${commentId}`, { method: "DELETE" });
    if (data.draft) setDraft(data.draft);
  }, []);

  // ── Toolbar position (near selection, never covering it) ──
  // Button: appears to the right of selection end, above the line
  // Modal: appears below the selection end, right-aligned to selection end
  // Never overlaps the selection bounding box
  const toolbarPos = useMemo(() => {
    if (!pendingSel) return null;
    const r = pendingSel.rect;
    const pad = 8; const edge = 10;
    if (isCommenting) {
      const mW = 288; const mH = 170;
      // Prefer below the selection end
      const fitsBelow = r.bottom + pad + mH <= window.innerHeight - edge;
      const fitsAbove = r.top - mH - pad >= edge;
      // Position: below selection end, or above if no room below
      const top = fitsBelow
        ? r.bottom + pad
        : fitsAbove
          ? r.top - mH - pad
          : Math.max(edge, window.innerHeight - mH - edge);
      // Align right edge of modal with the right edge of selection
      const left = Math.max(edge, Math.min(r.right - mW, window.innerWidth - mW - edge));
      return { top, left };
    }
    // Comment button: small pill to the right of selection end, above the line
    const bW = 110; const bH = 30;
    return {
      top: Math.max(edge, r.top - bH - pad),
      left: Math.max(edge, Math.min(r.right + pad, window.innerWidth - bW - edge)),
    };
  }, [pendingSel, isCommenting]);

  // ── Render highlighted content ──
  const displayText = draft?.content || editText;

  const renderContent = useMemo(() => {
    type Region = { start: number; end: number; id: string; tooltip: string; kind: "comment" | "pending" };
    const regions: Region[] = [];
    if (draft) {
      for (const c of draft.comments) {
        if (c.start_offset >= 0 && c.end_offset <= displayText.length && c.start_offset < c.end_offset) {
          regions.push({ start: c.start_offset, end: c.end_offset, id: c.id, tooltip: c.text, kind: "comment" as const });
        }
      }
    }
    if (pendingSel && pendingSel.start >= 0 && pendingSel.end <= displayText.length && pendingSel.start < pendingSel.end) {
      regions.push({ start: pendingSel.start, end: pendingSel.end, id: "pending", tooltip: "", kind: "pending" as const });
    }
    regions.sort((a, b) => a.start - b.start || a.end - b.end);
    if (regions.length === 0) return displayText;

    const parts: React.ReactNode[] = [];
    let cursor = 0;
    for (const reg of regions) {
      if (reg.start > cursor) parts.push(displayText.substring(cursor, reg.start));
      // Pending highlight: amber while typing, transitions to green when justSubmitted
      // Theme-aware highlight colors using CSS custom properties
      const cls = reg.kind === "pending"
        ? (justSubmitted
            ? "text-inherit rounded-sm ring-1 transition-colors duration-300"
            : "text-inherit rounded-sm ring-1 transition-colors duration-300")
        : "text-inherit rounded-sm border-b cursor-help";
      const inlineStyle = reg.kind === "pending"
        ? (justSubmitted
            ? { background: "var(--glow, var(--accent, #10b981))" + "25", ringColor: "var(--glow, var(--accent, #10b981))" }
            : { background: "color-mix(in srgb, var(--accent, #f59e0b) 25%, transparent)", boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--accent, #f59e0b) 50%, transparent)" })
        : { background: "color-mix(in srgb, var(--glow, var(--accent, #10b981)) 15%, transparent)", borderColor: "color-mix(in srgb, var(--glow, var(--accent, #10b981)) 40%, transparent)" };
      parts.push(
        <mark key={reg.id} className={cls} style={inlineStyle} title={reg.kind === "comment" ? reg.tooltip : undefined}>
          {displayText.substring(Math.max(cursor, reg.start), reg.end)}
        </mark>
      );
      cursor = Math.max(cursor, reg.end);
    }
    if (cursor < displayText.length) parts.push(displayText.substring(cursor));
    return <>{parts}</>;
  }, [displayText, draft?.comments, pendingSel, justSubmitted]);

  // ── Render diff ──
  const renderDiff = useMemo(() => {
    if (!diffOps.length) return null;
    return (
      <div className="whitespace-pre-wrap leading-[1.7] text-[13px]" style={{ fontFamily: "ui-sans-serif, system-ui, -apple-system, sans-serif" }}>
        {diffOps.map((op, i) => {
          if (op.op === "equal") return <span key={i} className="text-white/70">{op.text}</span>;
          if (op.op === "insert") return <span key={i} className="bg-emerald-500/20 text-emerald-300">{op.text}</span>;
          if (op.op === "delete") return <span key={i} className="bg-red-500/20 text-red-400 line-through">{op.text}</span>;
          return null;
        })}
      </div>
    );
  }, [diffOps]);

  // ── Derived ──
  const v = draft?.current_version || 1;
  const vCount = draft?.version_count || 1;
  const hasComments = (draft?.comments.length || 0) > 0;
  const hasEdits = isEditing && editText !== (draft?.content || content);
  const canRefine = hasEdits || hasComments;
  const lang = language || draft?.language || "text";

  if (loading && !draft) {
    return (
      <div className="my-3 rounded-xl border border-white/8 bg-[#080c14]/80 p-6 flex items-center gap-2 text-white/40 text-sm">
        <Loader2 size={14} className="animate-spin" /> Preparing draft...
      </div>
    );
  }

  return (
    <div className="my-3 rounded-xl border border-white/8 overflow-hidden bg-[#080c14]/80 shadow-[0_2px_12px_rgba(0,0,0,0.3)]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-white/[0.025] border-b border-white/6">
        <div className="flex items-center gap-2">
          <FileText size={12} className="text-white/30" />
          <span className="text-[10px] uppercase tracking-wider text-white/30 font-mono">{lang}</span>
          {draft?.finalized && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400/80 font-medium flex items-center gap-1">
              <CheckCircle2 size={8} /> Finalized
            </span>
          )}
          {hasEdits && <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-400/80 font-medium">edited</span>}
        </div>
        <div className="flex items-center gap-1">
          {!draft?.finalized && (
          <button onClick={handleEditDone}
            className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium transition-all ${isEditing ? "bg-[var(--accent)]/15 text-[var(--accent)]" : "bg-white/[0.04] hover:bg-white/[0.08] text-white/50"}`}
            title={isEditing ? "Save edits" : "Edit draft"}>
            {isEditing ? <><Check size={10} /> Done</> : <><Pencil size={10} /> Edit</>}
          </button>
          )}
          {hasEdits && (
            <button onClick={handleDiscard}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-white/[0.04] hover:bg-red-500/10 text-white/40 hover:text-red-400 text-[10px] font-medium transition-all"
              title="Discard edits"><X size={10} /> Discard</button>
          )}
          <button onClick={handleCopy}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-white/[0.04] hover:bg-white/[0.08] text-white/50 text-[10px] font-medium transition-colors"
            title="Copy">{copied ? <><Check size={10} /> Copied</> : <><Copy size={10} /> Copy</>}</button>
          <button onClick={handleDownload}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-white/[0.04] hover:bg-white/[0.08] text-white/50 text-[10px] font-medium transition-colors"
            title="Download"><Download size={10} /></button>
        </div>
      </div>

      {/* Version navigator */}
      {vCount > 1 && (
        <div className="border-b border-white/6">
          <div className="flex items-center justify-between px-4 py-1.5 bg-black/20">
            <div className="flex items-center gap-1.5">
              <button onClick={() => navigateVersion(Math.max(1, v - 1))} disabled={v <= 1}
                className="p-0.5 rounded hover:bg-white/10 text-white/40 hover:text-white disabled:opacity-20 disabled:cursor-not-allowed transition-colors">
                <ChevronLeft size={14} />
              </button>
              <button onClick={() => setShowTimeline(!showTimeline)}
                className="text-[10px] font-mono text-white/50 min-w-[80px] text-center hover:text-white/70 transition-colors flex items-center justify-center gap-1 cursor-pointer">
                v{v} / {vCount}
                {draft?.versions[v - 1] && (
                  <span className={`px-1 py-0.5 rounded-full text-[8px] font-medium ${draft.versions[v - 1].author === "ai" ? "bg-purple-500/15 text-purple-400/80" : "bg-amber-500/15 text-amber-400/80"}`}>
                    {draft.versions[v - 1].author === "ai" ? "AI" : "You"}
                  </span>
                )}
                <ChevronDown size={10} className={`transition-transform duration-150 ${showTimeline ? "rotate-180" : ""}`} />
              </button>
              <button onClick={() => navigateVersion(Math.min(vCount, v + 1))} disabled={v >= vCount}
                className="p-0.5 rounded hover:bg-white/10 text-white/40 hover:text-white disabled:opacity-20 disabled:cursor-not-allowed transition-colors">
                <ChevronRight size={14} />
              </button>
            </div>
            <div className="flex items-center gap-1">
              {v > 1 && (
                <button onClick={() => viewMode === "diff" ? setViewMode("content") : showDiff(v - 1, v)}
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium transition-all ${viewMode === "diff" ? "bg-[var(--accent)]/15 text-[var(--accent)]" : "bg-white/[0.04] hover:bg-white/[0.08] text-white/40"}`}
                  title="Show changes from previous version">
                  {diffLoading ? <Loader2 size={10} className="animate-spin" /> : <Diff size={10} />}
                  <span>Diff</span>
                </button>
              )}
              {v < vCount && (
                <button onClick={() => navigateVersion(vCount)}
                  className="px-2 py-0.5 rounded text-[10px] font-medium bg-white/[0.04] hover:bg-white/[0.08] text-white/40 transition-colors">Latest</button>
              )}
            </div>
          </div>

          {/* Diff stats bar */}
          {viewMode === "diff" && diffStats && (
            <div className="flex items-center gap-3 px-4 py-1 bg-black/30 border-t border-white/4 text-[10px] font-mono">
              <span className="text-white/40">v{diffFrom} → v{diffTo}</span>
              <span className="text-emerald-400/70">+{diffStats.chars_added} chars</span>
              <span className="text-red-400/70">−{diffStats.chars_removed} chars</span>
              <span className="text-white/25">{diffStats.additions} insert{diffStats.additions !== 1 ? "s" : ""}, {diffStats.deletions} deletion{diffStats.deletions !== 1 ? "s" : ""}</span>
            </div>
          )}

          {/* Version timeline panel */}
          {showTimeline && draft?.versions && (
            <div className="bg-black/30 border-t border-white/4 max-h-[200px] overflow-y-auto crt-scroll">
              {[...draft.versions].reverse().map((ver, _i) => {
                const prevVer = ver.number > 1 ? draft.versions[ver.number - 2] : null;
                const charDelta = prevVer ? ver.char_count - prevVer.char_count : ver.char_count;
                const isActive = ver.number === v;
                return (
                  <div key={ver.number}
                    className={`flex items-center justify-between px-4 py-1.5 text-[10px] hover:bg-white/[0.03] transition-colors ${isActive ? "bg-white/[0.04]" : ""}`}>
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={`font-mono font-bold ${isActive ? "text-[var(--accent)]" : "text-white/50"}`}>v{ver.number}</span>
                      <span className={`px-1 py-0.5 rounded-full text-[8px] font-medium ${ver.author === "ai" ? "bg-purple-500/15 text-purple-400/70" : "bg-amber-500/15 text-amber-400/70"}`}>
                        {ver.author === "ai" ? "AI" : "You"}
                      </span>
                      <span className="text-white/25 flex items-center gap-0.5"><Clock size={8} /> {timeAgo(ver.timestamp)}</span>
                      <span className={`font-mono ${charDelta >= 0 ? "text-emerald-400/50" : "text-red-400/50"}`}>
                        {charDelta >= 0 ? "+" : ""}{charDelta}
                      </span>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {!isActive && (
                        <button onClick={() => { navigateVersion(ver.number); setShowTimeline(false); }}
                          className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-white/[0.04] hover:bg-white/[0.08] text-white/40 transition-colors">
                          View
                        </button>
                      )}
                      {ver.number > 1 && (
                        <button onClick={() => { showDiff(ver.number - 1, ver.number); setShowTimeline(false); }}
                          className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-white/[0.04] hover:bg-white/[0.08] text-white/40 transition-colors flex items-center gap-0.5">
                          <GitCompare size={8} /> vs v{ver.number - 1}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
              {/* Arbitrary version comparison */}
              {vCount > 2 && (
                <div className="flex items-center gap-2 px-4 py-2 border-t border-white/4">
                  <span className="text-[9px] text-white/30 font-medium">Compare</span>
                  <select value={diffFrom || 1} onChange={(e) => setDiffFrom(Number(e.target.value))}
                    className="bg-black/40 border border-white/10 rounded text-[10px] text-white/60 px-1.5 py-0.5 outline-none">
                    {draft.versions.map((ver) => (
                      <option key={ver.number} value={ver.number}>v{ver.number}</option>
                    ))}
                  </select>
                  <span className="text-[9px] text-white/20">→</span>
                  <select value={diffTo || vCount} onChange={(e) => setDiffTo(Number(e.target.value))}
                    className="bg-black/40 border border-white/10 rounded text-[10px] text-white/60 px-1.5 py-0.5 outline-none">
                    {draft.versions.map((ver) => (
                      <option key={ver.number} value={ver.number}>v{ver.number}</option>
                    ))}
                  </select>
                  <button onClick={() => { showDiff(diffFrom || 1, diffTo || vCount); setShowTimeline(false); }}
                    className="px-2 py-0.5 rounded text-[9px] font-medium bg-[var(--accent)]/15 text-[var(--accent)] hover:bg-[var(--accent)]/25 transition-colors">
                    Compare
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Content area */}
      <div className="relative">
        {isEditing ? (
          <textarea ref={textareaRef} value={editText} onChange={(e) => setEditText(e.target.value)}
            className="w-full bg-black/40 px-4 py-3 text-[13px] text-white/85 leading-[1.7] resize-none outline-none crt-scroll"
            style={{ minHeight: "120px", fontFamily: "ui-sans-serif, system-ui, -apple-system, sans-serif" }} spellCheck />
        ) : viewMode === "diff" ? (
          <div className="px-4 py-3 max-h-[500px] overflow-y-auto crt-scroll">
            {renderDiff || <span className="text-white/30 text-sm">No changes</span>}
          </div>
        ) : (
          <div ref={contentRef}
            className="px-4 py-3 text-[13px] text-white/80 leading-[1.7] whitespace-pre-wrap max-h-[500px] overflow-y-auto crt-scroll cursor-text select-text"
            style={{ fontFamily: "ui-sans-serif, system-ui, -apple-system, sans-serif" }}
            onMouseUp={handleMouseUp}>
            {renderContent}
          </div>
        )}

        {/* Floating comment toolbar (portal to body) — blocked when finalized */}
        {pendingSel && !isEditing && !draft?.finalized && viewMode === "content" && toolbarPos && typeof document !== "undefined" && createPortal(
          <div className="fixed z-[9999] border shadow-xl rounded-lg overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-150"
            style={{ top: toolbarPos.top, left: toolbarPos.left, background: "color-mix(in srgb, var(--accent, #3f3f46) 8%, #18181b)", borderColor: "color-mix(in srgb, var(--accent, #3f3f46) 20%, rgba(255,255,255,0.1))" }}
            onMouseDown={(e) => e.stopPropagation()}>
            {isCommenting ? (
              <div className="p-3 w-72 flex flex-col gap-2">
                <div className="text-[10px] text-white/40 font-mono truncate px-0.5">
                  &ldquo;{pendingSel.text.length > 40 ? pendingSel.text.slice(0, 40) + "..." : pendingSel.text}&rdquo;
                </div>
                <textarea ref={commentInputRef} value={commentInput} onChange={(e) => setCommentInput(e.target.value)}
                  placeholder="What should change here?"
                  className="w-full bg-black/40 border border-white/10 rounded-md px-2.5 py-2 text-xs text-white placeholder-white/30 resize-none outline-none focus:border-[var(--accent)]/40 h-16"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submitComment(); }
                    if (e.key === "Escape") { clearPending(); window.getSelection()?.removeAllRanges(); }
                  }} />
                <div className="flex justify-end gap-1.5">
                  <button onClick={() => { clearPending(); window.getSelection()?.removeAllRanges(); }}
                    className="px-2.5 py-1 rounded-md text-[10px] text-white/40 hover:text-white hover:bg-white/5 transition-colors">Cancel</button>
                  <button onClick={submitComment}
                    className="px-2.5 py-1 rounded-md text-[10px] bg-[var(--accent)]/20 text-[var(--accent)] hover:bg-[var(--accent)]/30 font-medium transition-colors">Add</button>
                </div>
              </div>
            ) : (
              <button onClick={openCommentBox}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-white/80 hover:text-white transition-colors"
                onPointerDown={(e) => e.preventDefault()}>
                <MessageSquare size={12} />
                <span>Comment</span>
              </button>
            )}
          </div>,
          document.body
        )}
      </div>

      {/* Comments panel — themed to match kasset accent */}
      {hasComments && !isEditing && viewMode === "content" && (
        <div className="px-4 py-2.5 border-t space-y-1.5"
          style={{ background: "color-mix(in srgb, var(--glow, var(--accent, #10b981)) 3%, transparent)", borderColor: "color-mix(in srgb, var(--glow, var(--accent, #10b981)) 10%, transparent)" }}>
          <div className="text-[10px] uppercase font-bold tracking-wider"
            style={{ color: "color-mix(in srgb, var(--glow, var(--accent, #10b981)) 70%, white)" }}>
            Annotations ({draft!.comments.length})
          </div>
          {draft!.comments.map((c: DraftComment) => (
            <div key={c.id} className="flex items-start gap-2 text-xs bg-black/20 rounded-md p-2 border group"
              style={{ borderColor: "color-mix(in srgb, var(--glow, var(--accent, #10b981)) 10%, transparent)" }}>
              <div className="flex-1 min-w-0">
                <div className="text-white/35 italic truncate mb-0.5 pl-2 text-[11px]"
                  style={{ borderLeft: "2px solid color-mix(in srgb, var(--glow, var(--accent, #10b981)) 30%, transparent)" }}>
                  &ldquo;{c.selection}&rdquo;
                </div>
                <div className="text-white/85 font-medium">{c.text}</div>
              </div>
              {!draft?.finalized && (
                <button onClick={() => deleteComment(c.id)}
                  className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-500/10 text-white/20 hover:text-red-400 transition-all flex-shrink-0"
                  title="Delete comment"><Trash2 size={11} /></button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Finalized card — prominent file path display */}
      {draft?.finalized && draft.finalized_path && (
        <div className="mx-4 my-3 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.04] p-3">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle2 size={14} className="text-emerald-400" />
            <span className="text-[12px] font-medium text-emerald-400">Draft Finalized</span>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-white/60 bg-black/30 rounded-md px-3 py-2 font-mono">
            <ExternalLink size={11} className="text-emerald-400/60 shrink-0" />
            <span className="truncate">{draft.finalized_path}</span>
          </div>
          <div className="text-[10px] text-white/30 mt-1.5">
            Saved to Desktop and <span className="text-white/40">~/.kasset/finalized/</span>
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between px-4 py-2 border-t border-white/6 bg-white/[0.015]">
        <div className="text-[10px] text-white/25 font-mono flex gap-3">
          <span>{(draft?.char_count || editText.length).toLocaleString()} chars</span>
          <span>{(draft?.word_count || editText.split(/\s+/).filter(Boolean).length).toLocaleString()} words</span>
        </div>
        <div className="flex items-center gap-2">
          {ctx && canRefine && !draft?.finalized && (
            <button onClick={handleRefine}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium bg-[var(--accent)]/10 text-[var(--accent)]/90 hover:bg-[var(--accent)]/20 transition-all border border-[var(--accent)]/15 hover:border-[var(--accent)]/30"
              title="Send to agent for refinement">
              <Sparkles size={11} /> Refine with AI
            </button>
          )}
          {!draft?.finalized && (
            <button onClick={handleFinalize} disabled={finalizing}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium bg-emerald-500/10 text-emerald-400/90 hover:bg-emerald-500/20 transition-all border border-emerald-500/15 hover:border-emerald-500/30 disabled:opacity-50 disabled:cursor-not-allowed"
              title="Finalize and save to Desktop">
              {finalizing ? <><Loader2 size={11} className="animate-spin" /> Saving...</> : <><CheckCircle2 size={11} /> Finalize</>}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
