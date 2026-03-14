"""
Knowledge Graph — structured context for conversations.

Instead of flat text blocks for user memory / cartridge context / global profile,
the agent builds a lightweight graph during each conversation. The graph is 
serialized into a compact "knowledge map" in the system prompt (~200-400 tokens)
that gives the model structured awareness of what it has discovered.

Node types: intent, file, concept, tool_result, error, state, note
Edge types: references, modifies, depends_on, caused_by, related_to, satisfies
"""

import json
import re
import time
import hashlib
import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════

VALID_NODE_TYPES = {"intent", "file", "concept", "tool_result", "error", "state", "note", "working_memory", "episode", "summary"}
VALID_EDGE_TYPES = {"references", "modifies", "depends_on", "caused_by", "related_to", "satisfies", "summarizes"}
VALID_NOTE_CATEGORIES = {"finding", "plan", "todo", "progress", "observation"}


@dataclass
class GraphNode:
    """A node in the conversation knowledge graph."""
    id: str
    type: str              # One of VALID_NODE_TYPES
    content: str           # Short description (~50-100 chars)
    detail: str = ""       # Full detail (expanded on request)
    resolved: bool = False # True if intent completed or error fixed
    round_created: int = 0 # Which tool round created this
    importance: float = 0.5 # 0.0 to 1.0 (for pruning)
    last_accessed: float = field(default_factory=time.time)
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
        self._edge_set: set = set()  # O(1) dedup: {(from_id, to_id, edge_type)}
        self._round: int = 0

    # ─── Core API ──────────────────────────────────

    def add_node(self, node_type: str, node_id: str, content: str,
                 detail: str = "", importance: float = 0.5, metadata: dict = None) -> str:
        """Add or update a node. Returns the node ID."""
        if node_type not in VALID_NODE_TYPES:
            logger.warning(f"Invalid node type '{node_type}', defaulting to 'concept'")
            node_type = "concept"

        if node_id in self.nodes:
            # Update existing node
            existing = self.nodes[node_id]
            existing.content = content
            existing.last_accessed = time.time()
            if detail:
                existing.detail = detail
            if importance is not None:
                existing.importance = max(existing.importance, importance)
            if metadata:
                existing.metadata.update(metadata)
        else:
            self.nodes[node_id] = GraphNode(
                id=node_id,
                type=node_type,
                content=content,
                detail=detail,
                round_created=self._round,
                importance=importance,
                metadata=metadata or {},
            )
        return node_id

    def add_edge(self, from_id: str, to_id: str, edge_type: str) -> None:
        """Add a directed edge between two nodes."""
        if edge_type not in VALID_EDGE_TYPES:
            logger.warning(f"Invalid edge type '{edge_type}', defaulting to 'related_to'")
            edge_type = "related_to"
        # O(1) duplicate check via set
        key = (from_id, to_id, edge_type)
        if key in self._edge_set:
            return
        self._edge_set.add(key)
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

    def update_working_memory(self, intent: str, state: str = "",
                              subgoal: str = "", completed: str = "") -> None:
        """Update the agent's active 'working memory' node.
        
        Args:
            intent: Current high-level goal
            state: Free-form state description
            subgoal: Current active subgoal being worked on
            completed: Comma-separated list of completed subgoals
        """
        # Build structured working memory content
        parts = [intent[:200]]
        if subgoal:
            parts.append(f"Subgoal: {subgoal[:150]}")
        if completed:
            parts.append(f"Done: {completed[:200]}")
        if state:
            parts.append(f"State: {state[:200]}")
        content = " | ".join(parts)
        
        self.add_node(
            "working_memory", "working_memory", 
            content=content, 
            detail=state, 
            importance=1.0,  # Never prune working memory
            metadata={
                "last_update": time.time(),
                "subgoal": subgoal,
                "completed": completed,
            }
        )

    def add_episode(self, summary: str) -> str:
        """Add an 'episode' node summarizing a segment of the task."""
        episode_id = f"episode_{self._round}_{_short_hash(summary)}"
        self.add_node("episode", episode_id, summary, importance=0.8)
        # Link to working memory
        self.add_edge(episode_id, "working_memory", "references")
        return episode_id

    def set_round(self, round_num: int) -> None:
        """Set current tool round number."""
        self._round = round_num

    # ─── High-Level Builders ──────────────────────

    def add_user_intent(self, message: str) -> Optional[str]:
        """Extract and add intent nodes from a user message.
        Uses semantic dedup — similar intents merge into one node."""
        text = message.strip()
        if len(text) < 5 or text.startswith("[Attached file:") or text.startswith("Tool result"):
            return None

        # Compress the intent to a short summary
        intent_text = text[:120].strip()
        if len(text) > 120:
            intent_text += "..."

        # Semantic dedup: normalize text before hashing
        normalized = _normalize_for_dedup(text)
        node_id = f"intent_{_short_hash(normalized)}"
        self.add_node("intent", node_id, intent_text, detail=text)
        return node_id

    def add_note(self, text: str, category: str = "finding") -> str:
        """Add a scratchpad note as a first-class graph node.
        
        Categories: finding, plan, todo, progress, observation.
        Notes persist across rounds and are available on continuation.
        """
        if category not in VALID_NOTE_CATEGORIES:
            category = "finding"
        
        note_id = f"note_{self._round}_{_short_hash(text + str(time.time()))}"
        content = f"[{category}] {text[:200].strip()}"
        self.add_node(
            "note", note_id, content,
            detail=text,
            metadata={"category": category, "timestamp": time.time()},
        )
        
        # Link to active intents
        active_intents = [n for n in self.nodes.values()
                          if n.type == "intent" and not n.resolved]
        for intent in active_intents[-1:]:
            self.add_edge(note_id, intent.id, "related_to")
        
        return note_id

    def get_scratchpad_view(self) -> str:
        """Return all note nodes formatted as a readable scratchpad.
        
        Returns only note nodes in chronological order, grouped by category.
        """
        notes = sorted(
            [n for n in self.nodes.values() if n.type == "note"],
            key=lambda n: n.metadata.get("timestamp", n.round_created)
        )
        if not notes:
            return ""
        
        lines = ["## Agent Scratchpad"]
        for n in notes:
            cat = n.metadata.get("category", "note")
            marker = {"finding": "💡", "plan": "📋", "todo": "☐", 
                      "progress": "✓", "observation": "👁"}.get(cat, "•")
            # Use detail (full text) if available, else content
            text = n.detail if n.detail else n.content
            lines.append(f"{marker} {text.strip()}")
        
        return "\n".join(lines)

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
        
        Prioritizes:
        1. Working Memory (Current Intent)
        2. Unresolved Intents
        3. High Importance / Recent Nodes
        """
        if not self.nodes:
            return ""

        sections = []

        # 1. Working Memory (Longest-lived working context)
        wm = self.nodes.get("working_memory")
        if wm:
            sections.append(f"## ACTIVE INTENT\n{wm.content}")
            if wm.detail:
                sections.append(f"State: {wm.detail}")

        # Categorize other nodes and sort by importance/recency
        non_wm_nodes = [n for n in self.nodes.values() if n.id != "working_memory"]
        important_nodes = sorted(
            non_wm_nodes, 
            key=lambda n: (n.importance, n.last_accessed), 
            reverse=True
        )

        # Categorize for summary sections
        intents = [n for n in important_nodes if n.type == "intent"]
        files = [n for n in important_nodes if n.type == "file"]
        concepts = [n for n in important_nodes if n.type == "concept"]
        errors = [n for n in important_nodes if n.type == "error"]
        states = [n for n in important_nodes if n.type == "state"]
        tool_results = [n for n in important_nodes if n.type == "tool_result"]
        episodes = [n for n in important_nodes if n.type == "episode"]

        # Active intents (Highest priority)
        if intents:
            active = [n for n in intents if not n.resolved]
            resolved = [n for n in intents if n.resolved]
            parts = []
            for n in active[:3]: # Most significant 3
                linked = self._get_linked_names(n.id, "references")
                suffix = f" → {', '.join(linked)}" if linked else ""
                parts.append(f"{n.content}{suffix}")
            if resolved:
                parts.append(f"({len(resolved)} resolved)")
            if parts:
                sections.append("[Active intents] " + " | ".join(parts))

        # Recent Focus (Episodic)
        if episodes:
            epi_parts = [n.content for n in episodes[:2]]
            sections.append("[Recent focus] " + " → ".join(epi_parts))

        # Files
        if files:
            file_parts = []
            for n in files[:6]: # Top 6 important files
                ops = set()
                for e in self.edges:
                    if e.to_id == n.id:
                        if e.edge_type == "modifies": ops.add("modified")
                        elif e.edge_type == "references": ops.add("read")
                op_str = f" ({', '.join(sorted(ops))})" if ops else ""
                name = Path(n.metadata.get("path", n.content)).name if n.metadata.get("path") else n.content
                file_parts.append(f"{name}{op_str}")
            sections.append("[Files touched] " + ", ".join(file_parts))

        # Discoveries
        if concepts:
            concept_strs = [n.content for n in concepts[:4]]
            sections.append("[Discoveries] " + "; ".join(concept_strs))

        # Errors
        if errors:
            err_parts = []
            for n in errors[:3]:
                status = "fixed" if n.resolved else "pending"
                err_parts.append(f"✗ {n.content} → {status}")
            sections.append("[Errors] " + " | ".join(err_parts))

        # State
        if states:
            state_strs = [n.content for n in states[:2]]
            sections.append("[State] " + "; ".join(state_strs))

        # Notes / Scratchpad summary
        notes = [n for n in important_nodes if n.type == "note"]
        if notes:
            # Group by category, show most recent per category
            by_cat: Dict[str, List[GraphNode]] = {}
            for n in notes:
                cat = n.metadata.get("category", "note")
                by_cat.setdefault(cat, []).append(n)
            note_parts = []
            for cat, cat_notes in by_cat.items():
                latest = cat_notes[-1]
                text = latest.detail[:80] if latest.detail else latest.content[:80]
                count_str = f" (+{len(cat_notes)-1} more)" if len(cat_notes) > 1 else ""
                note_parts.append(f"{cat}: {text}{count_str}")
            sections.append("[Notes] " + " | ".join(note_parts))

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

    def get_focused_map(self, max_tokens: int = 400) -> str:
        """Generate a relevance-filtered knowledge map.
        
        Unlike get_compact_map() which includes everything, this focuses on:
        1. Working memory (always)
        2. Unresolved intents and errors (always)
        3. Recent notes (last 5)
        4. Files connected to active intents (max 4)
        5. Skips: resolved intents, old tool_results, old episodes
        
        This reduces context noise by ~40-60% compared to get_compact_map.
        """
        if not self.nodes:
            return ""

        sections = []

        # 1. Working Memory — always show
        wm = self.nodes.get("working_memory")
        if wm:
            sections.append(f"**Active:** {wm.content}")

        # 2. Unresolved intents
        active_intents = [n for n in self.nodes.values()
                          if n.type == "intent" and not n.resolved]
        if active_intents:
            intent_strs = [n.content for n in active_intents[-3:]]
            sections.append("[Goals] " + " | ".join(intent_strs))

        # Collect node IDs connected to active intents (for relevance filtering)
        relevant_ids = set()
        active_ids = {n.id for n in active_intents}
        active_ids.add("working_memory")
        for e in self.edges:
            if e.from_id in active_ids or e.to_id in active_ids:
                relevant_ids.add(e.from_id)
                relevant_ids.add(e.to_id)

        # 3. Unresolved errors — always show regardless of connections
        errors = [n for n in self.nodes.values()
                  if n.type == "error" and not n.resolved]
        if errors:
            err_parts = [f"✗ {n.content}" for n in errors[-3:]]
            sections.append("[Errors] " + " | ".join(err_parts))

        # 4. Recent notes — show last 5 regardless of connections
        notes = sorted(
            [n for n in self.nodes.values() if n.type == "note"],
            key=lambda n: n.metadata.get("timestamp", n.round_created)
        )
        if notes:
            for n in notes[-5:]:
                cat = n.metadata.get("category", "note")
                text = n.detail[:100] if n.detail else n.content[:100]
                sections.append(f"  [{cat}] {text}")

        # 5. Files connected to active intents (or most recent)
        files = [n for n in self.nodes.values() if n.type == "file"]
        relevant_files = [f for f in files if f.id in relevant_ids]
        if not relevant_files:
            # Fall back to most recently accessed files
            relevant_files = sorted(files, key=lambda n: n.last_accessed, reverse=True)[:4]
        else:
            relevant_files = relevant_files[:4]
        if relevant_files:
            file_names = [Path(n.metadata.get("path", n.content)).name
                          if n.metadata.get("path") else n.content
                          for n in relevant_files]
            sections.append("[Files] " + ", ".join(file_names))

        if not sections:
            return ""

        body = "\n".join(sections)
        max_chars = max_tokens * 4
        if len(body) > max_chars:
            body = body[:max_chars - 3] + "..."

        return "\n\n## Context\n" + body

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

    def _prune_by_importance(self, target_count: int = 60) -> None:
        """Prune low-importance, old nodes when the graph grows too large."""
        if len(self.nodes) <= target_count:
            return
            
        prunable = []
        for nid, node in self.nodes.items():
            if nid == "working_memory": continue
            if node.type == "intent" and not node.resolved: continue
            if node.importance >= 0.9: continue
            
            # Score prunability: low importance + old access = high prunability
            access_age = (time.time() - node.last_accessed) / 3600
            score = (1.0 - node.importance) * (1.1 + access_age)
            prunable.append((nid, score))
            
        # Sort by prunability score descending (highest score = most prunable)
        prunable.sort(key=lambda x: x[1], reverse=True)
        
        num_to_remove = len(self.nodes) - target_count
        for i in range(min(num_to_remove, len(prunable))):
            nid = prunable[i][0]
            del self.nodes[nid]
            self.edges = [e for e in self.edges if e.from_id != nid and e.to_id != nid]

    def _prune_old_results(self, max_results: int = 20) -> None:
        """Fallback for tool result management, now delegated to importance pruning."""
        self._prune_by_importance(target_count=60)

    # ─── Disk I/O ──────────────────────────────────

    def save_to_disk(self, path: str) -> None:
        """Save graph to a JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, 'w') as f:
            json.dump(self.to_dict(), f, indent=1)
        logger.debug(f"Graph saved: {len(self.nodes)} nodes → {path}")

    @classmethod
    def load_from_disk(cls, path: str, apply_decay: bool = True) -> 'ConversationGraph':
        """Load graph from JSON file. Applies temporal decay to node importance."""
        p = Path(path)
        if not p.exists():
            return cls()
        try:
            with open(p) as f:
                data = json.load(f)
            graph = cls.from_dict(data)
            if apply_decay:
                graph._apply_temporal_decay()
            return graph
        except Exception as e:
            logger.warning(f"Failed to load graph from {path}: {e}")
            return cls()

    def _apply_temporal_decay(self) -> None:
        """Decay node importance based on age. Older nodes lose relevance."""
        now = time.time()
        for node in self.nodes.values():
            if node.id == "working_memory":
                continue  # Never decay working memory
            age_days = (now - node.last_accessed) / 86400
            decay = max(0.1, 1.0 - age_days * 0.05)
            node.importance *= decay

    # ─── Graph-Guided Retrieval ─────────────────────

    def get_relevant_subgraph(self, query: str, max_tokens: int = 400) -> str:
        """Retrieve a relevance-filtered subgraph based on a query.
        
        1. Keyword-match seed nodes from query
        2. BFS expand 2 hops from seeds
        3. Rank by importance * recency
        4. Serialize within token budget
        """
        if not self.nodes:
            return ""

        # Always include working memory and unresolved intents/errors
        seed_ids = set()
        if "working_memory" in self.nodes:
            seed_ids.add("working_memory")
        for n in self.nodes.values():
            if n.type in ("intent", "error") and not n.resolved:
                seed_ids.add(n.id)

        # Keyword match from query
        if query:
            query_lower = query.lower()
            keywords = set(re.findall(r'\b\w{3,}\b', query_lower))
            for nid, node in self.nodes.items():
                text = (node.content + " " + node.detail).lower()
                if any(kw in text for kw in keywords):
                    seed_ids.add(nid)

        # BFS expand 2 hops
        visited = set(seed_ids)
        frontier = set(seed_ids)
        for _ in range(2):
            next_frontier = set()
            for e in self.edges:
                if e.from_id in frontier and e.to_id not in visited:
                    next_frontier.add(e.to_id)
                    visited.add(e.to_id)
                if e.to_id in frontier and e.from_id not in visited:
                    next_frontier.add(e.from_id)
                    visited.add(e.from_id)
            frontier = next_frontier

        # Rank by importance * recency
        now = time.time()
        ranked = []
        for nid in visited:
            node = self.nodes.get(nid)
            if not node:
                continue
            recency = max(0.1, 1.0 - (now - node.last_accessed) / 86400)
            score = node.importance * recency
            ranked.append((node, score))
        ranked.sort(key=lambda x: x[1], reverse=True)

        # Serialize within budget
        sections = []
        wm = self.nodes.get("working_memory")
        if wm:
            sections.append(f"**Active:** {wm.content}")

        for node, score in ranked:
            if node.id == "working_memory":
                continue
            prefix = {"intent": "🎯", "error": "✗", "file": "📄",
                      "note": "📝", "concept": "💡", "state": "⚡",
                      "episode": "📖"}.get(node.type, "•")
            line = f"{prefix} {node.content}"
            if node.resolved:
                line += " ✓"
            sections.append(line)

        if not sections:
            return ""

        body = "\n".join(sections)
        max_chars = max_tokens * 4
        if len(body) > max_chars:
            body = body[:max_chars - 3] + "..."
        return "\n\n## Context\n" + body


