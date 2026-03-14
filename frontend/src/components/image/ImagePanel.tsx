"use client";

import React, { useRef, useState, useCallback, useEffect } from "react";
import {
  Move, MousePointer, Pen, Crop, Pipette,
  ZoomIn, ZoomOut, Maximize2, SplitSquareVertical,
  ExternalLink, X, Info,
} from "lucide-react";
import { useImageStore, type CanvasTool } from "@/stores/imageStore";

// ─────────────────────────────────────────────
// Coordinate helpers: client coords → image-space
// ─────────────────────────────────────────────
function useCoords(
  containerRef: React.RefObject<HTMLDivElement | null>,
  zoomLevel: number,
  panOffset: { x: number; y: number },
  imgW: number,
  imgH: number,
) {
  const toImage = useCallback((cx: number, cy: number) => {
    const r = containerRef.current?.getBoundingClientRect();
    if (!r || !imgW || !imgH) return { x: 0, y: 0 };
    const rx = cx - r.left - r.width / 2 - panOffset.x;
    const ry = cy - r.top - r.height / 2 - panOffset.y;
    return {
      x: Math.max(0, Math.min(imgW, Math.round(rx / zoomLevel + imgW / 2))),
      y: Math.max(0, Math.min(imgH, Math.round(ry / zoomLevel + imgH / 2))),
    };
  }, [containerRef, zoomLevel, panOffset, imgW, imgH]);

  const toScreen = useCallback((ix: number, iy: number) => {
    const r = containerRef.current?.getBoundingClientRect();
    if (!r) return { x: 0, y: 0 };
    return {
      x: (ix - imgW / 2) * zoomLevel + r.width / 2 + panOffset.x,
      y: (iy - imgH / 2) * zoomLevel + r.height / 2 + panOffset.y,
    };
  }, [containerRef, zoomLevel, panOffset, imgW, imgH]);

  return { toImage, toScreen };
}

// ─────────────────────────────────────────────
// Tool definitions
// ─────────────────────────────────────────────
const TOOLS: { id: CanvasTool; icon: React.ReactNode; label: string; cursor: string }[] = [
  { id: "pan", icon: <Move size={14} />, label: "Pan", cursor: "grab" },
  { id: "select", icon: <MousePointer size={14} />, label: "Select", cursor: "crosshair" },
  { id: "lasso", icon: <Pen size={14} />, label: "Freeform", cursor: "crosshair" },
  { id: "crop", icon: <Crop size={14} />, label: "Crop", cursor: "crosshair" },
  { id: "eyedropper", icon: <Pipette size={14} />, label: "Pick Color", cursor: "crosshair" },
];

// ─────────────────────────────────────────────
// ImagePanel — unified canvas component
// Works identically embedded in CRT or in pop-out window.
// ─────────────────────────────────────────────
interface ImagePanelProps {
  standalone?: boolean;       // true in pop-out window
  onClose?: () => void;       // close canvas (hide or close window)
  onPopOut?: () => void;      // pop out to new window
  showPopOut?: boolean;       // show pop-out button
}

