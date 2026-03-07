"use client";

import { Terminal, Calculator, Globe, Code, FileText, Clock, Search, Cpu } from "lucide-react";

const TOOL_BADGES: Record<string, { icon: React.ReactNode; label: string }> = {
  execute_python: { icon: <Code size={12} />, label: "Python" },
  execute_cpp: { icon: <Cpu size={12} />, label: "C++" },
  run_command: { icon: <Terminal size={12} />, label: "Shell" },
  search_web: { icon: <Globe size={12} />, label: "Web Search" },
  read_url: { icon: <Globe size={12} />, label: "Read URL" },
  read_file: { icon: <FileText size={12} />, label: "Read File" },
  list_directory: { icon: <FileText size={12} />, label: "Browse Files" },
  search_files: { icon: <Search size={12} />, label: "Search Files" },
  calculate: { icon: <Calculator size={12} />, label: "Calculate" },
  get_current_time: { icon: <Clock size={12} />, label: "Time" },
  get_system_info: { icon: <Cpu size={12} />, label: "System Info" },
};

const EXAMPLE_PROMPTS: Record<string, string[]> = {
  "general-assistant": [
    "Summarize the files in ~/Downloads and suggest what to clean up",
    "What processes are using the most memory right now?",
    "Convert this CSV to a bar chart showing top 10 entries",
    "Explain the difference between concurrency and parallelism with a diagram",
  ],
  "code-pilot": [
    "Read my project structure and suggest improvements",
    "Find all TODO comments in this repo and prioritize them",
    "Write a complete CLI tool in Python that converts Markdown to HTML",
    "Debug why this function returns None instead of the expected value",
  ],
  "tutor": [
    "Teach me how HashMap works internally — with a visual diagram",
    "Explain quantum entanglement using only everyday analogies",
    "Walk me through solving a dynamic programming problem step by step",
    "What's the intuition behind Fourier transforms? Show me with code",
  ],
  "data-analyst": [
    "Read sales.csv and show me the top 5 trends with charts",
    "Compare these two CSVs and highlight every difference",
    "Build a correlation heatmap from my dataset with annotations",
    "Run a statistical significance test on columns A vs B",
  ],
  "terminal": [
    "Find and list the 20 largest files on my system",
    "Kill whatever process is hogging my CPU right now",
    "Show me all apps listening on network ports",
    "Recursively find duplicate files in ~/Documents",
  ],
  "writer": [
    "Write a product launch email that sounds excited but not salesy",
    "Turn these bullet points into a compelling blog post with a hook",
    "Rewrite this dense paragraph at an 8th-grade reading level",
    "Draft a README.md for my open-source project with badges and examples",
  ],
  "devops": [
    "Analyze my git history and show commit frequency by author this month",
    "Write a multi-stage Dockerfile that builds and serves this project",
    "Create a GitHub Actions workflow that tests, builds, and deploys on push",
    "My container exits with code 137 — diagnose and fix it",
  ],
  "web-pilot": [
    "What happened in tech news today? Give me a 5-bullet briefing",
    "Research the current state of WebAssembly — who's using it and why",
    "Find the official docs for this library and summarize the API",
    "Compare the pricing and features of Vercel vs Cloudflare Pages vs Netlify",
  ],
};

const DEFAULT_PROMPTS = [
  "What's eating my disk space? Show me the biggest files",
  "Run a quick system health check",
  "Write and run a Python script that does something cool",
  "Explain how this project is structured",
];

interface WelcomeScreenProps {
  cartridgeId: string;
  cartridgeName: string;
  cartridgeIcon: string;
  cartridgeDescription: string;
  tools: string[];
  bootMessage?: string;
  onSendPrompt: (prompt: string) => void;
}

export default function WelcomeScreen({ cartridgeId, cartridgeName, cartridgeIcon, cartridgeDescription, tools, bootMessage, onSendPrompt }: WelcomeScreenProps) {
  const prompts = EXAMPLE_PROMPTS[cartridgeId] || DEFAULT_PROMPTS;
  const activeToolBadges = tools
    .map(t => TOOL_BADGES[t])
    .filter(Boolean);

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-3 sm:px-4 select-none overflow-y-auto momentum-scroll">
      {/* Cartridge identity */}
      <div className="text-4xl sm:text-5xl mb-2 sm:mb-3 drop-shadow-lg" style={{ filter: 'drop-shadow(0 0 12px var(--glow))' }}>{cartridgeIcon}</div>
      <h2 className="text-base sm:text-lg font-bold text-white/75 mb-0.5">{cartridgeName}</h2>
      <p className="text-[11px] sm:text-xs text-white/25 max-w-xs text-center mb-1.5 leading-relaxed">{cartridgeDescription}</p>
      {bootMessage && (
        <p className="text-[11px] text-[var(--accent)]/50 font-mono max-w-sm text-center mb-5 sm:mb-8">{bootMessage}</p>
      )}
      {!bootMessage && <div className="mb-5 sm:mb-8" />}

      {/* Example prompts */}
      <div className="w-full max-w-lg mb-5 sm:mb-8">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 sm:gap-2">
          {prompts.map((prompt, i) => (
            <button
              key={i}
              onClick={() => onSendPrompt(prompt)}
              className="text-left px-3 py-2.5 rounded-lg border border-white/[0.05] hover:border-[var(--accent)]/25 bg-white/[0.02] hover:bg-[var(--accent)]/[0.04] text-white/35 hover:text-white/70 text-[11px] sm:text-xs font-mono transition-all leading-relaxed group"
            >
              <span className="opacity-40 group-hover:opacity-70 mr-1">›</span> {prompt}
            </button>
          ))}
        </div>
      </div>

      {/* Tool badges */}
      {activeToolBadges.length > 0 && (
        <div className="flex flex-wrap gap-1 justify-center mb-5 max-w-md">
          {activeToolBadges.map((badge, i) => (
            <span key={i} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-white/[0.02] border border-white/[0.04] text-white/20 text-[8px] font-mono">
              {badge.icon}
              {badge.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
