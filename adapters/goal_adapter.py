"""
Goal adapter — continuous goal feeder for the event-driven architecture.

The agent is ALWAYS doing something. When no user/scheduled events are
pending, the GoalAdapter immediately provides the next goal to work on.
Goals are pulled from the memory system (the real source of truth).

Each goal gets its own session_id ("goal_{goal_id}") so the agent
maintains a separate chain of thought per goal.
"""

import asyncio
import hashlib
import logging
import os
import time
from typing import Dict, List, Optional

from adapters.base import EventSourceAdapter
from event_bus import EventBus
from event_types import Event, EventPriority, EventType

logger = logging.getLogger(__name__)


class GoalAdapter(EventSourceAdapter):
    """
    Continuous goal feeder. The EventProcessor calls next_goal_event()
    whenever the bus is empty, so the agent is never idle.

    Each goal gets a dedicated session_id so the agent's chain of thought
    is preserved per-goal. Journal entries (stored on the goal in the
    knowledge graph) provide durable breadcrumbs across restarts.
    """

    def __init__(
        self,
        bus: EventBus,
        memory_system,
        agent_name: str = None,
        user_name: str = None,
        cooldown_seconds: float = 30,
        max_consecutive_goals: int = 10,
        rest_seconds: float = 300,
    ):
        super().__init__(bus)
        self.memory = memory_system
        self.agent_name = agent_name or os.environ.get("AGENT_NAME", "Sophia")
        self.user_name = user_name or os.environ.get("USER_NAME", "User")
        self.cooldown_seconds = cooldown_seconds
        self.max_consecutive = max_consecutive_goals
        self.rest_seconds = rest_seconds

        self._consecutive_count = 0
        self._last_goal_time = 0.0
        self._enabled = True

        # Track the last goal we suggested so EventProcessor can journal it
        self._current_goal_desc: Optional[str] = None

    @property
    def current_goal_description(self) -> Optional[str]:
        """The goal description currently being worked on."""
        return self._current_goal_desc

    async def start(self) -> None:
        logger.info(
            f"[GoalAdapter] Started (cooldown={self.cooldown_seconds}s, "
            f"max_consecutive={self.max_consecutive}, rest={self.rest_seconds}s)"
        )

    async def stop(self) -> None:
        self._enabled = False
        logger.info("[GoalAdapter] Stopped")

    def reset_consecutive(self) -> None:
        """Called by EventProcessor when a user event is processed."""
        self._consecutive_count = 0

    def _goal_session_id(self, goal_desc: str) -> str:
        """Deterministic session_id for a goal (stable across restarts)."""
        h = hashlib.sha256(goal_desc.encode()).hexdigest()[:10]
        return f"goal_{h}"

    async def next_goal_event(self) -> Optional[Event]:
        """
        Called by EventProcessor when the bus is empty.
        Returns the next goal Event with a per-goal session_id.
        """
        if not self._enabled:
            return None

        # Respect cooldown
        elapsed = time.time() - self._last_goal_time
        if elapsed < self.cooldown_seconds:
            await asyncio.sleep(self.cooldown_seconds - elapsed)

        # Rest break after too many consecutive goals
        if self._consecutive_count >= self.max_consecutive:
            logger.info(
                f"[GoalAdapter] Hit max consecutive ({self.max_consecutive}), "
                f"resting for {self.rest_seconds}s"
            )
            self._consecutive_count = 0
            await asyncio.sleep(self.rest_seconds)

        # Get the suggested goal from memory
        suggestion = self._get_suggestion()
        if not suggestion:
            return None

        goal_desc = suggestion["goal_description"]
        goal_metadata = suggestion.get("metadata", {})
        self._current_goal_desc = goal_desc

        # Build prompt with journal context
        prompt = self._generate_goal_prompt(goal_desc, goal_metadata, suggestion)
        session_id = self._goal_session_id(goal_desc)

        event = Event(
            event_type=EventType.GOAL_PURSUIT,
            payload={
                "session_id": session_id,
                "content": prompt,
                "goal_description": goal_desc,
            },
            priority=EventPriority.GOAL_DRIVEN,
            source_channel="goal",
            metadata={"goal_description": goal_desc},
        )

        self._consecutive_count += 1
        self._last_goal_time = time.time()
        logger.info(
            f"[GoalAdapter] Generated event for goal '{goal_desc[:60]}' "
            f"(session={session_id}, consecutive={self._consecutive_count})"
        )
        return event

    def _get_suggestion(self) -> Optional[Dict]:
        """Get the next goal suggestion from memory."""
        try:
            return self.memory.suggest_next_goal(owner=self.agent_name)
        except Exception as e:
            logger.error(f"[GoalAdapter] Error getting suggestion: {e}")
            return None

    def get_workspace_summary(self) -> str:
        """
        Build a brief summary of all active goal workspaces.
        Used by StreamMonitor for cross-workspace awareness.
        """
        try:
            goals_text = self.memory.get_active_goals_for_prompt(
                owner=self.agent_name, limit=10
            )
            if not goals_text:
                return ""

            # Also get journal entries for active goals
            active_goals = self.memory.query_goals(
                owner=self.agent_name, active_only=True, limit=10
            )

            lines = []
            for triple, metadata in active_goals:
                desc = triple[2]
                status = metadata.get("goal_status", "pending")
                journal = metadata.get("journal_entries", [])
                last_entry = journal[-1] if journal else None

                line = f"- [{status}] {desc}"
                if last_entry:
                    line += f"\n  Last progress: {last_entry.get('note', '')[:100]}"
                lines.append(line)

            return "\n".join(lines) if lines else ""

        except Exception as e:
            logger.error(f"[GoalAdapter] Error building workspace summary: {e}")
            return ""

    def _generate_goal_prompt(
        self, goal_desc: str, goal_metadata: Dict, suggestion: Dict
    ) -> str:
        """
        Build a prompt for a specific goal, including journal entries
        from previous work sessions.
        """
        # Get all active goals for context
        try:
            all_goals = self.memory.get_active_goals_for_prompt(
                owner=self.agent_name, limit=10
            )
        except Exception:
            all_goals = ""

        # Extract journal entries from this goal's metadata
        journal_entries = goal_metadata.get("journal_entries", [])
        journal_text = ""
        if journal_entries:
            journal_lines = []
            for entry in journal_entries[-5:]:  # last 5 entries
                journal_lines.append(f"- {entry.get('note', '(no note)')}")
            journal_text = "\n".join(journal_lines)

        reasoning = suggestion.get("reasoning", "")

        prompt = f"""AUTONOMOUS MODE — Working on a specific goal.

TARGET GOAL: {goal_desc}
{f"Why this goal: {reasoning}" if reasoning else ""}

{"YOUR PREVIOUS PROGRESS ON THIS GOAL:" if journal_text else ""}
{journal_text}

ALL ACTIVE GOALS:
{all_goals if all_goals else "(No goals set yet)"}

Take concrete action on the target goal. Use skills, run code, search the web.
When done with a step, summarize what you accomplished and what's next."""

        return prompt