class PersistentGraph(ConversationGraph):
    """Knowledge graph with automatic disk persistence.
    
    Auto-saves on structural changes. Used for cross-session persistence
    at the cartridge level.
    """

    def __init__(self, store_path: str = None):
        super().__init__()
        self._store_path = store_path
        self._dirty = False
        if store_path:
            loaded = ConversationGraph.load_from_disk(store_path)
            self.nodes = loaded.nodes
            self.edges = loaded.edges
            self._round = loaded._round

    def add_node(self, *args, **kwargs) -> str:
        result = super().add_node(*args, **kwargs)
        self._dirty = True
        return result

    def add_edge(self, *args, **kwargs) -> None:
        super().add_edge(*args, **kwargs)
        self._dirty = True

    def save(self) -> None:
        """Save to disk if dirty."""
        if self._dirty and self._store_path:
            self.save_to_disk(self._store_path)
            self._dirty = False

    def merge_session(self, session_graph: 'ConversationGraph',
                      min_importance: float = 0.3) -> int:
        """Merge important nodes from a session graph into this persistent graph.
        
        Only merges nodes with importance >= min_importance.
        Returns count of nodes merged.
        """
        merged = 0
        for nid, node in session_graph.nodes.items():
            if node.importance < min_importance:
                continue
            # Skip transient types
            if node.type in ("tool_result",):
                continue
            # Merge: update if exists, add if new
            if nid in self.nodes:
                existing = self.nodes[nid]
                existing.importance = max(existing.importance, node.importance)
                existing.last_accessed = max(existing.last_accessed, node.last_accessed)
                if node.content and len(node.content) > len(existing.content):
                    existing.content = node.content
                if node.detail and len(node.detail) > len(existing.detail):
                    existing.detail = node.detail
            else:
                self.nodes[nid] = GraphNode(**{**asdict(node)})
                merged += 1

        # Merge edges (dedup)
        existing_edges = {(e.from_id, e.to_id, e.edge_type) for e in self.edges}
        for e in session_graph.edges:
            key = (e.from_id, e.to_id, e.edge_type)
            if key not in existing_edges and e.from_id in self.nodes and e.to_id in self.nodes:
                self.edges.append(GraphEdge(**asdict(e)))
                existing_edges.add(key)

        # Prune to keep persistent graph manageable
        self._prune_by_importance(target_count=100)
        self._dirty = True
        logger.info(f"Merged {merged} nodes from session into persistent graph")
        return merged


# ═══════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════

def _short_hash(text: str) -> str:
    """Generate a short hash for deduplication."""
    return hashlib.md5(text.encode()).hexdigest()[:8]


def _normalize_for_dedup(text: str) -> str:
    """Normalize text for semantic deduplication.
    Strips articles, punctuation, extra whitespace, and lowercases.
    'Fix the login bug!' and 'fix login bug' produce the same hash."""
    text = text.lower().strip()
    # Remove common articles/filler words
    for word in ("the ", "a ", "an ", "please ", "can you ", "could you ",
                 "i want to ", "i need to ", "let's ", "let us "):
        text = text.replace(word, "")
    # Remove punctuation
    text = re.sub(r'[^a-z0-9\s]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


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
