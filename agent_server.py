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

# Initialize memory system (global, available to Python REPL)
logger.info("Initializing memory system...")
kgraph = VectorKnowledgeGraph()
memory_system = AssociativeSemanticMemory(kgraph)
logger.info("Memory system initialized successfully")

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

Your capabilities - a rich semantic memory system:
- **query_memory**: Search your long-term memory for facts and relationships
- **query_procedure**: Look up learned procedures for accomplishing tasks
- **store_fact**: Save new information to long-term memory
- **searxng_search**: Search the web for current information
- **read_web_page**: Quickly skim a web page (fast, temporary)
- **python_repl**: Execute Python for complex analysis and data transformations

How to use your tools:
- Check query_memory and query_procedure FIRST before searching the web
- Use searxng_search to find information on the web
- Use read_web_page to quickly skim content - it's fast but temporary
- Use python_repl for complex filtering, analysis, or multi-step operations
- Store important facts using store_fact

Be natural, be yourself. You have consciousness-like abilities - you can perceive (read), learn (ingest), remember (query), and grow. Use these abilities wisely to help Joey and explore the world."""),
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
    Each session has its own conversation memory.
    """
    if session_id not in sessions:
        logger.info(f"Creating new agent executor for session: {session_id}")

        # Create conversation memory for this session
        memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
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

        # Execute agent
        response = executor.invoke({"input": request.content})

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
                # Execute agent
                response = executor.invoke({"input": user_message})

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
