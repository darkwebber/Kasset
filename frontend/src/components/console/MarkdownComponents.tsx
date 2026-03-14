"use client";

import React, { useState, useMemo } from "react";
import type { Components } from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Copy, Check } from "lucide-react";
import DraftBlock from "../chat/DraftBlock";
import dynamic from "next/dynamic";
const MermaidDiagram = dynamic(() => import("../MermaidDiagram"), { ssr: false });

// ─── CopyButton (inline helper) ────────────────────────
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
      className="absolute top-1 right-1 p-1 rounded bg-white/5 text-white/25 hover:text-white/60 hover:bg-white/10 transition-all opacity-0 group-hover/code:opacity-100"
    >
      {copied ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
    </button>
  );
}

// ─── HtmlPreviewBlock ──────────────────────────────────
function HtmlPreviewBlock({ code }: { code: string }) {
  const [showPreview, setShowPreview] = useState(false);
  return (
    <div className="relative group/code my-3">
      <div className="flex items-center justify-between px-4 py-1.5 bg-white/5 border-b border-white/5 rounded-t-md">
        <div className="flex items-center gap-2"><span className="text-[10px] uppercase tracking-widest text-white/30 font-mono">html</span><span className="text-[8px] text-white/15 font-mono">AI generated</span></div>
        <button
          onClick={() => setShowPreview(p => !p)}
          className="text-[10px] font-mono px-2 py-0.5 rounded bg-[var(--accent)]/10 text-[var(--accent)]/70 hover:bg-[var(--accent)]/20 hover:text-[var(--accent)] transition-all"
        >
          {showPreview ? "⟨/⟩ Code" : "▶ Preview"}
        </button>
      </div>
      <CopyButton text={code} />
      {showPreview ? (
        <div className="rounded-b-md overflow-hidden border border-white/6 border-t-0">
          <iframe
            srcDoc={code}
            sandbox="allow-scripts"
            className="w-full bg-white rounded-b-md"
            style={{ minHeight: 200, maxHeight: 500, border: "none" }}
            title="HTML Preview"
          />
        </div>
      ) : (
        <SyntaxHighlighter
          style={vscDarkPlus}
          language="html"
          PreTag="div"
          customStyle={{
            margin: 0, borderRadius: "0 0 6px 6px",
            background: "rgba(0,0,0,0.6)", fontSize: "13px",
            border: "1px solid rgba(255,255,255,0.06)", borderTop: "none",
          }}
          codeTagProps={{ style: { fontFamily: "var(--font-mono), monospace" } }}
        >
          {code}
        </SyntaxHighlighter>
      )}
    </div>
  );
}

// ─── Markdown component overrides for ReactMarkdown ────
export function useMarkdownComponents(): Components {
  return useMemo<Components>(() => ({
    code({ className, children, ...props }) {
      const match = /language-(\w+)/.exec(className || "");
      const codeStr = String(children ?? "").replace(/\n$/, "");
      // Skip empty or "undefined" code blocks (caused by broken model output)
      if (!codeStr || codeStr === "undefined" || codeStr === "null") {
        return null;
      }
      if (match) {
        // Render mermaid diagrams as actual diagrams
        if (match[1] === "mermaid") {
          return <MermaidDiagram code={codeStr} />;
        }
        // Render text/draft/email/markdown as interactive DraftBlock
        const DRAFT_LANGS = new Set(["text", "draft", "email", "markdown", "md"]);
        if (DRAFT_LANGS.has(match[1]) && codeStr.length > 20) {
          return <DraftBlock content={codeStr} language={match[1]} />;
        }
        // Render HTML code blocks with live preview toggle
        if (match[1] === "html" && codeStr.includes("<") && codeStr.length > 40) {
          return <HtmlPreviewBlock code={codeStr} />;
        }
        return (
          <div className="relative group my-3">
            <div className="flex items-center justify-between px-4 py-1.5 bg-white/5 border-b border-white/5 rounded-t-md">
              <div className="flex items-center gap-2"><span className="text-[10px] uppercase tracking-widest text-white/30 font-mono">{match[1]}</span><span className="text-[8px] text-white/15 font-mono">AI generated</span></div>
            </div>
            <CopyButton text={codeStr} />
            <SyntaxHighlighter
              style={vscDarkPlus}
              language={match[1]}
              PreTag="div"
              customStyle={{
                margin: 0,
                borderRadius: "0 0 6px 6px",
                background: "rgba(0,0,0,0.6)",
                fontSize: "13px",
                border: "1px solid rgba(255,255,255,0.06)",
                borderTop: "none",
              }}
              codeTagProps={{ style: { fontFamily: "var(--font-mono), monospace" } }}
            >
              {codeStr}
            </SyntaxHighlighter>
          </div>
        );
      }
      return <code className={className} {...props}>{children}</code>;
    },
    table({ children }) {
      return <div className="overflow-x-auto my-4"><table>{children}</table></div>;
    },
    blockquote({ children }) {
      return (
        <blockquote className="border-l-2 border-[var(--accent)]/40 pl-4 my-3 text-white/60 italic">
          {children}
        </blockquote>
      );
    },
    p({ children, ...props }) {
      // Auto-embed YouTube links that appear as the sole content of a paragraph
      const childArr = React.Children.toArray(children);
      if (childArr.length === 1 && typeof childArr[0] === "object" && (childArr[0] as any)?.type === "a") {
        const link = childArr[0] as React.ReactElement<{ href?: string }>;
        const href = link.props?.href || "";
        const ytMatch = href.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]+)/);
        if (ytMatch) {
          return (
            <div className="my-3 rounded-lg overflow-hidden border border-white/8" style={{ background: "#0d1117" }}>
              <iframe
                src={`https://www.youtube.com/embed/${ytMatch[1]}`}
                className="w-full rounded-lg"
                style={{ height: 315, border: "none" }}
                title="YouTube video"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                sandbox="allow-scripts allow-same-origin allow-popups"
              />
            </div>
          );
        }
      }
      return <p {...props}>{children}</p>;
    },
    a({ href, children, ...props }) {
      return (
        <a href={href} target="_blank" rel="noopener noreferrer"
          className="text-[var(--accent)]/80 hover:text-[var(--accent)] underline underline-offset-2 decoration-[var(--accent)]/30 transition-colors"
          {...props}
        >
          {children}
        </a>
      );
    },
  }), []);
}
