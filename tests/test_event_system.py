"""Tests for the event-driven architecture core: event_types, event_bus, event_processor."""

import asyncio
import time
import pytest

from event_types import Event, EventPriority, EventType
from event_bus import EventBus


# ============================================================================
# Event tests
# ============================================================================

class TestEvent:
    def test_priority_ordering(self):
        """Higher priority (lower number) events sort first."""
        e_user = Event(
            event_type=EventType.CHAT_MESSAGE,
            payload={},
            priority=EventPriority.USER_DIRECT,
            source_channel="webui",
        )
        e_goal = Event(
            event_type=EventType.GOAL_PURSUIT,
            payload={},
            priority=EventPriority.GOAL_DRIVEN,
            source_channel="goal",
        )
        assert e_user < e_goal

    def test_fifo_within_same_priority(self):
        """Events with same priority are ordered by creation time."""
        e1 = Event(
            event_type="a",
            payload={},
            priority=EventPriority.SCHEDULED,
            source_channel="cron",
            created_at=100.0,
        )
        e2 = Event(
            event_type="b",
            payload={},
            priority=EventPriority.SCHEDULED,
            source_channel="cron",
            created_at=200.0,
        )
        assert e1 < e2

    def test_event_id_generated(self):
        e = Event(
            event_type="test",
            payload={},
            priority=EventPriority.BACKGROUND,
            source_channel="test",
        )
        assert len(e.event_id) == 12

    def test_repr(self):
        e = Event(
            event_type="chat_message",
            payload={},
            priority=EventPriority.USER_DIRECT,
            source_channel="webui",
        )
        r = repr(e)
        assert "chat_message" in r
        assert "USER_DIRECT" in r

    def test_default_metadata(self):
        e = Event(
            event_type="test",
            payload={"key": "val"},
            priority=EventPriority.BACKGROUND,
            source_channel="test",
        )
        assert e.metadata == {}
        assert e.reply_to is None


# ============================================================================
# EventBus tests
# ============================================================================

class TestEventBus:
    def test_empty_initially(self):
        bus = EventBus()
        assert bus.empty()
        assert bus.qsize() == 0

    def test_put_get(self):
        async def _test():
            bus = EventBus()
            event = Event(
                event_type="test",
                payload={"msg": "hello"},
                priority=EventPriority.USER_DIRECT,
                source_channel="test",
            )
            await bus.put(event)
            assert not bus.empty()

            got = await bus.get()
            assert got.event_type == "test"
            assert got.payload["msg"] == "hello"
            bus.task_done()

        asyncio.run(_test())

    def test_priority_ordering(self):
        """Events come out in priority order."""
        async def _test():
            bus = EventBus()
            low = Event(
                event_type="low",
                payload={},
                priority=EventPriority.BACKGROUND,
                source_channel="test",
            )
            high = Event(
                event_type="high",
                payload={},
                priority=EventPriority.USER_DIRECT,
                source_channel="test",
            )

            await bus.put(low)
            await bus.put(high)

            first = await bus.get()
            bus.task_done()
            second = await bus.get()
            bus.task_done()

            assert first.event_type == "high"
            assert second.event_type == "low"

        asyncio.run(_test())

    def test_put_threadsafe_requires_loop(self):
        bus = EventBus()
        event = Event(
            event_type="test",
            payload={},
            priority=EventPriority.BACKGROUND,
            source_channel="test",
        )
        with pytest.raises(RuntimeError, match="bind_loop"):
            bus.put_threadsafe(event)

    def test_put_threadsafe_with_loop(self):
        async def _test():
            bus = EventBus()
            loop = asyncio.get_running_loop()
            bus.bind_loop(loop)

            event = Event(
                event_type="threadsafe_test",
                payload={},
                priority=EventPriority.USER_DIRECT,
                source_channel="test",
            )
            bus.put_threadsafe(event)

            await asyncio.sleep(0.01)

            assert not bus.empty()
            got = await bus.get()
            assert got.event_type == "threadsafe_test"
            bus.task_done()

        asyncio.run(_test())


# ============================================================================
# EventProcessor tests
# ============================================================================

