"""
WebUI adapter — bridges FastAPI HTTP/WS endpoints to the EventBus.

Each incoming chat request creates an Event + asyncio.Future.
The EventProcessor resolves the Future when the response is ready,
and the HTTP handler awaits it, preserving full backward compatibility.
"""

import asyncio
import logging
from typing import Dict

from adapters.base import EventSourceAdapter
from event_bus import EventBus
from event_types import Event, EventPriority, EventType

logger = logging.getLogger(__name__)


class WebUIAdapter(EventSourceAdapter):
    """
    Converts FastAPI chat requests into events.

    Usage from a FastAPI endpoint:

        future = await adapter.submit(session_id, content)
        response_text = await future          # blocks until agent replies
    """

    def __init__(self, bus: EventBus):
        super().__init__(bus)
        # Map event_id -> Future that the HTTP handler is awaiting
        self._pending: Dict[str, asyncio.Future] = {}

    async def start(self) -> None:
        """No background work — events are created on-demand by submit()."""
        logger.info("[WebUIAdapter] Started")

    async def stop(self) -> None:
        """Cancel any in-flight futures."""
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()
        logger.info("[WebUIAdapter] Stopped")

    async def submit(self, session_id: str, content: str) -> asyncio.Future:
        """
        Create an event for a user chat message and return a Future
        that will be resolved with the agent's response text.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()

        event = Event(
            event_type=EventType.CHAT_MESSAGE,
            payload={"session_id": session_id, "content": content},
            priority=EventPriority.USER_DIRECT,
            source_channel="webui",
        )

        self._pending[event.event_id] = future
        await self.bus.put(event)

        logger.debug(f"[WebUIAdapter] Submitted event {event.event_id} for session {session_id}")
        return future

    async def handle_response(self, event: Event, response: str) -> None:
        """
        Called by EventProcessor when the agent produces a response.
        Resolves the Future so the HTTP handler can return.
        """
        future = self._pending.pop(event.event_id, None)
        if future and not future.done():
            future.set_result(response)
            logger.debug(f"[WebUIAdapter] Resolved future for event {event.event_id}")
        else:
            logger.warning(
                f"[WebUIAdapter] No pending future for event {event.event_id} "
                f"(already done or missing)"
            )
