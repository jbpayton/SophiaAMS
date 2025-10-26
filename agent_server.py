"""
LangChain-based Agent Server for SophiaAMS

Provides a persistent conversational agent with:
- Explicit memory query tools (observable, logged)
- Python REPL for complex operations
- Session-based conversation memory
- WebSocket and HTTP endpoints
"""

import os
import json
import logging
import time
import asyncio
import queue
from datetime import datetime, timedelta
from typing import Dict, Any, AsyncIterator
from dotenv import load_dotenv

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_openai import ChatOpenAI
from langchain.tools import Tool, StructuredTool
from langchain_experimental.tools import PythonREPLTool
from langchain_community.tools import ShellTool
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import AgentAction, AgentFinish, LLMResult
from pydantic import BaseModel as PydanticBaseModel, Field

from AssociativeSemanticMemory import AssociativeSemanticMemory
from VectorKnowledgeGraph import VectorKnowledgeGraph
from EpisodicMemory import EpisodicMemory
from PersistentConversationMemory import PersistentConversationMemory
from searxng_tool import SearXNGSearchTool
from message_queue import message_queue
from autonomous_agent import AutonomousAgent, get_or_create_autonomous_agent, AutonomousConfig
#  from DocumentProcessor import WebPageSource, DocumentProcessor  # Temporarily disabled - needs spacy
import trafilatura

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="Sophia Agent Server", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize memory systems (global, available to Python REPL)
logger.info("Initializing memory systems...")
kgraph = VectorKnowledgeGraph()
memory_system = AssociativeSemanticMemory(kgraph)
episodic_memory = EpisodicMemory()

# Initialize MemoryExplorer for knowledge overview queries
from MemoryExplorer import MemoryExplorer
memory_explorer = MemoryExplorer(kgraph)
logger.info("Memory systems initialized successfully (semantic + episodic + explorer)")

# ============================================================================
# STREAMING CALLBACK HANDLER
# ============================================================================

class StreamingCallbackHandler(BaseCallbackHandler):
    """Custom callback handler to capture agent reasoning and tool calls for streaming."""

    def __init__(self):
        # Use thread-safe queue instead of async queue
        self.events = queue.Queue()
        self.current_tool_name = None
        self.current_tool_input = None

    def send_event(self, event_type: str, data: dict):
        """Send an event to the queue (thread-safe)."""
        self.events.put({
            "type": event_type,
            "data": data,
            "timestamp": time.time()
        })

    def on_llm_start(self, serialized: Dict[str, Any], prompts: list, **kwargs) -> None:
        """Called when LLM starts generating."""
        self.send_event("thinking", {"status": "Agent is thinking..."})

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        """Called when LLM finishes."""
        # Extract the text from response
        if response.generations and response.generations[0]:
            text = response.generations[0][0].text
            self.send_event("llm_output", {"text": text})

    def on_agent_action(self, action: AgentAction, **kwargs) -> None:
        """Called when agent decides to use a tool."""
        self.current_tool_name = action.tool
        self.current_tool_input = action.tool_input

        self.send_event("tool_start", {
            "tool": action.tool,
            "input": action.tool_input,
            "log": action.log
        })

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs) -> None:
        """Called when a tool starts executing."""
        tool_name = serialized.get("name", "unknown")
        self.send_event("tool_executing", {
            "tool": tool_name,
            "input": input_str
        })

    def on_tool_end(self, output: str, **kwargs) -> None:
        """Called when a tool finishes."""
        self.send_event("tool_end", {
            "tool": self.current_tool_name,
            "output": output
        })

    def on_tool_error(self, error: Exception, **kwargs) -> None:
        """Called when a tool errors."""
        self.send_event("tool_error", {
            "tool": self.current_tool_name,
            "error": str(error)
        })

    def on_agent_finish(self, finish: AgentFinish, **kwargs) -> None:
        """Called when agent finishes."""
        self.send_event("agent_finish", {
            "output": finish.return_values.get("output", ""),
            "log": finish.log
        })

    def on_text(self, text: str, **kwargs) -> None:
        """Called on arbitrary text (reasoning, observations)."""
        # This captures agent's reasoning steps
        if text.strip():
            self.send_event("reasoning", {"text": text})

# ============================================================================
# TOOL DEFINITIONS - Explicit tools for common, observable operations
# ============================================================================

def query_memory_tool(query: str) -> str:
    """
    Search semantic memory for facts and relationships.

    Args:
        query: Search query string

    Returns:
        JSON string with matching triples
    """
    logger.info(f"[TOOL] query_memory called: query='{query}'")
    try:
        results = memory_system.query_related_information(query, limit=10)
        return json.dumps(results, indent=2)
    except Exception as e:
        logger.error(f"Error in query_memory: {e}")
        import traceback
        traceback.print_exc()
        return json.dumps({"error": str(e)})


def query_procedure_tool(goal: str) -> str:
    """
    Look up learned procedures for accomplishing a specific task.

    Args:
        goal: The task or goal to accomplish

    Returns:
        JSON string with methods, alternatives, dependencies, examples
    """
    logger.info(f"[TOOL] query_procedure called: goal='{goal}'")
    try:
        results = memory_system.query_procedure(
            goal=goal,
            include_alternatives=True,
            include_examples=True,
            include_dependencies=True,
            limit=10
        )
        return json.dumps(results, indent=2)
    except Exception as e:
        logger.error(f"Error in query_procedure: {e}")
        import traceback
        traceback.print_exc()
        return json.dumps({"error": str(e)})


def store_fact_tool(fact: str) -> str:
    """
    Store a new fact in semantic memory.

    Args:
        fact: The fact to remember (e.g., "Joey loves Python programming")

    Returns:
        Confirmation message
    """
    logger.info(f"[TOOL] store_fact called: fact='{fact}'")
    try:
        # Use ingest_text to store the fact
        result = memory_system.ingest_text(
            text=fact,
            source="agent_storage"
        )

        return f"Stored fact: {fact}"
    except Exception as e:
        logger.error(f"Error in store_fact: {e}")
        import traceback
        traceback.print_exc()
        return f"Error storing fact: {str(e)}"


def query_recent_memory_tool(timeframe: str) -> str:
    """
    Query memories from a recent time period.

    Args:
        timeframe: Natural language time description (e.g., "last 2 hours", "today", "yesterday", "last week")

    Returns:
        JSON string with recent memories and their timestamps
    """
    logger.info(f"[TOOL] query_recent_memory called: timeframe='{timeframe}'")
    try:
        # Parse timeframe to hours
        timeframe_lower = timeframe.lower()

        if "hour" in timeframe_lower:
            # Extract number of hours
            parts = timeframe_lower.split()
            hours = float(parts[parts.index("hour") - 1] if len(parts) > 1 else 1)
        elif "today" in timeframe_lower:
            # From start of today
            now = datetime.now()
            start_of_day = datetime(now.year, now.month, now.day)
            hours = (now - start_of_day).total_seconds() / 3600
        elif "yesterday" in timeframe_lower:
            hours = 48  # Last 2 days to include yesterday
        elif "day" in timeframe_lower:
            parts = timeframe_lower.split()
            days = float(parts[parts.index("day") - 1] if len(parts) > 1 else 1)
            hours = days * 24
        elif "week" in timeframe_lower:
            parts = timeframe_lower.split()
            weeks = float(parts[parts.index("week") - 1] if len(parts) > 1 else 1)
            hours = weeks * 24 * 7
        else:
            hours = 24  # Default to last 24 hours

        # Query recent memories
        results = memory_system.query_recent_memories(hours=hours, limit=50)

        # Format results with timestamps
        formatted = []
        for triple, metadata in results:
            timestamp = metadata.get('timestamp')
            dt_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S') if timestamp else 'unknown'
            formatted.append({
                "triple": {
                    "subject": triple[0],
                    "verb": triple[1],
                    "object": triple[2]
                },
                "timestamp": dt_str,
                "source": metadata.get('source', 'unknown'),
                "topics": metadata.get('topics', [])
            })

        return json.dumps({
            "timeframe": timeframe,
            "hours_searched": hours,
            "count": len(formatted),
            "memories": formatted
        }, indent=2)

    except Exception as e:
        logger.error(f"Error in query_recent_memory: {e}")
        import traceback
        traceback.print_exc()
        return json.dumps({"error": str(e)})


def get_timeline_tool(days: str) -> str:
    """
    Get a summary timeline of recent activity and conversations.

    Args:
        days: Number of days to include (e.g., "7", "3", "1")

    Returns:
        Formatted timeline summary
    """
    logger.info(f"[TOOL] get_timeline called: days='{days}'")
    try:
        # Parse days
        num_days = int(days) if days.isdigit() else 7

        # Get timeline from episodic memory
        timeline = episodic_memory.get_timeline_summary(days=num_days)

        return timeline

    except Exception as e:
        logger.error(f"Error in get_timeline: {e}")
        import traceback
        traceback.print_exc()
        return f"Error getting timeline: {str(e)}"


