import { create } from "zustand";
import { useEffect, useRef } from "react";

// ─── Types ───────────────────────────────────────
export interface EditHistoryEntry {
  index: number;
  imageUrl: string;
  timestamp: number;
  description?: string;
}

export interface ImageSelection {
  type: "rect" | "lasso" | "color";
  data: any;
}

export type CanvasTool = "pan" | "select" | "lasso" | "crop" | "eyedropper";

// ─── State Interface ─────────────────────────────
interface ImageState {
  currentImageUrl: string | null;
  originalImageUrl: string | null;
  canvasActive: boolean;

  zoomLevel: number;
  panOffset: { x: number; y: number };

  activeTool: CanvasTool;
  selection: ImageSelection | null;

  editHistory: EditHistoryEntry[];
  historyIndex: number;

  showBeforeAfter: boolean;
  beforeAfterPosition: number;

  imageWidth: number;
  imageHeight: number;

  poppedOut: boolean;

  // ─── Actions ─────────────────────────────────
  setCurrentImage: (url: string | null) => void;
  setOriginalImage: (url: string | null) => void;
  showCanvas: () => void;
  hideCanvas: () => void;
  setZoomLevel: (z: number) => void;
  setPanOffset: (offset: { x: number; y: number }) => void;
  setActiveTool: (tool: CanvasTool) => void;
  setSelection: (sel: ImageSelection | null) => void;
  pushHistory: (entry: EditHistoryEntry) => void;
  setHistoryIndex: (i: number) => void;
  clearHistory: () => void;
  toggleBeforeAfter: () => void;
  setBeforeAfterPosition: (p: number) => void;
  setImageDimensions: (w: number, h: number) => void;
  resetCanvas: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  zoomFit: () => void;
  setPoppedOut: (v: boolean) => void;
}

const INITIAL_STATE = {
  currentImageUrl: null as string | null,
  originalImageUrl: null as string | null,
  canvasActive: false,
  zoomLevel: 1,
  panOffset: { x: 0, y: 0 },
  activeTool: "pan" as CanvasTool,
  selection: null as ImageSelection | null,
  editHistory: [] as EditHistoryEntry[],
  historyIndex: -1,
  showBeforeAfter: false,
  beforeAfterPosition: 50,
  imageWidth: 0,
  imageHeight: 0,
  poppedOut: false,
};

// ─── Store ───────────────────────────────────────
export const useImageStore = create<ImageState>((set, get) => ({
  ...INITIAL_STATE,

  setCurrentImage: (url) =>
    set((s) => {
      if (url && !s.originalImageUrl) {
        return { currentImageUrl: url, originalImageUrl: url, canvasActive: true };
      }
      return { currentImageUrl: url, canvasActive: url !== null };
    }),
  setOriginalImage: (url) => set({ originalImageUrl: url }),
  showCanvas: () => set({ canvasActive: true }),
  hideCanvas: () => set({ canvasActive: false, selection: null }),
  setZoomLevel: (z) => set({ zoomLevel: Math.max(0.05, Math.min(20, z)) }),
  setPanOffset: (offset) => set({ panOffset: offset }),
  setActiveTool: (tool) => set({ activeTool: tool, selection: null }),
  setSelection: (sel) => set({ selection: sel }),
  pushHistory: (entry) =>
    set((s) => ({
      editHistory: [...s.editHistory, entry],
      historyIndex: s.editHistory.length,
    })),
  setHistoryIndex: (i) => set({ historyIndex: i }),
  clearHistory: () => set({ editHistory: [], historyIndex: -1 }),
  toggleBeforeAfter: () => set((s) => ({ showBeforeAfter: !s.showBeforeAfter })),
  setBeforeAfterPosition: (p) => set({ beforeAfterPosition: p }),
  setImageDimensions: (w, h) => set({ imageWidth: w, imageHeight: h }),
  resetCanvas: () => set({ ...INITIAL_STATE }),
  zoomIn: () => set((s) => ({ zoomLevel: Math.min(20, s.zoomLevel * 1.25) })),
  zoomOut: () => set((s) => ({ zoomLevel: Math.max(0.05, s.zoomLevel / 1.25) })),
  zoomFit: () => {
    const s = get();
    let fitZoom = 1;
    if (s.imageWidth > 0 && s.imageHeight > 0) {
      fitZoom = Math.min(1, 800 / s.imageWidth, 600 / s.imageHeight) * 0.92;
    }
    set({ zoomLevel: fitZoom, panOffset: { x: 0, y: 0 } });
  },
  setPoppedOut: (v) => set({ poppedOut: v }),
}));

