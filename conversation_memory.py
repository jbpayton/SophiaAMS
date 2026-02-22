"""
Short-term conversation memory with LLM-based summarization.
Replaces LangChain's ConversationBufferMemory.
"""

import copy
from typing import Callable, List, Dict, Optional


class ConversationMemory:
    """
    Rolling message window that summarizes older messages when the window grows
    beyond a threshold. Framework-agnostic — no LangChain dependency.
    """

    def __init__(
        self,
        max_messages: int = 50,
        summarize_fn: Callable[[List[Dict]], str] = None,
        summary_threshold: int = 40,
    ):
        """
        Args:
            max_messages: Maximum messages to keep before forcing summarization.
            summarize_fn: Callable that takes a list of messages and returns a summary string.
                          If None, older messages are simply dropped.
            summary_threshold: Trigger summarization when message count reaches this.
        """
        self.max_messages = max_messages
        self.summarize_fn = summarize_fn
        self.summary_threshold = summary_threshold
        self._messages: List[Dict] = []
        self._summary: Optional[str] = None

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation history."""
        self._messages.append({"role": role, "content": content})

    def get_messages(self) -> List[Dict]:
        """
        Return messages for inclusion in the LLM prompt.
        If a summary exists, it is prepended as a system message.
        """
        result = []
        if self._summary:
            result.append({
                "role": "system",
                "content": f"Summary of earlier conversation:\n{self._summary}",
            })
        result.extend(copy.deepcopy(self._messages))
        return result

    def needs_summarization(self) -> bool:
        """Check if the message count has reached the summarization threshold."""
        return len(self._messages) >= self.summary_threshold

    def summarize(self) -> None:
        """
        Compress older messages into a summary, keeping the most recent messages.
        Uses summarize_fn if provided; otherwise drops old messages silently.
        """
        if not self.needs_summarization():
            return

        # Keep the most recent quarter of messages
        keep_count = max(len(self._messages) // 4, 4)
        older = self._messages[:-keep_count]
        recent = self._messages[-keep_count:]

        if self.summarize_fn and older:
            # Build context for summarization including existing summary
            to_summarize = []
            if self._summary:
                to_summarize.append({"role": "system", "content": f"Previous summary: {self._summary}"})
            to_summarize.extend(older)
            self._summary = self.summarize_fn(to_summarize)
        elif self._summary and older:
            # No summarize_fn — just note that messages were dropped
            self._summary = self._summary + "\n[additional messages dropped]"
        elif older:
            self._summary = f"[{len(older)} earlier messages dropped]"

        self._messages = recent

    def clear(self) -> None:
        """Reset all conversation state."""
        self._messages = []
        self._summary = None

    @property
    def message_count(self) -> int:
        return len(self._messages)
