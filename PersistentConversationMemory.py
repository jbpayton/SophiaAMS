"""
PersistentConversationMemory - Bridge between LangChain and Episodic Memory

This custom memory class extends LangChain's ConversationBufferMemory to add:
- Automatic persistence of conversations to EpisodicMemory
- Automatic episode creation and management
- Link conversation turns to semantic memory extraction
"""

import logging
import time
from typing import Any, Dict, List, Optional
from langchain.memory import ConversationBufferMemory
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from EpisodicMemory import EpisodicMemory
from AssociativeSemanticMemory import AssociativeSemanticMemory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PersistentConversationMemory(ConversationBufferMemory):
    """
    LangChain memory that automatically persists conversations to episodic memory.

    Features:
    - Creates episode on first message in session
    - Saves each conversation turn to episodic memory
    - Links semantic memory extraction to episodes
    - Loads recent episode context on session start
    """

    def __init__(
        self,
        session_id: str,
        episodic_memory: EpisodicMemory,
        semantic_memory: Optional[AssociativeSemanticMemory] = None,
        auto_extract_semantics: bool = True,
        context_hours: float = 24,
        **kwargs
    ):
        """
        Initialize persistent conversation memory.

        Args:
            session_id: Unique session identifier
            episodic_memory: EpisodicMemory instance for persistence
            semantic_memory: Optional AssociativeSemanticMemory for extraction
            auto_extract_semantics: Whether to automatically extract triples from messages
            context_hours: Hours of recent context to load on initialization
            **kwargs: Additional args passed to ConversationBufferMemory
        """
        # Initialize parent first
        super().__init__(**kwargs)

        # Store as private attributes to avoid pydantic field validation issues
        self._session_id = session_id
        self._episodic_memory = episodic_memory
        self._semantic_memory = semantic_memory
        self._auto_extract_semantics = auto_extract_semantics
        self._context_hours = context_hours

        # Episode tracking
        self._current_episode_id: Optional[str] = None
        self._episode_message_count = 0

        # Load recent context from previous episodes
        self._load_recent_context()

        logger.info(f"[PersistentMemory] Initialized for session {session_id}")

    def _load_recent_context(self):
        """Load recent conversation context from episodic memory."""
        try:
            # Get recent episodes for this session
            recent_episodes = self._episodic_memory.get_recent_episodes(
                hours=self._context_hours,
                limit=3
            )

            # Filter to this session only
            session_episodes = [ep for ep in recent_episodes if ep.session_id == self._session_id]

            if session_episodes:
                logger.info(f"[PersistentMemory] Loading context from {len(session_episodes)} recent episodes")

                # Load the most recent episode's last few messages
                latest_episode = session_episodes[0]
                for msg_turn in latest_episode.messages[-5:]:  # Last 5 messages
                    if msg_turn.speaker == "user":
                        self.chat_memory.add_message(HumanMessage(content=msg_turn.content))
                    else:
                        self.chat_memory.add_message(AIMessage(content=msg_turn.content))

                logger.info(f"[PersistentMemory] Loaded {len(latest_episode.messages[-5:])} messages from episode {latest_episode.episode_id}")
            else:
                logger.info(f"[PersistentMemory] No recent episodes found for session {self._session_id}")

        except Exception as e:
            logger.warning(f"[PersistentMemory] Could not load recent context: {e}")

    def _ensure_episode_exists(self):
        """Ensure an active episode exists, create if needed."""
        if self._current_episode_id is None:
            self._current_episode_id = self._episodic_memory.create_episode(
                session_id=self._session_id,
                metadata={"context_hours": self._context_hours}
            )
            self._episode_message_count = 0
            logger.info(f"[PersistentMemory] Created new episode: {self._current_episode_id}")

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, str]) -> None:
        """
        Override save_context to add episodic persistence.

        Called after each agent interaction to save the conversation turn.
        """
        # Call parent to save to buffer
        super().save_context(inputs, outputs)

        # Ensure episode exists
        self._ensure_episode_exists()

        # Extract user input and assistant output
        user_input = inputs.get(self.input_key, "")
        assistant_output = outputs.get(self.output_key, "")

        current_time = time.time()

        # Save user message to episode
        if user_input:
            self._episodic_memory.add_message_to_episode(
                episode_id=self._current_episode_id,
                speaker="user",
                content=user_input,
                timestamp=current_time
            )
            self._episode_message_count += 1
            logger.debug(f"[PersistentMemory] Saved user message to episode {self._current_episode_id}")

        # Save assistant message to episode
        if assistant_output:
            self._episodic_memory.add_message_to_episode(
                episode_id=self._current_episode_id,
                speaker="assistant",
                content=assistant_output,
                timestamp=current_time
            )
            self._episode_message_count += 1
            logger.debug(f"[PersistentMemory] Saved assistant message to episode {self._current_episode_id}")

        # Extract semantics if enabled
        if self._auto_extract_semantics and self._semantic_memory:
            self._extract_semantics(user_input, assistant_output)

        # Check if episode should be finalized (e.g., after many messages)
        if self._episode_message_count >= 50:  # Finalize after 50 messages
            self._finalize_current_episode()

    def _extract_semantics(self, user_input: str, assistant_output: str):
        """Extract semantic triples from conversation and link to episode."""
        try:
            # Extract from user input
            if user_input and len(user_input) > 10:
                self._semantic_memory.ingest_text(
                    text=user_input,
                    source=f"conversation_{self._session_id}",
                    speaker="user",
                    episode_id=self._current_episode_id
                )
                logger.debug(f"[PersistentMemory] Extracted semantics from user input")

            # Extract from assistant output
            if assistant_output and len(assistant_output) > 10:
                self._semantic_memory.ingest_text(
                    text=assistant_output,
                    source=f"conversation_{self._session_id}",
                    speaker="assistant",
                    episode_id=self._current_episode_id
                )
                logger.debug(f"[PersistentMemory] Extracted semantics from assistant output")

        except Exception as e:
            logger.warning(f"[PersistentMemory] Failed to extract semantics: {e}")

    def _finalize_current_episode(self):
        """Finalize the current episode and prepare for a new one."""
        if self._current_episode_id:
            try:
                # Get episode to extract topics for summary
                episode = self._episodic_memory.get_episode(self._current_episode_id)

                # Create a simple summary
                message_preview = episode.messages[0].content[:100] if episode.messages else ""
                summary = f"Conversation with {self._episode_message_count} messages. Started with: {message_preview}"

                # Finalize
                self._episodic_memory.finalize_episode(
                    episode_id=self._current_episode_id,
                    summary=summary
                )

                logger.info(f"[PersistentMemory] Finalized episode {self._current_episode_id} with {self._episode_message_count} messages")

                # Reset for new episode
                self._current_episode_id = None
                self._episode_message_count = 0

            except Exception as e:
                logger.error(f"[PersistentMemory] Failed to finalize episode: {e}")

    def finalize_episode_now(self, summary: Optional[str] = None):
        """
        Manually finalize the current episode.

        Args:
            summary: Optional custom summary for the episode
        """
        if self._current_episode_id:
            try:
                if summary is None:
                    # Auto-generate summary
                    episode = self._episodic_memory.get_episode(self._current_episode_id)
                    message_preview = episode.messages[0].content[:100] if episode.messages else ""
                    summary = f"Conversation with {self._episode_message_count} messages. Started with: {message_preview}"

                self._episodic_memory.finalize_episode(
                    episode_id=self._current_episode_id,
                    summary=summary
                )

                logger.info(f"[PersistentMemory] Manually finalized episode {self._current_episode_id}")

                # Reset
                self._current_episode_id = None
                self._episode_message_count = 0

            except Exception as e:
                logger.error(f"[PersistentMemory] Failed to finalize episode: {e}")

    def clear(self) -> None:
        """Clear the conversation buffer and finalize current episode."""
        # Finalize episode before clearing
        self._finalize_current_episode()

        # Clear parent buffer
        super().clear()

        logger.info(f"[PersistentMemory] Cleared conversation memory for session {self._session_id}")
