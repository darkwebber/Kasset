"use client";

import { useState, useEffect } from "react";
import { X, ChevronRight, ChevronLeft, Gamepad2, MessageSquare, Paperclip, Wrench, Brain, Keyboard } from "lucide-react";
import { getApiBase } from "@/lib/api";

interface TutorialProps {
  onClose: () => void;
}

const STEPS = [
  {
    icon: <Gamepad2 size={28} />,
    title: "Welcome to Kasset Console",
    description: "A fully local AI assistant running on your Mac. No cloud, no API keys — everything stays on your machine.",
    details: [
      "Runs fully local on Apple Silicon via MLX",
      "Real-time streaming with thinking display",
      "Multiple specialized agent kassets",
    ],
  },
  {
    icon: <Gamepad2 size={28} />,
    title: "Kassets",
    description: "Swap kassets to change your AI's specialization. Each one has different tools, personality, and focus.",
    details: [
      "General Assistant — all-purpose helper",
      "Code Pilot — pair programming & debugging",
      "Tutor — teaching with examples & analogies",
      "Data Analyst — stats, charts, data exploration",
      "Terminal — natural language shell interface",
      "Writer, DevOps, Web Pilot — and more",
    ],
  },
  {
    icon: <MessageSquare size={28} />,
    title: "Chat",
    description: "Type your message and press Enter. The AI streams responses in real-time with visible thinking.",
    details: [
      "Edit any message — click the pencil icon",
      "Regenerate responses — click the retry icon",
      "Revert conversation — cut to any point",
      "Export chats as Markdown files",
    ],
  },
  {
    icon: <Wrench size={28} />,
    title: "Tools & Commands",
    description: "Your AI can run shell commands, execute Python/C++ code, search the web, and more — all locally.",
    details: [
      "Most commands run automatically",
      "Dangerous commands (rm, sudo) are blocked",
      "Write operations need your approval first",
      "Python sandbox with pandas, numpy, matplotlib",
      "Plots are auto-captured and displayed inline",
    ],
  },
  {
    icon: <Paperclip size={28} />,
    title: "File Attachments",
    description: "Attach files and images to your messages for the AI to analyze.",
    details: [
      "Click 📎 to browse and attach files",
      "Paste images directly (Ctrl/Cmd+V)",
      "Attached files appear inline with your text",
      "Images enable vision analysis",
    ],
  },
  {
    icon: <Wrench size={28} />,
    title: "Kasset Forge",
    description: "Create custom kassets and tools to extend your AI.",
    details: [
      "Click 🔧 in the top bar to open the Forge",
      "Create kassets — custom personality, tools, theme",
      "Create tools — Python handlers the AI can call",
      "Import & export kassets as JSON files",
      "Share your creations with others",
    ],
  },
  {
    icon: <Brain size={28} />,
    title: "Memory & Context",
    description: "The AI learns about you over time and maintains context across sessions.",
    details: [
      "Memories — auto-learned preferences & facts",
      "Kasset Context — per-kasset history",
      "Global Profile — app-wide understanding of you",
      "Toggle each layer in the Context tab (drawer)",
    ],
  },
  {
    icon: <Keyboard size={28} />,
    title: "Mobile & Touch",
    description: "Kasset works on phones and tablets too.",
    details: [
      "Swipe left/right on kasset carousel to browse",
      "Swipe to steer in the Snake game",
      "Tap the ⌘ button for the command palette (all actions)",
      "All buttons have touch-friendly tap targets",
      "Less-used buttons are hidden on small screens — use the command palette to access them",
      "Your data syncs via the backend at ~/.kasset/",
    ],
  },
  {
    icon: <Keyboard size={28} />,
    title: "Keyboard Shortcuts",
    description: "Power-user shortcuts for faster navigation.",
    details: [
      "Enter — send message",
      "Shift+Enter — new line in input",
      "Escape — close topmost overlay / stop generation",
      "⌘K / Ctrl+K — command palette",
      "⌘N / Ctrl+N — new chat",
      "⌘E / Ctrl+E — export chat",
      "⌘⇧C — copy full conversation",
      "⌘⇧F — open Kasset Forge",
      "⌘/ — toggle this help guide",
      "⌘. — focus the input box",
      "/ in carousel — search kassets",
      "←→ in carousel — navigate kassets",
    ],
  },
];

export default function Tutorial({ onClose }: TutorialProps) {
  const [step, setStep] = useState(0);
  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;
  const isFirst = step === 0;

  // Mark tutorial as seen
  useEffect(() => {
    fetch(`${getApiBase()}/api/settings/tutorial`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ completed: true }),
    }).catch(() => {});
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="relative w-full max-w-lg mx-4 bg-[#0a0a0a] border border-white/10 rounded-2xl shadow-2xl overflow-hidden">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 rounded text-white/30 hover:text-white/60 hover:bg-white/5 transition-all z-10"
        >
          <X size={16} />
        </button>

        {/* Progress bar */}
        <div className="flex gap-1 px-6 pt-5">
          {STEPS.map((_, i) => (
            <div
              key={i}
              className="h-1 flex-1 rounded-full transition-all duration-300"
              style={{
                background: i <= step ? "var(--accent, #00ff88)" : "rgba(255,255,255,0.08)",
                opacity: i <= step ? 1 : 0.5,
              }}
            />
          ))}
        </div>

        {/* Step counter */}
        <div className="px-6 pt-3 text-[10px] text-white/20 font-mono uppercase tracking-widest">
          Step {step + 1} of {STEPS.length}
        </div>

        {/* Content */}
        <div className="px-6 pt-4 pb-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2.5 rounded-xl bg-[var(--accent,#00ff88)]/10 text-[var(--accent,#00ff88)]">
              {current.icon}
            </div>
            <h2 className="text-lg font-bold text-white/90">{current.title}</h2>
          </div>
          <p className="text-sm text-white/50 leading-relaxed mb-4">{current.description}</p>
          <div className="space-y-2">
            {current.details.map((detail, i) => (
              <div key={i} className="flex items-start gap-2 text-[12px] text-white/35 font-mono leading-relaxed">
                <span className="text-[var(--accent,#00ff88)]/40 mt-0.5 shrink-0">›</span>
                <span>{detail}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between px-6 pb-5">
          <button
            onClick={() => setStep(s => s - 1)}
            disabled={isFirst}
            className="flex items-center gap-1 px-3 py-1.5 text-[11px] text-white/30 hover:text-white/60 font-mono uppercase tracking-wider transition-all disabled:opacity-20 disabled:cursor-default"
          >
            <ChevronLeft size={14} />
            Back
          </button>
          {isLast ? (
            <button
              onClick={onClose}
              className="flex items-center gap-1.5 px-5 py-2 bg-[var(--accent,#00ff88)] text-black font-bold text-sm uppercase tracking-wider rounded-lg hover:bg-white transition-colors"
            >
              Get Started
            </button>
          ) : (
            <button
              onClick={() => setStep(s => s + 1)}
              className="flex items-center gap-1 px-4 py-2 bg-white/5 hover:bg-white/10 text-white/60 font-medium text-sm rounded-lg transition-all"
            >
              Next
              <ChevronRight size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
