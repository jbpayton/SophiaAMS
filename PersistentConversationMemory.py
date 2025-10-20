"""
PersistentConversationMemory - Bridge between LangChain and Episodic Memory

This custom memory class extends LangChain's ConversationBufferMemory to add:
- Automatic persistence of conversations to EpisodicMemory
- Automatic episode creation and management
- Link conversation turns to semantic memory extraction
- Background memory consolidation during idle periods
"""

import logging
import time
import asyncio
import threading
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
        idle_seconds: float = 30.0,  # Consolidate after 30s of inactivity
        **kwargs
    ):
        """
        Initialize persistent conversation memory with background consolidation.

        Args:
            session_id: Unique session identifier
            episodic_memory: EpisodicMemory instance for persistence
            semantic_memory: Optional AssociativeSemanticMemory for extraction
            auto_extract_semantics: Whether to automatically extract triples from messages
            context_hours: Hours of recent context to load on initialization
            idle_seconds: Seconds of inactivity before background consolidation
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
        self._idle_seconds = idle_seconds

        # Episode tracking
        self._current_episode_id: Optional[str] = None
        self._episode_message_count = 0

        # Background consolidation tracking
        self._pending_extractions = []  # Queue of (user_input, assistant_output) tuples
        self._last_activity_time = time.time()
        self._consolidation_timer = None
        self._lock = threading.Lock()

        # Load recent context from previous episodes
        self._load_recent_context()

        logger.info(f"[PersistentMemory] Initialized for session {session_id} (idle consolidation after {idle_seconds}s)")

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

        # Queue for background extraction instead of doing it immediately
        if self._auto_extract_semantics and self._semantic_memory:
            with self._lock:
                self._pending_extractions.append((user_input, assistant_output))
                self._last_activity_time = time.time()
                logger.debug(f"[PersistentMemory] Queued extraction ({len(self._pending_extractions)} pending)")

        # Schedule background consolidation
        self._schedule_consolidation()

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
        # Process any pending extractions before clearing
        self._consolidate_now()

        # Finalize episode before clearing
        self._finalize_current_episode()

        # Clear parent buffer
        super().clear()

        logger.info(f"[PersistentMemory] Cleared conversation memory for session {self._session_id}")

    def _schedule_consolidation(self):
        """Schedule background consolidation after idle period."""
        # Cancel existing timer if any
        if self._consolidation_timer:
            self._consolidation_timer.cancel()

        # Schedule new timer
        self._consolidation_timer = threading.Timer(
            self._idle_seconds,
            self._consolidate_background
        )
        self._consolidation_timer.daemon = True
        self._consolidation_timer.start()
        logger.debug(f"[PersistentMemory] Scheduled consolidation in {self._idle_seconds}s")

    def _consolidate_background(self):
        """Background task to consolidate pending extractions during idle time."""
        with self._lock:
            # Check if still idle
            time_since_activity = time.time() - self._last_activity_time
            if time_since_activity < self._idle_seconds:
                # Not idle yet, reschedule
                logger.debug(f"[PersistentMemory] Not idle yet ({time_since_activity:.1f}s), rescheduling")
                self._schedule_consolidation()
                return

            if not self._pending_extractions:
                logger.debug("[PersistentMemory] No pending extractions to process")
                return

            # Get pending extractions
            pending = list(self._pending_extractions)
            self._pending_extractions.clear()

        logger.info(f"[PersistentMemory] 🧠 Background consolidation starting ({len(pending)} conversations → memory)")

        # Process each queued extraction
        for user_input, assistant_output in pending:
            try:
                self._extract_semantics(user_input, assistant_output)
            except Exception as e:
                logger.error(f"[PersistentMemory] Error in background extraction: {e}")

        logger.info(f"[PersistentMemory] ✅ Background consolidation complete")

    def _consolidate_now(self):
        """Immediately process all pending extractions (blocking)."""
        with self._lock:
            if not self._pending_extractions:
                return

            pending = list(self._pending_extractions)
            self._pending_extractions.clear()

        logger.info(f"[PersistentMemory] ⚡ Immediate consolidation ({len(pending)} conversations)")

        for user_input, assistant_output in pending:
            try:
                self._extract_semantics(user_input, assistant_output)
            except Exception as e:
                logger.error(f"[PersistentMemory] Error in immediate extraction: {e}")

        logger.info(f"[PersistentMemory] ✅ Immediate consolidation complete")

    def get_pending_count(self) -> int:
        """Get the number of pending extractions waiting for consolidation."""
        with self._lock:
            return len(self._pending_extractions)
