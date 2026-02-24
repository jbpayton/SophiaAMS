"""
Async priority queue (EventBus) for the event-driven architecture.

Single producer/consumer pattern: adapters put events, EventProcessor gets them.
"""

import asyncio
import logging
from typing import Optional

from event_types import Event

logger = logging.getLogger(__name__)


class EventBus:
    """
    Async priority queue wrapper.

    Events are ordered by (priority, created_at) so higher-priority events
    are always processed first, with FIFO ordering within the same priority.
    """

    def __init__(self, maxsize: int = 0):
        self._queue: asyncio.PriorityQueue[Event] = asyncio.PriorityQueue(maxsize=maxsize)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind to an event loop (needed for put_threadsafe)."""
        self._loop = loop

    async def put(self, event: Event) -> None:
        """Put an event onto the bus (async — call from coroutines)."""
        await self._queue.put(event)
        logger.debug(f"[EventBus] Enqueued {event}")

    def put_threadsafe(self, event: Event) -> None:
        """
        Put an event from a non-async thread (e.g., Telegram callback).

        Requires bind_loop() to have been called first.
        """
        if self._loop is None:
            raise RuntimeError("EventBus.bind_loop() must be called before put_threadsafe()")
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        logger.debug(f"[EventBus] Enqueued (threadsafe) {event}")

    async def get(self) -> Event:
        """Block until an event is available and return it."""
        return await self._queue.get()

    def task_done(self) -> None:
        """Mark the most recent get() as processed."""
        self._queue.task_done()

    def empty(self) -> bool:
        """Return True if the queue has no pending events."""
        return self._queue.empty()

    def qsize(self) -> int:
        """Return the approximate number of pending events."""
        return self._queue.qsize()

    def peek(self) -> Optional[Event]:
        """Peek at the highest-priority event without removing it.

        Returns None if the queue is empty. Not thread-safe for the
        actual item (it may be consumed before you act on it), but
        sufficient for preemption heuristics.
        """
        # Access the internal heap of the PriorityQueue
        try:
            internal = self._queue._queue
            if internal:
                return internal[0]
        except (AttributeError, IndexError):
            pass
        return None
