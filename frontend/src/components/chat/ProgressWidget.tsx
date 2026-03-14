import React from "react";
import { CheckCircle2, Circle, Loader2 } from "lucide-react";

export interface ProgressStep {
  label: string;
  status: "pending" | "running" | "completed" | "error";
  detail?: string;
}

export interface ProgressConfig {
  title?: string;
  steps: ProgressStep[];
}

export default function ProgressWidget({ config }: { config: ProgressConfig }) {
  const { title = "Task Progress", steps = [] } = config;

  return (
    <div className="my-3 bg-zinc-950/80 border border-white/10 rounded-xl overflow-hidden shadow-lg font-mono">
      <div className="px-3 py-2 bg-white/5 border-b border-white/5 flex items-center gap-2">
        <Loader2 className="animate-spin text-[var(--accent)]" size={14} />
        <span className="text-xs uppercase tracking-widest text-white/80 font-bold">{title}</span>
      </div>
      <div className="p-4 space-y-4">
        {steps.map((step, idx) => {
          const isPending = step.status === "pending";
          const isRunning = step.status === "running";
          const isCompleted = step.status === "completed";
          const isError = step.status === "error";

          return (
            <div key={idx} className="flex gap-3">
              <div className="flex flex-col items-center mt-0.5">
                {isCompleted && <CheckCircle2 size={16} className="text-green-400" />}
                {isRunning && <Loader2 size={16} className="text-[var(--accent)] animate-spin" />}
                {isPending && <Circle size={16} className="text-white/20" />}
                {isError && <Circle size={16} className="text-red-400 fill-red-400/20" />}
                
                {idx < steps.length - 1 && (
                  <div className={`w-[2px] h-full mt-1 ${isCompleted ? 'bg-green-400/30' : 'bg-white/10'}`} />
                )}
              </div>
              <div className="flex-1 pb-2">
                <div className={`text-sm font-bold ${isCompleted ? 'text-white/90' : isRunning ? 'text-[var(--accent)]' : isError ? 'text-red-400' : 'text-white/40'}`}>
                  {step.label}
                </div>
                {step.detail && (
                  <div className="text-xs text-white/50 mt-1 leading-relaxed">
                    {step.detail}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