export default function ImagePanel({ standalone, onClose, onPopOut, showPopOut }: ImagePanelProps) {
  const {
    currentImageUrl, originalImageUrl, zoomLevel, panOffset,
    activeTool, selection, showBeforeAfter, beforeAfterPosition,
    imageWidth, imageHeight, editHistory, historyIndex,
    setZoomLevel, setPanOffset, setActiveTool, setSelection,
    setImageDimensions, toggleBeforeAfter, setBeforeAfterPosition,
    zoomIn, zoomOut, zoomFit, hideCanvas,
  } = useImageStore();

  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const { toImage, toScreen } = useCoords(containerRef, zoomLevel, panOffset, imageWidth, imageHeight);

  // ─── Local interaction state ───
  const [hovered, setHovered] = useState(false);
  const [toolbarPinned, setToolbarPinned] = useState(false);
  const showToolbar = hovered || toolbarPinned;

  // Pan state
  const isPanning = useRef(false);
  const panStart = useRef({ x: 0, y: 0 });
  const panOffsetStart = useRef({ x: 0, y: 0 });

  // Selection state
  const [selRect, setSelRect] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  // Lasso path is stored in image-space coordinates to avoid viewport/zoom drift.
  const [lassoPath, setLassoPath] = useState<{ x: number; y: number }[]>([]);
  const isDrawing = useRef(false);

  // Before/after drag state
  const [baDragging, setBaDragging] = useState(false);

  // ─── Auto-fit on first load ───
  useEffect(() => {
    if (!currentImageUrl) return;
    const img = new Image();
    img.onload = () => {
      setImageDimensions(img.naturalWidth, img.naturalHeight);
      if (containerRef.current) {
        const r = containerRef.current.getBoundingClientRect();
        const fit = Math.min(r.width / img.naturalWidth, r.height / img.naturalHeight) * 0.92;
        setZoomLevel(Math.min(fit, 1));
        setPanOffset({ x: 0, y: 0 });
      }
    };
    img.src = currentImageUrl;
  }, [currentImageUrl]);

  // ─── Clear selection on tool change ───
  useEffect(() => {
    setSelRect(null);
    setLassoPath([]);
    setSelection(null);
  }, [activeTool]);

  // ─── Native wheel zoom (passive: false) ───
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      const factor = e.deltaY > 0 ? 0.9 : 1.1;
      const z = Math.max(0.05, Math.min(20, zoomLevel * factor));
      setZoomLevel(z);
    };
    el.addEventListener("wheel", handler, { passive: false });
    return () => el.removeEventListener("wheel", handler);
  }, [zoomLevel, setZoomLevel]);

  // ─── Pointer handlers ───
  const onPointerDown = useCallback((e: React.PointerEvent) => {
    const el = e.currentTarget as HTMLElement;
    el.setPointerCapture(e.pointerId);

    if (activeTool === "pan") {
      isPanning.current = true;
      panStart.current = { x: e.clientX, y: e.clientY };
      panOffsetStart.current = { ...panOffset };
      return;
    }

    if (activeTool === "select" || activeTool === "crop") {
      const r = containerRef.current?.getBoundingClientRect();
      if (!r) return;
      const sx = e.clientX - r.left;
      const sy = e.clientY - r.top;
      setSelRect({ x1: sx, y1: sy, x2: sx, y2: sy });
      isDrawing.current = true;
      return;
    }

    if (activeTool === "lasso") {
      const pt = toImage(e.clientX, e.clientY);
      setLassoPath([pt]);
      isDrawing.current = true;
      return;
    }

    if (activeTool === "eyedropper") {
      const pt = toImage(e.clientX, e.clientY);
      setSelection({ type: "color", data: pt });
      return;
    }
  }, [activeTool, panOffset, toImage, setSelection]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (isPanning.current) {
      const dx = e.clientX - panStart.current.x;
      const dy = e.clientY - panStart.current.y;
      setPanOffset({ x: panOffsetStart.current.x + dx, y: panOffsetStart.current.y + dy });
      return;
    }

    if (!isDrawing.current) return;
    const r = containerRef.current?.getBoundingClientRect();
    if (!r) return;
    const sx = e.clientX - r.left;
    const sy = e.clientY - r.top;

    if (activeTool === "select" || activeTool === "crop") {
      setSelRect((prev) => prev ? { ...prev, x2: sx, y2: sy } : null);
    } else if (activeTool === "lasso") {
      const pt = toImage(e.clientX, e.clientY);
      setLassoPath((prev) => {
        if (prev.length === 0) return [pt];
        const last = prev[prev.length - 1];
        // Drop near-duplicate points to keep the polygon clean while preserving shape.
        if (Math.hypot(pt.x - last.x, pt.y - last.y) < 1.5) return prev;
        return [...prev, pt];
      });
    }
  }, [activeTool, setPanOffset, toImage]);

  const onPointerUp = useCallback(() => {
    if (isPanning.current) {
      isPanning.current = false;
      return;
    }

    if (!isDrawing.current) return;
    isDrawing.current = false;

    if ((activeTool === "select" || activeTool === "crop") && selRect) {
      const r = containerRef.current?.getBoundingClientRect();
      if (!r) return;
      const x1 = Math.min(selRect.x1, selRect.x2);
      const y1 = Math.min(selRect.y1, selRect.y2);
      const x2 = Math.max(selRect.x1, selRect.x2);
      const y2 = Math.max(selRect.y1, selRect.y2);
      if (x2 - x1 < 4 || y2 - y1 < 4) {
        setSelRect(null);
        setSelection(null);
        return;
      }
      const tl = toImage(x1 + (r?.left ?? 0), y1 + (r?.top ?? 0));
      const br = toImage(x2 + (r?.left ?? 0), y2 + (r?.top ?? 0));
      setSelection({
        type: "rect",
        data: { x: tl.x, y: tl.y, w: br.x - tl.x, h: br.y - tl.y, tool: activeTool },
      });
    }

    if (activeTool === "lasso" && lassoPath.length > 4) {
      const points = [...lassoPath];
      const first = points[0];
      const last = points[points.length - 1];
      // Ensure the polygon closes explicitly so there is no long implicit closing edge.
      if (first && last && Math.hypot(first.x - last.x, first.y - last.y) > 2) {
        points.push(first);
      }
      setSelection({ type: "lasso", data: { points } });
    }
  }, [activeTool, selRect, lassoPath, toImage, setSelection]);

  // ─── Before/After slider ───
  const onBAPointerDown = useCallback((e: React.PointerEvent) => {
    e.stopPropagation();
    setBaDragging(true);
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }, []);
  const onBAPointerMove = useCallback((e: React.PointerEvent) => {
    if (!baDragging) return;
    const r = containerRef.current?.getBoundingClientRect();
    if (!r) return;
    const pct = ((e.clientX - r.left) / r.width) * 100;
    setBeforeAfterPosition(Math.max(0, Math.min(100, pct)));
  }, [baDragging, setBeforeAfterPosition]);
  const onBAPointerUp = useCallback(() => setBaDragging(false), []);

  // ─── Cursor ───
  const cursor = (() => {
    if (isPanning.current) return "grabbing";
    const t = TOOLS.find((t) => t.id === activeTool);
    return t?.cursor ?? "default";
  })();

  const lassoScreenPath = lassoPath.map((p) => toScreen(p.x, p.y));

  if (!currentImageUrl) return null;

  return (
    <div
      className="relative w-full h-full select-none"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* ─── Image viewport ─── */}
      <div
        ref={containerRef}
        className="absolute inset-0 overflow-hidden"
        style={{ cursor }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        {/* Checkerboard for transparency */}
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage:
              "linear-gradient(45deg,#666 25%,transparent 25%),linear-gradient(-45deg,#666 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#666 75%),linear-gradient(-45deg,transparent 75%,#666 75%)",
            backgroundSize: "16px 16px",
            backgroundPosition: "0 0,0 8px,8px -8px,-8px 0",
          }}
        />

        {/* Image layer */}
        <div
          className="absolute inset-0 flex items-center justify-center"
          style={{
            transform: `translate(${panOffset.x}px,${panOffset.y}px) scale(${zoomLevel})`,
            transformOrigin: "center center",
          }}
        >
          {/* Before/After: show original clipped to left portion */}
          {showBeforeAfter && originalImageUrl && (
            <img
              src={originalImageUrl}
              alt="Before"
              className="absolute max-w-none pointer-events-none"
              draggable={false}
              style={{
                imageRendering: zoomLevel > 3 ? "pixelated" : "auto",
                clipPath: `inset(0 ${100 - beforeAfterPosition}% 0 0)`,
              }}
            />
          )}
          <img
            ref={imgRef}
            src={currentImageUrl}
            alt="Editing"
            className="max-w-none pointer-events-none"
            draggable={false}
            style={{
              imageRendering: zoomLevel > 3 ? "pixelated" : "auto",
              ...(showBeforeAfter ? { clipPath: `inset(0 0 0 ${beforeAfterPosition}%)` } : {}),
            }}
          />
        </div>

        {/* Before/After divider line */}
        {showBeforeAfter && (
          <div
            className="absolute top-0 bottom-0 z-20"
            style={{ left: `${beforeAfterPosition}%`, width: 3, cursor: "ew-resize" }}
            onPointerDown={onBAPointerDown}
            onPointerMove={onBAPointerMove}
            onPointerUp={onBAPointerUp}
          >
            <div className="w-full h-full bg-white/60" />
            <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 left-1/2 w-6 h-6 rounded-full bg-white/80 border-2 border-black/20 flex items-center justify-center">
              <span className="text-[9px] text-black/60 font-bold">↔</span>
            </div>
          </div>
        )}

        {/* Selection overlay — rect */}
        {selRect && (activeTool === "select" || activeTool === "crop") && (() => {
          const x = Math.min(selRect.x1, selRect.x2);
          const y = Math.min(selRect.y1, selRect.y2);
          const w = Math.abs(selRect.x2 - selRect.x1);
          const h = Math.abs(selRect.y2 - selRect.y1);
          return (
            <>
              <div className="absolute inset-0 bg-black/40 pointer-events-none z-10"
                style={{ clipPath: `polygon(0 0,100% 0,100% 100%,0 100%,0 0,${x}px ${y}px,${x}px ${y + h}px,${x + w}px ${y + h}px,${x + w}px ${y}px,${x}px ${y}px)` }}
              />
              <div className="absolute border border-white/70 border-dashed pointer-events-none z-10"
                style={{ left: x, top: y, width: w, height: h }}
              />
              {w > 30 && h > 20 && (
                <div className="absolute z-10 pointer-events-none text-[10px] font-mono text-white/70 bg-black/50 px-1 rounded"
                  style={{ left: x, top: y - 16 }}
                >
                  {Math.round(w / zoomLevel)}×{Math.round(h / zoomLevel)}
                </div>
              )}
            </>
          );
        })()}

        {/* Selection overlay — lasso */}
        {lassoPath.length > 2 && activeTool === "lasso" && (
          <svg className="absolute inset-0 w-full h-full pointer-events-none z-10">
            <polyline
              points={lassoScreenPath.map((p) => `${p.x},${p.y}`).join(" ")}
              fill="none"
              stroke="rgba(255,255,255,0.7)"
              strokeWidth="1.5"
              strokeDasharray="4 3"
            />
            {!isDrawing.current && lassoPath.length > 4 && (
              <polygon
                points={lassoScreenPath.map((p) => `${p.x},${p.y}`).join(" ")}
                fill="rgba(var(--accent-rgb, 168,85,247),0.15)"
                stroke="rgba(255,255,255,0.8)"
                strokeWidth="1.5"
                strokeDasharray="4 3"
              />
            )}
          </svg>
        )}
      </div>

      {/* ─── Floating Toolbar ─── */}
      <div
        className={`absolute top-2 left-1/2 -translate-x-1/2 z-30 transition-all duration-200 ${
          showToolbar ? "opacity-100 translate-y-0" : "opacity-0 -translate-y-2 pointer-events-none"
        }`}
      >
        <div className="flex items-center gap-0.5 bg-black/70 backdrop-blur-md rounded-lg px-1.5 py-1 border border-white/10 shadow-xl">
          {/* Tool buttons */}
          {TOOLS.map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTool(t.id)}
              className={`p-1.5 rounded-md transition-colors ${
                activeTool === t.id
                  ? "bg-white/15 text-white"
                  : "text-white/40 hover:text-white/70 hover:bg-white/5"
              }`}
              title={t.label}
            >
              {t.icon}
            </button>
          ))}

          <div className="w-px h-5 bg-white/10 mx-1" />

          {/* Zoom controls */}
          <button onClick={zoomOut} className="p-1.5 text-white/40 hover:text-white/70 rounded-md hover:bg-white/5" title="Zoom Out">
            <ZoomOut size={14} />
          </button>
          <span className="text-[10px] text-white/50 font-mono w-9 text-center tabular-nums">
            {Math.round(zoomLevel * 100)}%
          </span>
          <button onClick={zoomIn} className="p-1.5 text-white/40 hover:text-white/70 rounded-md hover:bg-white/5" title="Zoom In">
            <ZoomIn size={14} />
          </button>
          <button onClick={zoomFit} className="p-1.5 text-white/40 hover:text-white/70 rounded-md hover:bg-white/5" title="Fit">
            <Maximize2 size={14} />
          </button>

          <div className="w-px h-5 bg-white/10 mx-1" />

          {/* Before/After */}
          <button
            onClick={toggleBeforeAfter}
            className={`p-1.5 rounded-md transition-colors ${
              showBeforeAfter ? "bg-white/15 text-white" : "text-white/40 hover:text-white/70 hover:bg-white/5"
            }`}
            title="Before / After"
          >
            <SplitSquareVertical size={14} />
          </button>

          {/* Image info */}
          {imageWidth > 0 && (
            <>
              <div className="w-px h-5 bg-white/10 mx-1" />
              <span className="text-[9px] text-white/30 font-mono flex items-center gap-1">
                <Info size={9} />
                {imageWidth}×{imageHeight}
              </span>
            </>
          )}

          {/* Pop-out */}
          {showPopOut && onPopOut && (
            <>
              <div className="w-px h-5 bg-white/10 mx-1" />
              <button onClick={onPopOut} className="p-1.5 text-white/40 hover:text-white/70 rounded-md hover:bg-white/5" title="Pop out">
                <ExternalLink size={14} />
              </button>
            </>
          )}

          {/* Close */}
          {onClose && (
            <button onClick={onClose} className="p-1.5 text-white/40 hover:text-red-400/70 rounded-md hover:bg-white/5" title="Close">
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* ─── Selection action bar ─── */}
      {selection && (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-30">
          <div className="flex items-center gap-2 bg-black/80 backdrop-blur-md rounded-lg px-3 py-2 border border-white/10 shadow-xl">
            <span className="text-[11px] text-white/60 font-mono">
              {selection.type === "rect"
                ? `${selection.data.w}×${selection.data.h}px`
                : selection.type === "lasso"
                ? `${selection.data.points.length} points`
                : "Color sampled"}
            </span>
            <button
              onClick={() => { setSelection(null); setSelRect(null); setLassoPath([]); }}
              className="text-[11px] text-white/40 hover:text-white/70 px-2 py-0.5 rounded hover:bg-white/5"
            >
              Clear
            </button>
            {selection.type !== "color" && (
              <span className="text-[10px] text-white/30 italic">
                Region attached to next message
              </span>
            )}
          </div>
        </div>
      )}

      {/* ─── History filmstrip ─── */}
      {editHistory.length > 1 && (
        <div className="absolute bottom-3 left-3 z-30 flex items-center gap-1">
          {editHistory.slice(-6).map((entry, i) => {
            const globalIdx = editHistory.length - 6 + i;
            const idx = Math.max(0, globalIdx);
            const isActive = idx === historyIndex;
            return (
              <button
                key={entry.timestamp}
                onClick={() => {
                  useImageStore.getState().setHistoryIndex(idx);
                  useImageStore.getState().setCurrentImage(entry.imageUrl);
                }}
                className={`w-8 h-8 rounded border overflow-hidden transition-all ${
                  isActive ? "border-white/50 ring-1 ring-white/20" : "border-white/10 opacity-50 hover:opacity-80"
                }`}
                title={entry.description || `Edit ${idx + 1}`}
              >
                <img src={entry.imageUrl} alt="" className="w-full h-full object-cover" />
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