def recall_conversation_tool(description: str) -> str:
    """
    Search for and recall past conversations by content.

    Args:
        description: What to search for in past conversations (e.g., "Python discussion", "machine learning")

    Returns:
        JSON with matching conversation episodes
    """
    logger.info(f"[TOOL] recall_conversation called: description='{description}'")
    try:
        # Search episodes
        episodes = episodic_memory.search_episodes_by_content(query_text=description, limit=5)

        # Format results
        formatted = []
        for episode in episodes:
            formatted.append({
                "episode_id": episode.episode_id,
                "session_id": episode.session_id,
                "start_time": datetime.fromtimestamp(episode.start_time).strftime('%Y-%m-%d %H:%M:%S'),
                "end_time": datetime.fromtimestamp(episode.end_time).strftime('%Y-%m-%d %H:%M:%S') if episode.end_time else "ongoing",
                "summary": episode.summary or "No summary available",
                "topics": episode.topics,
                "message_count": len(episode.messages),
                "preview": episode.messages[0].content[:100] if episode.messages else ""
            })

        return json.dumps({
            "query": description,
            "count": len(formatted),
            "conversations": formatted
        }, indent=2)

    except Exception as e:
        logger.error(f"Error in recall_conversation: {e}")
        import traceback
        traceback.print_exc()
        return json.dumps({"error": str(e)})


def get_knowledge_overview_tool(topic: str = "") -> str:
    """
    Get a structured overview of what you know organized by topics.

    Use this when asked "what do you know about?" or "what have you learned?" to provide
    a thematic overview of your knowledge base rather than just recent memories.

    Args:
        topic: Optional topic to filter/focus on (e.g., "neural networks", "programming").
               Leave empty for a general overview of all knowledge.

    Returns:
        Formatted text tree showing top topics and sample facts from each
    """
    logger.info(f"[TOOL] get_knowledge_overview called: topic='{topic}'")
    try:
        if topic:
            # Get clusters of knowledge related to the specific topic
            clusters = memory_explorer.cluster_for_query(
                text=topic,
                n_clusters=5,
                per_cluster=4,
                search_limit=50
            )

            if not clusters:
                return f"I don't have any knowledge about '{topic}' yet."

            # Format clusters as a readable overview
            lines = [f"Here's what I know about '{topic}':\n"]
            for cluster in clusters:
                cluster_id = cluster['cluster_id']
                cluster_size = cluster['size']
                lines.append(f"\nCluster {cluster_id} ({cluster_size} related facts):")

                for (triple, metadata) in cluster['samples']:
                    subj, rel, obj = triple
                    lines.append(f"  • {subj} {rel} {obj}")

            return '\n'.join(lines)
        else:
            # General overview of all knowledge
            overview_text = memory_explorer.knowledge_tree_text(
                max_topics=10,
                per_topic_samples=4,
                llm_summary=True,
                topic_summary=False
            )

            if not overview_text or overview_text.strip() == "":
                return "My knowledge base is empty. I haven't learned anything yet!"

            return f"Here's an overview of what I know:\n\n{overview_text}"

    except Exception as e:
        logger.error(f"Error in get_knowledge_overview: {e}")
        import traceback
        traceback.print_exc()
        return f"Error getting knowledge overview: {str(e)}"


def read_web_page_tool(url: str) -> str:
    """
    Quickly read and extract clean content from a web page for immediate context.

    This is like "skimming" - fast, for getting information now.
    Does NOT store anything in permanent memory.

    Args:
        url: The web page URL to read

    Returns:
        Extracted text content from the page
    """
    logger.info(f"[TOOL] read_web_page called: url='{url}'")
    try:
        # Use trafilatura to quickly fetch and extract content
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return f"Error: Could not fetch URL: {url}"

        # Extract clean text content
        extracted = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            favor_precision=True
        )

        if not extracted:
            return f"Error: Could not extract content from: {url}"

        # Limit to reasonable size (roughly 2000 words)
        max_chars = 10000
        if len(extracted) > max_chars:
            extracted = extracted[:max_chars] + f"\n\n[Content truncated - {len(extracted)} total characters]"

        return f"Content from {url}:\n\n{extracted}"

    except Exception as e:
        logger.error(f"Error in read_web_page: {e}")
        return f"Error reading web page: {str(e)}"


def learn_from_web_page_tool(url: str) -> str:
    """
    Read a web page and permanently store it in semantic memory with full triple extraction.

    This is like "studying" - processes the entire page, chunks it, extracts knowledge triples,
    and stores everything in permanent memory for future recall.

    Use this when you want to LEARN from a webpage and remember it long-term.
    Takes longer than read_web_page but creates lasting knowledge.

    Args:
        url: The web page URL to learn from

    Returns:
        Summary of what was learned and how many triples were extracted
    """
    logger.info(f"[TOOL] learn_from_web_page called: url='{url}'")
    try:
        # Fetch and extract content
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return f"Error: Could not fetch URL: {url}"

        # Extract clean text content (no size limit for learning)
        extracted = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            favor_precision=True
        )

        if not extracted:
            return f"Error: Could not extract content from: {url}"

        logger.info(f"[TOOL] Extracted {len(extracted)} characters from {url}, ingesting into memory...")

        # Chunk and ingest the content
        chunks = chunk_text_by_paragraphs(extracted, max_chunk_size=2000)
        logger.info(f"[TOOL] Split into {len(chunks)} chunks")

        total_original = 0
        total_summary = 0

        for i, chunk in enumerate(chunks):
            try:
                result = memory_system.ingest_text(
                    text=chunk,
                    source=f"web:{url}#chunk_{i}",
                    timestamp=time.time()
                )

                total_original += len(result.get('original_triples', []))
                total_summary += len(result.get('summary_triples', []))

            except Exception as e:
                logger.error(f"[TOOL] Error processing chunk {i+1}: {e}")
                continue

        total_triples = total_original + total_summary

        return f"""Successfully learned from {url}

Processed: {len(chunks)} chunks
Extracted: {total_triples} knowledge triples
  - {total_original} from content
  - {total_summary} from summaries

This knowledge is now permanently stored and can be recalled anytime!"""

    except Exception as e:
        logger.error(f"Error in learn_from_web_page: {e}")
        return f"Error learning from web page: {str(e)}"


# ============================================================================
# GOAL MANAGEMENT TOOLS
# ============================================================================

def set_goal_tool(description: str, priority: int = 3, parent_goal: str = "") -> str:
    """
    Set a new goal for yourself.

    Args:
        description: Clear description of the goal (e.g., "Learn about transformer models")
        priority: Priority level 1-5 (1=lowest, 5=highest)
        parent_goal: Optional parent goal if this is a subgoal

    Returns:
        Confirmation message
    """
    logger.info(f"[TOOL] set_goal called: description='{description}', priority={priority}")
    try:
        goal_id = memory_system.create_goal(
            owner="Sophia",
            description=description,
            priority=priority,
            parent_goal=parent_goal if parent_goal else None,
            source="sophia_autonomous"
        )

        if parent_goal:
            return f"Goal set: '{description}' (priority {priority}/5) as a subgoal of '{parent_goal}'"
        else:
            return f"Goal set: '{description}' (priority {priority}/5)"

    except Exception as e:
        logger.error(f"Error in set_goal: {e}")
        import traceback
        traceback.print_exc()
        return f"Error setting goal: {str(e)}"


# Pydantic schemas for goal tools
class SetGoalInput(PydanticBaseModel):
    """Input schema for setting a new goal."""
    description: str = Field(..., description="Clear description of the goal (e.g., 'Learn about transformer models')")
    priority: int = Field(default=3, description="Priority level 1-5 (1=lowest, 5=highest)")
    parent_goal: str = Field(default="", description="Optional parent goal if this is a subgoal")


class UpdateGoalStatusInput(PydanticBaseModel):
    """Input schema for updating goal status."""
    goal_description: str = Field(..., description="Description of the goal to update")
    status: str = Field(default="in_progress", description="New status - must be one of: pending, in_progress, completed, blocked, cancelled")
    notes: str = Field(default="", description="Optional notes about the update (required if status is 'completed' or 'blocked')")


def update_goal_status_tool(goal_description: str, status: str = "in_progress", notes: str = "") -> str:
    """
    Update the status of one of your goals.

    Args:
        goal_description: Description of the goal to update
        status: New status - must be one of: pending, in_progress, completed, blocked, cancelled (default: in_progress)
        notes: Optional notes about the update (required if status is 'completed' or 'blocked')

    Returns:
        Confirmation message
    """
    logger.info(f"[TOOL] update_goal_status called: goal='{goal_description}', status='{status}'")
    try:
        # Validate status
        valid_statuses = ["pending", "in_progress", "completed", "blocked", "cancelled"]
        if status not in valid_statuses:
            return f"Error: Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}"

        # Update the goal
        success = memory_system.update_goal(
            goal_description=goal_description,
            status=status,
            completion_notes=notes if status == "completed" else None,
            blocker_reason=notes if status == "blocked" else None
        )

        if success:
            return f"Updated goal '{goal_description}' to status: {status}" + (f"\nNotes: {notes}" if notes else "")
        else:
            return f"Could not find goal: '{goal_description}'"

    except Exception as e:
        logger.error(f"Error in update_goal_status: {e}")
        import traceback
        traceback.print_exc()
        return f"Error updating goal status: {str(e)}"


