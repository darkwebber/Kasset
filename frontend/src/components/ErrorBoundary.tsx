"use client";

import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

interface Props {
  children: ReactNode;
  fallbackMessage?: string;
  onReset?: () => void;
  inline?: boolean;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("[ErrorBoundary]", error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
  };

  render() {
    if (this.state.hasError) {
      if (this.props.inline) {
        return (
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-300/70 font-mono">
            <AlertTriangle size={12} className="shrink-0" />
            <span className="truncate">{this.props.fallbackMessage || "Render error"}</span>
            <button
              onClick={this.handleReset}
              className="ml-auto shrink-0 p-1 rounded hover:bg-red-500/20 transition-colors"
              title="Retry"
            >
              <RotateCcw size={12} />
            </button>
          </div>
        );
      }

      return (
        <div className="flex flex-col items-center justify-center gap-3 p-6 rounded-xl bg-red-500/5 border border-red-500/15 text-center">
          <div className="w-10 h-10 rounded-xl bg-red-500/10 border border-red-500/20 flex items-center justify-center">
            <AlertTriangle size={20} className="text-red-400" />
          </div>
          <div className="space-y-1">
            <p className="text-sm text-white/70 font-medium">
              {this.props.fallbackMessage || "Something went wrong"}
            </p>
            {this.state.error && (
              <p className="text-[10px] text-white/30 font-mono max-w-md truncate">
                {this.state.error.message}
              </p>
            )}
          </div>
          <button
            onClick={this.handleReset}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-300/80 font-mono hover:bg-red-500/20 transition-colors"
          >
            <RotateCcw size={12} />
            Retry
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
