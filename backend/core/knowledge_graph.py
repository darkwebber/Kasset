"""
Knowledge Graph — structured context for conversations.

Instead of flat text blocks for user memory / cartridge context / global profile,
the agent builds a lightweight graph during each conversation. The graph is 
serialized into a compact "knowledge map" in the system prompt (~200-400 tokens)
that gives the model structured awareness of what it has discovered.

Node types: intent, file, concept, tool_result, error, state
Edge types: references, modifies, depends_on, caused_by, related_to, satisfies
"""

import json
import re
import hashlib
import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════

VALID_NODE_TYPES = {"intent", "file", "concept", "tool_result", "error", "state"}
VALID_EDGE_TYPES = {"references", "modifies", "depends_on", "caused_by", "related_to", "satisfies"}


@dataclass
class GraphNode:
    """A node in the conversation knowledge graph."""
    id: str
    type: str              # One of VALID_NODE_TYPES
    content: str           # Short description (~50-100 chars)
    detail: str = ""       # Full detail (expanded on request)
    resolved: bool = False # True if intent completed or error fixed
    round_created: int = 0 # Which tool round created this
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """A directed edge between two nodes."""
    from_id: str
    to_id: str
    edge_type: str         # One of VALID_EDGE_TYPES


class ConversationGraph:
    """
    In-memory knowledge graph for a single conversation.
    
    Built incrementally during chat via add_* methods.
    Serialized to a compact map via get_compact_map().
    """

    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[GraphEdge] = []
        self._round: int = 0

    # ─── Core API ──────────────────────────────────

    def add_node(self, node_type: str, node_id: str, content: str,
                 detail: str = "", metadata: dict = None) -> str:
        """Add or update a node. Returns the node ID."""
        if node_type not in VALID_NODE_TYPES:
            logger.warning(f"Invalid node type '{node_type}', defaulting to 'concept'")
            node_type = "concept"

        if node_id in self.nodes:
            # Update existing node
            existing = self.nodes[node_id]
            existing.content = content
            if detail:
                existing.detail = detail
            if metadata:
                existing.metadata.update(metadata)
        else:
            self.nodes[node_id] = GraphNode(
                id=node_id,
                type=node_type,
                content=content,
                detail=detail,
                round_created=self._round,
                metadata=metadata or {},
            )
        return node_id

    def add_edge(self, from_id: str, to_id: str, edge_type: str) -> None:
        """Add a directed edge between two nodes."""
        if edge_type not in VALID_EDGE_TYPES:
            logger.warning(f"Invalid edge type '{edge_type}', defaulting to 'related_to'")
            edge_type = "related_to"
        # Avoid duplicate edges
        for e in self.edges:
            if e.from_id == from_id and e.to_id == to_id and e.edge_type == edge_type:
                return
        self.edges.append(GraphEdge(from_id=from_id, to_id=to_id, edge_type=edge_type))

    def update_node(self, node_id: str, content: str = None, detail: str = None) -> None:
        """Update an existing node's content/detail."""
        if node_id in self.nodes:
            if content is not None:
                self.nodes[node_id].content = content
            if detail is not None:
                self.nodes[node_id].detail = detail

    def mark_resolved(self, node_id: str) -> None:
        """Mark an intent or error as resolved."""
        if node_id in self.nodes:
            self.nodes[node_id].resolved = True

    def set_round(self, round_num: int) -> None:
        """Set current tool round number."""
        self._round = round_num

    # ─── High-Level Builders ──────────────────────

    def add_user_intent(self, message: str) -> Optional[str]:
        """Extract and add intent nodes from a user message."""
        text = message.strip()
        if len(text) < 5 or text.startswith("[Attached file:") or text.startswith("Tool result"):
            return None

        # Compress the intent to a short summary
        intent_text = text[:120].strip()
        if len(text) > 120:
            intent_text += "..."

        node_id = f"intent_{_short_hash(text)}"
        self.add_node("intent", node_id, intent_text, detail=text)
        return node_id

    def add_file_node(self, path: str, summary: str = "", symbols: str = "") -> str:
        """Add/update a file node from a read_file or list_directory result."""
        name = Path(path).name
        node_id = f"file_{_sanitize_id(name)}"
        content = f"{path}"
        if summary:
            content += f" — {summary[:80]}"

        self.add_node("file", node_id, content, detail=symbols or summary, metadata={"path": path})
        return node_id

    def add_tool_result(self, tool_name: str, args: dict, result: str,
                        has_images: bool = False) -> str:
        """Add a tool result node and auto-detect related file/concept nodes."""
        node_id = f"tool_{self._round}_{tool_name}"

        # Compress result for content (short summary)
        result_preview = result[:150].replace("\n", " ").strip()
        if len(result) > 150:
            result_preview += "..."
        if has_images:
            result_preview = "[image generated] " + result_preview

        content = f"{tool_name} → {result_preview}"
        self.add_node("tool_result", node_id, content, detail=result[:2000])

        # Auto-link: file operations → file nodes
        if tool_name in ("read_file", "list_directory", "search_files"):
            path = args.get("path", args.get("directory", ""))
            if path:
                file_id = self.add_file_node(path)
                self.add_edge(node_id, file_id, "references")

        # Auto-link: run_command with cwd → file context
        if tool_name == "run_command":
            cwd = args.get("cwd", "")
            if cwd:
                cwd_id = self.add_file_node(cwd, summary="working directory")
                self.add_edge(node_id, cwd_id, "references")

        # Auto-link: code execution results
        if tool_name in ("execute_python", "execute_cpp"):
            # Extract file paths from code
            code = args.get("code", "")
            for path_match in re.findall(r"""['"]([/~][^'"]{5,120})['"]""", code):
                file_id = self.add_file_node(path_match)
                self.add_edge(node_id, file_id, "references")

        # Auto-detect if result is an error
        err_lower = result.lower()
        if any(sig in err_lower for sig in ("error:", "traceback", "exception", "failed")):
            err_id = f"error_{self._round}"
            err_content = _extract_error_summary(result)
            self.add_node("error", err_id, err_content, detail=result[:1500])
            self.add_edge(err_id, node_id, "caused_by")

        # Link to active (unresolved) intents
        active_intents = [n for n in self.nodes.values()
                          if n.type == "intent" and not n.resolved]
        for intent in active_intents[-2:]:  # Link to most recent 2 intents
            self.add_edge(node_id, intent.id, "satisfies")

        return node_id

    def add_concept(self, concept_id: str, description: str, detail: str = "") -> str:
        """Add a discovered concept/pattern."""
        return self.add_node("concept", f"concept_{_sanitize_id(concept_id)}",
                             description, detail=detail)

    def add_state(self, state_id: str, description: str) -> str:
        """Track a mutable state (e.g., current image, current file being edited)."""
        return self.add_node("state", f"state_{_sanitize_id(state_id)}", description)

    # ─── Serialization ──────────────────────────────

    def get_compact_map(self, max_tokens: int = 600) -> str:
        """
        Serialize the graph into a compact text map for system prompt injection.
        
        Output format (~200-400 tokens):
        ## Session Knowledge Map
        [Active intents] Fix login bug → auth.py, routes.py (in progress)
        [Files touched] auth.py (read, modified L45), routes.py (read)
        [Discoveries] JWT in httpOnly cookies; AuthService validates via bcrypt
        [Errors] ✗ NameError L45 → fixed | ✗ plotly missing → pending
        [State] Image: edited.png (brightness +30%, cropped)
        """
        if not self.nodes:
            return ""

        # Categorize nodes
        intents = [n for n in self.nodes.values() if n.type == "intent"]
        files = [n for n in self.nodes.values() if n.type == "file"]
        concepts = [n for n in self.nodes.values() if n.type == "concept"]
        errors = [n for n in self.nodes.values() if n.type == "error"]
        states = [n for n in self.nodes.values() if n.type == "state"]
        tool_results = [n for n in self.nodes.values() if n.type == "tool_result"]

        sections = []

        # Active intents
        if intents:
            active = [n for n in intents if not n.resolved]
            resolved = [n for n in intents if n.resolved]
            parts = []
            for n in active[-4:]:
                # Find linked files
                linked = self._get_linked_names(n.id, "references")
                suffix = f" → {', '.join(linked)}" if linked else ""
                parts.append(f"{n.content}{suffix}")
            if resolved:
                parts.append(f"({len(resolved)} resolved)")
            if parts:
                sections.append("[Active intents] " + " | ".join(parts))

        # Files
        if files:
            file_parts = []
            for n in files[-8:]:
                # Determine operations performed on this file
                ops = set()
                for e in self.edges:
                    if e.to_id == n.id:
                        if e.edge_type == "modifies":
                            ops.add("modified")
                        elif e.edge_type == "references":
                            ops.add("read")
                op_str = f" ({', '.join(sorted(ops))})" if ops else ""
                name = Path(n.metadata.get("path", n.content)).name if n.metadata.get("path") else n.content
                file_parts.append(f"{name}{op_str}")
            sections.append("[Files touched] " + ", ".join(file_parts))

        # Concepts
        if concepts:
            concept_strs = [n.content for n in concepts[-5:]]
            sections.append("[Discoveries] " + "; ".join(concept_strs))

        # Errors
        if errors:
            err_parts = []
            for n in errors[-4:]:
                status = "fixed" if n.resolved else "pending"
                err_parts.append(f"✗ {n.content} → {status}")
            sections.append("[Errors] " + " | ".join(err_parts))

        # State
        if states:
            state_strs = [n.content for n in states[-3:]]
            sections.append("[State] " + "; ".join(state_strs))

        # Tool result summary (count only, details are in individual sections)
        if tool_results:
            sections.append(f"[Tool calls] {len(tool_results)} executed this session")

        if not sections:
            return ""

        # Truncate to fit token budget (rough: 4 chars/token)
        header = "\n\n## Session Knowledge Map\n"
        body = "\n".join(sections)

        max_chars = max_tokens * 4
        if len(body) > max_chars:
            body = body[:max_chars - 3] + "..."

        return header + body

    def get_node_detail(self, node_id: str) -> str:
        """Get full details for a specific node (for selective expansion)."""
        node = self.nodes.get(node_id)
        if not node:
            return f"Node '{node_id}' not found."
        
        detail = f"**{node.type.title()}: {node.content}**\n"
        if node.detail:
            detail += f"\n{node.detail}\n"
        
        # Show connections
        outgoing = [(e.to_id, e.edge_type) for e in self.edges if e.from_id == node_id]
        incoming = [(e.from_id, e.edge_type) for e in self.edges if e.to_id == node_id]
        
        if outgoing:
            detail += "\nOutgoing: " + ", ".join(f"{tid} ({etype})" for tid, etype in outgoing)
        if incoming:
            detail += "\nIncoming: " + ", ".join(f"{fid} ({etype})" for fid, etype in incoming)
        
        return detail

    # ─── Persistence ────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize graph for persistence."""
        return {
            "nodes": {nid: asdict(n) for nid, n in self.nodes.items()},
            "edges": [asdict(e) for e in self.edges],
            "round": self._round,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ConversationGraph':
        """Deserialize graph from persistence."""
        graph = cls()
        for nid, ndata in data.get("nodes", {}).items():
            graph.nodes[nid] = GraphNode(**ndata)
        for edata in data.get("edges", []):
            graph.edges.append(GraphEdge(**edata))
        graph._round = data.get("round", 0)
        return graph

    @classmethod
    def from_messages(cls, messages: List[Dict]) -> 'ConversationGraph':
        """Rebuild a graph from conversation history (for resuming sessions)."""
        graph = cls()
        round_num = 0
        
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if role == "user":
                if content.startswith("Tool result for "):
                    # Parse tool result: "Tool result for <tool_name>: <result>"
                    round_num += 1
                    graph.set_round(round_num)
                    try:
                        after_prefix = content[len("Tool result for "):]
                        tool_name = after_prefix.split(":")[0].strip()
                        tool_result = after_prefix.split(":", 1)[1].strip() if ":" in after_prefix else ""
                        # Reconstruct tool result node
                        graph.add_tool_result(tool_name, {}, tool_result[:2000])
                        # Extract file paths from result
                        for path_match in re.findall(r'([/~][^\s,\]]{5,120})', tool_result[:500]):
                            if '.' in Path(path_match).name or path_match.endswith('/'):
                                graph.add_file_node(path_match.rstrip('/'))
                    except Exception:
                        pass
                else:
                    graph.add_user_intent(content)
            elif role == "assistant":
                # Extract any file paths mentioned in backticks
                for path_match in re.findall(r'`([/~][^`]{5,100})`', content):
                    if '.' in Path(path_match).name:
                        graph.add_file_node(path_match)

        return graph

    # ─── Internal ───────────────────────────────────

    def _get_linked_names(self, node_id: str, edge_type: str) -> List[str]:
        """Get content of nodes linked FROM this node by edge_type."""
        linked_ids = [e.to_id for e in self.edges
                      if e.from_id == node_id and e.edge_type == edge_type]
        names = []
        for lid in linked_ids:
            node = self.nodes.get(lid)
            if node:
                if node.metadata.get("path"):
                    names.append(Path(node.metadata["path"]).name)
                else:
                    names.append(node.content[:30])
        return names

    def _prune_old_results(self, max_results: int = 20) -> None:
        """Remove oldest tool_result nodes if over limit (keep errors and files)."""
        results = sorted(
            [n for n in self.nodes.values() if n.type == "tool_result"],
            key=lambda n: n.round_created
        )
        if len(results) > max_results:
            for old in results[:len(results) - max_results]:
                del self.nodes[old.id]
                self.edges = [e for e in self.edges
                              if e.from_id != old.id and e.to_id != old.id]


# ═══════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════

def _short_hash(text: str) -> str:
    """Generate a short hash for deduplication."""
    return hashlib.md5(text.encode()).hexdigest()[:8]


def _sanitize_id(name: str) -> str:
    """Convert a name to a safe node ID."""
    return re.sub(r'[^a-z0-9_]', '_', name.lower().strip())[:40]


def _extract_error_summary(result: str) -> str:
    """Extract a short error summary from a tool result."""
    lines = result.strip().split('\n')
    
    # Look for common error patterns
    for line in reversed(lines):
        line = line.strip()
        if any(line.startswith(prefix) for prefix in
               ("Error:", "NameError:", "TypeError:", "ValueError:",
                "FileNotFoundError:", "ImportError:", "KeyError:",
                "IndexError:", "AttributeError:", "SyntaxError:")):
            return line[:120]
    
    # Fallback: last non-empty line
    for line in reversed(lines):
        if line.strip():
            return line.strip()[:120]
    
    return "Unknown error"
