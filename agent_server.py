"""
SophiaAMS Agent Server — v2

FastAPI server providing chat, memory, goal, and exploration endpoints.
Uses SophiaAgent (zero-dependency agent loop) instead of LangChain.

When launched via main.py, shared objects (sophia, memory, etc.) are
injected via set_shared_objects(). When run directly (`python agent_server.py`),
it self-initializes for backward compatibility.
"""

import os
import json
import logging
import time
import asyncio
import re
from datetime import datetime
from typing import AsyncIterator, Optional
from collections import Counter
from dotenv import load_dotenv

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="Sophia Agent Server", version="2.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Module-level shared objects (populated by set_shared_objects or _self_init)
# ---------------------------------------------------------------------------
sophia = None
memory_system = None
episodic_memory = None
memory_explorer = None
kgraph = None
_webui_adapter = None  # set when launched via main.py
_event_processor = None  # set when launched via main.py


def set_shared_objects(
    sophia_agent,
    memory_system_ref,
    episodic_memory_ref,
    memory_explorer_ref,
    kgraph_ref,
    webui_adapter_ref=None,
    event_processor_ref=None,
):
    """Called by main.py to inject shared instances (avoids double init)."""
    global sophia, memory_system, episodic_memory, memory_explorer, kgraph, _webui_adapter, _event_processor
    sophia = sophia_agent
    memory_system = memory_system_ref
    episodic_memory = episodic_memory_ref
    memory_explorer = memory_explorer_ref
    kgraph = kgraph_ref
    _webui_adapter = webui_adapter_ref
    _event_processor = event_processor_ref
    logger.info("[agent_server] Shared objects injected by main.py")


def _self_init():
    """Lazy self-init for standalone mode (python agent_server.py)."""
    global sophia, memory_system, episodic_memory, memory_explorer, kgraph

    if sophia is not None:
        return  # already initialized

    from AssociativeSemanticMemory import AssociativeSemanticMemory
    from VectorKnowledgeGraph import VectorKnowledgeGraph
    from EpisodicMemory import EpisodicMemory
    from MemoryExplorer import MemoryExplorer
    from sophia_agent import SophiaAgent

    logger.info("Initializing memory systems (standalone mode)...")
    kgraph = VectorKnowledgeGraph()
    memory_system = AssociativeSemanticMemory(kgraph)
    episodic_memory = EpisodicMemory()
    memory_explorer = MemoryExplorer(kgraph)
    logger.info("Memory systems initialized successfully (semantic + episodic + explorer)")

    sophia = SophiaAgent(
        semantic_memory=memory_system,
        episodic_memory=episodic_memory,
        memory_explorer=memory_explorer,
        workspace_dir=os.environ.get("WORKSPACE_PATH", "./workspace"),
        skill_paths=[os.environ.get("SKILLS_PATH", "./skills")],
        server_base_url=f"http://localhost:{os.environ.get('AGENT_PORT', '5001')}",
    )


@app.on_event("startup")
async def on_startup():
    """Ensure objects are initialized (covers standalone mode)."""
    _self_init()


# ============================================================================
# API MODELS
# ============================================================================

class ChatRequest(BaseModel):
    content: str

class ChatResponse(BaseModel):
    response: str
    session_id: str

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

class QueryRequest(BaseModel):
    text: str
    limit: int = 10
    return_summary: bool = True

class DocumentIngestRequest(BaseModel):
    text: str
    source: str
    metadata: dict = {}


# ============================================================================
# CHAT ENDPOINTS
# ============================================================================

async def _chat_via_bus(session_id: str, content: str) -> str:
    """Route chat through event bus. All channels are unified."""
    if _webui_adapter is None:
        raise HTTPException(
            status_code=503,
            detail="Event bus not initialized. Use 'python main.py' to start."
        )
    future = await _webui_adapter.submit(session_id, content)
    return await future


