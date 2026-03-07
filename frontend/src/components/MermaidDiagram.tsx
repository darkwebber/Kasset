"use client";

import { useEffect, useRef, useState } from "react";

let mermaidInitialized = false;

async function getMermaid() {
  const m = (await import("mermaid")).default;
  if (!mermaidInitialized) {
    m.initialize({
      startOnLoad: false,
      theme: "dark",
      themeVariables: {
        primaryColor: "#1a1a2e",
        primaryTextColor: "#e0e0e0",
        primaryBorderColor: "#444",
        lineColor: "#888",
        secondaryColor: "#16213e",
        tertiaryColor: "#0f3460",
        fontFamily: "ui-monospace, monospace",
        fontSize: "13px",
      },
      flowchart: { curve: "basis", padding: 12 },
      securityLevel: "loose",
    });
    mermaidInitialized = true;
  }
  return m;
}

let renderCounter = 0;

export default function MermaidDiagram({ code }: { code: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const id = `mermaid-${++renderCounter}`;

    (async () => {
      try {
        const m = await getMermaid();
        const { svg: rendered } = await m.render(id, code.trim());
        if (!cancelled) {
          setSvg(rendered);
          setError(null);
        }
      } catch (e: any) {
        if (!cancelled) {
          setError(e?.message || "Mermaid render error");
          setSvg(null);
        }
      }
    })();

    return () => { cancelled = true; };
  }, [code]);

  if (error) {
    return (
      <div className="my-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-mono">
        <div className="text-[10px] uppercase tracking-wider text-red-400/60 mb-1">Mermaid Error</div>
        {error}
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="my-2 p-4 rounded-lg bg-white/[0.03] border border-white/5 flex items-center justify-center">
        <div className="w-4 h-4 border-2 border-white/20 border-t-white/60 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="my-2 p-4 rounded-lg bg-white/[0.03] border border-white/5 overflow-x-auto [&_svg]:max-w-full [&_svg]:h-auto"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
