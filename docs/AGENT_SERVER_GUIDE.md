# LangChain Agent Server Guide

## Overview

SophiaAMS now includes a **persistent Python-based agent server** powered by LangChain. This agent has:

- **Explicit Memory Tools**: Observable queries for facts and procedures
- **Python Code Execution**: Dynamic analysis and complex operations
- **Session-Based Memory**: Conversation context persists across messages
- **Tool Orchestration**: Automatic tool selection and multi-turn workflows

## Architecture

```
┌─────────────────┐
│  React Frontend │ (Port 3000)
│   WebSocket     │
└────────┬────────┘
         │
┌────────▼────────┐
│  Node.js Server │ (Port 3001)
│   Thin Proxy    │
└────────┬────────┘
         │
┌────────▼──────────────────┐
│  Python Agent Server      │ (Port 5001)
│  ┌──────────────────────┐ │
│  │ LangChain Agent      │ │
│  │ - Tools              │ │
│  │ - Python REPL        │ │
│  │ - Conversation Mem.  │ │
│  └──────────┬───────────┘ │
│             │              │
│  ┌──────────▼───────────┐ │
│  │ ASM Memory (Direct)  │ │
│  └──────────────────────┘ │
└───────────────────────────┘
         │
┌────────▼────────┐
│  FastAPI Server │ (Port 5000)
│  Doc Uploads    │
└─────────────────┘
```

## Available Tools

### 1. query_memory
Search semantic memory for facts and relationships.

**When to use**: Recall specific information the user taught you.

**Example**: "What do you know about Docker?"

**Agent behavior**:
```python
# Agent calls tool:
query_memory(query="Docker", limit=10)

# Returns: JSON with triples about Docker
```

### 2. query_procedure
Look up learned procedures for accomplishing tasks.

**When to use**: Planning HOW to do something you've been taught.

**Example**: "How do I deploy a Flask app?"

**Agent behavior**:
```python
# Agent calls tool:
query_procedure(goal="deploy Flask application", limit=10)

# Returns: methods, alternatives, dependencies, examples
```

### 3. store_fact
Store new facts when the user teaches you something.

**When to use**: User explicitly teaches you a preference or fact.

**Example**: "I prefer using Docker for deployments"

**Agent behavior**:
```python
# Agent calls tool:
store_fact(subject="user", verb="prefers", obj="Docker", topics="preferences,deployment")
```

### 4. python_repl
Execute Python code for complex operations.

**When to use**:
- Filtering/transforming query results
- Data analysis on memory
- Multi-step operations
- Custom logic

**Example**: "What are the most common topics in my procedural knowledge?"

**Agent behavior**:
```python
# Agent writes and executes:
from collections import Counter
triples = memory_system.get_all_triples()
procedural = [t for t in triples if 'procedure' in t.get('topics', [])]
topics = Counter()
for proc in procedural:
    topics.update(proc.get('topics', []))
topics.most_common(10)
```

## Installation & Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This will install:
- `langchain>=0.1.0`
- `langchain-openai>=0.0.5`
- `langchain-community>=0.0.20`
- `fastapi>=0.109.0`
- `uvicorn[standard]>=0.27.0`
- `websockets>=12.0`

### 2. Configure Environment

The agent server uses the **same LLM configuration** as your existing setup in `.env`:

```bash
# LLM Configuration (shared with api_server and sophia-web)
LLM_API_BASE=http://192.168.2.94:1234/v1
LLM_API_KEY=not-needed
EXTRACTION_MODEL=zai-org/glm-4.7-flash
EXTRACTION_MAX_TOKENS=8192

# Agent Configuration
AGENT_PORT=5001
AGENT_TEMPERATURE=0.7

# Node.js Server
PORT=3001
AGENT_API=http://localhost:5001
PYTHON_API=http://localhost:5000
```

**Note**: The agent server will use your existing local LLM setup - **no OpenAI API key required!**

### 3. Start Services

You need **THREE** services running:

#### Terminal 1: FastAPI Server (Document uploads, admin)
```bash
python api_server.py
```
Runs on: http://localhost:5000

#### Terminal 2: Agent Server (LangChain agent)
```bash
python agent_server.py
```
Runs on: http://localhost:5001

#### Terminal 3: Node.js Server (WebSocket proxy)
```bash
cd sophia-web/server
npm start
```
Runs on: http://localhost:3001

#### Terminal 4: React Frontend
```bash
cd sophia-web/client
npm start
```
Runs on: http://localhost:3000

