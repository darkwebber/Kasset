import React from "react";
import { FileText, Terminal, Play, Search, FolderOpen, Calculator, Clock, Wrench, Globe, Rss, MapPin, MessageSquare, Code, StickyNote, FileCode, Pencil } from "lucide-react";

export const TOOL_META: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  read_file:       { icon: <FileText size={13} />,   label: "Reading file",       color: "#60a5fa" },
  run_command:     { icon: <Terminal size={13} />,    label: "Running command",    color: "#a78bfa" },
  execute_python:  { icon: <Play size={13} />,        label: "Running Python",     color: "#34d399" },
  execute_cpp:     { icon: <Play size={13} />,        label: "Running C++",        color: "#38bdf8" },
  search_files:    { icon: <Search size={13} />,      label: "Searching files",    color: "#fbbf24" },
  list_directory:  { icon: <FolderOpen size={13} />,  label: "Listing directory",  color: "#fb923c" },
  calculate:       { icon: <Calculator size={13} />,  label: "Calculating",        color: "#f472b6" },
  get_current_time:{ icon: <Clock size={13} />,       label: "Getting time",       color: "#38bdf8" },
  get_system_info: { icon: <Terminal size={13} />,    label: "System info",        color: "#818cf8" },
  search_web:      { icon: <Globe size={13} />,        label: "Web search",        color: "#22d3ee" },
  read_url:        { icon: <Globe size={13} />,        label: "Reading URL",        color: "#2dd4bf" },
  read_rss:        { icon: <Rss size={13} />,          label: "Reading RSS",        color: "#fb923c" },
  get_location:    { icon: <MapPin size={13} />,       label: "Getting location",   color: "#f472b6" },
  request_user_input: { icon: <MessageSquare size={13} />, label: "Requesting input", color: "#a78bfa" },
  write_file:      { icon: <FileText size={13} />,   label: "Writing file",       color: "#4ade80" },
  edit_file:       { icon: <Pencil size={13} />,     label: "Editing file",       color: "#fbbf24" },
  grep_code:       { icon: <Search size={13} />,     label: "Searching code",     color: "#c084fc" },
  html_preview:    { icon: <Code size={13} />,       label: "HTML preview",       color: "#22d3ee" },
  save_notes:      { icon: <StickyNote size={13} />, label: "Saving notes",       color: "#a3e635" },
};

export function getToolMeta(name: string) {
  return TOOL_META[name] || { icon: <Wrench size={13} />, label: name, color: "#94a3b8" };
}

export const TOOL_DISPLAY: Record<string, string> = {
  run_command: "Shell",
  execute_python: "Python",
  execute_cpp: "C++",
  read_file: "File Reader",
  search_files: "Search",
  list_directory: "Browse",
  calculate: "Math",
  get_current_time: "Clock",
  get_system_info: "System",
  search_web: "Web Search",
  read_url: "URL Reader",
  read_rss: "RSS Reader",
  get_location: "Location",
  request_user_input: "User Input",
  write_file: "File Writer",
  edit_file: "Editor",
  grep_code: "Code Search",
  html_preview: "HTML Preview",
  save_notes: "Notes",
};

export const TOOL_EXAMPLES: Record<string, string> = {
  run_command: "Show my disk usage and top processes",
  execute_python: "Plot a sine wave using matplotlib",
  read_file: "Read my ~/.zshrc and explain what it does",
  search_files: "Find all Python files in my home directory",
  list_directory: "What's in my Downloads folder?",
  calculate: "What's the square root of 2048?",
  get_system_info: "What are my system specs?",
  get_current_time: "What time is it right now?",
  execute_cpp: "Write and run a C++ hello world program",
  search_web: "Search for the latest AI news",
  read_url: "Summarize the top story on Hacker News",
  read_rss: "What's new on TechCrunch today?",
  get_location: "Where am I located right now?",
};