@app.post("/chat/{session_id}", response_model=ChatResponse)
async def chat_http(session_id: str, request: ChatRequest):
    """HTTP endpoint for chat."""
    logger.info(f"[HTTP] Chat request from session {session_id}: {request.content[:100]}")

    try:
        response = await _chat_via_bus(session_id, request.content)
        logger.info(f"[HTTP] Response for session {session_id}: {response[:100]}")

        return ChatResponse(
            response=response,
            session_id=session_id
        )

    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time chat."""
    await websocket.accept()
    logger.info(f"[WS] WebSocket connected for session: {session_id}")

    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            user_message = message_data.get("content", "")

            logger.info(f"[WS] Received from {session_id}: {user_message[:100]}")

            await websocket.send_json({
                "type": "status",
                "message": "thinking..."
            })

            try:
                response = await _chat_via_bus(session_id, user_message)

                await websocket.send_json({
                    "type": "message",
                    "content": response
                })

                logger.info(f"[WS] Sent response to {session_id}: {response[:100]}")

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
    """Streaming endpoint that returns Server-Sent Events with real-time thoughts."""
    async def event_generator() -> AsyncIterator[str]:
        try:
            if _webui_adapter is None:
                yield f"data: {json.dumps({'type': 'error', 'data': {'message': 'Event bus not initialized'}, 'timestamp': time.time()})}\n\n"
                return

            queue = await _webui_adapter.submit_streaming(session_id, request.content)

            while True:
                try:
                    event_type, data = await asyncio.wait_for(queue.get(), timeout=300)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'error', 'data': {'message': 'Request timed out'}, 'timestamp': time.time()})}\n\n"
                    break

                if event_type == "done":
                    break

                yield f"data: {json.dumps({'type': event_type, 'data': data, 'timestamp': time.time()})}\n\n"

                if event_type in ("final_response", "error"):
                    break

        except Exception as e:
            logger.error(f"Error in streaming agent: {e}")
            yield f"data: {json.dumps({'type': 'error', 'data': {'message': str(e)}, 'timestamp': time.time()})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "active_sessions": len(sophia._sessions) if sophia else 0,
        "memory_loaded": memory_system is not None,
        "event_driven": _webui_adapter is not None,
    }


@app.delete("/session/{session_id}")
async def clear_session(session_id: str):
    """Clear a session's conversation memory."""
    if session_id in sophia._sessions:
        sophia.clear_session(session_id)
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
        return {"timeline": timeline, "days": days}

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

@app.post("/api/goals/create")
async def create_goal(request: GoalCreateRequest):
    """Create a new goal."""
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

        formatted_goals = []
        for triple, metadata in goals:
            goal_desc = triple[2]
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
# ACTIVITY FEED ENDPOINT (Feature 2)
# ============================================================================

@app.get("/api/activity/feed")
async def get_activity_feed(limit: int = 50, offset: int = 0, source: str = None):
    """Get the unified activity feed."""
    if _event_processor is None:
        return {"entries": [], "count": 0}
    entries = _event_processor.get_activity_feed(limit=limit, offset=offset, source_filter=source)
    return {"entries": entries, "count": len(entries)}


# ============================================================================
# PERSONALITY ENDPOINTS (Feature 5)
# ============================================================================

class PersonalityRefineRequest(BaseModel):
    archetype_id: str
    agent_name: str = "Sophia"

class PersonalitySaveRequest(BaseModel):
    personality_text: str

@app.get("/api/personality/presets")
async def get_personality_presets():
    """Return available personality presets."""
    from personality_presets import list_presets, PRESETS
    presets = list_presets()
    # Include the full snippet for the editor
    for p in presets:
        p["system_prompt_snippet"] = PRESETS[p["id"]]["system_prompt_snippet"]
    return {"presets": presets}

@app.get("/api/personality/current")
async def get_current_personality():
    """Return the current personality block from persona_template.txt."""
    template_path = os.path.join(os.path.dirname(__file__), "persona_template.txt")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return {"personality": "", "full_template": ""}

    # Extract the personality section
    personality = _extract_personality_section(content)
    return {"personality": personality, "full_template": content}