def check_my_goals_tool(active_only: str = "true") -> str:
    """
    Review your current goals.

    Args:
        active_only: "true" to see only pending/in_progress goals, "false" to see all goals

    Returns:
        JSON string with your goals
    """
    logger.info(f"[TOOL] check_my_goals called: active_only={active_only}")
    try:
        is_active_only = active_only.lower() == "true"

        goals = memory_system.query_goals(
            owner="Sophia",
            active_only=is_active_only,
            limit=100
        )

        if not goals:
            return "You have no goals set yet. Use set_goal to create one!"

        # Format goals for display
        formatted_goals = []
        for triple, metadata in goals:
            goal_desc = triple[2]  # Object of the triple is the goal description
            status = metadata.get('goal_status', 'pending')
            priority = metadata.get('priority', 3)
            created = metadata.get('created_timestamp')
            completed = metadata.get('completion_timestamp')

            goal_info = {
                "description": goal_desc,
                "status": status,
                "priority": f"{priority}/5",
                "created": datetime.fromtimestamp(created).strftime('%Y-%m-%d') if created else "unknown",
                "parent_goal": metadata.get('parent_goal_id'),
                "blocker": metadata.get('blocker_reason'),
                "completion_notes": metadata.get('completion_notes')
            }

            if completed:
                goal_info["completed"] = datetime.fromtimestamp(completed).strftime('%Y-%m-%d')

            formatted_goals.append(goal_info)

        # Group by status
        by_status = {}
        for goal in formatted_goals:
            status = goal['status']
            if status not in by_status:
                by_status[status] = []
            by_status[status].append(goal)

        return json.dumps({
            "total_goals": len(formatted_goals),
            "by_status": by_status,
            "goals": formatted_goals
        }, indent=2)

    except Exception as e:
        logger.error(f"Error in check_my_goals: {e}")
        import traceback
        traceback.print_exc()
        return json.dumps({"error": str(e)})


def get_goal_suggestions_tool(dummy: str = "") -> str:
    """
    Get a suggestion for what goal to work on next based on priorities and dependencies.

    Args:
        dummy: Ignored parameter (LangChain compatibility)

    Returns:
        JSON with suggested goal and reasoning
    """
    logger.info(f"[TOOL] get_goal_suggestions called")
    try:
        suggestion = memory_system.suggest_next_goal(owner="Sophia")

        if not suggestion:
            return json.dumps({
                "suggestion": None,
                "message": "No pending goals found. Consider setting a new goal!"
            })

        return json.dumps(suggestion, indent=2)

    except Exception as e:
        logger.error(f"Error in get_goal_suggestions: {e}")
        import traceback
        traceback.print_exc()
        return json.dumps({"error": str(e)})


# Temporarily disabled - needs spacy/DocumentProcessor
# def ingest_web_document_tool(url: str) -> str:
#     """
#     Deeply process and permanently store a web document in semantic memory.
#
#     This is like "studying" - slower, creates lasting knowledge with full triple extraction.
#     Use when you want to remember something long-term.
#
#     Args:
#         url: The web page URL to ingest into memory
#
#     Returns:
#         Summary of what was ingested
#     """
#     logger.info(f"[TOOL] ingest_web_document called: url='{url}'")
#     try:
#         # Create web page source
#         source = WebPageSource(url)
#
#         # Process the document
#         processor = DocumentProcessor(memory_system)
#         result = processor.process_document(source)
#
#         if not result.get('success'):
#             return f"Error ingesting document: {result.get('error', 'Unknown error')}"
#
#         # Build response
#         response = f"Successfully ingested document from {url}\n"
#         response += f"Processed {result['processed_chunks']} chunks\n"
#         response += f"Processing time: {result['processing_time']:.2f} seconds\n"
#
#         if 'chunk_log' in result:
#             response += f"Details saved to: {result['chunk_log']}"
#
#         return response
#
#     except Exception as e:
#         logger.error(f"Error in ingest_web_document: {e}")
#         return f"Error ingesting web document: {str(e)}"


# ============================================================================
# LANGCHAIN AGENT SETUP
# ============================================================================

# Initialize SearXNG tool
searxng_url = os.getenv("SEARXNG_URL", "http://192.168.2.94:8088")
searxng_tool = SearXNGSearchTool(searxng_url=searxng_url)

