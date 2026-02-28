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
import collections
import json
import logging
import os
import re
import time
import uuid
from typing import Any, Callable, Coroutine, Dict, List, Optional, TYPE_CHECKING

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
        sophia_chat_streaming: Callable = None,
        sophia_cancel_session: Callable = None,
        memory_system=None,
        rate_limit_per_hour: int = 120,
        skill_env_config=None,
    ):
        self.bus = bus
        self.sophia_chat = sophia_chat
        self.sophia_chat_streaming = sophia_chat_streaming
        self.sophia_cancel_session = sophia_cancel_session
        self.memory_system = memory_system
        self.rate_limit_per_hour = rate_limit_per_hour
        self.skill_env_config = skill_env_config

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

        # Activity log (Feature 2) — persisted to JSONL
        self._activity_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "logs", "activity.jsonl"
        )
        self._activity_log: collections.deque = collections.deque(maxlen=500)
        self._load_activity_log()

        # Currently processing event tracking (for preemption)
        self._current_event: Optional[Event] = None
        self._current_session_id: Optional[str] = None

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
        is_streaming = event.payload.get("streaming", False)

        if not content:
            logger.warning(f"[EventProcessor] Empty content in event {event.event_id}")
            if is_from_bus:
                self.bus.task_done()
            return

        # Track current processing for preemption
        self._current_event = event
        self._current_session_id = session_id

        # Streaming thoughts collected during processing
        thoughts_data = []

        # Call sophia.chat in a thread (it's synchronous)
        try:
            loop = asyncio.get_running_loop()

            if is_streaming and self.sophia_chat_streaming:
                # Get the streaming queue from the pending map
                from adapters.webui_adapter import WebUIAdapter
                streaming_queue = None
                for handler in self._response_handlers.values():
                    adapter = getattr(handler, '__self__', None)
                    if isinstance(adapter, WebUIAdapter):
                        streaming_queue = adapter._pending.get(event.event_id)
                        break

                if streaming_queue and isinstance(streaming_queue, asyncio.Queue):
                    # Create thread-safe callback that pushes to the async queue
                    def on_event(event_type, data):
                        thoughts_data.append({"type": event_type, "data": data})
                        loop.call_soon_threadsafe(
                            streaming_queue.put_nowait,
                            (event_type, data)
                        )

                    response = await loop.run_in_executor(
                        None,
                        lambda: self.sophia_chat_streaming(session_id, content, on_event),
                    )
                else:
                    response = await loop.run_in_executor(
                        None, self.sophia_chat, session_id, content
                    )
            elif self.sophia_chat_streaming:
                # Non-streaming request but streaming is available —
                # use it with a collector callback to capture thoughts
                # (reasoning, tool calls, auto-recall) without a streaming queue.
                preempt_task = None
                if not is_user and self.sophia_cancel_session:
                    preempt_task = asyncio.create_task(
                        self._preemption_monitor(session_id)
                    )

                def on_event_collector(event_type, data):
                    thoughts_data.append({"type": event_type, "data": data})

                response = await loop.run_in_executor(
                    None,
                    lambda: self.sophia_chat_streaming(session_id, content, on_event_collector),
                )

                if preempt_task and not preempt_task.done():
                    preempt_task.cancel()
            else:
                # No streaming available at all — plain chat
                preempt_task = None
                if not is_user and self.sophia_cancel_session:
                    preempt_task = asyncio.create_task(
                        self._preemption_monitor(session_id)
                    )

                response = await loop.run_in_executor(
                    None, self.sophia_chat, session_id, content
                )

                if preempt_task and not preempt_task.done():
                    preempt_task.cancel()

        except Exception as e:
            logger.error(f"[EventProcessor] Error calling sophia.chat: {e}", exc_info=True)
            response = f"Error processing event: {e}"
        finally:
            self._current_event = None
            self._current_session_id = None

        if is_from_bus:
            self.bus.task_done()

        # Scrub any secret values from the response (defense in depth)
        if self.skill_env_config:
            response = self.skill_env_config.scrub_secrets(response)

        # Log activity (Feature 2)
        self._log_activity(event, content, response, thoughts_data)

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
            await self._journal_goal_progress(event, response, thoughts_data)

    # ------------------------------------------------------------------
    # Preemption monitor (Feature 3)
    # ------------------------------------------------------------------

    async def _preemption_monitor(self, current_session_id: str) -> None:
        """Watch the bus for USER_DIRECT events during long-running processing."""
        while self._running and self._current_event is not None:
            await asyncio.sleep(0.5)
            if not self.bus.empty():
                # Peek at the bus — if a user event is waiting, preempt
                try:
                    # Check without consuming
                    next_event = self.bus.peek()
                    if next_event and next_event.priority <= EventPriority.USER_DIRECT:
                        logger.info(
                            f"[EventProcessor] Preempting {self._current_event.event_type} "
                            f"for incoming user message"
                        )
                        if self.sophia_cancel_session:
                            self.sophia_cancel_session(current_session_id)
                        return
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Activity log (Feature 2)
    # ------------------------------------------------------------------

    def _load_activity_log(self) -> None:
        """Load persisted activity entries from JSONL on startup."""
        if not os.path.isfile(self._activity_file):
            return
        try:
            with open(self._activity_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self._activity_log.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            logger.info(
                f"[EventProcessor] Loaded {len(self._activity_log)} activity entries from disk"
            )
        except Exception as e:
            logger.error(f"[EventProcessor] Failed to load activity log: {e}")

    def _persist_activity(self, entry: dict) -> None:
        """Append a single activity entry to the JSONL file."""
        try:
            os.makedirs(os.path.dirname(self._activity_file), exist_ok=True)
            with open(self._activity_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
            # Trim file if it exceeds 5 MB — rewrite with current deque contents
            try:
                if os.path.getsize(self._activity_file) > 5 * 1024 * 1024:
                    with open(self._activity_file, "w", encoding="utf-8") as f:
                        for e in self._activity_log:
                            f.write(json.dumps(e, default=str) + "\n")
                    logger.info("[EventProcessor] Trimmed activity log file")
            except OSError:
                pass
        except Exception as e:
            logger.error(f"[EventProcessor] Failed to persist activity: {e}")

    def _log_activity(self, event: Event, content: str, response: str, thoughts: list) -> None:
        """Append a processed event to the activity log."""
        entry = {
            "id": uuid.uuid4().hex[:12],
            "timestamp": time.time(),
            "event_type": event.event_type,
            "source_channel": event.source_channel,
            "priority": event.priority.name,
            "session_id": event.payload.get("session_id", "unknown"),
            "content_preview": content[:200] if content else "",
            "content_full": content or "",
            "response_preview": response[:300] if response else "",
            "response_full": response or "",
            "thoughts": thoughts,
            "status": "completed",
        }
        self._activity_log.append(entry)
        self._persist_activity(entry)

    def get_activity_feed(self, limit: int = 50, offset: int = 0, source_filter: str = None) -> List[dict]:
        """Return recent activity entries, newest first."""
        entries = list(self._activity_log)
        entries.reverse()  # newest first

        if source_filter and source_filter != "all":
            entries = [e for e in entries if e["source_channel"] == source_filter]

        return entries[offset:offset + limit]

    # ------------------------------------------------------------------
    # Goal journaling
    # ------------------------------------------------------------------

    async def _journal_goal_progress(
        self, event: Event, response: str, thoughts_data: list = None
    ) -> None:
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
        note = self._extract_progress_note(response, thoughts_data)

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

    def _extract_progress_note(
        self, response: str, thoughts_data: list = None, max_len: int = 200
    ) -> str:
        """
        Extract a concise progress note from an agent response.
        Takes the first meaningful paragraph or sentence.
        Falls back to thoughts_data (tool calls, reasoning) when response is code-only.
        """
        # Strip code blocks — they're not useful as journal notes
        cleaned = re.sub(r"```.*?```", "", response, flags=re.DOTALL)
        cleaned = cleaned.strip()

        if not cleaned:
            # Try to build a note from thoughts_data
            if thoughts_data:
                return self._note_from_thoughts(thoughts_data, max_len)
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

    def _note_from_thoughts(self, thoughts_data: list, max_len: int = 200) -> str:
        """Build a journal note from thoughts_data when the response text is empty."""
        tool_names = []
        first_reasoning = None

        for item in thoughts_data:
            etype = item.get("type", "")
            data = item.get("data", "")

            if etype == "tool_start":
                # data is typically the tool name or "tool_name: args"
                name = str(data).split(":")[0].split("(")[0].strip()
                if name and name not in tool_names:
                    tool_names.append(name)
            elif etype == "reasoning" and not first_reasoning and data:
                first_reasoning = str(data).strip().split("\n")[0]

        parts = []
        if tool_names:
            names_str = ", ".join(tool_names[:4])
            parts.append(f"Used {len(tool_names)} tool{'s' if len(tool_names) != 1 else ''} ({names_str})")
        if first_reasoning:
            parts.append(f"Reasoning: {first_reasoning}")

        if parts:
            note = ". ".join(parts)
            if len(note) > max_len:
                note = note[:max_len].rsplit(" ", 1)[0] + "..."
            return note

        return "(agent produced code output only)"

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
