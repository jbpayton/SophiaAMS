"""Abstract base class for all event source adapters."""

import abc
from event_bus import EventBus


class EventSourceAdapter(abc.ABC):
    """
    Base class for anything that produces events.

    Each adapter receives a reference to the shared EventBus and is
    responsible for creating Event objects and putting them on the bus.
    """

    def __init__(self, bus: EventBus):
        self.bus = bus

    @abc.abstractmethod
    async def start(self) -> None:
        """Start producing events (called once at application boot)."""

    @abc.abstractmethod
    async def stop(self) -> None:
        """Gracefully shut down the adapter."""
