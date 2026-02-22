"""Tests for sophia_agent.py — mock LLMClient and memory systems."""

import unittest
from unittest.mock import MagicMock, patch

from sophia_agent import SophiaAgent


class TestSophiaAgent(unittest.TestCase):
    def setUp(self):
        self.semantic = MagicMock()
        self.episodic = MagicMock()
        self.explorer = MagicMock()

        # Mock memory returns
        self.semantic.query_related_information.return_value = {"triples": []}
        self.semantic.get_active_goals_for_prompt.return_value = ""
        episode = MagicMock()
        episode.episode_id = "ep1"
        self.episodic.start_episode.return_value = episode

        # Patch LLMClient.chat and workspace init
        self.llm_patcher = patch("sophia_agent.LLMClient")
        self.ws_patcher = patch("sophia_agent.init_workspace")
        self.mock_llm_cls = self.llm_patcher.start()
        self.mock_ws = self.ws_patcher.start()

        self.mock_llm = MagicMock()
        self.mock_llm.chat.return_value = "Hello from Sophia!"
        self.mock_llm_cls.return_value = self.mock_llm

        self.agent = SophiaAgent(
            semantic_memory=self.semantic,
            episodic_memory=self.episodic,
            memory_explorer=self.explorer,
            workspace_dir="/tmp/test_ws",
            skill_paths=[],
        )

    def tearDown(self):
        self.llm_patcher.stop()
        self.ws_patcher.stop()

    def test_chat_returns_string(self):
        result = self.agent.chat("s1", "Hello")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_session_creation(self):
        self.agent.chat("s1", "Hello")
        self.assertIn("s1", self.agent._sessions)

    def test_session_reuse(self):
        self.agent.chat("s1", "Hello")
        self.agent.chat("s1", "How are you?")
        # Should reuse the same session
        self.assertEqual(len(self.agent._sessions), 1)

    def test_multiple_sessions(self):
        self.agent.chat("s1", "Hello")
        self.agent.chat("s2", "Hi")
        self.assertEqual(len(self.agent._sessions), 2)

    def test_clear_session(self):
        self.agent.chat("s1", "Hello")
        self.agent.clear_session("s1")
        self.assertNotIn("s1", self.agent._sessions)

    def test_clear_nonexistent_session(self):
        # Should not raise
        self.agent.clear_session("nonexistent")

    def test_hooks_wired(self):
        """Stream monitor hooks should be connected."""
        self.agent.chat("s1", "Hello")
        # pre_process should have been called
        self.semantic.query_related_information.assert_called()
        # post_process should have been called
        self.episodic.start_episode.assert_called()

    def test_system_prompt_contains_time(self):
        self.agent.chat("s1", "Hello")
        loop = self.agent._sessions["s1"]
        # Template is stored; time is injected dynamically each turn
        self.assertIn("Current time:", loop.system_prompt_template)
        # Verify the built prompt has an actual timestamp
        built = loop._build_system_prompt()
        self.assertIn("Current time: 20", built)


if __name__ == "__main__":
    unittest.main()
