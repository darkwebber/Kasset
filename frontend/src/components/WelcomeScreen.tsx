"use client";

import { Command, Paperclip, Wrench, Terminal, Calculator, Globe, Code, FileText, Clock, Search, Cpu, Keyboard } from "lucide-react";

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
    "Summarize this PDF for me",
    "What's the weather like? Search the web",
    "Help me write a professional email",
    "Explain quantum computing simply",
  ],
  "code-pilot": [
    "Review this function for bugs",
    "Write a React component for a todo list",
    "Explain this error message",
    "Refactor this code to be more readable",
  ],
  "tutor": [
    "Teach me about recursion with examples",
    "Explain calculus derivatives step by step",
    "Quiz me on Python data structures",
    "What's the difference between TCP and UDP?",
  ],
  "data-analyst": [
    "Analyze this CSV and find trends",
    "Create a bar chart of monthly sales",
    "Calculate the standard deviation",
    "Run a linear regression on this data",
  ],
  "terminal": [
    "Show me disk usage by directory",
    "Find all Python files modified today",
    "What processes are using the most memory?",
    "List all git branches",
  ],
  "writer": [
    "Write a short story about a robot",
    "Help me with this blog post introduction",
    "Proofread and improve this paragraph",
    "Generate 5 creative headlines",
  ],
  "devops": [
    "Show me running Docker containers",
    "Check the git log for recent changes",
    "What's my Node.js version?",
    "Help me write a Dockerfile",
  ],
  "web-pilot": [
    "Search for the latest AI news",
    "Summarize this article for me",
    "Compare React vs Vue vs Svelte",
    "Find documentation for FastAPI",
  ],
};

const DEFAULT_PROMPTS = [
  "What can you help me with?",
  "Run a quick system check",
  "Search the web for something interesting",
  "Write and run a Python script",
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
    <div className="flex-1 flex flex-col items-center justify-center px-2 sm:px-4 select-none overflow-y-auto momentum-scroll">
      {/* Cartridge identity */}
      <div className="text-4xl sm:text-5xl mb-2 sm:mb-3 drop-shadow-lg">{cartridgeIcon}</div>
      <h2 className="text-base sm:text-lg font-bold text-white/70 mb-1">{cartridgeName}</h2>
      <p className="text-[11px] sm:text-xs text-white/30 max-w-sm text-center mb-2 leading-relaxed">{cartridgeDescription}</p>
      {bootMessage && (
        <p className="text-xs text-[var(--accent)]/60 font-mono max-w-sm text-center mb-4 sm:mb-8">{bootMessage}</p>
      )}
      {!bootMessage && <div className="mb-4 sm:mb-8" />}

      {/* Example prompts */}
      <div className="w-full max-w-lg space-y-2 mb-4 sm:mb-8">
        <div className="text-[10px] uppercase tracking-widest text-white/20 font-mono mb-2 text-center">Try asking</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 sm:gap-2">
          {prompts.map((prompt, i) => (
            <button
              key={i}
              onClick={() => onSendPrompt(prompt)}
              className="text-left px-3 py-2 sm:py-2.5 rounded-lg border border-white/5 hover:border-[var(--accent)]/30 active:border-[var(--accent)]/30 bg-white/[0.02] hover:bg-[var(--accent)]/5 active:bg-[var(--accent)]/5 text-white/40 hover:text-[var(--accent)] active:text-[var(--accent)] text-xs font-mono transition-all leading-relaxed"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>

      {/* Tool badges */}
      {activeToolBadges.length > 0 && (
        <div className="flex flex-wrap gap-1.5 justify-center mb-6 max-w-md">
          <span className="text-[9px] uppercase tracking-widest text-white/15 font-mono mr-1 self-center">Tools:</span>
          {activeToolBadges.map((badge, i) => (
            <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/[0.03] border border-white/5 text-white/25 text-[9px] font-mono">
              {badge.icon}
              {badge.label}
            </span>
          ))}
        </div>
      )}

      {/* Keyboard hints — hidden on touch devices */}
      <div className="hidden sm:flex items-center gap-4 text-[9px] text-white/12 font-mono">
        <span className="flex items-center gap-1"><Keyboard size={10} /> Enter = send</span>
        <span>Shift+Enter = newline</span>
        <span className="flex items-center gap-1"><Paperclip size={9} /> attach files</span>
        <span className="flex items-center gap-1"><Command size={9} />K = commands</span>
      </div>
    </div>
  );
}
