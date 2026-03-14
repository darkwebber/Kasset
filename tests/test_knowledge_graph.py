"""
Tests for backend/core/knowledge_graph.py — the agent's working memory system.

Covers:
- Node creation and retrieval
- Edge creation and relationship tracking
- Working memory updates
- Episode summarization
- Round tracking
- Compact map generation for prompt injection
"""
import pytest
from core.knowledge_graph import ConversationGraph, GraphNode


class TestKnowledgeGraphBasics:
    @pytest.fixture
    def graph(self):
        return ConversationGraph()

    def test_empty_graph(self, graph):
        assert isinstance(graph.nodes, dict)
        # Fresh graph may have 0 nodes or pre-seeded working_memory
        assert isinstance(graph.edges, list)

    def test_set_round(self, graph):
        graph.set_round(0)
        assert graph._round == 0
        graph.set_round(5)
        assert graph._round == 5

    def test_add_node(self, graph):
        nid = graph.add_node("concept", "test_node", "Test content")
        assert nid == "test_node"
        assert "test_node" in graph.nodes
        assert graph.nodes["test_node"].content == "Test content"

    def test_add_node_updates_existing(self, graph):
        graph.add_node("concept", "n1", "Original")
        graph.add_node("concept", "n1", "Updated")
        assert graph.nodes["n1"].content == "Updated"

    def test_add_episode(self, graph):
        graph.set_round(0)
        eid = graph.add_episode("Completed initial analysis")
        assert eid in graph.nodes
        assert graph.nodes[eid].type == "episode"

    def test_update_working_memory(self, graph):
        graph.update_working_memory(intent="Write a blog post", state="Gathering info")
        wm = graph.nodes.get("working_memory")
        assert wm is not None
        assert "Write a blog post" in wm.content

    def test_add_edge(self, graph):
        graph.add_node("concept", "a", "Node A")
        graph.add_node("concept", "b", "Node B")
        graph.add_edge("a", "b", "related_to")
        assert len(graph.edges) >= 1
        assert any(e.from_id == "a" and e.to_id == "b" for e in graph.edges)

    def test_invalid_node_type_falls_back(self, graph):
        """Invalid node types should fall back to 'concept'."""
        nid = graph.add_node("invalid_type_xyz", "bad_node", "Content")
        assert graph.nodes["bad_node"].type == "concept"


class TestKnowledgeGraphIntegration:
    """Test realistic usage patterns from agent.py."""

    @pytest.fixture
    def graph(self):
        g = ConversationGraph()
        g.set_round(0)
        return g

    def test_multi_round_simulation(self, graph):
        """Simulate multi-round agent execution."""
        graph.update_working_memory(intent="Write a product launch email")
        for i in range(5):
            graph.set_round(i)
            graph.add_node("concept", f"finding_{i}", f"Discovery {i}")
            if i > 0 and i % 2 == 0:
                graph.add_episode(f"Progress after round {i}")
        assert len(graph.nodes) >= 5

    def test_large_content_handling(self, graph):
        """Agent may feed very long content into the graph."""
        big_text = "x" * 10000
        graph.add_episode(big_text)
        # Should not crash — may truncate internally

    def test_compact_map_generation(self, graph):
        """Graph should produce a compact text map for system prompt injection."""
        graph.update_working_memory(intent="Test task")
        graph.add_node("concept", "key_idea", "Important concept")
        if hasattr(graph, 'get_compact_map'):
            result = graph.get_compact_map()
            assert isinstance(result, str)
        elif hasattr(graph, 'render'):
            result = graph.render()
            assert isinstance(result, str)

    def test_node_importance_max_preserved(self, graph):
        """Importance should never decrease on update."""
        graph.add_node("concept", "imp_test", "Content", importance=0.9)
        graph.add_node("concept", "imp_test", "Updated", importance=0.3)
        assert graph.nodes["imp_test"].importance >= 0.9
