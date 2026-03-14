/**
 * BroadcastChannel wrapper for main window ↔ pop-out canvas sync.
 * 
 * Messages:
 *  - IMAGE_UPDATE: { imageUrl, editHistory, historyIndex }
 *  - TOOL_CHANGE: { activeTool }
 *  - ZOOM_CHANGE: { zoomLevel, panOffset }
 *  - ANNOTATIONS_UPDATE: { annotations }
 *  - SLIDERS_UPDATE: { pendingSliders }
 *  - CANVAS_CLOSE: pop-out closed, return to inline
 *  - STATE_SYNC: full state snapshot (on connect)
 */

export type CanvasMessageType =
  | "IMAGE_UPDATE"
  | "TOOL_CHANGE"
  | "ZOOM_CHANGE"
  | "SELECTION"
  | "CANVAS_CLOSE"
  | "STATE_SYNC"
  | "REQUEST_SYNC";

export interface CanvasMessage {
  type: CanvasMessageType;
  payload?: any;
  source: "main" | "popout";
  ts: number;
}

const CHANNEL_NAME = "kasset-canvas-sync";

let _channel: BroadcastChannel | null = null;

export function getCanvasChannel(): BroadcastChannel {
  if (!_channel) {
    _channel = new BroadcastChannel(CHANNEL_NAME);
  }
  return _channel;
}

export function postCanvasMessage(type: CanvasMessageType, payload: any = {}, source: "main" | "popout" = "main") {
  try {
    getCanvasChannel().postMessage({
      type,
      payload,
      source,
      ts: Date.now(),
    } satisfies CanvasMessage);
  } catch {
    // Channel may be closed
  }
}

export function closeCanvasChannel() {
  if (_channel) {
    _channel.close();
    _channel = null;
  }
}
