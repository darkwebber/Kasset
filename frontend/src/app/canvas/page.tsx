"use client";

import React, { useEffect, useState } from "react";
import { getCanvasChannel, postCanvasMessage, type CanvasMessage } from "@/lib/canvasChannel";
import { useImageStore } from "@/stores/imageStore";
import ImagePanel from "@/components/image/ImagePanel";

// ─── Hook: sync BroadcastChannel → local Zustand store ───
function usePopoutSync() {
  const [connected, setConnected] = useState(false);
  const store = useImageStore;
  const remoteUpdate = { current: false }; // guard against feedback loops

  useEffect(() => {
    const ch = getCanvasChannel();

    const handle = (e: MessageEvent<CanvasMessage>) => {
      const msg = e.data;
      if (msg.source === "popout") return;
      const s = store.getState();

      switch (msg.type) {
        case "STATE_SYNC":
        case "IMAGE_UPDATE": {
          remoteUpdate.current = true;
          const p = msg.payload;
          if (p.currentImageUrl != null) s.setCurrentImage(p.currentImageUrl);
          if (p.originalImageUrl != null) s.setOriginalImage(p.originalImageUrl);
          if (p.imageWidth && p.imageHeight) s.setImageDimensions(p.imageWidth, p.imageHeight);
          if (p.activeTool) s.setActiveTool(p.activeTool);
          if (p.zoomLevel != null) s.setZoomLevel(p.zoomLevel);
          if (p.panOffset) s.setPanOffset(p.panOffset);
          if (p.editHistory) {
            store.setState({ editHistory: p.editHistory, historyIndex: p.historyIndex ?? p.editHistory.length - 1 });
          }
          if (p.showBeforeAfter != null) store.setState({ showBeforeAfter: p.showBeforeAfter });
          setConnected(true);
          break;
        }
        case "TOOL_CHANGE":
          remoteUpdate.current = true;
          if (msg.payload?.activeTool) s.setActiveTool(msg.payload.activeTool);
          break;
        case "ZOOM_CHANGE":
          remoteUpdate.current = true;
          if (msg.payload?.zoomLevel != null) s.setZoomLevel(msg.payload.zoomLevel);
          if (msg.payload?.panOffset) s.setPanOffset(msg.payload.panOffset);
          break;
      }
    };

    ch.onmessage = handle;
    postCanvasMessage("REQUEST_SYNC", {}, "popout");

    // Broadcast local changes back to main — skip if change came from remote
    const unsub = store.subscribe((state, prev) => {
      if (remoteUpdate.current) {
        remoteUpdate.current = false;
        return;
      }
      if (state.activeTool !== prev.activeTool) {
        postCanvasMessage("TOOL_CHANGE", { activeTool: state.activeTool }, "popout");
      }
      if (state.zoomLevel !== prev.zoomLevel || state.panOffset !== prev.panOffset) {
        postCanvasMessage("ZOOM_CHANGE", { zoomLevel: state.zoomLevel, panOffset: state.panOffset }, "popout");
      }
      if (state.selection !== prev.selection) {
        postCanvasMessage("SELECTION", { selection: state.selection }, "popout");
      }
    });

    return () => {
      unsub();
      postCanvasMessage("CANVAS_CLOSE", {}, "popout");
    };
  }, []);

  // Notify main on window close
  useEffect(() => {
    const onUnload = () => postCanvasMessage("CANVAS_CLOSE", {}, "popout");
    window.addEventListener("beforeunload", onUnload);
    return () => window.removeEventListener("beforeunload", onUnload);
  }, []);

  return connected;
}

// ─── Pop-out Canvas Page ───
export default function PopOutCanvas() {
  const connected = usePopoutSync();
  const currentImageUrl = useImageStore((s) => s.currentImageUrl);

  if (!currentImageUrl) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-[#0a0a0a]">
        <div className="text-center space-y-3">
          <div className="w-12 h-12 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center mx-auto">
            <span className="text-2xl">🎨</span>
          </div>
          <p className="text-white/30 font-mono text-sm">
            {connected ? "Waiting for image..." : "Connecting to main window..."}
          </p>
          {!connected && (
            <div className="w-4 h-4 border-2 border-white/20 border-t-white/60 rounded-full animate-spin mx-auto" />
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      className="h-screen w-screen bg-[#0a0a0a] overflow-hidden"
      style={{ "--accent": "#f472b6", "--tint": "rgba(244,114,182,0.02)" } as React.CSSProperties}
    >
      <ImagePanel
        standalone
        onClose={() => window.close()}
      />
    </div>
  );
}
