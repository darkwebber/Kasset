"use client";

import React from "react";
import { AlertTriangle, RefreshCw, MessageSquare, Wifi } from "lucide-react";

interface ErrorRecoveryProps {
  error: string;
  onRetry?: () => void;
  onNewChat?: () => void;
}

/** Maps raw error strings to user-friendly messages + recovery hints. */
function classifyError(error: string): { title: string; description: string; icon: React.ReactNode; actions: ("retry" | "new")[] } {
  const lower = error.toLowerCase();

  if (lower.includes("connection") || lower.includes("fetch") || lower.includes("network") || lower.includes("econnrefused")) {
    return {
      title: "Connection Lost",
      description: "Couldn't reach the backend. Check that the server is running.",
      icon: <Wifi size={14} />,
      actions: ["retry"],
    };
  }
  if (lower.includes("timeout") || lower.includes("timed out")) {
    return {
      title: "Request Timed Out",
      description: "The model took too long to respond. This can happen with complex prompts.",
      icon: <AlertTriangle size={14} />,
      actions: ["retry"],
    };
  }
  if (lower.includes("context") || lower.includes("token") || lower.includes("too long")) {
    return {
      title: "Context Limit Reached",
      description: "The conversation is too long for the model. Start a new chat to continue.",
      icon: <MessageSquare size={14} />,
      actions: ["new"],
    };
  }
  if (lower.includes("out of memory") || lower.includes("oom") || lower.includes("cuda")) {
    return {
      title: "Out of Memory",
      description: "The model ran out of GPU/system memory. Try a shorter prompt or restart the server.",
      icon: <AlertTriangle size={14} />,
      actions: ["retry", "new"],
    };
  }
  // Generic fallback
  return {
    title: "Something Went Wrong",
    description: error.length > 120 ? error.slice(0, 120) + "…" : error,
    icon: <AlertTriangle size={14} />,
    actions: ["retry"],
  };
}

export default function ErrorRecovery({ error, onRetry, onNewChat }: ErrorRecoveryProps) {
  const info = classifyError(error);

  return (
    <div className="my-2 rounded-lg border border-red-500/15 bg-red-500/[0.04] px-4 py-3">
      <div className="flex items-start gap-2.5">
        <div className="mt-0.5 text-red-400/70">{info.icon}</div>
        <div className="flex-1 min-w-0">
          <p className="text-[12px] font-medium text-red-400/90">{info.title}</p>
          <p className="text-[11px] text-white/40 mt-0.5 leading-relaxed">{info.description}</p>
          <div className="flex items-center gap-2 mt-2.5">
            {info.actions.includes("retry") && onRetry && (
              <button
                onClick={onRetry}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[10px] font-medium bg-white/[0.06] text-white/60 hover:bg-white/[0.1] hover:text-white/80 transition-all"
              >
                <RefreshCw size={10} />
                Retry
              </button>
            )}
            {info.actions.includes("new") && onNewChat && (
              <button
                onClick={onNewChat}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[10px] font-medium bg-white/[0.06] text-white/60 hover:bg-white/[0.1] hover:text-white/80 transition-all"
              >
                <MessageSquare size={10} />
                New Chat
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