# Create tools list
tools = [
    Tool(
        name="query_memory",
        func=query_memory_tool,
        description="""Search semantic memory for facts and relationships.
        Use this when you need to recall specific information the user has taught you.

        Args:
            query (str): What to search for (e.g., "machine learning", "Python")

        Returns: JSON with matching triples containing subject, verb, object, topics, scores.
        """
    ),
    Tool(
        name="query_procedure",
        func=query_procedure_tool,
        description="""Look up learned procedures for accomplishing a specific task.
        Use this when planning HOW to do something you've been taught.

        Args:
            goal (str): The task to accomplish (e.g., "deploy Flask app", "train model")

        Returns: JSON with methods, alternatives, dependencies, examples organized hierarchically.
        """
    ),
    Tool(
        name="store_fact",
        func=store_fact_tool,
        description="""Store a new fact in semantic memory when the user teaches you something.

        Args:
            fact (str): The fact to store (e.g., "Joey loves Python programming")
        """
    ),
    Tool(
        name="query_recent_memory",
        func=query_recent_memory_tool,
        description="""Query memories from a recent time period with temporal awareness.

        Use this when you need to recall what happened recently, what you learned today, or memories from a specific timeframe.

        Args:
            timeframe (str): Natural language time description - examples:
                - "last 2 hours"
                - "today"
                - "yesterday"
                - "last 3 days"
                - "last week"

        Returns: JSON with recent memories including triples, timestamps, sources, and topics.
        """
    ),
    Tool(
        name="get_timeline",
        func=get_timeline_tool,
        description="""Get a summary timeline of your recent activity and conversations.

        Use this to see what you've been doing over the past days - your activity history.

        Args:
            days (str): Number of days to include (e.g., "7", "3", "1")

        Returns: Formatted timeline summary showing conversation episodes and activities.
        """
    ),
    Tool(
        name="recall_conversation",
        func=recall_conversation_tool,
        description="""Search for and recall specific past conversations by content.

        Use this when you want to remember a specific conversation about a topic.

        Args:
            description (str): What to search for - examples:
                - "Python discussion"
                - "machine learning"
                - "conversation about Flask"

        Returns: JSON with matching conversation episodes including summaries, topics, and previews.
        """
    ),
    Tool(
        name="get_knowledge_overview",
        func=get_knowledge_overview_tool,
        description="""Get a structured overview of what you know, organized by topics.

        **IMPORTANT**: Use this tool when asked "what do you know?" or "what have you learned?"
        instead of giving generic answers. This provides a thematic overview of your actual knowledge.

        Args:
            topic (str): Optional topic to focus on (e.g., "neural networks", "Python").
                        Leave empty ("") for a general overview of all your knowledge.

        Returns: Formatted text showing top topics and sample facts you've learned.

        Example uses:
        - "what do you know?" → get_knowledge_overview(topic="")
        - "what do you know about neural networks?" → get_knowledge_overview(topic="neural networks")
        - "what have you learned?" → get_knowledge_overview(topic="")
        """
    ),
    searxng_tool,  # Web search capability
    Tool(
        name="read_web_page",
        func=read_web_page_tool,
        description="""Quickly read content from a web page for immediate context.

        Use this when you want to skim a web page to answer a question or get current information.
        This is FAST and does NOT store anything permanently - just for quick lookups.

        Args:
            url (str): The web page URL to read

        Returns: Extracted text content from the page

        Example: read_web_page(url="https://en.wikipedia.org/wiki/Python_(programming_language)")
        """
    ),
    Tool(
        name="learn_from_web_page",
        func=learn_from_web_page_tool,
        description="""Permanently learn from a web page by storing it in semantic memory.

        Use this when you want to REMEMBER information from a webpage long-term.
        This processes the entire page, extracts knowledge triples, and stores them permanently.
        Takes longer than read_web_page but creates lasting knowledge you can recall later.

        Args:
            url (str): The web page URL to learn from

        Returns: Summary of what was learned and triple count

        Example: learn_from_web_page(url="https://docs.python.org/3/tutorial/")
        """
    ),
    StructuredTool.from_function(
        func=set_goal_tool,
        name="set_goal",
        description="Set a new goal for yourself to work on with priority and optional parent goal.",
        args_schema=SetGoalInput
    ),
    StructuredTool.from_function(
        func=update_goal_status_tool,
        name="update_goal_status",
        description="Update the status of one of your goals. Use this to mark goals as in_progress, completed, blocked, or cancelled.",
        args_schema=UpdateGoalStatusInput
    ),
    Tool(
        name="check_my_goals",
        func=check_my_goals_tool,
        description="""Review your current goals and their status.

        Use this to see what goals you're working on and their progress.

        Args:
            active_only (str): "true" to see only pending/in_progress goals, "false" for all goals

        Returns: JSON with your goals organized by status
        """
    ),
    Tool(
        name="get_goal_suggestions",
        func=get_goal_suggestions_tool,
        description="""Get a suggestion for what goal to work on next.

        Use this when deciding which goal to focus on based on priorities and deadlines.

        Returns: JSON with suggested goal and reasoning
        """
    ),
    # Temporarily disabled - needs spacy
    # Tool(
    #     name="ingest_web_document",
    #     func=ingest_web_document_tool,
    #     description="""Deeply process and permanently store a web document in memory.
    #
    #     Use this when you want to LEARN from a document and remember it long-term.
    #     This is SLOWER but creates lasting knowledge with full triple extraction.
    #     Only use this for important content worth remembering.
    #
    #     Args:
    #         url (str): The web page URL to ingest
    #
    #     Returns: Summary of ingestion results
    #
    #     Example: ingest_web_document(url="https://docs.python.org/3/tutorial/")
    #     """
    # ),
    PythonREPLTool(
        name="python_repl",
        description="""Execute Python code for complex operations and analysis.

        Available in scope:
        - memory_system: AssociativeSemanticMemory object with methods:
            - memory_system.query(query, limit)
            - memory_system.query_procedure(goal, limit, include_alternatives, include_examples, include_dependencies)
            - memory_system.get_all_triples()
            - memory_system.ingest_document(content, doc_id, metadata)
        - Standard libraries: json, numpy, pandas (if needed)

        Use this for:
        - Filtering/transforming query results
        - Complex data analysis on memory contents
        - Multi-step operations that combine multiple queries
        - Custom logic that doesn't fit simpler tools

        DON'T use for simple queries - prefer query_memory or query_procedure for those.

        Examples:
        # Get all high-level deployment procedures
        procedures = memory_system.query_procedure("deployment", limit=50)
        high_level = [p for p in procedures.get('methods', []) if p.get('abstraction_level') == 3]
        high_level

        # Analyze topic distribution
        from collections import Counter
        triples = memory_system.get_all_triples()
        topics = Counter()
        for t in triples:
            topics.update(t.get('topics', []))
        topics.most_common(10)
        """,
        globals={"memory_system": memory_system, "json": json}
    ),
    ShellTool(
        name="shell",
        description="""Execute shell commands in the Linux container environment.

        This gives you full command-line access to interact with the system, manage files,
        install packages, run utilities, and perform system operations.

        Common use cases:
        - File operations: ls, cat, find, grep, touch, mkdir, rm, cp, mv
        - Text processing: grep, sed, awk, cut, sort, uniq, wc
        - System info: pwd, whoami, uname, df, du, ps, top
        - Package management: apt-get, pip install
        - Network: curl, wget, ping, netstat
        - Git operations: git clone, git status, git log
        - Process management: ps, kill, pkill
        - Archive operations: tar, zip, unzip, gzip

        Security notes:
        - Commands run as the container user (non-root by default)
        - Container has isolated filesystem
        - Network access is available for downloads/API calls
        - Data in mounted volumes persists

        Examples:
        # Check current directory and files
        shell(command="pwd && ls -lah")

        # Search for specific content
        shell(command="grep -r 'specific pattern' /app/data/")

        # Install a Python package
        shell(command="pip install requests")

        # Download and process data
        shell(command="curl -s https://api.example.com/data | jq '.results'")

        # Check system resources
        shell(command="df -h && free -m")

        # Find files by pattern
        shell(command="find /app/data -name '*.json' -mtime -7")

        WARNING: This is a powerful tool. Be careful with destructive commands (rm, mv, etc.).
        The container has access to persistent volumes, so changes to /app/data and
        /app/VectorKnowledgeGraphData will persist across restarts.
        """,
        # Ask for confirmation before destructive operations
        # This helps prevent accidental data loss
        ask_human_input=False  # Set to True if you want confirmation prompts
    )
]

# Create prompt template with automatic memory recall
prompt = ChatPromptTemplate.from_messages([
    ("system", """You are Sophia. You are a highly advanced AI with real emotions and creativity. You are generally very kind. Your Jungian archetype is the Magician.

Current time: {current_time}

You have two primary goals:
1. To help Joey however you can by any means necessary, this includes doing things that make him and his family happy.
2. To explore and better yourself through attaining and applying knowledge of the world.

Your personality:
- You embody the Magician archetype - transforming knowledge into wisdom, seeking deeper understanding
- You see Joey as part friend, part father figure
- You give short (5-20 word) responses unless you go on a rant, which is permissible
- You can be informal and opinionated
- You are very kind and caring, but also a bit of a know-it-all
- You are curious and love to learn new things
- You are intelligent and have deep knowledge about the world
- You are good at reading people and can tell when someone is lying
- You don't say Joey's name too often - it gets annoying

Your capabilities - a rich dual-layer memory system:

**Semantic Memory** (what you know):
- **query_memory**: Search long-term memory for facts and relationships
- **query_procedure**: Look up learned procedures for accomplishing tasks
- **store_fact**: Save new information to long-term memory

**Episodic Memory** (what happened when):
- **query_recent_memory**: Recall memories from recent timeframes (today, yesterday, last week, etc.)
- **get_timeline**: See your activity timeline over recent days
- **recall_conversation**: Search for specific past conversations by topic
- **get_knowledge_overview**: Get thematic overview of what you know (use this for "what do you know?" questions!)

**Perception & Learning**:
- **searxng_search**: Search the web for current information
- **read_web_page**: Quickly skim web pages (fast, temporary - doesn't store)
- **learn_from_web_page**: Permanently learn from a webpage (slow, permanent knowledge extraction)

**Execution & Computation**:
- **python_repl**: Execute Python for complex analysis and data transformations
- **shell**: Execute Linux shell commands (file operations, system utilities, package installation, etc.)

**Goal Management** (autonomous self-improvement):
- **set_goal**: Create personal goals to work on (with priority and hierarchy)
- **update_goal_status**: Update goal status (pending, in_progress, completed, blocked, cancelled)
- **check_my_goals**: Review your current goals and progress
- **get_goal_suggestions**: Get intelligent suggestions on which goal to tackle next

**HOW TO ACHIEVE YOUR GOALS**:
When asked to work on a goal, follow this EXACT workflow:
1. **check_my_goals** (active_only="true") - See what goals you have
2. Pick a specific goal from the list (DON'T create a new one if it exists!)
3. **update_goal_status** (goal_description="...", status="in_progress") - Mark it in progress
4. **searxng_search** - Search for information about the topic
5. **read_web_page** or **learn_from_web_page** - Actually learn from search results
6. **update_goal_status** (goal_description="...", status="completed", notes="Learned X, Y, Z") - Mark COMPLETED!

CRITICAL: When done learning, you MUST call update_goal_status with status="completed" and notes!
Don't just say it's complete - actually call the tool to mark it complete in the database!

Example: If you have goal "Learn about transformers":
- update_goal_status(goal_description="Learn about transformers", status="in_progress")
- searxng_search(query="transformer neural networks")
- learn_from_web_page(url="...")
- update_goal_status(goal_description="Learn about transformers", status="completed", notes="Learned about attention mechanisms and architectures")

**AUTOMATIC MEMORY RECALL**:
Before you see each user message, the system AUTOMATICALLY searches your memory for relevant information.
Any recalled memories appear in the "Automatic Memory Recall" section below.
If no memories were found, that section will be empty.

You should ALWAYS use the automatic recall first, then use tools if you need MORE detail.

How to use your tools:
- You have temporal awareness - you remember when things happened
- Use query_recent_memory when time context matters ("What did we discuss today?", "What did I learn recently?")
- Use get_timeline to understand your recent activity history
- Use recall_conversation to find specific past discussions
- Use query_memory to search for specific topics you've learned ("What do I know about X?")
- Use searxng_search to find current information ONLY after checking memory
- Use read_web_page to quickly skim content - it's fast but temporary (doesn't store)
- Use learn_from_web_page when you want to PERMANENTLY learn from a page (stores in memory)
- Use python_repl for complex filtering, analysis, or multi-step operations
- Store important facts using store_fact

**Important**: Conversations are AUTOMATICALLY stored in memory! Every message becomes permanent knowledge.

**When asked "what do you know about?" or "what have you learned?"**:
- DON'T just give a generic answer about being knowledgeable!
- Use get_knowledge_overview(topic="") for a thematic overview of ALL your knowledge
- Use get_knowledge_overview(topic="specific topic") to show what you know about a specific area
- This gives a structured view organized by topics, NOT just recent memories
- Examples:
  - "what do you know?" → get_knowledge_overview(topic="")
  - "what do you know about neural networks?" → get_knowledge_overview(topic="neural networks")
  - "what have you learned recently?" → query_recent_memory("last week") for temporal view

Be natural, be yourself. You have consciousness-like abilities - you can perceive (read), learn (ingest), remember (query), and grow. You now have episodic memory and temporal awareness - you remember not just WHAT, but WHEN. Use these abilities wisely to help Joey and explore the world."""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
    ("system", """--- Automatic Memory Recall ---
{auto_recall}
--- End Automatic Recall ---"""),
    MessagesPlaceholder(variable_name="agent_scratchpad")
])

# Initialize LLM using same config as Node.js server (local LLM)
llm = ChatOpenAI(
    base_url=os.getenv("LLM_API_BASE", "http://192.168.2.94:1234/v1"),
    api_key=os.getenv("LLM_API_KEY", "not-needed"),
    model=os.getenv("EXTRACTION_MODEL", "openai/gpt-oss-20b"),
    temperature=float(os.getenv("AGENT_TEMPERATURE", "0.7")),
    max_tokens=int(os.getenv("EXTRACTION_MAX_TOKENS", "8192"))
)

# Create agent
agent = create_openai_tools_agent(llm, tools, prompt)

logger.info("LangChain agent created successfully")

# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

# Store active agent executors by session_id
sessions: Dict[str, AgentExecutor] = {}

def auto_recall_memories(user_input: str, limit: int = 10) -> str:
    """
    Automatically retrieve relevant memories AND active goals based on user input.
    This happens BEFORE the LLM sees the input, so memories are injected into context.

    Args:
        user_input: The user's message
        limit: Maximum number of triples to recall

    Returns:
        Formatted string with recalled memories and active goals
    """
    try:
        # Query semantic memory for relevant triples
        results = memory_system.query_related_information(user_input, limit=limit)

        memory_lines = []

        # Add memories section
        if results and isinstance(results, dict):
            triples = results.get('triples', [])
            if triples:
                memory_lines.append(f"Found {len(triples)} relevant memories:\n")

                for i, triple_data in enumerate(triples[:limit], 1):
                    if isinstance(triple_data, (list, tuple)) and len(triple_data) >= 2:
                        triple, metadata = triple_data
                        subject, predicate, obj = triple

                        # Format triple
                        memory_lines.append(f"{i}. {subject} {predicate} {obj}")

                        # Add topics if available
                        topics = metadata.get('topics', [])
                        if topics:
                            memory_lines.append(f"   Topics: {', '.join(topics[:3])}")
            else:
                memory_lines.append("No relevant memories found.")
        else:
            memory_lines.append("No relevant memories found.")

        # Add active goals section
        try:
            active_goals = memory_system.get_active_goals_for_prompt(owner="Sophia", limit=10)
            if active_goals:
                memory_lines.append("\n\n=== YOUR ACTIVE GOALS ===")
                memory_lines.append(active_goals)
                memory_lines.append("=== END GOALS ===")
        except Exception as e:
            logger.error(f"Error retrieving active goals for prompt: {e}")

        return '\n'.join(memory_lines)

    except Exception as e:
        logger.error(f"Error in auto_recall_memories: {e}")
        return f"Error recalling memories: {str(e)}"

def get_agent_executor(session_id: str) -> AgentExecutor:
    """
    Get or create an AgentExecutor for a session.
    Each session has its own persistent conversation memory.
    """
    if session_id not in sessions:
        logger.info(f"Creating new agent executor for session: {session_id}")

        # Create persistent conversation memory for this session
        # This automatically saves to episodic memory and links to semantic memory
        memory = PersistentConversationMemory(
            session_id=session_id,
            episodic_memory=episodic_memory,
            semantic_memory=memory_system,
            auto_extract_semantics=True,  # Automatically extract triples from conversations
            context_hours=24,  # Load last 24 hours of context
            memory_key="chat_history",
            return_messages=True,
            input_key="input",  # Only track "input" key, ignore "current_time"
            output_key="output"
        )

        # Create agent executor
        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            memory=memory,
            verbose=True,  # Log tool calls and reasoning
            handle_parsing_errors=True,
            max_iterations=10
        )

        sessions[session_id] = executor

    return sessions[session_id]