class TestEventProcessor:
    def test_processes_event_and_routes_response(self):
        """EventProcessor calls sophia_chat and routes response to handler."""
        from event_processor import EventProcessor

        async def _test():
            bus = EventBus()
            responses_received = []

            def mock_chat(session_id, content):
                return f"Reply to: {content}"

            async def mock_handler(event, response):
                responses_received.append((event.event_id, response))

            processor = EventProcessor(bus=bus, sophia_chat=mock_chat)
            processor.register_response_handler("webui", mock_handler)

            event = Event(
                event_type=EventType.CHAT_MESSAGE,
                payload={"session_id": "test", "content": "Hello"},
                priority=EventPriority.USER_DIRECT,
                source_channel="webui",
            )
            await bus.put(event)

            # Put a shutdown event so the processor stops
            shutdown = Event(
                event_type=EventType.SHUTDOWN,
                payload={},
                priority=EventPriority.BACKGROUND,
                source_channel="system",
            )
            await bus.put(shutdown)

            await processor.run()

            assert len(responses_received) == 1
            assert responses_received[0][1] == "Reply to: Hello"

        asyncio.run(_test())

    def test_rate_limiting(self):
        """Non-user events are rate-limited."""
        from event_processor import EventProcessor

        async def _test():
            bus = EventBus()

            call_count = 0
            def mock_chat(session_id, content):
                nonlocal call_count
                call_count += 1
                return "ok"

            processor = EventProcessor(bus=bus, sophia_chat=mock_chat, rate_limit_per_hour=2)

            # Put 3 non-user events + shutdown
            for i in range(3):
                await bus.put(Event(
                    event_type=EventType.CRON_TRIGGER,
                    payload={"session_id": "auto", "content": f"cron {i}"},
                    priority=EventPriority.SCHEDULED,
                    source_channel="cron",
                ))

            await bus.put(Event(
                event_type=EventType.SHUTDOWN,
                payload={},
                priority=EventPriority.BACKGROUND,
                source_channel="system",
            ))

            await processor.run()

            # Only 2 should have been processed (rate limit = 2)
            assert call_count == 2

        asyncio.run(_test())

    def test_user_events_bypass_rate_limit(self):
        """User events are never rate-limited."""
        from event_processor import EventProcessor

        async def _test():
            bus = EventBus()

            call_count = 0
            def mock_chat(session_id, content):
                nonlocal call_count
                call_count += 1
                return "ok"

            # rate limit = 0 for non-user, but user events should still work
            processor = EventProcessor(bus=bus, sophia_chat=mock_chat, rate_limit_per_hour=0)

            await bus.put(Event(
                event_type=EventType.CHAT_MESSAGE,
                payload={"session_id": "test", "content": "hello"},
                priority=EventPriority.USER_DIRECT,
                source_channel="webui",
            ))

            await bus.put(Event(
                event_type=EventType.SHUTDOWN,
                payload={},
                priority=EventPriority.BACKGROUND,
                source_channel="system",
            ))

            await processor.run()
            assert call_count == 1

        asyncio.run(_test())

    def test_self_schedule_parsing(self):
        """Agent responses with [SCHEDULE: N | prompt] create delayed events."""
        from event_processor import EventProcessor

        async def _test():
            bus = EventBus()

            def mock_chat(session_id, content):
                return "Done. [SCHEDULE: 1 | Check on my progress]"

            processor = EventProcessor(bus=bus, sophia_chat=mock_chat)

            await bus.put(Event(
                event_type=EventType.CHAT_MESSAGE,
                payload={"session_id": "test", "content": "work on goals"},
                priority=EventPriority.USER_DIRECT,
                source_channel="webui",
            ))

            await bus.put(Event(
                event_type=EventType.SHUTDOWN,
                payload={},
                priority=EventPriority.BACKGROUND,
                source_channel="system",
            ))

            await processor.run()

            # Wait for the delayed self-event to fire
            await asyncio.sleep(1.5)

            # The self-scheduled event should be on the bus
            assert not bus.empty()
            event = await bus.get()
            assert event.event_type == EventType.SELF_SCHEDULED
            assert "Check on my progress" in event.payload["content"]

        asyncio.run(_test())

    def test_continuous_loop_with_goal_adapter(self):
        """When bus is empty, processor asks GoalAdapter for work."""
        from event_processor import EventProcessor
        from adapters.goal_adapter import GoalAdapter

        async def _test():
            bus = EventBus()
            processed = []

            def mock_chat(session_id, content):
                processed.append(content)
                return "done"

            # Fake memory system
            class FakeMemory:
                def get_active_goals_for_prompt(self, owner, limit):
                    return "- Learn Python async"
                def suggest_next_goal(self, owner):
                    return {"goal_description": "Learn Python async", "reasoning": "curious"}

            processor = EventProcessor(bus=bus, sophia_chat=mock_chat)
            goal_adapter = GoalAdapter(
                bus=bus,
                memory_system=FakeMemory(),
                cooldown_seconds=0,  # no delay for test
                max_consecutive_goals=2,
                rest_seconds=0,
            )
            await goal_adapter.start()
            processor.set_goal_adapter(goal_adapter)

            # No events on bus — processor should get goals from adapter
            # Run for a brief time then stop
            async def stop_after_goals():
                while len(processed) < 2:
                    await asyncio.sleep(0.1)
                processor.stop()

            await asyncio.gather(
                processor.run(),
                stop_after_goals(),
            )

            assert len(processed) >= 2
            assert "Learn Python async" in processed[0]

        asyncio.run(_test())

    def test_user_event_preempts_goals(self):
        """User events are processed before goal events."""
        from event_processor import EventProcessor
        from adapters.goal_adapter import GoalAdapter

        async def _test():
            bus = EventBus()
            order = []

            def mock_chat(session_id, content):
                if "USER:" in content:
                    order.append("user")
                else:
                    order.append("goal")
                return "done"

            class FakeMemory:
                def get_active_goals_for_prompt(self, owner, limit):
                    return "- Some goal"
                def suggest_next_goal(self, owner):
                    return {"goal_description": "Some goal"}

            processor = EventProcessor(bus=bus, sophia_chat=mock_chat)
            goal_adapter = GoalAdapter(
                bus=bus, memory_system=FakeMemory(),
                cooldown_seconds=0, max_consecutive_goals=100, rest_seconds=0,
            )
            await goal_adapter.start()
            processor.set_goal_adapter(goal_adapter)

            # Put a user event on the bus
            await bus.put(Event(
                event_type=EventType.CHAT_MESSAGE,
                payload={"session_id": "test", "content": "USER: hello"},
                priority=EventPriority.USER_DIRECT,
                source_channel="webui",
            ))

            async def stop_after():
                while len(order) < 3:
                    await asyncio.sleep(0.1)
                processor.stop()

            await asyncio.gather(
                processor.run(),
                stop_after(),
            )

            # User event should be first
            assert order[0] == "user"

        asyncio.run(_test())
