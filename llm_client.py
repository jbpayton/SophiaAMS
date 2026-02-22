"""
Zero-dependency HTTP client for OpenAI-compatible LLM endpoints.
Replaces LangChain's ChatOpenAI with raw urllib calls.
"""

import json
import os
import re
import urllib.request
import urllib.error


class LLMError(Exception):
    """Raised when the LLM request fails."""
    pass


# Pre-compiled pattern for stripping <think>...</think> blocks from LLM output.
# Many local models (via LM Studio, llama.cpp, etc.) emit reasoning tokens
# wrapped in these tags.  We strip them so downstream code sees only the
# final answer.
_THINK_RE = re.compile(r'<think>.*?</think>\s*', re.DOTALL)


class LLMClient:
    """
    Minimal client for OpenAI-compatible /v1/chat/completions endpoints.
    Uses only urllib — no third-party dependencies.
    """

    def __init__(
        self,
        base_url: str = None,
        api_key: str = None,
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: int = 120,
        strip_thinking: bool = True,
    ):
        self.base_url = (base_url or os.environ.get("LLM_API_BASE", "http://localhost:1234/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "not-needed")
        self.model = model or os.environ.get("LLM_MODEL", "default")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.strip_thinking = strip_thinking

    @staticmethod
    def _strip_think_tokens(text: str) -> str:
        """Remove <think>...</think> blocks from LLM output."""
        return _THINK_RE.sub('', text).strip()

    def chat(self, messages: list, **overrides) -> str:
        """
        Send a chat completion request and return the assistant's reply.

        Args:
            messages: List of {"role": ..., "content": ...} dicts
            **overrides: Override model, temperature, max_tokens per call

        Returns:
            The assistant message content string.

        Raises:
            LLMError: On HTTP errors, timeouts, or malformed responses.
        """
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": overrides.get("model", self.model),
            "messages": messages,
            "temperature": overrides.get("temperature", self.temperature),
            "max_tokens": overrides.get("max_tokens", self.max_tokens),
        }

        # Allow callers to disable thinking per-call (e.g., for summarization).
        # Default: leave it to the model/server config.
        if "enable_thinking" in overrides:
            payload["enable_thinking"] = overrides["enable_thinking"]

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=overrides.get("timeout", self.timeout)) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise LLMError(f"HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"Connection error: {exc.reason}") from exc
        except TimeoutError as exc:
            raise LLMError("Request timed out") from exc
        except json.JSONDecodeError as exc:
            raise LLMError("Malformed JSON response") from exc

        # Parse response
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Malformed response structure: {body}") from exc

        # Strip reasoning tokens if enabled
        if self.strip_thinking and content:
            content = self._strip_think_tokens(content)

        return content