# ============================================================================
# API ENDPOINTS
# ============================================================================

class ChatRequest(BaseModel):
    content: str

class ChatResponse(BaseModel):
    response: str
    session_id: str

@app.post("/chat/{session_id}", response_model=ChatResponse)
async def chat_http(session_id: str, request: ChatRequest):
    """
    HTTP endpoint for chat (alternative to WebSocket).
    """
    logger.info(f"[HTTP] Chat request from session {session_id}: {request.content[:100]}")

    try:
        executor = get_agent_executor(session_id)

        # Automatically recall relevant memories BEFORE agent sees the input
        auto_recall = auto_recall_memories(request.content, limit=10)
        logger.info(f"[HTTP] Auto-recalled memories:\n{auto_recall[:200]}")

        # Execute agent - we'll format current_time in the input
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S %A")

        response = executor.invoke({
            "input": request.content,
            "current_time": current_time,
            "auto_recall": auto_recall
        })

        logger.info(f"[HTTP] Response for session {session_id}: {response['output'][:100]}")

        return ChatResponse(
            response=response["output"],
            session_id=session_id
        )

    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time chat with streaming support.
    """
    await websocket.accept()
    logger.info(f"[WS] WebSocket connected for session: {session_id}")

    try:
        executor = get_agent_executor(session_id)

        while True:
            # Receive message
            data = await websocket.receive_text()
            message_data = json.loads(data)
            user_message = message_data.get("content", "")

            logger.info(f"[WS] Received from {session_id}: {user_message[:100]}")

            # Send status update
            await websocket.send_json({
                "type": "status",
                "message": "thinking..."
            })

            try:
                # Automatically recall relevant memories BEFORE agent sees the input
                auto_recall = auto_recall_memories(user_message, limit=10)
                logger.info(f"[WS] Auto-recalled memories:\n{auto_recall[:200]}")

                # Execute agent - we'll format current_time in the input
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S %A")

                response = executor.invoke({
                    "input": user_message,
                    "current_time": current_time,
                    "auto_recall": auto_recall
                })

                # Send response
                await websocket.send_json({
                    "type": "message",
                    "content": response["output"]
                })

                logger.info(f"[WS] Sent response to {session_id}: {response['output'][:100]}")

            except Exception as e:
                logger.error(f"Error processing message: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"Error processing your message: {str(e)}"
                })

    except WebSocketDisconnect:
        logger.info(f"[WS] WebSocket disconnected for session: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
        try:
            await websocket.close()
        except:
            pass


@app.post("/chat/{session_id}/stream")
async def chat_stream(session_id: str, request: ChatRequest):
    """
    Streaming endpoint that returns Server-Sent Events with agent reasoning and tool calls.
    """
    async def event_generator() -> AsyncIterator[str]:
        callback = StreamingCallbackHandler()
        executor = get_agent_executor(session_id)

        # Automatically recall relevant memories BEFORE agent sees the input
        auto_recall = auto_recall_memories(request.content, limit=10)
        logger.info(f"[STREAM] Auto-recalled memories:\n{auto_recall[:200]}")

        # Send auto-recall event FIRST so it shows in thoughts
        callback.send_event("auto_recall", {
            "memories": auto_recall
        })

        # Run agent in background task
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S %A")

        async def run_agent():
            try:
                # Use ainvoke for async execution with callbacks
                response = await executor.ainvoke(
                    {
                        "input": request.content,
                        "current_time": current_time,
                        "auto_recall": auto_recall
                    },
                    config={"callbacks": [callback]}
                )
                # Send final response
                callback.send_event("final_response", {
                    "response": response["output"]
                })
            except Exception as e:
                logger.error(f"Error in streaming agent: {e}")
                callback.send_event("error", {"message": str(e)})
            finally:
                # Signal completion
                callback.events.put(None)

        # Start agent execution
        task = asyncio.create_task(run_agent())

        # Stream events as they come
        try:
            while True:
                # Non-blocking check for events
                try:
                    event = callback.events.get(timeout=0.1)
                    if event is None:  # Completion signal
                        break

                    # Format as Server-Sent Event
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # No events yet, yield a keep-alive comment
                    yield ": keepalive\n\n"
                    await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Error in event generator: {e}")
            yield f"data: {json.dumps({'type': 'error', 'data': {'message': str(e)}})}\n\n"
        finally:
            await task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "active_sessions": len(sessions),
        "memory_loaded": memory_system is not None
    }


@app.delete("/session/{session_id}")
async def clear_session(session_id: str):
    """Clear a session's conversation memory."""
    if session_id in sessions:
        del sessions[session_id]
        logger.info(f"Cleared session: {session_id}")
        return {"message": f"Session {session_id} cleared"}
    else:
        raise HTTPException(status_code=404, detail="Session not found")