@app.post("/api/personality/refine")
async def refine_personality(request: PersonalityRefineRequest):
    """Use LLM to convert archetype personality into natural traits."""
    from personality_presets import get_preset

    preset = get_preset(request.archetype_id)
    snippet = preset.get("system_prompt_snippet", "")

    if not snippet:
        return {"refined": ""}

    refine_prompt = [
        {"role": "system", "content": (
            f"Convert this archetype personality into natural behavioral traits for an AI assistant named {request.agent_name}. "
            "Do NOT mention the archetype name, Jungian psychology, or any framework terminology. "
            "Write as direct personality instructions (5-8 bullet points starting with '- '). "
            "Keep the traits natural and conversational."
        )},
        {"role": "user", "content": f"Original personality:\n{snippet}"}
    ]

    try:
        loop = asyncio.get_running_loop()
        refined = await loop.run_in_executor(
            None,
            lambda: sophia.llm.chat(refine_prompt, max_tokens=500)
        )
        return {"refined": refined.strip()}
    except Exception as e:
        logger.error(f"Error refining personality: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/personality/save")
async def save_personality(request: PersonalitySaveRequest):
    """Save updated personality into persona_template.txt and reload."""
    template_path = os.path.join(os.path.dirname(__file__), "persona_template.txt")

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="persona_template.txt not found")

    # Replace personality section
    new_content = _replace_personality_section(content, request.personality_text)

    with open(template_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    # Reload persona in the agent
    sophia.reload_persona()

    return {"success": True, "message": "Personality saved and applied"}


def _extract_personality_section(template: str) -> str:
    """Extract 'Your personality:' block from persona template."""
    lines = template.split("\n")
    start = None
    end = None

    for i, line in enumerate(lines):
        if line.strip().startswith("Your personality:"):
            start = i
        elif start is not None and line.strip() and not line.startswith("-") and not line.startswith(" "):
            # Found start of next section
            end = i
            break

    if start is None:
        return ""

    if end is None:
        # Find the end by looking for next major section
        for i in range(start + 1, len(lines)):
            if lines[i].strip().startswith("Your capabilities:"):
                end = i
                break

    if end is None:
        end = len(lines)

    return "\n".join(lines[start:end]).strip()


def _replace_personality_section(template: str, new_personality: str) -> str:
    """Replace 'Your personality:' block in the template."""
    lines = template.split("\n")
    start = None
    end = None

    for i, line in enumerate(lines):
        if line.strip().startswith("Your personality:"):
            start = i
            continue
        if start is not None and end is None:
            # Find end of personality block (next section header)
            if line.strip().startswith("Your capabilities:"):
                end = i
                break

    if start is None:
        # No personality section found — prepend one
        return new_personality + "\n\n" + template

    if end is None:
        end = len(lines)

    # Ensure new_personality starts with "Your personality:" header
    if not new_personality.strip().startswith("Your personality:"):
        new_personality = "Your personality:\n" + new_personality

    result_lines = lines[:start] + [new_personality, ""] + lines[end:]
    return "\n".join(result_lines)


# ============================================================================
# SKILLS CONFIGURATION ENDPOINTS (Feature 4)
# ============================================================================

class SkillEnvSetRequest(BaseModel):
    skill_name: str = None
    var_name: str
    value: str

@app.get("/api/skills")
async def list_skills():
    """List all skills with env var requirements."""
    from skill_env_config import SkillEnvConfig
    config = SkillEnvConfig(sophia.skill_loader)
    skills = config.get_all_skills_info()
    return {"skills": skills}

@app.get("/api/skills/{name}/scan")
async def scan_skill(name: str):
    """Trigger rescan (static + LLM) for a skill."""
    from skill_env_config import SkillEnvConfig
    config = SkillEnvConfig(sophia.skill_loader)

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: config.scan_skill(name, sophia.llm)
        )
        return {"success": True, "skill": name, "env_vars": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/skills/{name}/test")
async def test_skill(name: str):
    """Run health check on a skill's env vars."""
    from skill_env_config import SkillEnvConfig
    config = SkillEnvConfig(sophia.skill_loader)

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: config.test_skill(name))
        return {"success": True, "skill": name, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/skills/env")
async def get_skill_env():
    """Get all configured env var values."""
    from skill_env_config import SkillEnvConfig
    config = SkillEnvConfig(sophia.skill_loader)
    return {"env_vars": config.get_all_env_vars()}

@app.post("/api/skills/env")
async def set_skill_env(request: SkillEnvSetRequest):
    """Set an env var value."""
    from skill_env_config import SkillEnvConfig
    config = SkillEnvConfig(sophia.skill_loader)
    config.set_env_var(request.var_name, request.value)
    return {"success": True, "var_name": request.var_name}

@app.delete("/api/skills/env/{var_name}")
async def delete_skill_env(var_name: str):
    """Remove an env var."""
    from skill_env_config import SkillEnvConfig
    config = SkillEnvConfig(sophia.skill_loader)
    config.remove_env_var(var_name)
    return {"success": True, "var_name": var_name}


# ============================================================================
# AUTONOMOUS MODE API ENDPOINTS (event-driven)
# ============================================================================

@app.get("/api/autonomous/status")
async def get_autonomous_status():
    """Get autonomous mode status (event-driven architecture)."""
    return {
        "success": True,
        "status": {
            "running": _webui_adapter is not None,
            "mode": "event_driven" if _webui_adapter else "standalone",
            "active_sessions": len(sophia._sessions) if sophia else 0,
        }
    }


# ============================================================================
# KNOWLEDGE GRAPH API ENDPOINTS (for web client visualization)
# ============================================================================

@app.post("/query")
async def query_graph(request: QueryRequest):
    """Query the knowledge graph for triples related to text."""
    try:
        results = memory_system.query_related_information(
            query=request.text,
            limit=request.limit
        )

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


@app.post("/query/procedure")
async def query_procedure(request: QueryRequest):
    """Query learned procedures for accomplishing tasks (REST endpoint for workspace shim)."""
    try:
        results = memory_system.query_procedure(
            goal=request.text,
            include_alternatives=True,
            include_examples=True,
            include_dependencies=True,
            limit=request.limit
        )
        return results

    except Exception as e:
        logger.error(f"Error in procedure query endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query/with_topics")
async def query_with_topic_structure(request: QueryRequest):
    """Enhanced query with topic-based clustering."""
    try:
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

        topic_map = {}
        all_triples = []

        for triple_data in result:
            if isinstance(triple_data, (list, tuple)) and len(triple_data) >= 2:
                triple, metadata = triple_data
                all_triples.append((triple, metadata))

                topics = metadata.get('topics', [])
                for topic in topics:
                    if topic not in topic_map:
                        topic_map[topic] = []
                    topic_map[topic].append({
                        'triple': triple,
                        'confidence': metadata.get('confidence', 0)
                    })

        entity_nodes = {}
        topic_nodes = {}
        triple_edges = []
        topic_edges = []

        for triple, metadata in all_triples:
            subject, predicate, obj = triple

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

            triple_edges.append({
                'source': f'entity:{subject}',
                'target': f'entity:{obj}',
                'label': predicate,
                'type': 'triple',
                'confidence': metadata.get('confidence', 0),
                'topics': metadata.get('topics', [])
            })

        for topic, triples in topic_map.items():
            topic_id = f'topic:{topic}'
            topic_nodes[topic] = {
                'id': topic_id,
                'label': topic,
                'type': 'topic',
                'triple_count': len(triples)
            }

            for triple_info in triples:
                triple = triple_info['triple']
                subject, predicate, obj = triple

                topic_edges.append({
                    'source': f'entity:{subject}',
                    'target': topic_id,
                    'label': 'belongs_to_topic',
                    'type': 'topic_link',
                    'confidence': triple_info['confidence']
                })

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


@app.post("/explore/entity")
async def explore_entity(request: QueryRequest):
    """Explore entity connections (REST endpoint for workspace shim)."""
    try:
        if request.text:
            clusters = memory_explorer.cluster_for_query(
                text=request.text,
                n_clusters=5,
                per_cluster=4,
                search_limit=50
            )
            return {"clusters": clusters, "query": request.text}
        else:
            overview_text = memory_explorer.knowledge_tree_text(
                max_topics=10,
                per_topic_samples=4,
                llm_summary=True,
                topic_summary=False
            )
            return {"overview": overview_text}

    except Exception as e:
        logger.error(f"Error in explore entity endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/episodes/search")
async def search_episodes_post(request: QueryRequest):
    """Search episodes by content (REST endpoint for workspace shim)."""
    try:
        episodes = episodic_memory.search_episodes_by_content(
            query_text=request.text, limit=request.limit
        )

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

        return {"episodes": result, "count": len(result), "query": request.text}

    except Exception as e:
        logger.error(f"Error searching episodes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_stats():
    """Get knowledge graph statistics."""
    try:
        all_triples = kgraph.get_all_triples()

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

        topic_counts = Counter()
        for triple in all_triples:
            if 'metadata' in triple and 'topics' in triple['metadata']:
                topic_counts.update(triple['metadata']['topics'])

        result = []
        for topic, count in topic_counts.most_common(top_k):
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

        entity_counts = Counter()
        for triple in all_triples:
            entity_counts[triple['subject']] += 1
            entity_counts[triple['object']] += 1

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


# ============================================================================
# INGEST ENDPOINTS
# ============================================================================

def chunk_text_by_paragraphs(text: str, max_chunk_size: int = 2000) -> list:
    """Split text into chunks by paragraphs, combining small paragraphs."""
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    if not paragraphs:
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]

    if not paragraphs:
        return [text]

    chunks = []
    current_chunk = []
    current_size = 0

    for para in paragraphs:
        para_size = len(para)

        if para_size > max_chunk_size:
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_size = 0

            sentences = re.split(r'([.!?]+\s+)', para)
            sentences = [''.join(sentences[i:i+2]).strip() for i in range(0, len(sentences)-1, 2)]
            if len(sentences) % 2 == 1 and sentences:
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

        if current_size + para_size > max_chunk_size and current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            current_chunk = [para]
            current_size = para_size
        else:
            current_chunk.append(para)
            current_size += para_size

    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))

    return chunks