// ─── BroadcastChannel Sync Hook ─────────────────
// Call once in Console.tsx to keep pop-out canvas in sync.
export function useCanvasSync() {
  const channelRef = useRef<BroadcastChannel | null>(null);
  const prevSnap = useRef("");
  const remoteUpdate = useRef(false); // guard against feedback loops

  useEffect(() => {
    if (typeof window === "undefined" || typeof BroadcastChannel === "undefined") return;

    const ch = new BroadcastChannel("kasset-canvas-sync");
    channelRef.current = ch;

    ch.onmessage = (e) => {
      const msg = e.data;
      if (msg?.source === "main") return;
      const store = useImageStore.getState();

      switch (msg?.type) {
        case "REQUEST_SYNC": {
          const s = useImageStore.getState();
          ch.postMessage({
            type: "STATE_SYNC", source: "main", ts: Date.now(),
            payload: {
              currentImageUrl: s.currentImageUrl,
              originalImageUrl: s.originalImageUrl,
              editHistory: s.editHistory,
              historyIndex: s.historyIndex,
              zoomLevel: s.zoomLevel,
              panOffset: s.panOffset,
              activeTool: s.activeTool,
              showBeforeAfter: s.showBeforeAfter,
              beforeAfterPosition: s.beforeAfterPosition,
              imageWidth: s.imageWidth,
              imageHeight: s.imageHeight,
            },
          });
          break;
        }
        case "TOOL_CHANGE":
          remoteUpdate.current = true;
          store.setActiveTool(msg.payload?.activeTool);
          break;
        case "ZOOM_CHANGE":
          remoteUpdate.current = true;
          if (msg.payload?.zoomLevel != null) store.setZoomLevel(msg.payload.zoomLevel);
          if (msg.payload?.panOffset) store.setPanOffset(msg.payload.panOffset);
          break;
        case "SELECTION":
          remoteUpdate.current = true;
          store.setSelection(msg.payload?.selection ?? null);
          break;
        case "CANVAS_CLOSE":
          store.setPoppedOut(false);
          break;
      }
    };

    const unsub = useImageStore.subscribe((state) => {
      if (!state.poppedOut || !channelRef.current) return;
      // Skip broadcasting if this change was caused by a remote message
      if (remoteUpdate.current) {
        remoteUpdate.current = false;
        return;
      }
      const snap = JSON.stringify({
        img: state.currentImageUrl, hi: state.historyIndex,
        hl: state.editHistory.length, z: state.zoomLevel,
        px: state.panOffset.x, py: state.panOffset.y,
        t: state.activeTool, ba: state.showBeforeAfter,
      });
      if (snap === prevSnap.current) return;
      prevSnap.current = snap;

      channelRef.current!.postMessage({
        type: "IMAGE_UPDATE", source: "main", ts: Date.now(),
        payload: {
          currentImageUrl: state.currentImageUrl,
          originalImageUrl: state.originalImageUrl,
          editHistory: state.editHistory,
          historyIndex: state.historyIndex,
          zoomLevel: state.zoomLevel,
          panOffset: state.panOffset,
          activeTool: state.activeTool,
          showBeforeAfter: state.showBeforeAfter,
          imageWidth: state.imageWidth,
          imageHeight: state.imageHeight,
        },
      });
    });

    return () => { unsub(); ch.close(); channelRef.current = null; };
  }, []);
}