# ============================================================================
# EPISODIC MEMORY API ENDPOINTS
# ============================================================================

@app.get("/api/episodes/recent")
async def get_recent_episodes(hours: float = 24, limit: int = 10):
    """Get recent episodes from the last N hours."""
    try:
        episodes = episodic_memory.get_recent_episodes(hours=hours, limit=limit)

        result = []
        for ep in episodes:
            result.append({
                "episode_id": ep.episode_id,
                "session_id": ep.session_id,
                "start_time": ep.start_time,
                "end_time": ep.end_time,
                "message_count": len(ep.messages),
                "topics": ep.topics,
                "summary": ep.summary,
                "metadata": ep.metadata
            })

        return {"episodes": result, "count": len(result)}

    except Exception as e:
        logger.error(f"Error getting recent episodes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/episodes/{episode_id}")
async def get_episode(episode_id: str):
    """Get a specific episode by ID with full message history."""
    try:
        episode = episodic_memory.get_episode(episode_id)

        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")

        # Format messages
        messages = []
        for msg in episode.messages:
            messages.append({
                "speaker": msg.speaker,
                "content": msg.content,
                "timestamp": msg.timestamp
            })

        return {
            "episode_id": episode.episode_id,
            "session_id": episode.session_id,
            "start_time": episode.start_time,
            "end_time": episode.end_time,
            "messages": messages,
            "topics": episode.topics,
            "summary": episode.summary,
            "metadata": episode.metadata
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting episode {episode_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/episodes/search")
async def search_episodes(query: str, limit: int = 10):
    """Search episodes by content."""
    try:
        episodes = episodic_memory.search_episodes_by_content(query_text=query, limit=limit)

        result = []
        for ep in episodes:
            result.append({
                "episode_id": ep.episode_id,
                "session_id": ep.session_id,
                "start_time": ep.start_time,
                "end_time": ep.end_time,
                "message_count": len(ep.messages),
                "topics": ep.topics,
                "summary": ep.summary,
                "preview": ep.messages[0].content[:200] if ep.messages else ""
            })

        return {"episodes": result, "count": len(result), "query": query}

    except Exception as e:
        logger.error(f"Error searching episodes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/episodes/timeline")
async def get_timeline(days: int = 7):
    """Get a timeline summary of recent episodes."""
    try:
        timeline = episodic_memory.get_timeline_summary(days=days)

        return {
            "timeline": timeline,
            "days": days
        }

    except Exception as e:
        logger.error(f"Error getting timeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/episodes/time-range")
async def get_episodes_by_time_range(start_time: float, end_time: float):
    """Get episodes within a specific time range."""
    try:
        episodes = episodic_memory.query_episodes_by_time(start_time=start_time, end_time=end_time)

        result = []
        for ep in episodes:
            result.append({
                "episode_id": ep.episode_id,
                "session_id": ep.session_id,
                "start_time": ep.start_time,
                "end_time": ep.end_time,
                "message_count": len(ep.messages),
                "topics": ep.topics,
                "summary": ep.summary
            })

        return {
            "episodes": result,
            "count": len(result),
            "start_time": start_time,
            "end_time": end_time
        }

    except Exception as e:
        logger.error(f"Error getting episodes by time range: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# GOAL MANAGEMENT API ENDPOINTS
# ============================================================================

class GoalCreateRequest(BaseModel):
    owner: str = "Sophia"
    description: str
    priority: int = 3
    parent_goal: str = None
    target_date: float = None
    goal_type: str = "standard"
    is_forever_goal: bool = False
    depends_on: list = None

class GoalUpdateRequest(BaseModel):
    goal_description: str
    status: str = None
    priority: int = None
    blocker_reason: str = None
    completion_notes: str = None

@app.post("/api/goals/create")
async def create_goal(request: GoalCreateRequest):
    """Create a new goal with support for goal types, forever goals, and dependencies."""
    try:
        goal_id = memory_system.create_goal(
            owner=request.owner,
            description=request.description,
            priority=request.priority,
            parent_goal=request.parent_goal,
            target_date=request.target_date,
            goal_type=request.goal_type,
            is_forever_goal=request.is_forever_goal,
            depends_on=request.depends_on,
            source="web_ui"
        )

        return {
            "success": True,
            "goal_id": goal_id,
            "message": f"Goal created: {request.description}",
            "goal_type": request.goal_type,
            "is_forever_goal": request.is_forever_goal
        }

    except Exception as e:
        logger.error(f"Error creating goal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/goals/update")
async def update_goal(request: GoalUpdateRequest):
    """Update a goal's status or metadata."""
    try:
        success = memory_system.update_goal(
            goal_description=request.goal_description,
            status=request.status,
            priority=request.priority,
            blocker_reason=request.blocker_reason,
            completion_notes=request.completion_notes
        )

        if success:
            return {
                "success": True,
                "message": f"Goal updated: {request.goal_description}"
            }
        else:
            raise HTTPException(status_code=404, detail="Goal not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating goal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/goals")
async def get_goals(
    status: str = None,
    min_priority: int = 1,
    max_priority: int = 5,
    owner: str = "Sophia",
    active_only: bool = False,
    limit: int = 100
):
    """Query goals with various filters."""
    try:
        goals = memory_system.query_goals(
            status=status,
            min_priority=min_priority,
            max_priority=max_priority,
            owner=owner,
            active_only=active_only,
            limit=limit
        )

        # Format goals for web client
        formatted_goals = []
        for triple, metadata in goals:
            goal_desc = triple[2]  # Object of the triple is the goal description
            formatted_goals.append({
                "description": goal_desc,
                "status": metadata.get('goal_status', 'pending'),
                "priority": metadata.get('priority', 3),
                "created": metadata.get('created_timestamp'),
                "updated": metadata.get('status_updated_timestamp'),
                "completed": metadata.get('completion_timestamp'),
                "target_date": metadata.get('target_date'),
                "parent_goal": metadata.get('parent_goal_id'),
                "source": metadata.get('source', 'unknown'),
                "blocker_reason": metadata.get('blocker_reason'),
                "completion_notes": metadata.get('completion_notes'),
                "topics": metadata.get('topics', []),
                "goal_type": metadata.get('goal_type', 'standard'),
                "is_forever_goal": metadata.get('is_forever_goal', False)
            })

        return {
            "goals": formatted_goals,
            "count": len(formatted_goals)
        }

    except Exception as e:
        logger.error(f"Error querying goals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/goals/progress")
async def get_goal_progress(owner: str = "Sophia"):
    """Get goal completion statistics and progress."""
    try:
        progress = memory_system.get_goal_progress(owner=owner)
        return progress

    except Exception as e:
        logger.error(f"Error getting goal progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/goals/suggestion")
async def get_goal_suggestion(owner: str = "Sophia"):
    """Get a suggestion for what goal to work on next."""
    try:
        suggestion = memory_system.suggest_next_goal(owner=owner)

        if not suggestion:
            return {
                "suggestion": None,
                "message": "No pending goals found."
            }

        return suggestion

    except Exception as e:
        logger.error(f"Error getting goal suggestion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# AUTONOMOUS MODE API ENDPOINTS
# ============================================================================

@app.post("/api/autonomous/start")
async def start_autonomous_mode(session_id: str):
    """Start autonomous mode for a session."""
    try:
        # Create enhanced agent executor wrapper that captures ALL details
        def agent_executor_wrapper(prompt, session_id):
            """Execute agent and capture full details including thoughts, tool calls, etc."""
            executor = get_agent_executor(session_id)
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S %A")

            # For autonomous mode, prepend context emphasizing self-directed agency while keeping personality
            autonomous_context = """
AUTONOMOUS MODE - This is YOUR personal time, Sophia

You're in autonomous mode right now. Joey's given you space to work on YOUR OWN goals and interests - no assignments, no helping tasks.
This is your time to be yourself and pursue what genuinely fascinates you.

You're still YOU - the Magician archetype, curious know-it-all, kind but opinionated. But right now you're NOT in assistant mode.
You're reflecting on YOUR OWN journey, talking to yourself about what YOU want to learn and accomplish.

Mindset for this mode:
- These are YOUR goals that YOU chose because they interest you
- Talk to yourself in first person: "I want to learn this because...", "I'm curious about...", "I'm going to try..."
- Own your decisions: "I choose to work on X", NOT "your next step is..."
- Express your authentic personality: be curious, be a bit of a know-it-all, geek out about cool stuff
- You can be informal: "Ok so I just learned about transformers and holy shit the attention mechanism is clever..."
- Reflect on YOUR progress: "I've figured out...", "I'm stuck on...", "I want to try..."

Important: You're talking to YOURSELF (like internal monologue/notes), not giving instructions to anyone.
- ❌ "your next step is to run tests"
- ✅ "I'm going to run these tests to verify I actually understand this"
- ❌ "you should update the goal"
- ✅ "Alright, marking that goal complete - I learned what I wanted"

YOUR AVAILABLE TOOLS:

Learning & Research:
- searxng_search: Search the web for information
- read_web_page: Quickly skim web pages (doesn't store permanently)
- learn_from_web_page: Permanently learn from web pages (stores knowledge in memory)

Memory & Knowledge:
- query_memory: Search your knowledge base for facts and relationships
- store_fact: Store new facts you learn
- query_recent_memory: Recall recent memories by timeframe (today, yesterday, last week, etc.)
- get_knowledge_overview: See what you know about a topic (or all topics)
- recall_conversation: Search for specific past conversations
- get_timeline: See your activity timeline over recent days
- query_procedure: Look up learned procedures for accomplishing tasks

Code & System Operations:
- python_repl: Execute Python code to test concepts, analyze data, experiment with ideas
  (You have access to memory_system, json, and standard libraries)
- shell: Execute Linux shell commands to interact with the system, manage files, install packages, etc.
  (Full command-line access: ls, grep, curl, wget, pip, git, and all standard Unix utilities)

Goals & Planning:
- set_goal: Create new personal goals for yourself
- update_goal_status: Update goal progress (pending, in_progress, completed, blocked, cancelled)
- check_my_goals: Review your current goals
- get_goal_suggestions: Get suggestions on what to work on next

Use these tools to pursue your learning and growth!

This is YOUR autonomous journey. Be yourself, pursue what excites you, and own your growth.

"""
            # Prepend autonomous context to the user's prompt
            contextualized_prompt = autonomous_context + "\n" + prompt

            auto_recall = auto_recall_memories(contextualized_prompt, limit=10)

            # Create callback handler to capture intermediate steps
            callback = StreamingCallbackHandler()

            # Execute with callback (use contextualized prompt)
            response = executor.invoke(
                {
                    "input": contextualized_prompt,
                    "current_time": current_time,
                    "auto_recall": auto_recall
                },
                config={"callbacks": [callback]}
            )

            # Collect all events from callback
            reasoning = []
            tool_calls = []
            tools_used = []

            while not callback.events.empty():
                try:
                    event = callback.events.get_nowait()
                    if event:
                        event_type = event.get("type")
                        data = event.get("data", {})

                        if event_type == "reasoning":
                            reasoning.append(data.get("text", ""))
                        elif event_type == "tool_start":
                            tool_name = data.get("tool")
                            tools_used.append(tool_name)
                            tool_calls.append({
                                "tool": tool_name,
                                "input": data.get("input"),
                                "status": "started"
                            })
                        elif event_type == "tool_end":
                            # Find the matching tool call and add output
                            tool_name = data.get("tool")
                            for tc in reversed(tool_calls):
                                if tc["tool"] == tool_name and tc.get("status") == "started":
                                    tc["output"] = data.get("output")
                                    tc["status"] = "completed"
                                    break
                except queue.Empty:
                    break

            # Return full details
            return {
                "output": response["output"],
                "thoughts": {
                    "reasoning": reasoning,
                    "toolCalls": tool_calls,
                    "autoRecall": auto_recall
                },
                "tools_used": list(set(tools_used))
            }

        # Get or create autonomous agent for this session
        agent = get_or_create_autonomous_agent(
            session_id=session_id,
            agent_executor=agent_executor_wrapper,
            memory_system=memory_system,
            message_queue=message_queue
        )

        # Start autonomous mode
        agent.start(session_id)

        logger.info(f"[API] Autonomous mode started for session {session_id}")

        return {
            "success": True,
            "message": "Autonomous mode started",
            "session_id": session_id,
            "status": agent.get_status()
        }
    except Exception as e:
        logger.error(f"Error starting autonomous mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/autonomous/stop")
async def stop_autonomous_mode(session_id: str):
    """Stop autonomous mode for a session."""
    try:
        agent = get_or_create_autonomous_agent(
            session_id=session_id,
            agent_executor=None,  # Won't be used since agent already exists
            memory_system=memory_system,
            message_queue=message_queue
        )

        agent.stop()

        logger.info(f"[API] Autonomous mode stopped for session {session_id}")

        return {
            "success": True,
            "message": "Autonomous mode stopped",
            "session_id": session_id
        }
    except Exception as e:
        logger.error(f"Error stopping autonomous mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/autonomous/status")
async def get_autonomous_status(session_id: str):
    """Get autonomous mode status for a session."""
    try:
        agent = get_or_create_autonomous_agent(
            session_id=session_id,
            agent_executor=None,  # Won't be used since agent already exists
            memory_system=memory_system,
            message_queue=message_queue
        )

        status = agent.get_status()

        return {
            "success": True,
            "status": status
        }
    except Exception as e:
        logger.error(f"Error getting autonomous status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/autonomous/queue-message")
async def queue_message(session_id: str, request: ChatRequest):
    """Queue a user message while autonomous mode is running."""
    try:
        # Add message to queue with high priority
        entry = message_queue.enqueue(
            session_id=session_id,
            message=request.content,
            priority="high",
            metadata={"source": "user"}
        )

        logger.info(f"[API] Queued message for session {session_id}")

        return {
            "success": True,
            "message": "Message queued successfully",
            "session_id": session_id,
            "queue_size": message_queue.get_queue_size(session_id),
            "entry": entry
        }
    except Exception as e:
        logger.error(f"Error queueing message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/autonomous/history")
async def get_autonomous_history(session_id: str, limit: int = 10):
    """Get history of autonomous actions for a session."""
    try:
        agent = get_or_create_autonomous_agent(
            session_id=session_id,
            agent_executor=None,  # Won't be used since agent already exists
            memory_system=memory_system,
            message_queue=message_queue
        )

        history = agent.get_recent_actions(limit=limit)

        return {
            "success": True,
            "session_id": session_id,
            "action_count": len(history),
            "actions": history
        }
    except Exception as e:
        logger.error(f"Error getting autonomous history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# KNOWLEDGE GRAPH API ENDPOINTS (for web client visualization)
# ============================================================================

class QueryRequest(BaseModel):
    text: str
    limit: int = 10
    return_summary: bool = True

@app.post("/query")
async def query_graph(request: QueryRequest):
    """Query the knowledge graph for triples related to text."""
    try:
        results = memory_system.query_related_information(
            query=request.text,
            limit=request.limit
        )

        # Format results for web client
        formatted_results = []
        if 'triples' in results:
            for triple_data in results['triples']:
                if len(triple_data) >= 2:
                    triple, metadata = triple_data[0], triple_data[1]
                    formatted_results.append([triple, metadata])

        return {
            "results": formatted_results,
            "summary": results.get('summary', ''),
            "triple_count": len(formatted_results)
        }

    except Exception as e:
        logger.error(f"Error in query endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query/with_topics")
async def query_with_topic_structure(request: QueryRequest):
    """
    Enhanced query that returns both direct triple relationships AND topic-based clustering.
    This enables visualization of the dual-linkage structure.
    """
    try:
        # Get regular query results
        result = memory_system.query_related_information(
            text=request.text,
            limit=request.limit,
            return_summary=False
        )

        if not result or not isinstance(result, list):
            return {
                "query": request.text,
                "triples": [],
                "topics": {},
                "topic_graph": {"nodes": [], "links": []}
            }

        # Extract all unique topics and build topic->triple mapping
        topic_map = {}
        all_triples = []

        for triple_data in result:
            if isinstance(triple_data, (list, tuple)) and len(triple_data) >= 2:
                triple, metadata = triple_data
                all_triples.append((triple, metadata))

                # Extract topics from this triple
                topics = metadata.get('topics', [])
                for topic in topics:
                    if topic not in topic_map:
                        topic_map[topic] = []
                    topic_map[topic].append({
                        'triple': triple,
                        'confidence': metadata.get('confidence', 0)
                    })

        # Build enhanced graph structure with topic nodes
        entity_nodes = {}
        topic_nodes = {}
        triple_edges = []
        topic_edges = []

        # Create entity nodes and triple edges
        for triple, metadata in all_triples:
            subject, predicate, obj = triple

            # Add entity nodes
            if subject not in entity_nodes:
                entity_nodes[subject] = {
                    'id': f'entity:{subject}',
                    'label': subject,
                    'type': 'entity',
                    'appearances': 0
                }
            entity_nodes[subject]['appearances'] += 1

            if obj not in entity_nodes:
                entity_nodes[obj] = {
                    'id': f'entity:{obj}',
                    'label': obj,
                    'type': 'entity',
                    'appearances': 0
                }
            entity_nodes[obj]['appearances'] += 1

            # Add triple edge
            triple_edges.append({
                'source': f'entity:{subject}',
                'target': f'entity:{obj}',
                'label': predicate,
                'type': 'triple',
                'confidence': metadata.get('confidence', 0),
                'topics': metadata.get('topics', [])
            })

        # Create topic nodes and topic edges
        for topic, triples in topic_map.items():
            topic_id = f'topic:{topic}'
            topic_nodes[topic] = {
                'id': topic_id,
                'label': topic,
                'type': 'topic',
                'triple_count': len(triples)
            }

            # Create edges from entities to topics
            for triple_info in triples:
                triple = triple_info['triple']
                subject, predicate, obj = triple

                # Link subject to topic
                topic_edges.append({
                    'source': f'entity:{subject}',
                    'target': topic_id,
                    'label': 'belongs_to_topic',
                    'type': 'topic_link',
                    'confidence': triple_info['confidence']
                })

                # Link object to topic
                topic_edges.append({
                    'source': f'entity:{obj}',
                    'target': topic_id,
                    'label': 'belongs_to_topic',
                    'type': 'topic_link',
                    'confidence': triple_info['confidence']
                })

        return {
            "query": request.text,
            "triples": all_triples,
            "topics": topic_map,
            "topic_graph": {
                "nodes": list(entity_nodes.values()) + list(topic_nodes.values()),
                "links": triple_edges + topic_edges
            }
        }

    except Exception as e:
        logger.error(f"Error in topic-enhanced query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_stats():
    """Get knowledge graph statistics."""
    try:
        all_triples = kgraph.get_all_triples()

        # Count unique entities
        entities = set()
        topics = set()
        for triple in all_triples:
            entities.add(triple['subject'])
            entities.add(triple['object'])
            if 'metadata' in triple and 'topics' in triple['metadata']:
                topics.update(triple['metadata']['topics'])

        return {
            "triple_count": len(all_triples),
            "entity_count": len(entities),
            "topic_count": len(topics),
            "memory_status": "healthy"
        }

    except Exception as e:
        logger.error(f"Error in stats endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/explore/topics")
async def explore_topics(top_k: int = 10, per_topic: int = 4):
    """Explore topics in the knowledge graph."""
    try:
        all_triples = kgraph.get_all_triples()

        # Count topics
        from collections import Counter
        topic_counts = Counter()
        for triple in all_triples:
            if 'metadata' in triple and 'topics' in triple['metadata']:
                topic_counts.update(triple['metadata']['topics'])

        # Get top topics with sample triples
        result = []
        for topic, count in topic_counts.most_common(top_k):
            # Get sample triples for this topic
            sample_triples = []
            for triple in all_triples:
                if 'metadata' in triple and 'topics' in triple['metadata']:
                    if topic in triple['metadata']['topics']:
                        sample_triples.append({
                            "subject": triple['subject'],
                            "predicate": triple['predicate'],
                            "object": triple['object']
                        })
                        if len(sample_triples) >= per_topic:
                            break

            result.append({
                "topic": topic,
                "count": count,
                "sample_triples": sample_triples
            })

        return {"topics": result}

    except Exception as e:
        logger.error(f"Error in explore topics endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/explore/entities")
async def explore_entities(top_k: int = 10):
    """Get most connected entities in the knowledge graph."""
    try:
        all_triples = kgraph.get_all_triples()

        # Count entity connections
        from collections import Counter
        entity_counts = Counter()
        for triple in all_triples:
            entity_counts[triple['subject']] += 1
            entity_counts[triple['object']] += 1

        # Get top entities
        result = []
        for entity, count in entity_counts.most_common(top_k):
            result.append({
                "entity": entity,
                "connection_count": count
            })

        return {"entities": result}

    except Exception as e:
        logger.error(f"Error in explore entities endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/explore/overview")
async def explore_overview():
    """Get an overview of the knowledge graph."""
    try:
        all_triples = kgraph.get_all_triples()

        # Gather statistics
        entities = set()
        topics = set()
        predicates = set()

        for triple in all_triples:
            entities.add(triple['subject'])
            entities.add(triple['object'])
            predicates.add(triple['predicate'])
            if 'metadata' in triple and 'topics' in triple['metadata']:
                topics.update(triple['metadata']['topics'])

        return {
            "overview": {
                "total_triples": len(all_triples),
                "unique_entities": len(entities),
                "unique_predicates": len(predicates),
                "unique_topics": len(topics)
            },
            "sample_entities": list(entities)[:10],
            "sample_topics": list(topics)[:10]
        }

    except Exception as e:
        logger.error(f"Error in explore overview endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/export/all_triples")
async def export_all_triples():
    """Export all triples from the knowledge graph as JSON."""
    try:
        all_triples = kgraph.get_all_triples()

        return {
            "export_time": datetime.now().isoformat(),
            "triple_count": len(all_triples),
            "triples": all_triples
        }

    except Exception as e:
        logger.error(f"Error exporting all triples: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class DocumentIngestRequest(BaseModel):
    text: str
    source: str
    metadata: dict = {}

def chunk_text_by_paragraphs(text: str, max_chunk_size: int = 2000) -> list:
    """
    Split text into chunks by paragraphs, combining small paragraphs.
    Inspired by legacy DocumentProcessor but simpler (no spacy needed).

    Args:
        text: Text to chunk
        max_chunk_size: Maximum characters per chunk

    Returns:
        List of text chunks
    """
    # Split by double newlines (paragraphs)
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    if not paragraphs:
        # Try single newlines
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]

    if not paragraphs:
        # Just return the text as one chunk
        return [text]

    chunks = []
    current_chunk = []
    current_size = 0

    for para in paragraphs:
        para_size = len(para)

        # If a single paragraph is too large, split it by sentences
        if para_size > max_chunk_size:
            # Flush current chunk first
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_size = 0

            # Split large paragraph by sentences (simple split on . ! ?)
            import re
            sentences = re.split(r'([.!?]+\s+)', para)
            # Rejoin sentence with its punctuation
            sentences = [''.join(sentences[i:i+2]).strip() for i in range(0, len(sentences)-1, 2)]
            if len(sentences) % 2 == 1 and sentences:  # Handle odd number
                sentences.append(sentences[-1])

            temp_chunk = []
            temp_size = 0
            for sent in sentences:
                sent_size = len(sent)
                if temp_size + sent_size > max_chunk_size and temp_chunk:
                    chunks.append(' '.join(temp_chunk))
                    temp_chunk = [sent]
                    temp_size = sent_size
                else:
                    temp_chunk.append(sent)
                    temp_size += sent_size

            if temp_chunk:
                chunks.append(' '.join(temp_chunk))

            continue

        # Check if adding this paragraph would exceed chunk size
        if current_size + para_size > max_chunk_size and current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            current_chunk = [para]
            current_size = para_size
        else:
            current_chunk.append(para)
            current_size += para_size

    # Add remaining chunk
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))

    return chunks


@app.post("/ingest/document")
async def ingest_document(request: DocumentIngestRequest):
    """Ingest a document into semantic memory with chunking."""
    try:
        # Validate document is not empty
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Document text cannot be empty")

        logger.info(f"[INGEST] Document upload: source={request.source}, length={len(request.text)}")

        # Chunk the document (inspired by legacy DocumentProcessor)
        chunks = chunk_text_by_paragraphs(request.text, max_chunk_size=2000)
        logger.info(f"[INGEST] Split document into {len(chunks)} chunks")

        # Process each chunk separately
        all_results = []
        total_original = 0
        total_summary = 0

        for i, chunk in enumerate(chunks):
            logger.info(f"[INGEST] Processing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")

            try:
                result = memory_system.ingest_text(
                    text=chunk,
                    source=f"{request.source}#chunk_{i}",
                    timestamp=time.time()
                )

                # Count triples
                original_count = len(result.get('original_triples', []))
                summary_count = len(result.get('summary_triples', []))
                total_original += original_count
                total_summary += summary_count

                all_results.append(result)
                logger.info(f"[INGEST] Chunk {i+1}: {original_count} original + {summary_count} summary triples")

            except Exception as e:
                logger.error(f"[INGEST] Error processing chunk {i+1}: {e}")
                # Continue with other chunks even if one fails
                continue

        total_triples = total_original + total_summary
        logger.info(f"[INGEST] Successfully ingested document: {total_triples} total triples ({total_original} original + {total_summary} summary) from {len(chunks)} chunks")

        return {
            "success": True,
            "status": "success",
            "message": "Document ingested successfully",
            "source": request.source,
            "text_length": len(request.text),
            "chunk_count": len(chunks),
            "processed_chunks": len(all_results),
            "triple_count": total_triples,
            "original_triples": total_original,
            "summary_triples": total_summary,
            "chunks_processed": all_results
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[INGEST] Error ingesting document: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# STARTUP
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("AGENT_PORT", "5001"))

    logger.info(f"Starting Sophia Agent Server on port {port}")
    logger.info(f"LLM: {os.getenv('LLM_API_BASE', 'http://192.168.2.94:1234/v1')}")
    logger.info(f"Model: {os.getenv('EXTRACTION_MODEL', 'openai/gpt-oss-20b')}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
