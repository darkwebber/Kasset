"use client";

import React, { useState, useRef, useCallback } from "react";
import { ChevronDown } from "lucide-react";
import { ErrorBoundary } from "../ErrorBoundary";
import { getToolMeta } from "./toolMeta";
import type { ToolCallSegment } from "./types";

const ToolCallCard = React.memo(function ToolCallCard({ segment, onConsent }: { segment: ToolCallSegment; onConsent?: (id: string, approved: boolean) => void }) {
  const [expanded, setExpanded] = useState(false);
  const [iframeHeight, setIframeHeight] = useState(400);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const handleIframeLoad = useCallback(() => {
    try {
      const iframe = iframeRef.current;
      if (!iframe?.contentDocument?.body) return;
      const h = iframe.contentDocument.body.scrollHeight;
      if (h > 50) setIframeHeight(Math.min(Math.max(h + 16, 200), 800));
    } catch { /* cross-origin — keep default */ }
  }, []);
  const meta = getToolMeta(segment.name);
  const isRunning = segment.status === "running";
  const isPreparing = segment.status === "preparing";
  const isConsent = segment.status === "consent";
  const hasImages = segment.images && segment.images.length > 0;
  const hasHtml = !!segment.html;

  const formatArgs = (args: Record<string, any>) => {
    const entries = Object.entries(args);
    if (entries.length === 0) return null;
    const [, firstVal] = entries[0];
    const valStr = typeof firstVal === "string" ? firstVal : JSON.stringify(firstVal);
    return { value: valStr, extra: entries.length > 1 ? entries.length - 1 : 0 };
  };

  const argInfo = formatArgs(segment.args);

  return (
    <div className="my-2 rounded-lg border overflow-hidden transition-all"
      style={{ borderColor: `${meta.color}20` }}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2.5 px-3 py-2 text-left transition-all hover:bg-white/[0.02]"
      >
        <div className="flex items-center justify-center w-6 h-6 rounded-md"
          style={{ background: `${meta.color}15`, color: meta.color }}
        >
          {isRunning || isPreparing ? <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" /> : meta.icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium" style={{ color: isConsent ? '#f59e0b' : meta.color }}>
              {isPreparing ? "Writing code…" : isRunning ? meta.label + "..." : isConsent ? "Approval Required" : meta.label}
            </span>
            {argInfo && (
              <span className="text-[10px] text-white/25 font-mono truncate max-w-[300px]">
                {argInfo.value.length > 60 ? argInfo.value.slice(0, 60) + "..." : argInfo.value}
              </span>
            )}
          </div>
        </div>
        {segment.result && (
          <ChevronDown size={12} className={`text-white/20 transition-transform ${expanded ? "rotate-0" : "-rotate-90"}`} />
        )}
      </button>

      {/* Live code preview during preparation */}
      {isPreparing && segment.args?.code && (
        <div className="px-3 pb-2.5">
          <div className="bg-black/40 rounded border border-white/5 p-2.5 text-[11px] text-[var(--accent)]/60 font-mono max-h-48 overflow-y-auto crt-scroll whitespace-pre-wrap leading-relaxed">
            {segment.args.code}
            <span className="inline-block w-[2px] h-[14px] bg-[var(--accent)] animate-blink ml-0.5 align-text-bottom" />
          </div>
        </div>
      )}

      {/* Expanded text result */}
      {expanded && segment.result && (
        <div className="px-3 pb-2.5 pt-0">
          <div className="bg-black/40 rounded border border-white/5 p-2.5 text-[11px] text-white/50 font-mono max-h-48 overflow-y-auto crt-scroll whitespace-pre-wrap leading-relaxed">
            {segment.result}
          </div>
        </div>
      )}

      {/* Consent approval buttons */}
      {isConsent && segment.consentId && (
        <div className="px-3 pb-3">
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
            <p className="text-[11px] text-white/60 mb-2">
              This command requires your approval:
            </p>
            <code className="block text-[11px] text-amber-400/90 font-mono bg-black/30 rounded px-2 py-1.5 mb-3">
              {segment.consentCommand || segment.args?.command || ''}
            </code>
            <div className="flex gap-2">
              <button
                onClick={() => onConsent?.(segment.consentId!, true)}
                className="px-3 py-1.5 rounded-md text-[11px] font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors"
              >
                Approve
              </button>
              <button
                onClick={() => onConsent?.(segment.consentId!, false)}
                className="px-3 py-1.5 rounded-md text-[11px] font-medium bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
              >
                Deny
              </button>
            </div>
          </div>
        </div>
      )}

      {/* HTML artifact (Plotly, custom tools) — rendered in sandboxed iframe */}
      {hasHtml && (
        <div className="px-3 pb-3">
          <ErrorBoundary inline fallbackMessage="Failed to render visualization">
            <div className="rounded-lg overflow-hidden border border-white/5" style={{ background: '#0d1117' }}>
              <iframe
                ref={iframeRef}
                srcDoc={segment.html}
                sandbox="allow-scripts"
                className="w-full rounded-lg"
                style={{ height: iframeHeight, border: 'none', background: '#0d1117' }}
                title="Interactive visualization"
                onLoad={handleIframeLoad}
              />
            </div>
          </ErrorBoundary>
        </div>
      )}

      {/* Images always visible inline — not hidden behind expand */}
      {hasImages && (
        <div className="px-3 pb-3 space-y-2">
          {segment.images!.map((src, i) => (
            <div key={i} className="rounded-lg overflow-hidden bg-black/60 border border-white/5">
              <img src={src} alt={`Plot ${i + 1}`} className="w-full max-h-[400px] object-contain rounded-lg" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
});

export default ToolCallCard;
