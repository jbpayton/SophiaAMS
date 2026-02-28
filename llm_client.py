"""
Zero-dependency HTTP client for OpenAI-compatible LLM endpoints.
Replaces LangChain's ChatOpenAI with raw urllib calls.
"""

import json
import logging
import os
import re
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when the LLM request fails."""
    pass


# Pre-compiled patterns for stripping <think> blocks from LLM output.
# Many local models (via LM Studio, llama.cpp, etc.) emit reasoning tokens
# wrapped in these tags.  We strip them so downstream code sees only the
# final answer.
_THINK_RE = re.compile(r'<think>.*?</think>\s*', re.DOTALL)
# Unclosed <think> — model started reasoning but never closed the tag.
_UNCLOSED_THINK_RE = re.compile(r'<think>(?:(?!</think>).)*$', re.DOTALL)
# Missing opening <think> — model started thinking without the tag, then closed it.
_ORPHAN_CLOSE_THINK_RE = re.compile(r'^[^<]*</think>\s*', re.DOTALL)

# Plaintext thinking format used by Qwen3.5 and similar models.
# Matches "Thinking Process:\n..." followed by the actual response.
# The response typically starts after a blank line or a markdown heading.
_PLAINTEXT_THINK_RE = re.compile(
    r'^(?:Thinking Process|Internal Reasoning|Reasoning|Thought Process)\s*:\s*\n'
    r'(?:.*?\n)*?'         # thinking content (non-greedy lines)
    r'(?=\n(?:```|[A-Z]))',  # stop before a code fence or a line starting with uppercase
    re.MULTILINE | re.DOTALL
)

# Fallback: if the entire response is a "Thinking Process:" block with no
# clear answer section, strip everything up to the last numbered list item
# or markdown section.
_PLAINTEXT_THINK_ONLY_RE = re.compile(
    r'^(?:Thinking Process|Internal Reasoning|Reasoning|Thought Process)\s*:\s*\n',
    re.MULTILINE
)


def strip_think_tokens(text: str) -> str:
    """Remove thinking/reasoning blocks from LLM output.

    Handles:
    - ``<think>...</think>`` tags (closed, unclosed, orphan close)
    - Plaintext "Thinking Process:" blocks (Qwen3.5 style)
    - Text with no think patterns (returned as-is)
    """
    # 1. Handle <think> tag variants
    result = _THINK_RE.sub('', text)
    result = _UNCLOSED_THINK_RE.sub('', result)
    if '</think>' in result and '<think>' not in result:
        result = _ORPHAN_CLOSE_THINK_RE.sub('', result)

    # 2. Handle plaintext thinking (Qwen3.5 style)
    if _PLAINTEXT_THINK_ONLY_RE.match(result):
        # Try to find where thinking ends and answer begins
        stripped = _PLAINTEXT_THINK_RE.sub('', result)
        if stripped.strip():
            result = stripped
        # else: entire response is thinking — leave it for the empty-response
        # retry handler in agent_loop to deal with

    return result.strip()


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
        context_window: int = None,
    ):
        self.base_url = (base_url or os.environ.get("LLM_API_BASE", "http://localhost:1234/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "not-needed")
        self.model = model or os.environ.get("LLM_MODEL", "default")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.strip_thinking = strip_thinking
        self.context_window = context_window or int(os.environ.get("LLM_CONTEXT_WINDOW", "0"))

    @staticmethod
    def _strip_think_tokens(text: str) -> str:
        """Remove <think>...</think> blocks from LLM output."""
        return strip_think_tokens(text)

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
        requested_max = overrides.get("max_tokens", self.max_tokens)

        # If we know the context window, clamp max_tokens so input + output
        # fits.  Estimate ~4 chars per token, leave 256-token safety margin.
        if self.context_window and self.context_window > 0:
            input_chars = sum(len(m.get("content", "")) for m in messages)
            input_tokens_est = input_chars // 4
            available = self.context_window - input_tokens_est - 256
            logger.info(
                f"Token budget: input~{input_tokens_est}t, available~{available}t, "
                f"requested={requested_max}, context_window={self.context_window}"
            )
            if available < requested_max and available > 0:
                logger.info(f"Clamping max_tokens from {requested_max} to {available}")
                requested_max = available
            elif available <= 0:
                logger.warning(
                    f"Input may exceed context window! input~{input_tokens_est}t, "
                    f"context_window={self.context_window}"
                )
                # Still send a reasonable request — let the server decide
                requested_max = min(requested_max, 1024)

        payload = {
            "model": overrides.get("model", self.model),
            "messages": messages,
            "temperature": overrides.get("temperature", self.temperature),
            "max_tokens": requested_max,
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
            error_body = ""
            try:
                error_body = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            logger.error(f"HTTP {exc.code} from LLM API: {error_body}")
            raise LLMError(f"HTTP {exc.code}: {exc.reason} — {error_body}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"Connection error: {exc.reason}") from exc
        except TimeoutError as exc:
            raise LLMError("Request timed out") from exc
        except json.JSONDecodeError as exc:
            raise LLMError("Malformed JSON response") from exc

        # Parse response
        try:
            choice = body["choices"][0]
            content = choice["message"]["content"]
            self._last_finish_reason = choice.get("finish_reason", "unknown")
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Malformed response structure: {body}") from exc

        # Strip reasoning tokens if enabled
        if self.strip_thinking and content:
            content = self._strip_think_tokens(content)

        return content
