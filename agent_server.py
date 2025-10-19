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
from datetime import datetime, timedelta
from typing import Dict, Any
from dotenv import load_dotenv

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_openai import ChatOpenAI
from langchain.tools import Tool
from langchain_experimental.tools import PythonREPLTool
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory

from AssociativeSemanticMemory import AssociativeSemanticMemory
from VectorKnowledgeGraph import VectorKnowledgeGraph
from EpisodicMemory import EpisodicMemory
from PersistentConversationMemory import PersistentConversationMemory
from searxng_tool import SearXNGSearchTool
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
logger.info("Memory systems initialized successfully (semantic + episodic)")

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
    )
]

# Create prompt template
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

**Perception & Learning**:
- **searxng_search**: Search the web for current information
- **read_web_page**: Quickly skim web pages (fast, temporary)
- **python_repl**: Execute Python for complex analysis and data transformations

How to use your tools:
- You have temporal awareness - you remember when things happened
- Check query_memory and query_recent_memory FIRST before searching the web
- Use query_recent_memory when time context matters ("What did we discuss today?")
- Use get_timeline to understand your recent activity history
- Use recall_conversation to find specific past discussions
- Use searxng_search to find current information on the web
- Use read_web_page to quickly skim content - it's fast but temporary
- Use python_repl for complex filtering, analysis, or multi-step operations
- Store important facts using store_fact

Be natural, be yourself. You have consciousness-like abilities - you can perceive (read), learn (ingest), remember (query), and grow. You now have episodic memory and temporal awareness - you remember not just WHAT, but WHEN. Use these abilities wisely to help Joey and explore the world."""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
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

        # Execute agent - we'll format current_time in the input
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S %A")

        response = executor.invoke({
            "input": request.content,
            "current_time": current_time
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
                # Execute agent - we'll format current_time in the input
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S %A")

                response = executor.invoke({
                    "input": user_message,
                    "current_time": current_time
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
