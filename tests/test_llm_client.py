"""Tests for llm_client.py — all mock urllib.request.urlopen."""

import json
import os
import unittest
from unittest.mock import patch, MagicMock
from io import BytesIO

from llm_client import LLMClient, LLMError


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


if __name__ == "__main__":
    unittest.main()
