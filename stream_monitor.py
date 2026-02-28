"""
Framework-agnostic memory middleware.
Hooks into any agent loop to provide automatic memory recall and background consolidation.
Replaces PersistentConversationMemory.py.
"""

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class StreamMonitor:
    """
    Memory middleware that sits between the user and the agent loop.
    - pre_process: recalls relevant memories before the agent sees the input
    - post_process: saves the exchange to episodic memory and queues semantic extraction
    - flush: forces immediate consolidation
    """

    def __init__(
        self,
        semantic_memory,
        episodic_memory,
        auto_recall_limit: int = 10,
        idle_seconds: float = 30.0,
        episode_rotate_threshold: int = 50,
        agent_name: str = None,
        user_name: str = None,
    ):
        self.semantic_memory = semantic_memory
        self.episodic_memory = episodic_memory
        self.auto_recall_limit = auto_recall_limit
        self.idle_seconds = idle_seconds
        self.episode_rotate_threshold = episode_rotate_threshold
        self.agent_name = agent_name or "Sophia"
        self.user_name = user_name or "User"

        # Goal adapter reference — set by main.py for workspace awareness
        self._goal_adapter = None

        # Per-session state
        self._sessions = {}  # session_id -> session dict
        self._lock = threading.Lock()
        self._timers = {}  # session_id -> Timer

    def _ensure_session(self, session_id: str) -> dict:
        """Get or create session tracking state."""
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "message_count": 0,
                "episode_id": None,
                "extraction_queue": [],
                "last_activity": time.time(),
            }
        return self._sessions[session_id]

    def pre_process(self, user_input: str, session_id: str) -> str:
        """
        Called before the agent processes user input.
        Performs vector search and retrieves active goals.

        Returns:
            Formatted context string to inject into the prompt.
        """
        try:
            memory_lines = []

            # Query semantic memory for relevant triples
            results = self.semantic_memory.query_related_information(
                user_input, limit=self.auto_recall_limit
            )

            if results and isinstance(results, dict):
                triples = results.get("triples", [])
                if triples:
                    memory_lines.append(f"Found {len(triples)} relevant memories:\n")
                    for i, triple_data in enumerate(triples[: self.auto_recall_limit], 1):
                        if isinstance(triple_data, (list, tuple)) and len(triple_data) >= 2:
                            triple, metadata = triple_data
                            subject, predicate, obj = triple
                            memory_lines.append(f"{i}. {subject} {predicate} {obj}")
                            topics = metadata.get("topics", [])
                            if topics:
                                memory_lines.append(f"   Topics: {', '.join(topics[:3])}")
                else:
                    memory_lines.append("No relevant memories found.")
            else:
                memory_lines.append("No relevant memories found.")

            # Active goals
            try:
                active_goals = self.semantic_memory.get_active_goals_for_prompt(
                    owner=self.agent_name, limit=10
                )
                if active_goals:
                    memory_lines.append("\n\n=== YOUR ACTIVE GOALS ===")
                    memory_lines.append(active_goals)
                    memory_lines.append("=== END GOALS ===")
            except Exception as e:
                logger.error(f"Error retrieving active goals: {e}")

            # Workspace awareness — summarize active goal workspaces
            if self._goal_adapter:
                try:
                    workspace_summary = self._goal_adapter.get_workspace_summary()
                    if workspace_summary:
                        memory_lines.append("\n\n=== ACTIVE WORKSPACES ===")
                        memory_lines.append(workspace_summary)
                        memory_lines.append("=== END WORKSPACES ===")
                except Exception as e:
                    logger.error(f"Error retrieving workspace summary: {e}")

            return "\n".join(memory_lines)

        except Exception as e:
            logger.error(f"Error in pre_process: {e}")
            return ""

    def post_process(self, session_id: str, user_input: str, assistant_output: str) -> None:
        """
        Called after the agent produces a response.
        Saves messages to episodic memory and queues semantic extraction.
        """
        session = self._ensure_session(session_id)
        session["last_activity"] = time.time()

        try:
            # Ensure episode exists
            if session["episode_id"] is None:
                session["episode_id"] = self.episodic_memory.create_episode(session_id=session_id)

            # Save messages to episode
            self.episodic_memory.add_message_to_episode(
                episode_id=session["episode_id"],
                speaker="user",
                content=user_input,
            )
            self.episodic_memory.add_message_to_episode(
                episode_id=session["episode_id"],
                speaker="assistant",
                content=assistant_output,
            )

            session["message_count"] += 2

            # Queue semantic extraction (skip very short exchanges)
            if len(user_input) > 10 or len(assistant_output) > 10:
                session["extraction_queue"].append((user_input, assistant_output))

            # Rotate episode if threshold reached
            if session["message_count"] >= self.episode_rotate_threshold:
                self.episodic_memory.finalize_episode(session["episode_id"])
                session["episode_id"] = None
                session["message_count"] = 0

            # Schedule background consolidation
            self._schedule_consolidation(session_id)

        except Exception as e:
            logger.error(f"Error in post_process: {e}")

    def flush(self, session_id: str) -> None:
        """Force immediate consolidation of pending extractions."""
        session = self._sessions.get(session_id)
        if not session:
            return

        self._cancel_timer(session_id)
        self._consolidate(session_id)

        # Finalize current episode
        if session.get("episode_id"):
            try:
                self.episodic_memory.finalize_episode(session["episode_id"])
                session["episode_id"] = None
            except Exception as e:
                logger.error(f"Error finalizing episode: {e}")

    def _schedule_consolidation(self, session_id: str) -> None:
        """Schedule background consolidation after idle period."""
        self._cancel_timer(session_id)
        timer = threading.Timer(self.idle_seconds, self._consolidate, args=[session_id])
        timer.daemon = True
        timer.start()
        self._timers[session_id] = timer

    def _cancel_timer(self, session_id: str) -> None:
        """Cancel any pending consolidation timer."""
        timer = self._timers.pop(session_id, None)
        if timer:
            timer.cancel()

    def _consolidate(self, session_id: str) -> None:
        """Process queued semantic extractions."""
        session = self._sessions.get(session_id)
        if not session:
            return

        with self._lock:
            queue = session["extraction_queue"]
            session["extraction_queue"] = []

        for user_input, assistant_output in queue:
            try:
                text = f"SPEAKER:{self.user_name}|{user_input}\nSPEAKER:{self.agent_name}|{assistant_output}"
                self.semantic_memory.ingest_text(
                    text=text,
                    source=f"conversation:{session_id}",
                    timestamp=time.time(),
                )
            except Exception as e:
                logger.error(f"Error extracting semantics: {e}")
