"""
EventProcessor — the single consumer of the EventBus.

Continuous loop: always processing something.
1. If the bus has events, process them (user messages are highest priority).
2. If the bus is empty, ask the GoalAdapter for the next goal event.
3. After goal events, extract a journal entry and store it on the goal.
4. The agent is NEVER idle.

All channels (webui, telegram, cron, goals) are unified — every event
flows through the same pipeline regardless of origin.
"""

import asyncio
import logging
import re
import time
from typing import Any, Callable, Coroutine, Dict, Optional, TYPE_CHECKING

from event_bus import EventBus
from event_types import Event, EventPriority, EventType

if TYPE_CHECKING:
    from adapters.goal_adapter import GoalAdapter

logger = logging.getLogger(__name__)

# Pattern to detect self-scheduling directives in agent responses
# Format: [SCHEDULE: <seconds> | <prompt text>]
_SCHEDULE_RE = re.compile(r"\[SCHEDULE:\s*(\d+)\s*\|\s*(.+?)\]")


class EventProcessor:
    """
    Continuous event loop. Processes events from the bus (priority-ordered),
    and fills idle time with goal pursuit from the GoalAdapter.

    All channels are unified — the same sophia.chat() call handles every
    event regardless of source (webui, telegram, cron, goal).
    """

    def __init__(
        self,
        bus: EventBus,
        sophia_chat: Callable[[str, str], str],
        memory_system=None,
        rate_limit_per_hour: int = 120,
    ):
        self.bus = bus
        self.sophia_chat = sophia_chat
        self.memory_system = memory_system
        self.rate_limit_per_hour = rate_limit_per_hour

        # Response handlers keyed by source_channel
        self._response_handlers: Dict[
            str, Callable[[Event, str], Coroutine[Any, Any, None]]
        ] = {}

        # Goal adapter reference (set via set_goal_adapter)
        self._goal_adapter: Optional["GoalAdapter"] = None

        # Rate limiting state
        self._non_user_count = 0
        self._hour_start = time.time()

        # Running flag
        self._running = False

    def set_goal_adapter(self, adapter: "GoalAdapter") -> None:
        """Connect the goal adapter for continuous operation."""
        self._goal_adapter = adapter
        logger.info("[EventProcessor] Goal adapter connected — continuous mode enabled")

    def register_response_handler(
        self,
        channel: str,
        handler: Callable[[Event, str], Coroutine[Any, Any, None]],
    ) -> None:
        """Register an async callback for responses originating from *channel*."""
        self._response_handlers[channel] = handler
        logger.info(f"[EventProcessor] Registered response handler for '{channel}'")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        Continuous event loop. Never idle:
        1. Drain the bus (user/scheduled events first — they're higher priority)
        2. When bus is empty, get a goal event from the GoalAdapter
        3. Repeat forever
        """
        self._running = True
        logger.info("[EventProcessor] Started (continuous mode)")

        while self._running:
            event = await self._next_event()

            if event is None:
                await asyncio.sleep(5)
                continue

            # Shutdown sentinel
            if event.event_type == EventType.SHUTDOWN:
                logger.info("[EventProcessor] Received SHUTDOWN event")
                self.bus.task_done()
                break

            await self._handle_event(event)

        self._running = False
        logger.info("[EventProcessor] Stopped")

    async def _next_event(self) -> Optional[Event]:
        """
        Get the next event to process.
        - If bus has events, return the highest-priority one immediately.
        - If bus is empty and we have a goal adapter, generate a goal event.
        - If bus is empty and no goal adapter, block on bus.get().
        """
        if not self.bus.empty():
            event = await self.bus.get()
            if event.priority <= EventPriority.USER_QUEUED and self._goal_adapter:
                self._goal_adapter.reset_consecutive()
            return event

        if self._goal_adapter:
            try:
                goal_event = await self._goal_adapter.next_goal_event()
                if goal_event:
                    return goal_event
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"[EventProcessor] GoalAdapter error: {e}", exc_info=True)

            if not self.bus.empty():
                return await self.bus.get()
            return None

        try:
            return await self.bus.get()
        except asyncio.CancelledError:
            return None

    def stop(self) -> None:
        """Signal the processor to stop after the current event."""
        self._running = False

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Process a single event through the unified pipeline."""
        is_from_bus = event.source_channel != "goal"

        logger.info(
            f"[EventProcessor] Processing {event.event_type} "
            f"(priority={event.priority.name}, source={event.source_channel}, "
            f"id={event.event_id})"
        )

        # Rate-limit non-user events
        is_user = event.priority <= EventPriority.USER_QUEUED
        if not is_user and not self._check_rate_limit():
            logger.warning(
                f"[EventProcessor] Rate limit hit — skipping {event.event_type} "
                f"({self._non_user_count}/{self.rate_limit_per_hour} this hour)"
            )
            if is_from_bus:
                self.bus.task_done()
            return

        session_id = event.payload.get("session_id", "autonomous")
        content = event.payload.get("content", "")

        if not content:
            logger.warning(f"[EventProcessor] Empty content in event {event.event_id}")
            if is_from_bus:
                self.bus.task_done()
            return

        # Call sophia.chat in a thread (it's synchronous)
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, self.sophia_chat, session_id, content
            )
        except Exception as e:
            logger.error(f"[EventProcessor] Error calling sophia.chat: {e}", exc_info=True)
            response = f"Error processing event: {e}"

        if is_from_bus:
            self.bus.task_done()

        # Route response back to the source channel
        handler = self._response_handlers.get(event.source_channel)
        if handler:
            try:
                await handler(event, response)
            except Exception as e:
                logger.error(
                    f"[EventProcessor] Response handler error for "
                    f"'{event.source_channel}': {e}",
                    exc_info=True,
                )

        # Parse self-scheduling directives from the response
        await self._parse_self_events(response)

        # Journal goal progress after goal events
        if event.event_type == EventType.GOAL_PURSUIT:
            await self._journal_goal_progress(event, response)

    # ------------------------------------------------------------------
    # Goal journaling
    # ------------------------------------------------------------------

    async def _journal_goal_progress(self, event: Event, response: str) -> None:
        """
        After a goal event is processed, extract a brief progress note
        and store it on the goal in the knowledge graph.
        """
        if not self.memory_system:
            return

        goal_desc = (
            event.payload.get("goal_description")
            or event.metadata.get("goal_description")
        )
        if not goal_desc:
            return

        # Extract a concise progress note from the response
        note = self._extract_progress_note(response)

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                self._store_journal_entry,
                goal_desc,
                note,
            )
            logger.info(
                f"[EventProcessor] Journaled progress for '{goal_desc[:50]}': "
                f"{note[:80]}"
            )
        except Exception as e:
            logger.error(f"[EventProcessor] Error journaling goal: {e}")

    def _store_journal_entry(self, goal_desc: str, note: str) -> None:
        """Store a journal entry on the goal's metadata (runs in thread)."""
        from VectorKnowledgeGraph import VectorKnowledgeGraph

        # Get current metadata
        goal_result = self.memory_system.kgraph.query_goal_by_description(
            goal_desc, return_metadata=True
        )
        if not goal_result:
            return

        _, metadata = goal_result
        journal = metadata.get("journal_entries", [])

        journal.append({
            "note": note,
            "timestamp": time.time(),
        })

        # Keep last 20 entries to avoid unbounded growth
        if len(journal) > 20:
            journal = journal[-20:]

        self.memory_system.kgraph.update_goal_metadata(
            goal_desc, {"journal_entries": journal}
        )

    def _extract_progress_note(self, response: str, max_len: int = 200) -> str:
        """
        Extract a concise progress note from an agent response.
        Takes the first meaningful paragraph or sentence.
        """
        # Strip code blocks — they're not useful as journal notes
        cleaned = re.sub(r"```.*?```", "", response, flags=re.DOTALL)
        cleaned = cleaned.strip()

        if not cleaned:
            return "(agent produced code output only)"

        # Take the first paragraph
        paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
        if paragraphs:
            note = paragraphs[0]
        else:
            note = cleaned

        # Truncate
        if len(note) > max_len:
            note = note[:max_len].rsplit(" ", 1)[0] + "..."

        return note

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _check_rate_limit(self) -> bool:
        """Return True if a non-user event is allowed right now."""
        now = time.time()
        if now - self._hour_start >= 3600:
            self._non_user_count = 0
            self._hour_start = now

        if self._non_user_count >= self.rate_limit_per_hour:
            return False

        self._non_user_count += 1
        return True

    # ------------------------------------------------------------------
    # Self-scheduling
    # ------------------------------------------------------------------

    async def _parse_self_events(self, response: str) -> None:
        """
        Scan agent response for [SCHEDULE: N | prompt] directives
        and enqueue delayed self-events.
        """
        for match in _SCHEDULE_RE.finditer(response):
            delay_seconds = int(match.group(1))
            prompt_text = match.group(2).strip()

            logger.info(
                f"[EventProcessor] Self-schedule detected: "
                f"delay={delay_seconds}s, prompt={prompt_text[:60]!r}"
            )

            asyncio.get_running_loop().call_later(
                delay_seconds,
                lambda p=prompt_text: asyncio.ensure_future(
                    self.bus.put(
                        Event(
                            event_type=EventType.SELF_SCHEDULED,
                            payload={"session_id": "autonomous", "content": p},
                            priority=EventPriority.SELF_EVENT,
                            source_channel="self",
                        )
                    )
                ),
            )