@app.post("/ingest")
async def ingest_text(request: QueryRequest):
    """Ingest text into semantic memory (REST endpoint for workspace shim)."""
    try:
        result = memory_system.ingest_text(
            text=request.text,
            source="agent_code",
            timestamp=time.time()
        )
        return {"success": True, "result": result}

    except Exception as e:
        logger.error(f"Error in ingest endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/document")
async def ingest_document(request: DocumentIngestRequest):
    """Ingest a document into semantic memory with chunking."""
    try:
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Document text cannot be empty")

        logger.info(f"[INGEST] Document upload: source={request.source}, length={len(request.text)}")

        chunks = chunk_text_by_paragraphs(request.text, max_chunk_size=2000)
        logger.info(f"[INGEST] Split document into {len(chunks)} chunks")

        all_results = []
        total_triples = 0

        for i, chunk in enumerate(chunks):
            logger.info(f"[INGEST] Processing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")

            try:
                result = memory_system.ingest_text(
                    text=chunk,
                    source=f"{request.source}#chunk_{i}",
                    timestamp=time.time()
                )

                chunk_count = len(result.get('triples', []))
                total_triples += chunk_count

                all_results.append(result)
                logger.info(f"[INGEST] Chunk {i+1}: {chunk_count} triples")

            except Exception as e:
                logger.error(f"[INGEST] Error processing chunk {i+1}: {e}")
                continue

        logger.info(f"[INGEST] Successfully ingested document: {total_triples} triples from {len(chunks)} chunks")

        return {
            "success": True,
            "status": "success",
            "message": "Document ingested successfully",
            "source": request.source,
            "text_length": len(request.text),
            "chunk_count": len(chunks),
            "processed_chunks": len(all_results),
            "triple_count": total_triples,
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
    print("Use 'python main.py' to start SophiaAMS.")
    print("All channels (web, telegram, goals) run through the unified event bus.")
    from main import main
    main()