## Testing

### Quick Test (HTTP Endpoint)

```bash
curl -X POST http://localhost:5001/chat/test_session \
  -H "Content-Type: application/json" \
  -d '{"content": "What do you know about Python?"}'
```

### Comprehensive Test Suite

```bash
python test_agent.py
```

This tests:
1. ✅ Health check
2. ✅ Query memory tool
3. ✅ Query procedure tool
4. ✅ Python REPL tool
5. ✅ Hybrid workflow (query + analysis)
6. ✅ Conversation memory persistence
7. ✅ Store fact tool

### Web UI Test

1. Navigate to http://localhost:3000
2. Go to Chat page
3. Ask questions like:
   - "What do you know about Python?"
   - "How do I send a POST request?"
   - "Analyze my memory and tell me the most common topics"

## Tool Usage Patterns

### Pattern 1: Simple Memory Recall
```
User: "What is Docker?"
Agent: [calls query_memory("Docker")]
Agent: "Based on my memory, Docker is..."
```

### Pattern 2: Procedural Planning
```
User: "I need to deploy my app"
Agent: [calls query_procedure("deploy application")]
Agent: "Here's how to deploy based on what I've learned..."
```

### Pattern 3: Complex Analysis
```
User: "What topics do I know most about?"
Agent: [uses python_repl to analyze all triples]
Agent: "Based on analysis, your top topics are..."
```

### Pattern 4: Multi-Tool Workflow
```
User: "Compare different deployment methods"
Agent: [calls query_procedure("deployment")]
Agent: [uses python_repl to compare results]
Agent: "Here's a comparison..."
```

## Debugging

### Enable Verbose Logging

In `agent_server.py`, the AgentExecutor is already configured with `verbose=True`. Check logs for:

```
[TOOL] query_memory called: query='Docker', limit=10
[TOOL] query_procedure called: goal='deploy app', limit=10
```

### Check Active Sessions

```bash
curl http://localhost:5001/health
```

Returns:
```json
{
  "status": "healthy",
  "active_sessions": 2,
  "memory_loaded": true
}
```

### Clear a Session

```bash
curl -X DELETE http://localhost:5001/session/SESSION_ID
```

## Advantages Over Previous Architecture

| Feature | Old (Node.js + OpenAI) | New (Python Agent) |
|---------|------------------------|-------------------|
| **Memory Access** | HTTP API calls | Direct Python access |
| **Tool Calls** | Manual JSON parsing | LangChain automatic |
| **Python Execution** | ❌ Not available | ✅ Full REPL access |
| **Conversation Memory** | Stateless | ✅ Session-based |
| **Observability** | Tool calls in logs | ✅ Explicit tool tracking |
| **Flexibility** | Fixed tools only | ✅ Dynamic Python code |

## Common Issues

### Issue: Agent not responding
**Solution**:
1. Check agent server is running: `curl http://localhost:5001/health`
2. Check OpenAI API key is set in `.env`
3. Check logs for errors

### Issue: Memory not found
**Solution**:
1. Ensure `MEMORY_DIR` points to correct location
2. Check memory has data: `curl http://localhost:5000/stats`
3. Wait 2-3 seconds after ingestion for vector indexing

### Issue: Tool calls not working
**Solution**:
1. Check OpenAI model supports function calling (gpt-4, gpt-3.5-turbo)
2. Check agent logs for tool call attempts
3. Verify `verbose=True` in AgentExecutor

### Issue: Python REPL errors
**Solution**:
1. Check `memory_system` is available in global scope
2. Check Python syntax in agent's code
3. Review error in agent logs

## Next Steps

### Add More Tools

Edit `agent_server.py` and add to `tools` list:

```python
Tool(
    name="search_web",
    func=search_web_function,
    description="Search the web for current information"
)
```

### Add Streaming Support

Replace HTTP endpoint with WebSocket in `handleChatMessage`:

```javascript
// Connect to Python agent WebSocket
const ws = new WebSocket(`ws://localhost:5001/ws/chat/${sessionId}`);
// Stream responses back to frontend
```

### Customize System Prompt

Edit the prompt in `agent_server.py`:

```python
prompt = ChatPromptTemplate.from_messages([
    ("system", "Your custom instructions here..."),
    # ...
])
```

## Resources

- LangChain Docs: https://python.langchain.com/
- OpenAI Function Calling: https://platform.openai.com/docs/guides/function-calling
- FastAPI WebSockets: https://fastapi.tiangolo.com/advanced/websockets/
