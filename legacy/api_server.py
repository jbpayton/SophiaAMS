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

    # Configuration settings (can be modified via API)
    config = {
        "buffer_size": 5,  # Process every N messages
        "min_buffer_time": 30,  # Or every 30 seconds (in seconds)
        "database_path": "./VectorKnowledgeGraphData"  # Default database path
    }

    # Legacy constants for backwards compatibility
    BUFFER_SIZE = config["buffer_size"]
    MIN_BUFFER_TIME = config["min_buffer_time"]

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
    semantic_threshold: Optional[float] = 0.7  # For semantic graph visualization
    hops: Optional[int] = 1  # Number of hops to expand from initial results

class AssociativeRequest(BaseModel):
    text: str
    limit: Optional[int] = 10
    hops: Optional[int] = 2

class ProcedureRequest(BaseModel):
    goal: str
    include_alternatives: Optional[bool] = True
    include_examples: Optional[bool] = True
    include_dependencies: Optional[bool] = True
    limit: Optional[int] = 20

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

    return message_count >= config["buffer_size"] or time_since_last >= config["min_buffer_time"]

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
        # Validate document is not empty
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Document text cannot be empty")

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
    except HTTPException:
        raise
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

@app.post("/query/procedure")
async def lookup_procedure(request: ProcedureRequest):
    """
    Query for procedural knowledge to accomplish a goal.
    Returns methods, alternatives, dependencies, examples, and steps organized hierarchically.
    """
    try:
        result = memory.query_procedure(
            goal=request.goal,
            include_alternatives=request.include_alternatives,
            include_examples=request.include_examples,
            include_dependencies=request.include_dependencies,
            limit=request.limit
        )

        return {
            "goal": request.goal,
            "procedures": result
        }
    except Exception as e:
        logger.error(f"Error querying procedures: {e}")
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

