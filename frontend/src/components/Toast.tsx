"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { X } from "lucide-react";

export interface ToastItem {
  id: string;
  message: string;
  undoAction?: () => void;
  durationMs?: number;
}

let _addToast: (toast: Omit<ToastItem, "id">) => void = () => {};

/** Global function to show a toast from anywhere */
export function showToast(message: string, undoAction?: () => void, durationMs = 5000) {
  _addToast({ message, undoAction, durationMs });
}

export default function ToastContainer() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const removeToast = useCallback((id: string) => {
    if (timers.current[id]) {
      clearTimeout(timers.current[id]);
      delete timers.current[id];
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((toast: Omit<ToastItem, "id">) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const item: ToastItem = { ...toast, id };
    setToasts((prev) => [...prev, item]);

    const dur = toast.durationMs || 5000;
    timers.current[id] = setTimeout(() => {
      removeToast(id);
    }, dur);
  }, [removeToast]);

  useEffect(() => {
    _addToast = addToast;
    return () => { _addToast = () => {}; };
  }, [addToast]);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[100] flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className="pointer-events-auto flex items-center gap-3 px-4 py-2.5 rounded-lg bg-[#1a1f2e] border border-white/10 shadow-2xl backdrop-blur-md animate-in slide-in-from-bottom-4 duration-200"
        >
          <span className="text-xs text-white/80 font-mono">{t.message}</span>
          {t.undoAction && (
            <button
              onClick={() => {
                t.undoAction?.();
                removeToast(t.id);
              }}
              className="text-[var(--accent)] text-xs font-bold uppercase tracking-wider hover:text-white transition-colors shrink-0"
            >
              Undo
            </button>
          )}
          <button
            onClick={() => removeToast(t.id)}
            className="text-white/20 hover:text-white/50 transition-colors shrink-0"
          >
            <X size={12} />
          </button>
        </div>
      ))}
    </div>
  );
}
