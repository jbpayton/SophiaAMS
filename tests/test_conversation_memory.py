"""Tests for conversation_memory.py — pure data structure, no mocks needed."""

import unittest

from conversation_memory import ConversationMemory


class TestConversationMemory(unittest.TestCase):
    def test_add_and_get(self):
        mem = ConversationMemory()
        mem.add_message("user", "Hello")
        mem.add_message("assistant", "Hi there")
        msgs = mem.get_messages()
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[1]["content"], "Hi there")

    def test_threshold_detection(self):
        mem = ConversationMemory(summary_threshold=5)
        for i in range(4):
            mem.add_message("user", f"msg {i}")
        self.assertFalse(mem.needs_summarization())

        mem.add_message("user", "msg 4")
        self.assertTrue(mem.needs_summarization())

    def test_compaction_with_summarize_fn(self):
        def fake_summarize(messages):
            return f"Summary of {len(messages)} messages"

        mem = ConversationMemory(
            max_messages=20,
            summarize_fn=fake_summarize,
            summary_threshold=8,
        )
        for i in range(10):
            mem.add_message("user", f"message {i}")

        mem.summarize()

        # Should have kept recent messages and created summary
        self.assertLess(mem.message_count, 10)
        msgs = mem.get_messages()
        # First message should be the summary
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("Summary", msgs[0]["content"])

    def test_summary_prepended(self):
        mem = ConversationMemory(summary_threshold=4)
        mem._summary = "Previous conversation was about Python"
        mem.add_message("user", "New question")

        msgs = mem.get_messages()
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("Python", msgs[0]["content"])
        self.assertEqual(msgs[1]["role"], "user")

    def test_clear(self):
        mem = ConversationMemory()
        mem.add_message("user", "Hello")
        mem._summary = "old summary"
        mem.clear()

        self.assertEqual(mem.message_count, 0)
        self.assertEqual(len(mem.get_messages()), 0)

    def test_double_summarize(self):
        """Summarizing twice should incorporate previous summary."""
        call_count = [0]

        def summarize_fn(messages):
            call_count[0] += 1
            return f"Summary v{call_count[0]}"

        mem = ConversationMemory(summarize_fn=summarize_fn, summary_threshold=5)

        # First round
        for i in range(6):
            mem.add_message("user", f"batch1 msg {i}")
        mem.summarize()
        self.assertEqual(call_count[0], 1)

        # Second round
        for i in range(6):
            mem.add_message("user", f"batch2 msg {i}")
        mem.summarize()
        self.assertEqual(call_count[0], 2)

    def test_no_summarize_fn_drops_messages(self):
        """Without summarize_fn, old messages are dropped with a note."""
        mem = ConversationMemory(summary_threshold=5)
        for i in range(6):
            mem.add_message("user", f"msg {i}")

        mem.summarize()
        self.assertLess(mem.message_count, 6)
        self.assertIn("dropped", mem._summary)


if __name__ == "__main__":
    unittest.main()
