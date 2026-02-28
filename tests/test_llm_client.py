"""Tests for llm_client.py — all mock urllib.request.urlopen."""

import json
import os
import unittest
from unittest.mock import patch, MagicMock
from io import BytesIO

from llm_client import LLMClient, LLMError, strip_think_tokens


def _mock_response(body_dict, status=200):
    """Create a mock HTTP response."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(body_dict).encode("utf-8")
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestLLMClient(unittest.TestCase):
    def test_success_response(self):
        """Basic successful chat completion."""
        client = LLMClient(base_url="http://test:1234/v1", api_key="k", model="m")
        body = {"choices": [{"message": {"content": "Hello!"}}]}

        with patch("urllib.request.urlopen", return_value=_mock_response(body)):
            result = client.chat([{"role": "user", "content": "Hi"}])

        self.assertEqual(result, "Hello!")

    def test_env_defaults(self):
        """Client reads defaults from environment variables."""
        env = {
            "LLM_API_BASE": "http://env-host/v1",
            "LLM_API_KEY": "env-key",
            "LLM_MODEL": "env-model",
        }
        with patch.dict(os.environ, env, clear=False):
            client = LLMClient()

        self.assertEqual(client.base_url, "http://env-host/v1")
        self.assertEqual(client.api_key, "env-key")
        self.assertEqual(client.model, "env-model")

    def test_param_overrides(self):
        """Per-call overrides for model, temperature, max_tokens."""
        client = LLMClient(base_url="http://test:1234/v1", api_key="k", model="base")
        body = {"choices": [{"message": {"content": "ok"}}]}

        with patch("urllib.request.urlopen", return_value=_mock_response(body)) as mock_open:
            client.chat(
                [{"role": "user", "content": "x"}],
                model="override-model",
                temperature=0.1,
                max_tokens=100,
            )

            # Inspect the request payload
            call_args = mock_open.call_args
            req = call_args[0][0]
            payload = json.loads(req.data.decode("utf-8"))
            self.assertEqual(payload["model"], "override-model")
            self.assertEqual(payload["temperature"], 0.1)
            self.assertEqual(payload["max_tokens"], 100)

    def test_http_error(self):
        """HTTP errors raise LLMError."""
        import urllib.error

        client = LLMClient(base_url="http://test:1234/v1", api_key="k", model="m")
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url="", code=500, msg="Internal Server Error", hdrs=None, fp=None
        )):
            with self.assertRaises(LLMError) as ctx:
                client.chat([{"role": "user", "content": "Hi"}])
            self.assertIn("500", str(ctx.exception))

    def test_timeout(self):
        """Timeouts raise LLMError."""
        client = LLMClient(base_url="http://test:1234/v1", api_key="k", model="m", timeout=1)
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaises(LLMError) as ctx:
                client.chat([{"role": "user", "content": "Hi"}])
            self.assertIn("timed out", str(ctx.exception))

    def test_malformed_response(self):
        """Missing choices raises LLMError."""
        client = LLMClient(base_url="http://test:1234/v1", api_key="k", model="m")
        body = {"not_choices": []}
        with patch("urllib.request.urlopen", return_value=_mock_response(body)):
            with self.assertRaises(LLMError) as ctx:
                client.chat([{"role": "user", "content": "Hi"}])
            self.assertIn("Malformed", str(ctx.exception))


class TestStripThinkTokens(unittest.TestCase):
    """Tests for the module-level strip_think_tokens function."""

    def test_closed_tags(self):
        """Properly closed <think>...</think> tags are stripped."""
        text = "<think>reasoning here</think>The answer is 42."
        self.assertEqual(strip_think_tokens(text), "The answer is 42.")

    def test_unclosed_tag(self):
        """Unclosed <think> tag (model ran out of tokens) is stripped."""
        text = "<think>very long reasoning that never closes... The answer is"
        self.assertEqual(strip_think_tokens(text), "")

    def test_unclosed_after_content(self):
        """Unclosed <think> after real content is stripped, keeping the content."""
        text = "Here is the answer.\n<think>some trailing reasoning"
        self.assertEqual(strip_think_tokens(text), "Here is the answer.")

    def test_no_tags(self):
        """Text without think tags is returned as-is."""
        text = "Just a normal response."
        self.assertEqual(strip_think_tokens(text), "Just a normal response.")

    def test_mixed_closed_and_unclosed(self):
        """Handles both closed tags and a trailing unclosed tag."""
        text = "<think>first block</think>Middle content.<think>unclosed trailing"
        self.assertEqual(strip_think_tokens(text), "Middle content.")

    def test_empty_string(self):
        """Empty string returns empty."""
        self.assertEqual(strip_think_tokens(""), "")

    def test_large_think_block(self):
        """Large think blocks (simulating 60k+ chars) are handled."""
        big_think = "<think>" + "x" * 60000 + "</think>Result."
        self.assertEqual(strip_think_tokens(big_think), "Result.")

    def test_orphan_close_tag(self):
        """Missing opening <think> — model starts reasoning without the tag."""
        text = 'The user wants to do X.\nLet me think about this.</think>Here is my answer.'
        self.assertEqual(strip_think_tokens(text), "Here is my answer.")

    def test_orphan_close_tag_immediate(self):
        """Orphan </think> right at the start."""
        text = '</think>Hello!'
        self.assertEqual(strip_think_tokens(text), "Hello!")


class TestPlaintextThinkStripping(unittest.TestCase):
    """Tests for plaintext 'Thinking Process:' stripping (Qwen3.5 style)."""

    def test_thinking_process_with_answer(self):
        """Strips 'Thinking Process:' block, preserves answer after blank line."""
        text = (
            "Thinking Process:\n"
            "The user wants to know about cats.\n"
            "I should mention their traits.\n"
            "\n"
            "Cats are fascinating animals with unique behaviors."
        )
        result = strip_think_tokens(text)
        self.assertIn("Cats are fascinating", result)
        self.assertNotIn("Thinking Process", result)

    def test_thinking_process_with_code_block(self):
        """Preserves ```run blocks after the thinking section."""
        text = (
            "Thinking Process:\n"
            "I need to search the web for this.\n"
            "Let me use the web-search skill.\n"
            "\n"
            "```run\n"
            "print('hello')\n"
            "```\n"
            "Here is what I found."
        )
        result = strip_think_tokens(text)
        self.assertIn("```run", result)
        self.assertIn("print('hello')", result)
        self.assertIn("Here is what I found", result)

    def test_internal_reasoning_variant(self):
        """Handles 'Internal Reasoning:' header variant."""
        text = (
            "Internal Reasoning:\n"
            "Let me think step by step.\n"
            "\n"
            "The answer is 42."
        )
        result = strip_think_tokens(text)
        self.assertIn("The answer is 42", result)
        self.assertNotIn("Internal Reasoning", result)

    def test_reasoning_variant(self):
        """Handles bare 'Reasoning:' header variant."""
        text = (
            "Reasoning:\n"
            "Step 1: Consider the input.\n"
            "Step 2: Analyze it.\n"
            "\n"
            "Based on my analysis, the result is positive."
        )
        result = strip_think_tokens(text)
        self.assertIn("result is positive", result)

    def test_thinking_only_no_answer(self):
        """When entire response is thinking with no clear answer, returns as-is."""
        text = (
            "Thinking Process:\n"
            "the user asked about something\n"
            "i need to think more\n"
            "but i never got to the answer\n"
        )
        result = strip_think_tokens(text)
        # Should leave as-is when no clear answer section found
        # (empty-response retry in agent_loop handles this)
        self.assertTrue(len(result) > 0)

    def test_no_plaintext_thinking(self):
        """Normal text without thinking headers is returned unchanged."""
        text = "Here is a perfectly normal response with no thinking."
        self.assertEqual(strip_think_tokens(text), text)

    def test_combined_think_tags_and_plaintext(self):
        """Handles response with both <think> tags and plaintext thinking."""
        text = (
            "<think>Initial reasoning</think>"
            "Thinking Process:\n"
            "More reasoning here.\n"
            "\n"
            "Final answer."
        )
        result = strip_think_tokens(text)
        self.assertIn("Final answer", result)
        self.assertNotIn("<think>", result)


if __name__ == "__main__":
    unittest.main()
