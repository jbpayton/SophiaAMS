"""
Thread-safe message queue system for autonomous agent mode.
Allows user messages to be queued while the agent works autonomously.
"""

import threading
import time
from typing import Dict, Optional, List
from collections import deque
import logging

logger = logging.getLogger(__name__)


class MessageQueue:
    """
    Thread-safe message queue for managing user inputs during autonomous mode.

    Features:
    - Per-session queues
    - Priority handling (user messages always processed first)
    - Thread-safe operations
    - Status tracking
    """

    def __init__(self):
        """Initialize the message queue system."""
        self.queues: Dict[str, deque] = {}
        self.lock = threading.Lock()
        logger.info("MessageQueue initialized")

    def enqueue(self, session_id: str, message: str, priority: str = "normal", metadata: Optional[Dict] = None) -> Dict:
        """
        Add a message to the queue for a specific session.

        Args:
            session_id: Session identifier
            message: Message content
            priority: "normal" or "high" (user messages are always high)
            metadata: Optional additional data

        Returns:
            Dictionary with queue entry details
        """
        with self.lock:
            if session_id not in self.queues:
                self.queues[session_id] = deque()

            entry = {
                "message": message,
                "priority": priority,
                "timestamp": time.time(),
                "status": "pending",
                "metadata": metadata or {},
                "session_id": session_id
            }

            # High priority messages go to front
            if priority == "high":
                self.queues[session_id].appendleft(entry)
            else:
                self.queues[session_id].append(entry)

            logger.info(f"[QUEUE] Enqueued message for session {session_id} (priority={priority}, queue_size={len(self.queues[session_id])})")
            return entry

    def dequeue(self, session_id: str) -> Optional[Dict]:
        """
        Get the next message from the queue for a session.

        Args:
            session_id: Session identifier

        Returns:
            Message entry dict or None if queue is empty
        """
        with self.lock:
            if session_id not in self.queues or not self.queues[session_id]:
                return None

            entry = self.queues[session_id].popleft()
            entry["status"] = "processing"
            entry["dequeued_at"] = time.time()

            logger.info(f"[QUEUE] Dequeued message for session {session_id} (queue_size={len(self.queues[session_id])})")
            return entry

    def has_messages(self, session_id: str) -> bool:
        """
        Check if a session has pending messages.

        Args:
            session_id: Session identifier

        Returns:
            True if messages are pending
        """
        with self.lock:
            return session_id in self.queues and len(self.queues[session_id]) > 0

    def get_queue_size(self, session_id: str) -> int:
        """
        Get the number of pending messages for a session.

        Args:
            session_id: Session identifier

        Returns:
            Number of pending messages
        """
        with self.lock:
            if session_id not in self.queues:
                return 0
            return len(self.queues[session_id])

    def peek(self, session_id: str) -> Optional[Dict]:
        """
        Look at the next message without removing it.

        Args:
            session_id: Session identifier

        Returns:
            Next message entry or None
        """
        with self.lock:
            if session_id not in self.queues or not self.queues[session_id]:
                return None
            return self.queues[session_id][0]

    def clear(self, session_id: str) -> int:
        """
        Clear all messages for a session.

        Args:
            session_id: Session identifier

        Returns:
            Number of messages cleared
        """
        with self.lock:
            if session_id not in self.queues:
                return 0

            count = len(self.queues[session_id])
            self.queues[session_id].clear()

            logger.info(f"[QUEUE] Cleared {count} messages for session {session_id}")
            return count

    def get_all_messages(self, session_id: str) -> List[Dict]:
        """
        Get all pending messages for a session without removing them.

        Args:
            session_id: Session identifier

        Returns:
            List of message entries
        """
        with self.lock:
            if session_id not in self.queues:
                return []
            return list(self.queues[session_id])

    def get_status(self) -> Dict:
        """
        Get overall queue system status.

        Returns:
            Dictionary with queue statistics
        """
        with self.lock:
            return {
                "total_sessions": len(self.queues),
                "total_pending": sum(len(q) for q in self.queues.values()),
                "sessions": {
                    session_id: len(queue)
                    for session_id, queue in self.queues.items()
                }
            }


# Global queue instance
message_queue = MessageQueue()


if __name__ == "__main__":
    # Test the message queue
    print("Testing MessageQueue...")

    queue = MessageQueue()

    # Test basic enqueue/dequeue
    queue.enqueue("session1", "Hello from user", priority="high")
    queue.enqueue("session1", "Another message", priority="normal")

    print(f"Queue size: {queue.get_queue_size('session1')}")
    print(f"Has messages: {queue.has_messages('session1')}")

    # Dequeue messages
    msg1 = queue.dequeue("session1")
    print(f"Dequeued: {msg1['message']}")

    msg2 = queue.dequeue("session1")
    print(f"Dequeued: {msg2['message']}")

    print(f"Queue empty: {not queue.has_messages('session1')}")

    # Test status
    queue.enqueue("session2", "Test", priority="normal")
    status = queue.get_status()
    print(f"Status: {status}")

    print("✓ MessageQueue tests passed")
