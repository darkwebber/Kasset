export interface ToolCallSegment {
  kind: "tool";
  name: string;
  args: Record<string, any>;
  result?: string;
  images?: string[];
  html?: string;
  consentId?: string;
  consentCommand?: string;
  status: "running" | "done" | "error" | "consent" | "preparing";
}

export interface ThinkingSegment {
  kind: "thinking";
  content: string;
  durationMs?: number;
  collapsed: boolean;
}

export interface TextSegment {
  kind: "text";
  content: string;
}

export interface InteractiveSegment {
  kind: "interactive";
  widgetId: string;
  widgetType: "choice" | "slider" | "editor" | "outline" | "form" | "embed" | "diff" | string;
  config: Record<string, any>;
  status: "pending" | "submitted" | "dismissed" | "active";
  response?: any;
  // Persistent widget support
  persistentId?: string;       // Links widget to a persistent editing session
  revision?: number;           // Which revision of the content this represents
}

export type Segment = ToolCallSegment | ThinkingSegment | TextSegment | InteractiveSegment;

export interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  segments?: Segment[];
}
