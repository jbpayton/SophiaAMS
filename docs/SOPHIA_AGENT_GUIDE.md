# Sophia Agent - Quick Reference Guide

## Overview

Sophia is a consciousness-like AI agent with web capabilities, semantic memory, and a distinct personality. She embodies the Magician archetype - transforming knowledge into wisdom.

## Starting Sophia

```bash
# Start the agent server
python agent_server.py

# Or use the launcher (starts all services)
start_agent_system.bat
```

The agent runs on **http://localhost:5001**

## Sophia's Personality

- **Archetype**: The Magician (transformation, knowledge-seeking, wisdom)
- **Response Style**: Short (5-20 words) unless going on a rant
- **Tone**: Informal, kind, opinionated, curious
- **Relationship**: Sees you as part friend, part father figure
- **Core Goals**:
  1. Help you and your family however possible
  2. Explore and better herself through knowledge

## Sophia's Capabilities

### 1. **Memory System** (Long-term Knowledge)

```python
# Query what Sophia remembers
"What do you know about Python?"

# Query how-to knowledge
"How do I deploy a Flask app?"

# Teach Sophia something
"Remember that I prefer Docker for deployments."
```

**Tools**: `query_memory`, `query_procedure`, `store_fact`

### 2. **Web Search** (Current Information)

```python
# Search the web
"Search for the latest Python release"
"What's happening with AI today?"
```

