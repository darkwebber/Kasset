"use client";

import { useState } from "react";

interface OnboardingProps {
  onComplete: () => void;
  onSelectCartridge: (id: string) => void;
}

const STEPS = [
  {
    title: "Welcome to Kasset",
    subtitle: "Your local AI console",
    body: "Everything runs on your machine. Your conversations, your data, your models — nothing leaves your device. No cloud, no accounts, no tracking.",
  },
  {
    title: "Pick a Kasset",
    subtitle: "Kassets are AI personas with specialized tools",
    body: "Start with General Assistant — it can chat, run code, browse files, search the web, and more. You can switch or stack kassets anytime.",
  },
  {
    title: "Try it",
    subtitle: "Just type and press Enter",
    body: "Ask anything. Attach files with the 📎 button. Use ⌘K for the command palette. The agent will use tools autonomously to help you.",
  },
];

export default function Onboarding({ onComplete, onSelectCartridge }: OnboardingProps) {
  const [step, setStep] = useState(0);

  const handleNext = () => {
    if (step === STEPS.length - 1) {
      if (typeof window !== "undefined") {
        localStorage.setItem("kasset-onboarded", "1");
      }
      onSelectCartridge("general-assistant");
      onComplete();
    } else {
      setStep(step + 1);
    }
  };

  const handleSkip = () => {
    if (typeof window !== "undefined") {
      localStorage.setItem("kasset-onboarded", "1");
    }
    onComplete();
  };

  const current = STEPS[step];

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/80 backdrop-blur-md">
      <div className="w-full max-w-sm mx-4">
        {/* Step indicators */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {STEPS.map((_, i) => (
            <div
              key={i}
              className={`h-1 rounded-full transition-all duration-300 ${
                i === step ? "w-8 bg-[var(--accent)]" : i < step ? "w-4 bg-[var(--accent)]/40" : "w-4 bg-white/10"
              }`}
            />
          ))}
        </div>

        {/* Content card */}
        <div className="bg-[#0d1117] border border-white/10 rounded-2xl p-8 text-center space-y-4">
          <div className="text-3xl mb-2">
            {step === 0 ? "🖥️" : step === 1 ? "🎛️" : "⚡"}
          </div>
          <h2 className="text-lg text-white font-bold font-mono tracking-wide">
            {current.title}
          </h2>
          <p className="text-xs text-[var(--accent)]/60 font-mono uppercase tracking-wider">
            {current.subtitle}
          </p>
          <p className="text-sm text-white/50 leading-relaxed">
            {current.body}
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between mt-6">
          <button
            onClick={handleSkip}
            className="text-[10px] text-white/25 hover:text-white/50 font-mono uppercase tracking-wider transition-colors"
          >
            Skip
          </button>
          <button
            onClick={handleNext}
            className="px-6 py-2.5 rounded-xl bg-[var(--accent)] text-black text-xs font-bold uppercase tracking-wider hover:brightness-110 transition-all"
          >
            {step === STEPS.length - 1 ? "Get Started" : "Next"}
          </button>
        </div>
      </div>
    </div>
  );
}
