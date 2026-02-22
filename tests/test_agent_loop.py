"""Tests for agent_loop.py — mock LLMClient and CodeRunner."""

import unittest
from unittest.mock import MagicMock, patch, call

from agent_loop import AgentLoop, _RUN_BLOCK_RE
from llm_client import LLMClient
from code_runner import CodeRunner, RunResult
from conversation_memory import ConversationMemory
from skill_loader import SkillLoader


class TestRunBlockRegex(unittest.TestCase):
    def test_single_block(self):
        text = 'Here is code:\n```run\nprint("hello")\n```\nDone.'
        matches = _RUN_BLOCK_RE.findall(text)
        self.assertEqual(len(matches), 1)
        self.assertIn('print("hello")', matches[0])

    def test_multiple_blocks(self):
        text = '```run\ncode1()\n```\nSome text\n```run\ncode2()\n```'
        matches = _RUN_BLOCK_RE.findall(text)
        self.assertEqual(len(matches), 2)

    def test_no_blocks(self):
        text = "Just a normal response with no code."
        matches = _RUN_BLOCK_RE.findall(text)
        self.assertEqual(len(matches), 0)

    def test_regular_code_block_not_matched(self):
        text = '```python\nprint("hi")\n```'
        matches = _RUN_BLOCK_RE.findall(text)
        self.assertEqual(len(matches), 0)


class TestAgentLoop(unittest.TestCase):
    def setUp(self):
        self.llm = MagicMock(spec=LLMClient)
        self.runner = MagicMock(spec=CodeRunner)
        self.loop = AgentLoop(
            llm=self.llm,
            runner=self.runner,
            system_prompt="You are Sophia.",
            max_rounds=3,
        )

    def test_simple_response(self):
        """Response with no code blocks is returned directly."""
        self.llm.chat.return_value = "Hello! How can I help?"
        result = self.loop.chat("Hi")
        self.assertEqual(result, "Hello! How can I help?")
        self.llm.chat.assert_called_once()

    def test_code_block_execution(self):
        """Code blocks are executed and fed back."""
        # First LLM call returns code block
        self.llm.chat.side_effect = [
            'Let me check:\n```run\nprint("42")\n```',
            "The answer is 42.",
        ]
        self.runner.run.return_value = RunResult(stdout="42", stderr="", returncode=0)

        result = self.loop.chat("What is 6*7?")
        self.assertEqual(result, "The answer is 42.")
        self.runner.run.assert_called_once()
        self.assertEqual(self.llm.chat.call_count, 2)

    def test_max_rounds_enforcement(self):
        """Loop stops after max_rounds even if code blocks keep appearing."""
        self.llm.chat.return_value = '```run\nprint("loop")\n```'
        self.runner.run.return_value = RunResult(stdout="loop", stderr="", returncode=0)

        result = self.loop.chat("Go forever")
        # Should have been called max_rounds times
        self.assertEqual(self.llm.chat.call_count, 3)

    def test_hook_invocation(self):
        """Pre and post process hooks are called."""
        pre_hook = MagicMock(return_value="recalled: Joey likes Python")
        post_hook = MagicMock()

        loop = AgentLoop(
            llm=self.llm,
            runner=self.runner,
            system_prompt="You are Sophia.",
            pre_process_hook=pre_hook,
            post_process_hook=post_hook,
        )

        self.llm.chat.return_value = "I know Joey likes Python!"
        loop.chat("What does Joey like?", session_id="test-session")

        pre_hook.assert_called_once_with("What does Joey like?", "test-session")
        post_hook.assert_called_once_with(
            "test-session", "What does Joey like?", "I know Joey likes Python!"
        )

    def test_context_injection(self):
        """Pre-process context appears in system prompt."""
        pre_hook = MagicMock(return_value="recalled: important context")

        loop = AgentLoop(
            llm=self.llm,
            runner=self.runner,
            system_prompt="You are Sophia.",
            pre_process_hook=pre_hook,
        )

        self.llm.chat.return_value = "Got it."
        loop.chat("test")

        # Check that the messages sent to LLM contain the recall context
        # (now injected as a separate system message, not merged into the first)
        call_args = self.llm.chat.call_args
        messages = call_args[0][0]
        all_system = " ".join(m["content"] for m in messages if m["role"] == "system")
        self.assertIn("important context", all_system)

    def test_skill_descriptions_in_prompt(self):
        """Skill descriptions are included in system prompt via template."""
        skill_loader = MagicMock(spec=SkillLoader)
        skill_loader.descriptions.return_value = "  - memory-query: Search memory"

        # Use a template with {skills_section} placeholder
        loop = AgentLoop(
            llm=self.llm,
            runner=self.runner,
            system_prompt="You are Sophia.\n{skills_section}",
            skill_loader=skill_loader,
        )

        self.llm.chat.return_value = "Done."
        loop.chat("test")

        call_args = self.llm.chat.call_args
        messages = call_args[0][0]
        system_msg = messages[0]["content"]
        self.assertIn("memory-query", system_msg)

    def test_conversation_tracking(self):
        """Messages are added to conversation memory."""
        self.llm.chat.return_value = "Response"
        self.loop.chat("Input")

        msgs = self.loop.conversation_memory.get_messages()
        roles = [m["role"] for m in msgs]
        self.assertIn("user", roles)
        self.assertIn("assistant", roles)


if __name__ == "__main__":
    unittest.main()