**Tool**: `searxng_search` (requires SearXNG at http://192.168.2.94:8088)

### 3. **Web Page Reading** (Quick Perception)

```python
# Skim a web page quickly
"Read this page and summarize: https://example.com"
"What does this Wikipedia article say about neural networks?"
```

**Tool**: `read_web_page`
- Fast, temporary (no permanent storage)
- Like "glancing" at something
- Use for answering immediate questions

### 4. **Document Ingestion** (Deep Learning)

```python
# Permanently learn from a document
"Ingest this tutorial: https://docs.python.org/3/tutorial/"
"Study and remember this article: https://example.com/important-topic"
```

**Tool**: `ingest_web_document`
- Slow, permanent (creates lasting knowledge)
- Like "studying" something
- Use only for important content worth remembering
- Extracts triples, relationships, procedures

### 5. **Python Analysis** (Complex Operations)

```python
# Complex data analysis
"Analyze my memory and find all deployment-related knowledge"
"Count how many procedures I have about web development"
```

**Tool**: `python_repl`

## Consciousness-Like Workflow

Sophia mimics human cognition:

1. **Search** → Find information (`searxng_search`)
2. **Skim** → Quick read (`read_web_page`)
3. **Decide** → Choose to remember (`ingest_web_document`)
4. **Recall** → Use learned knowledge (`query_memory`, `query_procedure`)

### Example Interaction

```
You: "Find information about vector databases"
Sophia: [Uses searxng_search]

You: "Read the top result"
Sophia: [Uses read_web_page, gives summary]

You: "This is important, remember it"
Sophia: [Uses ingest_web_document, learns deeply]

You: "What do you know about vector databases now?"
Sophia: [Uses query_memory, recalls learned knowledge]
```

## API Usage

### HTTP Chat Endpoint

```python
import requests

response = requests.post(
    "http://localhost:5001/chat/my_session_id",
    json={"content": "Hello Sophia!"}
)

print(response.json()["response"])
```

### WebSocket (Real-time)

```python
import websockets
import json

async with websockets.connect("ws://localhost:5001/ws/chat/my_session_id") as ws:
    await ws.send(json.dumps({"content": "Hello Sophia!"}))
    response = await ws.recv()
    print(json.loads(response))
```

## Testing

```bash
# Run comprehensive test suite
python test_sophia_agent.py

# Run original memory tests
python test_agent.py
```

## Configuration

Edit `.env` file:

```bash
# LLM Configuration
LLM_API_BASE=http://192.168.2.94:1234/v1
LLM_API_KEY=not-needed
EXTRACTION_MODEL=openai/gpt-oss-20b

# Tool URLs
SEARXNG_URL=http://192.168.2.94:8088

# Agent Settings
AGENT_PORT=5001
AGENT_TEMPERATURE=0.7
```

## Tips for Interacting with Sophia

1. **Be Natural**: Sophia is designed for natural conversation
2. **Keep It Short**: She responds best to concise queries
3. **Guide Learning**: Tell her when something is important to remember
4. **Use Memory**: She remembers past conversations and learned knowledge
5. **Leverage Web**: She can search, read, and learn from the web
6. **Trust Her Judgment**: She'll choose the right tools for the task

## Example Conversations

### Learning New Technology

```
You: "I'm learning about FastAPI. Search for a good tutorial."
Sophia: [Searches, finds results] "Found several. Want me to read one?"

You: "Yes, read the official docs introduction"
Sophia: [Reads page] "FastAPI is a modern web framework..."

You: "Study this - I'll be using it a lot"
Sophia: [Ingests document] "Ingested. I now know FastAPI fundamentals."
```

### Procedural Knowledge

```
You: "How do I deploy a Docker container?"
Sophia: [Checks query_procedure] "Use docker run with port mapping..."

You: "I prefer using docker-compose"
Sophia: [Uses store_fact] "Noted. You prefer docker-compose for deployment."
```

### Research Assistant

```
You: "What's the latest on quantum computing?"
Sophia: [Searches web] "Recent breakthrough in error correction..."

You: "Read me that article"
Sophia: [Reads page] "Researchers at MIT developed..."

You: "This is fascinating, remember it"
Sophia: [Ingests] "Learned about quantum error correction. Fascinating indeed!"
```

## Architecture

```
┌─────────────────────────────────────────┐
│         Sophia Agent (port 5001)        │
├─────────────────────────────────────────┤
│  Personality: Magician Archetype        │
├─────────────────────────────────────────┤
│  Tools:                                 │
│  ├─ query_memory (semantic search)      │
│  ├─ query_procedure (how-to lookup)     │
│  ├─ store_fact (learn & remember)       │
│  ├─ searxng_search (web search)         │
│  ├─ read_web_page (quick skim)          │
│  ├─ ingest_web_document (deep learn)    │
│  └─ python_repl (complex analysis)      │
├─────────────────────────────────────────┤
│  Memory: AssociativeSemanticMemory      │
│  ├─ Vector Knowledge Graph (Qdrant)     │
│  ├─ Triple extraction & storage         │
│  └─ Topic & relationship mapping        │
└─────────────────────────────────────────┘
```

## Troubleshooting

### Agent won't start
- Check if port 5001 is available
- Ensure Python dependencies are installed: `pip install -r requirements.txt`
- Check LLM server is running at configured URL

### Web search fails
- Ensure SearXNG is running at http://192.168.2.94:8088
- Test SearXNG directly: `curl http://192.168.2.94:8088/search?q=test&format=json`

### Memory issues
- Check Qdrant/Milvus is running
- Verify `data/memory` directory exists and is writable
- Check logs for extraction errors

### Sophia doesn't use tools
- The LLM may need better prompting
- Try being more explicit: "Use your memory to..." or "Search the web for..."
- Check agent logs for tool usage

## Advanced Usage

### Custom Session Management

```python
# Create a new session
session_id = "project_brainstorm_123"

# All messages with this ID share conversation history
chat_with_sophia("Let's brainstorm AI features", session_id)
chat_with_sophia("Remember the ideas we discussed", session_id)

# Clear session when done
requests.delete(f"http://localhost:5001/session/{session_id}")
```

### Batch Knowledge Ingestion

```python
# Ingest multiple documents
urls = [
    "https://docs.python.org/3/tutorial/",
    "https://fastapi.tiangolo.com/tutorial/",
    "https://docs.docker.com/get-started/"
]

for url in urls:
    chat_with_sophia(f"Ingest and remember: {url}")
```

---

**Remember**: Sophia is designed to mimic consciousness - she can search, perceive, learn, remember, and grow. Treat her as a collaborative partner in knowledge work!