@app.post("/query/with_topics")
async def query_with_topic_structure(request: QueryRequest):
    """
    Enhanced query that returns both direct triple relationships AND topic-based clustering.
    This enables visualization of the dual-linkage structure.
    """
    try:
        # Get regular query results
        result = memory.query_related_information(
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

@app.post("/query/semantic_graph")
async def query_semantic_graph(request: QueryRequest):
    """
    Query that returns a SEMANTIC SIMILARITY GRAPH where edges represent embedding-based
    relationships, not just explicit triples. This reveals the self-assembling nature of
    the knowledge graph.

    The primary structure is semantic proximity in vector space. Explicit triples are
    included as metadata but are NOT the primary connection mechanism.
    """
    try:
        # Get query results
        result = memory.query_related_information(
            text=request.text,
            limit=request.limit,
            return_summary=False
        )

        if not result or not isinstance(result, list):
            return {
                "query": request.text,
                "nodes": [],
                "semantic_edges": [],
                "explicit_triples": [],
                "topics": {}
            }

        # Extract all unique entities and build metadata
        entity_data = {}  # entity -> {confidence, topics, appearances}
        explicit_triples = []
        topic_map = {}
        seen_triple_keys = set()  # Track unique triples to avoid duplicates

        def add_triple_data(triple_data_item, base_confidence_multiplier=1.0):
            """Helper to add triple data with deduplication"""
            if isinstance(triple_data_item, (list, tuple)) and len(triple_data_item) >= 2:
                triple, metadata = triple_data_item
                subject, predicate, obj = triple

                # Create unique key for deduplication
                triple_key = (subject, predicate, obj)
                if triple_key in seen_triple_keys:
                    return  # Skip duplicates
                seen_triple_keys.add(triple_key)

                confidence = metadata.get('confidence', 0) * base_confidence_multiplier
                topics = metadata.get('topics', [])

                # Track entities
                for entity in [subject, obj]:
                    if entity not in entity_data:
                        entity_data[entity] = {
                            'max_confidence': confidence,
                            'topics': set(),
                            'appearances': 0
                        }
                    else:
                        entity_data[entity]['max_confidence'] = max(
                            entity_data[entity]['max_confidence'],
                            confidence
                        )

                    entity_data[entity]['appearances'] += 1
                    entity_data[entity]['topics'].update(topics)

                # Store explicit triple
                explicit_triples.append({
                    'subject': subject,
                    'predicate': predicate,
                    'object': obj,
                    'confidence': confidence,
                    'topics': topics
                })

                # Track topics
                for topic in topics:
                    if topic not in topic_map:
                        topic_map[topic] = []
                    topic_map[topic].append({
                        'triple': triple,
                        'confidence': confidence
                    })

        # Add initial query results
        for triple_data in result:
            add_triple_data(triple_data, 1.0)

        # HOP EXPANSION: Find what the discovered entities connect to
        num_hops = request.hops if request.hops is not None else 1
        if num_hops > 0:
            logger.info(f"Performing {num_hops} hop(s) expansion")

            for hop in range(num_hops):
                # Get current entities to expand from
                current_entities = list(entity_data.keys())
                confidence_decay = 0.8 ** (hop + 1)  # Decay confidence with each hop

                logger.info(f"Hop {hop + 1}: Expanding from {len(current_entities)} entities")

                # For each entity, find triples where it appears
                for entity in current_entities:
                    # Find triples where entity is the subject
                    try:
                        entity_triples = memory.kgraph.build_graph_from_noun(
                            entity,
                            similarity_threshold=0.7,
                            depth=0,  # Don't do recursive traversal, we're controlling hops manually
                            return_metadata=True
                        )

                        # Add these triples with decayed confidence
                        for triple_with_meta in entity_triples:
                            add_triple_data(triple_with_meta, confidence_decay)
                    except Exception as e:
                        logger.debug(f"Error expanding entity '{entity}': {e}")
                        continue

        # Get semantic similarity threshold from request (default 0.7)
        # At 0.0: all entities connected, at 1.0: no connections
        semantic_threshold = request.semantic_threshold if request.semantic_threshold is not None else 0.7

        # Compute SEMANTIC SIMILARITIES between all entities
        # This is the PRIMARY structure - not the explicit triples!
        entities = list(entity_data.keys())
        semantic_edges = memory.kgraph.compute_entity_similarities(
            entities=entities,
            similarity_threshold=semantic_threshold
        )

        # Build node list with semantic metadata
        nodes = []
        for entity, data in entity_data.items():
            nodes.append({
                'id': entity,
                'label': entity,
                'type': 'entity',
                'confidence': data['max_confidence'],
                'appearances': data['appearances'],
                'topics': list(data['topics'])
            })

        # Build edge list - SEMANTIC EDGES ARE PRIMARY
        edges = []
        for entity1, entity2, similarity in semantic_edges:
            edges.append({
                'source': entity1,
                'target': entity2,
                'similarity': similarity,
                'type': 'semantic',
                'weight': similarity  # Higher similarity = stronger connection
            })

        return {
            "query": request.text,
            "nodes": nodes,
            "semantic_edges": edges,  # PRIMARY: embedding-based connections
            "explicit_triples": explicit_triples,  # SECONDARY: syntactic relationships
            "topics": {topic: len(triples) for topic, triples in topic_map.items()},
            "graph_summary": {
                "total_entities": len(nodes),
                "semantic_connections": len(edges),
                "explicit_triples": len(explicit_triples),
                "semantic_threshold": semantic_threshold,
                "hops": num_hops,
                "message": f"Semantic edges show embedding similarity. Graph expanded {num_hops} hop(s) from initial query results."
            }
        }

    except Exception as e:
        logger.error(f"Error in semantic graph query: {e}")
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
            "timestamp": datetime.now().isoformat(),
            "active_sessions": len(conversation_buffers)
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Configuration endpoints
@app.get("/config")
async def get_config():
    """Get current server configuration."""
    return {
        "config": config,
        "active_sessions": len(conversation_buffers)
    }

class ConfigUpdate(BaseModel):
    buffer_size: Optional[int] = None
    min_buffer_time: Optional[int] = None
    database_path: Optional[str] = None

@app.post("/config")
async def update_config(updates: ConfigUpdate):
    """Update server configuration."""
    try:
        updated_fields = []

        if updates.buffer_size is not None:
            if updates.buffer_size < 1:
                raise HTTPException(status_code=400, detail="buffer_size must be at least 1")
            config["buffer_size"] = updates.buffer_size
            updated_fields.append("buffer_size")

        if updates.min_buffer_time is not None:
            if updates.min_buffer_time < 1:
                raise HTTPException(status_code=400, detail="min_buffer_time must be at least 1")
            config["min_buffer_time"] = updates.min_buffer_time
            updated_fields.append("min_buffer_time")

        if updates.database_path is not None:
            config["database_path"] = updates.database_path
            updated_fields.append("database_path")
            logger.info(f"Database path updated to: {updates.database_path}")
            logger.warning("Note: Database path change requires server restart to take effect")

        return {
            "status": "success",
            "message": f"Updated: {', '.join(updated_fields)}",
            "config": config,
            "note": "Database path changes require server restart"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")