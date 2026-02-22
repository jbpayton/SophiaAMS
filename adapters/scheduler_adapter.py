"""
Scheduler adapter — fires events at configured intervals.

Simple asyncio-based scheduler (no external deps). Jobs are defined
in sophia_config.yaml under event_sources.scheduler.jobs.
"""

import asyncio
import logging
from typing import Dict, List, Optional

from adapters.base import EventSourceAdapter
from event_bus import EventBus
from event_types import Event, EventPriority, EventType

logger = logging.getLogger(__name__)


class SchedulerAdapter(EventSourceAdapter):
    """
    Periodically enqueues CRON_TRIGGER events based on configured jobs.

    Each job has an id, a prompt, and an interval_seconds.
    """

    def __init__(self, bus: EventBus, jobs: Optional[List[Dict]] = None):
        """
        Args:
            bus: Shared EventBus.
            jobs: List of job dicts, each with keys:
                  id (str), prompt (str), interval_seconds (int).
        """
        super().__init__(bus)
        self.jobs = jobs or []
        self._tasks: List[asyncio.Task] = []

    async def start(self) -> None:
        """Start an asyncio task for each configured job."""
        for job in self.jobs:
            job_id = job.get("id", "unnamed")
            interval = job.get("interval_seconds", 3600)
            prompt = job.get("prompt", "")

            if not prompt:
                logger.warning(f"[SchedulerAdapter] Skipping job '{job_id}' — no prompt")
                continue

            task = asyncio.create_task(
                self._run_job(job_id, prompt, interval),
                name=f"scheduler_{job_id}",
            )
            self._tasks.append(task)
            logger.info(
                f"[SchedulerAdapter] Scheduled job '{job_id}' every {interval}s"
            )

    async def stop(self) -> None:
        """Cancel all running scheduler tasks."""
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("[SchedulerAdapter] Stopped")

    async def _run_job(self, job_id: str, prompt: str, interval: int) -> None:
        """Loop forever, sleeping then enqueuing an event."""
        # Initial delay so the system can warm up
        await asyncio.sleep(interval)

        while True:
            event = Event(
                event_type=EventType.CRON_TRIGGER,
                payload={
                    "session_id": "autonomous",
                    "content": prompt,
                },
                priority=EventPriority.SCHEDULED,
                source_channel="cron",
                metadata={"job_id": job_id},
            )

            await self.bus.put(event)
            logger.info(f"[SchedulerAdapter] Fired job '{job_id}'")

            await asyncio.sleep(interval)
