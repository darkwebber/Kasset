"use client";

import React, { useEffect, useState } from "react";
import { Brain, Activity, History, FileText, Lightbulb, X, ChevronRight, Minimize2 } from "lucide-react";
import { getApiBase } from "@/lib/api";

interface GraphNode {
  id: string;
  type: string;
  content: string;
  detail?: string;
  importance: number;
  last_accessed: number;
}

interface MentalModelWidgetProps {
  chatId: string | null;
  onClose: () => void;
}

export default function MentalModelWidget({ chatId, onClose }: MentalModelWidgetProps) {
  const [nodes, setNodes] = useState<Record<string, GraphNode>>({});
  const [minimized, setMinimized] = useState(false);

  useEffect(() => {
    if (!chatId) return;
    const fetchGraph = async () => {
      try {
        const res = await fetch(`${getApiBase()}/api/chats/${chatId}/graph`);
        const data = await res.json();
        setNodes(data.nodes || {});
      } catch (err) {
        console.error("Failed to fetch graph:", err);
      }
    };

    fetchGraph();
    const interval = setInterval(fetchGraph, 5000); // Poll every 5s
    return () => clearInterval(interval);
  }, [chatId]);

  if (!chatId) return null;

  const nodeArray = Object.values(nodes);
  const workingMemory = nodes["working_memory"];
  const episodes = nodeArray.filter(n => n.type === "episode").sort((a, b) => b.last_accessed - a.last_accessed);
  const discoveries = nodeArray.filter(n => n.type === "concept" || n.type === "note").sort((a, b) => b.importance - a.importance);
  const files = nodeArray.filter(n => n.type === "file").sort((a, b) => b.last_accessed - a.last_accessed);

  if (minimized) {
    return (
      <div 
        onClick={() => setMinimized(false)}
        className="fixed bottom-20 right-3 sm:bottom-24 sm:right-8 z-50 p-3 bg-zinc-900/90 border border-white/10 rounded-full cursor-pointer hover:bg-zinc-800 transition-all shadow-xl text-[var(--accent)]"
        title="Show Mental Model"
      >
        <Brain size={20} />
      </div>
    );
  }

  return (
    <div className="fixed bottom-0 left-0 right-0 sm:bottom-24 sm:left-auto sm:right-8 z-50 w-full sm:w-80 max-h-[70dvh] sm:max-h-[500px] overflow-hidden bg-zinc-950/95 border-t sm:border border-white/10 rounded-t-xl sm:rounded-xl shadow-2xl flex flex-col font-mono text-xs text-white/80 animate-in fade-in slide-in-from-bottom-4 duration-300">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-white/5 bg-white/5">
        <div className="flex items-center gap-2">
          <Brain size={14} className="text-[var(--accent)]" />
          <span className="uppercase tracking-widest font-bold">Mental Model</span>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => setMinimized(true)} className="p-1 hover:bg-white/10 rounded transition-colors text-white/40 hover:text-white">
            <Minimize2 size={12} />
          </button>
          <button onClick={onClose} className="p-1 hover:bg-white/10 rounded transition-colors text-white/40 hover:text-white">
            <X size={12} />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6 scrollbar-thin">
        {/* Working Memory */}
        {workingMemory && (
          <section>
            <div className="flex items-center gap-2 mb-2 text-[var(--accent)]/70 uppercase tracking-wider text-[10px] font-bold">
              <Activity size={12} />
              <span>Working Memory</span>
            </div>
            <div className="p-2 bg-[var(--accent)]/5 border border-[var(--accent)]/20 rounded-lg">
               <div className="text-white font-bold leading-relaxed">{workingMemory.content}</div>
               {workingMemory.detail && (
                 <div className="mt-1 text-[10px] text-white/40 italic break-words">{workingMemory.detail}</div>
               )}
            </div>
          </section>
        )}

        {/* Recent Focus (Episodes) */}
        {episodes.length > 0 && (
          <section>
            <div className="flex items-center gap-2 mb-2 text-blue-400/70 uppercase tracking-wider text-[10px] font-bold">
              <History size={12} />
              <span>Recent Focus</span>
            </div>
            <div className="space-y-1 pl-1">
              {episodes.slice(0, 3).map(e => (
                <div key={e.id} className="flex gap-2 items-start py-1 border-l border-white/5 pl-3">
                  <ChevronRight size={10} className="mt-1 flex-shrink-0 text-white/20" />
                  <span>{e.content}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Discoveries & Context */}
        {discoveries.length > 0 && (
          <section>
            <div className="flex items-center gap-2 mb-2 text-yellow-400/70 uppercase tracking-wider text-[10px] font-bold">
              <Lightbulb size={12} />
              <span>Knowledge Distilled</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {discoveries.slice(0, 8).map(d => (
                <div key={d.id} className="px-2 py-0.5 bg-white/5 border border-white/5 rounded-full text-[10px] whitespace-nowrap overflow-hidden text-ellipsis max-w-full">
                  {d.content.replace(/^\[.*?\]\s*/, "")}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Files Touched */}
        {files.length > 0 && (
          <section>
            <div className="flex items-center gap-2 mb-2 text-white/40 uppercase tracking-wider text-[10px] font-bold">
              <FileText size={12} />
              <span>Context Origin</span>
            </div>
            <div className="grid grid-cols-1 gap-1">
              {files.slice(0, 5).map(f => (
                <div key={f.id} className="flex items-center gap-2 text-[10px] text-white/60 truncate" title={f.content}>
                  <div className="w-1.5 h-1.5 rounded-full bg-white/20" />
                  {f.content.split('/').pop()}
                </div>
              ))}
            </div>
          </section>
        )}
      </div>

      {/* Footer */}
      <div className="p-2 border-t border-white/5 bg-white/5 text-[9px] text-white/20 text-center uppercase tracking-widest">
        Hierarchical Memory (Cognitive-v1)
      </div>
    </div>
  );
}
