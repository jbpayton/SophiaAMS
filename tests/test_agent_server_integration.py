"""Tests for rewritten agent_server.py — use FastAPI TestClient, mock SophiaAgent."""

import json
import sys
import unittest
from unittest.mock import MagicMock, patch

# We need to mock heavy modules BEFORE agent_server is imported.
# Create mock modules for anything that touches Qdrant/embeddings/etc.

_mock_kgraph_instance = MagicMock()
_mock_kgraph_instance.get_all_triples.return_value = []

_mock_memory_instance = MagicMock()
_mock_memory_instance.query_related_information.return_value = {"triples": [], "summary": ""}
_mock_memory_instance.query_goals.return_value = []
_mock_memory_instance.query_procedure.return_value = {"methods": []}
_mock_memory_instance.ingest_text.return_value = {"triples": [1]}

_mock_episodic_instance = MagicMock()
_mock_episodic_instance.get_recent_episodes.return_value = []
_mock_episodic_instance.get_timeline_summary.return_value = "No activity"
_mock_episodic_instance.search_episodes_by_content.return_value = []
_mock_episodic_instance.query_episodes_by_time.return_value = []

_mock_explorer_instance = MagicMock()
_mock_explorer_instance.cluster_for_query.return_value = []

_mock_sophia_instance = MagicMock()
_mock_sophia_instance.chat.return_value = "Hello from Sophia!"
_mock_sophia_instance._sessions = {"test-session": MagicMock()}
_mock_sophia_instance.clear_session = MagicMock()

# Mock module-level classes
_mock_vkg_module = MagicMock()
_mock_vkg_module.VectorKnowledgeGraph.return_value = _mock_kgraph_instance
sys.modules['VectorKnowledgeGraph'] = _mock_vkg_module

_mock_asm_module = MagicMock()
_mock_asm_module.AssociativeSemanticMemory.return_value = _mock_memory_instance
sys.modules['AssociativeSemanticMemory'] = _mock_asm_module

_mock_em_module = MagicMock()
_mock_em_module.EpisodicMemory.return_value = _mock_episodic_instance
sys.modules['EpisodicMemory'] = _mock_em_module

_mock_me_module = MagicMock()
_mock_me_module.MemoryExplorer.return_value = _mock_explorer_instance
sys.modules['MemoryExplorer'] = _mock_me_module

_mock_mq_module = MagicMock()
sys.modules['message_queue'] = _mock_mq_module

_mock_aa_module = MagicMock()
sys.modules['autonomous_agent'] = _mock_aa_module

# Mock sophia_agent module
_mock_sa_module = MagicMock()
_mock_sa_module.SophiaAgent.return_value = _mock_sophia_instance
sys.modules['sophia_agent'] = _mock_sa_module

# Now we can safely import agent_server
import importlib
import agent_server
importlib.reload(agent_server)

# Override the module-level singletons with our mocks
agent_server.sophia = _mock_sophia_instance
agent_server.memory_system = _mock_memory_instance
agent_server.episodic_memory = _mock_episodic_instance
agent_server.kgraph = _mock_kgraph_instance
agent_server.memory_explorer = _mock_explorer_instance

from fastapi.testclient import TestClient

client = TestClient(agent_server.app)


class TestAgentServerIntegration(unittest.TestCase):

    def test_health_endpoint(self):
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("active_sessions", data)

    def test_chat_endpoint_shape(self):
        resp = client.post("/chat/test-session", json={"content": "Hello"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("response", data)
        self.assertIn("session_id", data)
        self.assertEqual(data["session_id"], "test-session")

    def test_session_clear(self):
        resp = client.delete("/session/test-session")
        self.assertEqual(resp.status_code, 200)

    def test_query_endpoint(self):
        resp = client.post("/query", json={"text": "test", "limit": 5})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("results", data)
        self.assertIn("triple_count", data)

    def test_stats_endpoint(self):
        resp = client.get("/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("triple_count", data)

    def test_episodes_recent(self):
        resp = client.get("/api/episodes/recent")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("episodes", data)

    def test_episodes_timeline(self):
        resp = client.get("/api/episodes/timeline?days=7")
        self.assertEqual(resp.status_code, 200)

    def test_goals_list(self):
        resp = client.get("/api/goals")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("goals", data)

    def test_ingest_endpoint(self):
        resp = client.post("/ingest", json={"text": "test fact", "limit": 10})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("success", data)

    def test_ingest_document(self):
        resp = client.post("/ingest/document", json={
            "text": "This is a test document with some content.",
            "source": "test",
            "metadata": {}
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])

    def test_explore_overview(self):
        resp = client.get("/explore/overview")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("overview", data)

    def test_export_triples(self):
        resp = client.get("/export/all_triples")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("triples", data)

    def test_procedure_query(self):
        resp = client.post("/query/procedure", json={"text": "how to test", "limit": 5})
        self.assertEqual(resp.status_code, 200)

    def test_explore_entity(self):
        resp = client.post("/explore/entity", json={"text": "Python", "limit": 5})
        self.assertEqual(resp.status_code, 200)

    def test_stream_endpoint(self):
        resp = client.post("/chat/test-session/stream", json={"content": "Hello"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp.headers["content-type"])

    def test_episodes_search_post(self):
        resp = client.post("/api/episodes/search", json={"text": "Python", "limit": 5})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("episodes", data)


if __name__ == "__main__":
    unittest.main()
