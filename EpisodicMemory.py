"""
Episodic Memory System for SophiaAMS

Stores conversation episodes as coherent temporal sequences, enabling Sophia to
remember "what happened when" in addition to "what is true" (semantic memory).

This provides the temporal scaffolding for consciousness - the ability to recall
experiences as they unfolded over time.
"""

import os
import time
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from tinydb import TinyDB, Query
from dataclasses import dataclass, asdict

@dataclass
class MessageTurn:
    """A single turn in a conversation."""
    speaker: str  # "user" or "assistant"
    content: str
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        return cls(**data)

@dataclass
class Episode:
    """A conversation episode with temporal boundaries."""
    episode_id: str
    session_id: str
    start_time: float
    end_time: Optional[float]
    messages: List[MessageTurn]
    topics: List[str]
    summary: Optional[str]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['messages'] = [msg.to_dict() if isinstance(msg, MessageTurn) else msg for msg in self.messages]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        messages = [MessageTurn.from_dict(msg) if isinstance(msg, dict) else msg for msg in data.get('messages', [])]
        return cls(
            episode_id=data['episode_id'],
            session_id=data['session_id'],
            start_time=data['start_time'],
            end_time=data.get('end_time'),
            messages=messages,
            topics=data.get('topics', []),
            summary=data.get('summary'),
            metadata=data.get('metadata', {})
        )

