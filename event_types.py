"""
Event types for the SophiaAMS event-driven architecture.

Defines the core Event dataclass and priority levels that flow through
the EventBus to the EventProcessor.
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, Optional


class EventPriority(IntEnum):
    """Priority levels for events. Lower number = higher priority."""
    CRITICAL = 0        # shutdown, error recovery
    USER_DIRECT = 10    # user typed a message right now
    USER_QUEUED = 20    # user message received while agent was busy
    SCHEDULED = 30      # cron/timer events
    SELF_EVENT = 40     # agent scheduled this for itself
    GOAL_DRIVEN = 50    # idle-time goal pursuit
    BACKGROUND = 60     # low-priority background tasks


class EventType:
    """Well-known event type constants."""
    CHAT_MESSAGE = "chat_message"
    CRON_TRIGGER = "cron_trigger"
    GOAL_PURSUIT = "goal_pursuit"
    SELF_SCHEDULED = "self_scheduled"
    SHUTDOWN = "shutdown"


@dataclass(order=False)
class Event:
    """
    A single event flowing through the system.

    Events are created by adapters and consumed by the EventProcessor.
    The priority field determines processing order in the EventBus.
    """
    event_type: str
    payload: Dict[str, Any]
    priority: EventPriority
    source_channel: str          # "webui", "telegram", "cron", "self", "goal"
    reply_to: Optional[str] = None   # channel-specific routing key
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other: "Event") -> bool:
        """Compare by priority first, then by creation time (FIFO within same priority)."""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.created_at < other.created_at

    def __le__(self, other: "Event") -> bool:
        return self == other or self < other

    def __gt__(self, other: "Event") -> bool:
        return not self <= other

    def __ge__(self, other: "Event") -> bool:
        return not self < other

    def __repr__(self) -> str:
        return (
            f"Event(type={self.event_type!r}, priority={self.priority.name}, "
            f"source={self.source_channel!r}, id={self.event_id!r})"
        )
