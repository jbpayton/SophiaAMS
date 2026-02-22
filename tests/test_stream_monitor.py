"""Tests for stream_monitor.py — mock both memory systems."""

import unittest
from unittest.mock import MagicMock, patch

from stream_monitor import StreamMonitor


class TestStreamMonitor(unittest.TestCase):
    def setUp(self):
        self.semantic = MagicMock()
        self.episodic = MagicMock()
        self.monitor = StreamMonitor(
            semantic_memory=self.semantic,
            episodic_memory=self.episodic,
            auto_recall_limit=5,
            idle_seconds=0.1,
            episode_rotate_threshold=4,
        )

    def tearDown(self):
        # Cancel any pending timers to prevent leaks
        for timer in self.monitor._timers.values():
            timer.cancel()
        self.monitor._timers.clear()

    def test_pre_process_recall_formatting(self):
        """pre_process formats recalled triples."""
        self.semantic.query_related_information.return_value = {
            "triples": [
                (("Joey", "likes", "Python"), {"topics": ["programming"]}),
                (("Joey", "lives in", "USA"), {"topics": ["geography"]}),
            ]
        }
        self.semantic.get_active_goals_for_prompt.return_value = ""

        result = self.monitor.pre_process("Tell me about Joey", "s1")
        self.assertIn("Joey likes Python", result)
        self.assertIn("Joey lives in USA", result)
        self.assertIn("programming", result)

    def test_pre_process_goals_inclusion(self):
        """pre_process includes active goals."""
        self.semantic.query_related_information.return_value = {"triples": []}
        self.semantic.get_active_goals_for_prompt.return_value = "1. Learn Python"

        result = self.monitor.pre_process("goals", "s1")
        self.assertIn("ACTIVE GOALS", result)
        self.assertIn("Learn Python", result)

    def test_pre_process_error_handling(self):
        """pre_process returns empty string on error."""
        self.semantic.query_related_information.side_effect = Exception("DB down")

        result = self.monitor.pre_process("test", "s1")
        self.assertEqual(result, "")

    def test_post_process_episode_creation(self):
        """post_process creates episode and saves messages."""
        episode = MagicMock()
        episode.episode_id = "ep1"
        self.episodic.start_episode.return_value = episode

        self.monitor.post_process("s1", "Hello", "Hi there!")

        self.episodic.start_episode.assert_called_once_with(session_id="s1")
        self.assertEqual(self.episodic.add_message.call_count, 2)

    def test_post_process_message_saving(self):
        """post_process saves user and assistant messages."""
        episode = MagicMock()
        episode.episode_id = "ep1"
        self.episodic.start_episode.return_value = episode

        self.monitor.post_process("s1", "user msg", "assistant msg")

        calls = self.episodic.add_message.call_args_list
        self.assertEqual(calls[0][1]["role"], "user")
        self.assertEqual(calls[0][1]["content"], "user msg")
        self.assertEqual(calls[1][1]["role"], "assistant")
        self.assertEqual(calls[1][1]["content"], "assistant msg")

    def test_post_process_extraction_queuing(self):
        """post_process queues non-trivial exchanges for extraction."""
        episode = MagicMock()
        episode.episode_id = "ep1"
        self.episodic.start_episode.return_value = episode

        self.monitor.post_process("s1", "Tell me about Python", "Python is a great language")

        session = self.monitor._sessions["s1"]
        self.assertEqual(len(session["extraction_queue"]), 1)

    def test_short_message_skipping(self):
        """Very short messages are not queued for extraction."""
        episode = MagicMock()
        episode.episode_id = "ep1"
        self.episodic.start_episode.return_value = episode

        self.monitor.post_process("s1", "hi", "hey")

        session = self.monitor._sessions["s1"]
        self.assertEqual(len(session["extraction_queue"]), 0)

    def test_episode_rotation(self):
        """Episode is rotated after threshold messages."""
        episode = MagicMock()
        episode.episode_id = "ep1"
        self.episodic.start_episode.return_value = episode

        # threshold is 4, each post_process adds 2 messages
        self.monitor.post_process("s1", "msg1 long enough", "resp1 long enough")
        self.monitor.post_process("s1", "msg2 long enough", "resp2 long enough")

        self.episodic.finalize_episode.assert_called_with("ep1")
        session = self.monitor._sessions["s1"]
        self.assertIsNone(session["episode_id"])
        self.assertEqual(session["message_count"], 0)

    def test_flush_processing(self):
        """flush() processes pending extractions immediately."""
        episode = MagicMock()
        episode.episode_id = "ep1"
        self.episodic.start_episode.return_value = episode

        self.monitor.post_process("s1", "Important conversation content", "Yes, very important response here")
        self.monitor.flush("s1")

        self.semantic.ingest_text.assert_called()
        self.episodic.finalize_episode.assert_called_with("ep1")

    def test_flush_nonexistent_session(self):
        """flush() on unknown session is a no-op."""
        self.monitor.flush("nonexistent")  # Should not raise


if __name__ == "__main__":
    unittest.main()