class EpisodicMemory:
    """
    Manages episodic (autobiographical) memory - the "what happened when" layer.

    Stores conversations as temporally-ordered episodes, enabling queries like:
    - "What did we discuss yesterday?"
    - "When did I learn about Python?"
    - "Tell me about our conversation on Monday"
    """

    def __init__(self, storage_path: str = "data/episodic_memory"):
        """
        Initialize episodic memory storage.

        Args:
            storage_path: Directory for episodic memory storage
        """
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)

        self.db = TinyDB(os.path.join(storage_path, 'episodes.json'))
        self.episodes_table = self.db.table('episodes')

        logging.info(f"Initialized EpisodicMemory at {storage_path}")

    def create_episode(self, session_id: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Start a new conversation episode.

        Args:
            session_id: The conversation session ID
            metadata: Optional metadata for the episode

        Returns:
            episode_id: Unique identifier for this episode
        """
        episode_id = f"{session_id}_{int(time.time())}"

        episode = Episode(
            episode_id=episode_id,
            session_id=session_id,
            start_time=time.time(),
            end_time=None,
            messages=[],
            topics=[],
            summary=None,
            metadata=metadata or {}
        )

        self.episodes_table.insert(episode.to_dict())
        logging.info(f"Created new episode: {episode_id}")

        return episode_id

    def add_message_to_episode(self, episode_id: str, speaker: str, content: str, timestamp: Optional[float] = None):
        """
        Add a message turn to an ongoing episode.

        Args:
            episode_id: The episode to add to
            speaker: "user" or "assistant"
            content: The message content
            timestamp: Optional timestamp (defaults to now)
        """
        timestamp = timestamp or time.time()

        message = MessageTurn(
            speaker=speaker,
            content=content,
            timestamp=timestamp
        )

        EpisodeQuery = Query()
        episode_data = self.episodes_table.get(EpisodeQuery.episode_id == episode_id)

        if episode_data:
            messages = episode_data.get('messages', [])
            messages.append(message.to_dict())

            self.episodes_table.update(
                {'messages': messages},
                EpisodeQuery.episode_id == episode_id
            )

            logging.debug(f"Added {speaker} message to episode {episode_id}")
        else:
            logging.warning(f"Episode {episode_id} not found")

    def finalize_episode(self, episode_id: str, topics: Optional[List[str]] = None, summary: Optional[str] = None):
        """
        Mark an episode as complete and add final metadata.

        Args:
            episode_id: The episode to finalize
            topics: Optional list of topics discussed
            summary: Optional summary of the episode
        """
        EpisodeQuery = Query()

        update_data = {
            'end_time': time.time()
        }

        if topics:
            update_data['topics'] = topics
        if summary:
            update_data['summary'] = summary

        self.episodes_table.update(update_data, EpisodeQuery.episode_id == episode_id)
        logging.info(f"Finalized episode {episode_id}")

    def get_episode(self, episode_id: str) -> Optional[Episode]:
        """
        Retrieve a specific episode by ID.

        Args:
            episode_id: The episode identifier

        Returns:
            Episode object or None if not found
        """
        EpisodeQuery = Query()
        episode_data = self.episodes_table.get(EpisodeQuery.episode_id == episode_id)

        if episode_data:
            return Episode.from_dict(episode_data)
        return None

    def query_episodes_by_time(self, start_time: float, end_time: float) -> List[Episode]:
        """
        Get all episodes within a time range.

        Args:
            start_time: Unix timestamp for range start
            end_time: Unix timestamp for range end

        Returns:
            List of episodes in the time range
        """
        EpisodeQuery = Query()
        results = self.episodes_table.search(
            (EpisodeQuery.start_time >= start_time) &
            (EpisodeQuery.start_time <= end_time)
        )

        episodes = [Episode.from_dict(data) for data in results]
        logging.info(f"Found {len(episodes)} episodes between {datetime.fromtimestamp(start_time)} and {datetime.fromtimestamp(end_time)}")

        return episodes

    def get_recent_episodes(self, hours: float = 24, limit: Optional[int] = None) -> List[Episode]:
        """
        Get recent episodes from the last N hours.

        Args:
            hours: Number of hours to look back
            limit: Optional max number of episodes

        Returns:
            List of recent episodes, sorted by start_time descending
        """
        end_time = time.time()
        start_time = end_time - (hours * 3600)

        episodes = self.query_episodes_by_time(start_time, end_time)

        # Sort by start_time descending (most recent first)
        episodes.sort(key=lambda e: e.start_time, reverse=True)

        if limit:
            episodes = episodes[:limit]

        return episodes

    def query_episodes_by_session(self, session_id: str) -> List[Episode]:
        """
        Get all episodes for a specific session.

        Args:
            session_id: The session identifier

        Returns:
            List of episodes for this session
        """
        EpisodeQuery = Query()
        results = self.episodes_table.search(EpisodeQuery.session_id == session_id)

        episodes = [Episode.from_dict(data) for data in results]
        episodes.sort(key=lambda e: e.start_time)

        logging.info(f"Found {len(episodes)} episodes for session {session_id}")
        return episodes

    def search_episodes_by_content(self, query_text: str, limit: int = 10) -> List[Episode]:
        """
        Search episodes by message content.

        Args:
            query_text: Text to search for
            limit: Max number of results

        Returns:
            List of matching episodes
        """
        query_lower = query_text.lower()
        all_episodes = [Episode.from_dict(data) for data in self.episodes_table.all()]

        matching_episodes = []
        for episode in all_episodes:
            # Search in messages
            for msg in episode.messages:
                if isinstance(msg, MessageTurn):
                    content = msg.content.lower()
                else:
                    content = msg.get('content', '').lower()

                if query_lower in content:
                    matching_episodes.append(episode)
                    break

            # Also search in summary if it exists
            if episode.summary and query_lower in episode.summary.lower():
                if episode not in matching_episodes:
                    matching_episodes.append(episode)

        # Sort by relevance (most recent first for now)
        matching_episodes.sort(key=lambda e: e.start_time, reverse=True)

        logging.info(f"Found {len(matching_episodes)} episodes matching '{query_text}'")
        return matching_episodes[:limit]

    def get_conversation_context(self, episode_id: str, max_turns: int = 10) -> str:
        """
        Get a formatted conversation context from an episode.

        Args:
            episode_id: The episode to retrieve
            max_turns: Maximum number of message turns to include

        Returns:
            Formatted conversation string
        """
        episode = self.get_episode(episode_id)
        if not episode:
            return ""

        context_lines = []
        context_lines.append(f"Conversation from {datetime.fromtimestamp(episode.start_time).strftime('%Y-%m-%d %H:%M')}")

        if episode.topics:
            context_lines.append(f"Topics: {', '.join(episode.topics)}")

        context_lines.append("")  # Blank line

        # Get recent messages
        recent_messages = episode.messages[-max_turns:]

        for msg in recent_messages:
            if isinstance(msg, MessageTurn):
                speaker_label = "User" if msg.speaker == "user" else "Sophia"
                context_lines.append(f"{speaker_label}: {msg.content}")
            else:
                speaker_label = "User" if msg.get('speaker') == "user" else "Sophia"
                context_lines.append(f"{speaker_label}: {msg.get('content', '')}")

        return "\n".join(context_lines)

    def get_timeline_summary(self, days: int = 7) -> str:
        """
        Get a summary timeline of recent activity.

        Args:
            days: Number of days to look back

        Returns:
            Formatted timeline string
        """
        hours = days * 24
        episodes = self.get_recent_episodes(hours=hours)

        if not episodes:
            return f"No conversations in the last {days} days."

        timeline = []
        timeline.append(f"Activity over the last {days} days:")
        timeline.append("")

        # Group by date
        episodes_by_date = {}
        for episode in episodes:
            date_key = datetime.fromtimestamp(episode.start_time).strftime('%Y-%m-%d')
            if date_key not in episodes_by_date:
                episodes_by_date[date_key] = []
            episodes_by_date[date_key].append(episode)

        # Format by date
        for date_key in sorted(episodes_by_date.keys(), reverse=True):
            date_episodes = episodes_by_date[date_key]
            date_label = datetime.strptime(date_key, '%Y-%m-%d').strftime('%B %d, %Y')

            timeline.append(f"**{date_label}** ({len(date_episodes)} conversations)")

            for episode in date_episodes:
                time_label = datetime.fromtimestamp(episode.start_time).strftime('%H:%M')
                duration = ""
                if episode.end_time:
                    duration_secs = episode.end_time - episode.start_time
                    duration_mins = int(duration_secs / 60)
                    duration = f" ({duration_mins}min)"

                topics_str = f": {', '.join(episode.topics)}" if episode.topics else ""
                timeline.append(f"  - {time_label}{duration}{topics_str}")

            timeline.append("")

        return "\n".join(timeline)

    def close(self):
        """Close the database connection."""
        if hasattr(self, 'db'):
            self.db.close()
            logging.info("Closed EpisodicMemory database")


# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Create episodic memory
    em = EpisodicMemory(storage_path="test_episodic_memory")

    # Create an episode
    episode_id = em.create_episode("test_session_123")
    print(f"Created episode: {episode_id}")

    # Add some messages
    em.add_message_to_episode(episode_id, "user", "Hello Sophia!")
    em.add_message_to_episode(episode_id, "assistant", "Hi! How can I help you today?")
    em.add_message_to_episode(episode_id, "user", "I want to learn about Python")
    em.add_message_to_episode(episode_id, "assistant", "Python is a great language! What specifically interests you?")

    # Finalize the episode
    em.finalize_episode(episode_id, topics=["Python", "learning"], summary="User wants to learn Python programming")

    # Retrieve the episode
    retrieved = em.get_episode(episode_id)
    print(f"\nRetrieved episode: {retrieved.episode_id}")
    print(f"Messages: {len(retrieved.messages)}")
    print(f"Topics: {retrieved.topics}")

    # Get context
    context = em.get_conversation_context(episode_id)
    print(f"\nConversation context:\n{context}")

    # Get timeline
    timeline = em.get_timeline_summary(days=7)
    print(f"\nTimeline:\n{timeline}")

    # Search
    results = em.search_episodes_by_content("Python")
    print(f"\nSearch results: {len(results)} episodes mention 'Python'")

    # Cleanup
    em.close()
    import shutil
    if os.path.exists("test_episodic_memory"):
        shutil.rmtree("test_episodic_memory")
