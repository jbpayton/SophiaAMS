"""
FastAPI REST server for SophiaAMS - Associative Semantic Memory System
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uvicorn
import logging
import time
from datetime import datetime

from AssociativeSemanticMemory import AssociativeSemanticMemory
from MemoryExplorer import MemoryExplorer
from ConversationProcessor import ConversationProcessor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SophiaAMS API",
    description="Associative Semantic Memory System REST API",
    version="1.0.0"
)

# Initialize memory system
try:
    from VectorKnowledgeGraph import VectorKnowledgeGraph
    kgraph = VectorKnowledgeGraph()
    memory = AssociativeSemanticMemory(kgraph)
    explorer = MemoryExplorer(memory.kgraph)
    conversation_processor = ConversationProcessor(memory)

    # Server-side conversation buffers
    conversation_buffers = {}  # session_id -> list of messages
    BUFFER_SIZE = 5  # Process every N messages
    MIN_BUFFER_TIME = 30  # Or every 30 seconds

    logger.info("SophiaAMS initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize SophiaAMS: {e}")
    raise

# Pydantic models for request/response
class ConversationMessage(BaseModel):
    role: str  # "user", "assistant", etc.
    content: str
    name: Optional[str] = None

class ConversationIngest(BaseModel):
    messages: List[ConversationMessage]
    session_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}
    speaker_names: Optional[Dict[str, str]] = {}  # role -> actual name mapping
    force_process: Optional[bool] = False  # Force immediate processing regardless of buffer

class DocumentIngest(BaseModel):
    text: str
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}

class QueryRequest(BaseModel):
    text: str
    limit: Optional[int] = 10
    session_id: Optional[str] = None
    return_summary: Optional[bool] = True

class AssociativeRequest(BaseModel):
    text: str
    limit: Optional[int] = 10
    hops: Optional[int] = 2

class LLMGenerationRequest(BaseModel):
    messages: List[Dict[str, str]]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 400

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# Ingestion endpoints
def should_process_buffer(session_id: str, force: bool = False) -> bool:
    """Determine if conversation buffer should be processed."""
    if force:
        return True

    if session_id not in conversation_buffers:
        return False

    buffer_info = conversation_buffers[session_id]
    message_count = len(buffer_info["messages"])
    time_since_last = time.time() - buffer_info["last_updated"]

    return message_count >= BUFFER_SIZE or time_since_last >= MIN_BUFFER_TIME

def process_conversation_buffer(session_id: str, speaker_names: Dict[str, str] = None):
    """Process and clear a conversation buffer."""
    if session_id not in conversation_buffers:
        return None

    buffer_info = conversation_buffers[session_id]
    messages = buffer_info["messages"]

    if not messages:
        return None

    # Apply speaker name mapping
    processed_messages = []
    for msg in messages:
        processed_msg = msg.copy()
        if speaker_names and msg["role"] in speaker_names:
            processed_msg["name"] = speaker_names[msg["role"]]
        processed_messages.append(processed_msg)

    # Process with ConversationProcessor
    result = conversation_processor.process_conversation(
        messages=processed_messages,
        entity_name=speaker_names.get("assistant", "assistant") if speaker_names else "assistant",
        timestamp=time.time()
    )

    # Clear the buffer
    conversation_buffers[session_id]["messages"] = []
    conversation_buffers[session_id]["last_processed"] = time.time()

    return result

@app.post("/ingest/conversation")
async def ingest_conversation(request: ConversationIngest):
    """Ingest conversation messages with smart buffering."""
    try:
        session_id = request.session_id or "default"

        # Initialize buffer if needed
        if session_id not in conversation_buffers:
            conversation_buffers[session_id] = {
                "messages": [],
                "last_updated": time.time(),
                "last_processed": time.time()
            }

        # Convert to OpenAI format and add to buffer
        buffer_info = conversation_buffers[session_id]
        for msg in request.messages:
            openai_msg = {"role": msg.role, "content": msg.content}
            if msg.name:
                openai_msg["name"] = msg.name
            buffer_info["messages"].append(openai_msg)

        buffer_info["last_updated"] = time.time()

        # Check if we should process the buffer
        processed = False
        processing_result = None

        if should_process_buffer(session_id, request.force_process):
            processing_result = process_conversation_buffer(session_id, request.speaker_names)
            processed = True

        buffered_count = len(buffer_info["messages"])
        total_received = len(request.messages)

        return {
            "status": "success",
            "message": "Messages added to conversation buffer",
            "session_id": session_id,
            "received_messages": total_received,
            "buffered_messages": buffered_count,
            "processed": processed,
            "processing_result": processing_result
        }

    except Exception as e:
        logger.error(f"Error ingesting conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/conversation/buffer/{session_id}")
async def get_buffer_status(session_id: str):
    """Get the status of a conversation buffer."""
    if session_id not in conversation_buffers:
        return {
            "session_id": session_id,
            "exists": False,
            "buffered_messages": 0
        }

    buffer_info = conversation_buffers[session_id]
    return {
        "session_id": session_id,
        "exists": True,
        "buffered_messages": len(buffer_info["messages"]),
        "last_updated": buffer_info["last_updated"],
        "last_processed": buffer_info.get("last_processed", 0),
        "time_since_update": time.time() - buffer_info["last_updated"],
        "should_process": should_process_buffer(session_id)
    }

@app.post("/conversation/process/{session_id}")
async def force_process_buffer(session_id: str, speaker_names: Optional[Dict[str, str]] = None):
    """Force processing of a conversation buffer."""
    try:
        if session_id not in conversation_buffers:
            raise HTTPException(status_code=404, detail="Session buffer not found")

        result = process_conversation_buffer(session_id, speaker_names)

        if result is None:
            return {
                "status": "no_processing",
                "message": "Buffer was empty, nothing to process"
            }

        return {
            "status": "success",
            "message": "Buffer processed successfully",
            "processing_result": result
        }

    except Exception as e:
        logger.error(f"Error processing buffer: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate_response")
async def generate_llm_response(request: LLMGenerationRequest):
    """Generate an LLM response using the same client as the memory system."""
    try:
        from openai import OpenAI
        import os

        # Use the same LLM client configuration as the memory system
        client = OpenAI(
            base_url=os.getenv("LLM_API_BASE", "http://192.168.2.94:1234/v1"),
            api_key=os.getenv("LLM_API_KEY", "not-needed")
        )

        # Convert messages to proper format
        formatted_messages = []
        for msg in request.messages:
            formatted_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

        # Make the LLM call
        response = client.chat.completions.create(
            model=os.getenv("EXTRACTION_MODEL", "gemma-3-4b-it-qat"),  # Use same model as memory system
            messages=formatted_messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )

        llm_response = response.choices[0].message.content

        return {
            "response": llm_response,
            "model_used": os.getenv("EXTRACTION_MODEL", "gemma-3-4b-it-qat"),
            "messages_count": len(formatted_messages)
        }

    except Exception as e:
        logger.error(f"Error generating LLM response: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ingest/document")
async def ingest_document(request: DocumentIngest):
    """Ingest a document or text content."""
    try:
        # Use existing document ingestion with simple parameters
        result = memory.ingest_text(
            text=request.text,
            source=request.source or "document",
            timestamp=time.time()
        )

        return {
            "status": "success",
            "message": "Document ingested successfully",
            "source": request.source,
            "text_length": len(request.text),
            "processing_result": result
        }
    except Exception as e:
        logger.error(f"Error ingesting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Retrieval endpoints
@app.post("/query")
async def query_memory(request: QueryRequest):
    """Query memory for related information."""
    try:
        # Add session context to metadata if provided
        query_metadata = {}
        if request.session_id:
            query_metadata["session_id"] = request.session_id

        result = memory.query_related_information(
            text=request.text,
            limit=request.limit,
            return_summary=request.return_summary
        )

        return {
            "query": request.text,
            "results": result,
            "session_id": request.session_id
        }
    except Exception as e:
        logger.error(f"Error querying memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/retrieve/associative")
async def get_associative_content(request: AssociativeRequest):
    """Get associatively related content using hop expansion."""
    try:
        result = memory.get_associated_content(
            query_text=request.text,
            max_hops=request.hops,
            limit=request.limit
        )

        return {
            "query": request.text,
            "hops": request.hops,
            "results": result
        }
    except Exception as e:
        logger.error(f"Error getting associative content: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Exploration endpoints
@app.get("/explore/topics")
async def explore_topics(top_k: int = 10, per_topic: int = 4):
    """Get overview of top topics in the knowledge graph."""
    try:
        overview = explorer.knowledge_overview(
            top_k_topics=top_k,
            per_topic_samples=per_topic
        )
        return {
            "topics": overview["topics"],
            "total_topics": len(overview["topics"])
        }
    except Exception as e:
        logger.error(f"Error exploring topics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/explore/entities")
async def explore_entities(top_k: int = 10):
    """Get most connected entities in the knowledge graph."""
    try:
        entities = explorer.top_entities(k=top_k)
        return {
            "entities": [{"entity": entity, "connections": count} for entity, count in entities],
            "total_entities": len(entities)
        }
    except Exception as e:
        logger.error(f"Error exploring entities: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/explore/overview")
async def knowledge_overview():
    """Get comprehensive knowledge overview with topics and entities."""
    try:
        overview = explorer.knowledge_overview()
        return overview
    except Exception as e:
        logger.error(f"Error getting knowledge overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/explore/cluster")
async def cluster_query(request: QueryRequest):
    """Cluster triples related to a query."""
    try:
        clusters = explorer.cluster_for_query(
            text=request.text,
            n_clusters=5,
            per_cluster=3,
            search_limit=75
        )
        return {
            "query": request.text,
            "clusters": clusters
        }
    except Exception as e:
        logger.error(f"Error clustering query: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Stats endpoint
@app.get("/stats")
async def get_stats():
    """Get basic statistics about the knowledge graph."""
    try:
        triples = memory.kgraph.get_all_triples()
        return {
            "total_triples": len(triples),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")