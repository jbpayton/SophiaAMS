# Agent Quick Reference

## What the Agent Can Do

### 🔍 **Query Memory** (Explicit Tool)
**Trigger phrases**:
- "What do you know about X?"
- "Tell me about Y"
- "Do you remember anything about Z?"

**How it works**: Agent calls `query_memory(query="X")` to search semantic memory.

**Example**:
```
User: "What do you know about Docker?"
Agent: [calls query_memory("Docker", limit=10)]
Agent: "Based on my memory, Docker is a containerization platform..."
```

---

### 📋 **Query Procedures** (Explicit Tool)
**Trigger phrases**:
- "How do I do X?"
- "Show me how to Y"
- "What's the process for Z?"
- "I need to implement A"

**How it works**: Agent calls `query_procedure(goal="X")` to retrieve learned methods.

**Example**:
```
User: "How do I send a POST request in Python?"
Agent: [calls query_procedure("send POST request Python")]
Agent: "Here's how to send a POST request:
       1. Import requests library
       2. Use requests.post(url, json=data)
       ..."
```

---

### 💾 **Store Facts** (Explicit Tool)
**Trigger phrases**:
- "Remember that I prefer X"
- "I like Y"
- "My favorite Z is A"
- "Don't forget B"

**How it works**: Agent calls `store_fact(subject, verb, obj, topics)` to save information.

**Example**:
```
User: "Remember that I prefer Docker for deployments"
Agent: [calls store_fact("user", "prefers", "Docker", "preferences,deployment")]
Agent: "Got it! I'll remember you prefer Docker for deployments."
```

---

### 🐍 **Python Code Execution** (Dynamic Tool)
**Trigger phrases**:
- "Analyze my memory"
- "Count how many X I have"
- "Compare A and B"
- "Find all triples about Y"
- "What's the most common Z?"

**How it works**: Agent writes and executes Python code with direct `memory_system` access.

**Example**:
```
User: "What are my most common procedural topics?"
Agent: [uses python_repl]
Agent writes:
  from collections import Counter
  triples = memory_system.get_all_triples()
  procedural = [t for t in triples if 'procedure' in t.get('topics', [])]
  topics = Counter()
  for proc in procedural:
      topics.update(proc.get('topics', []))
  topics.most_common(10)

Agent: "Your most common procedural topics are:
       1. deployment (15 triples)
       2. testing (12 triples)
       3. API requests (8 triples)
       ..."
```

---

## Hybrid Workflows

### Example 1: Query + Analysis
```
User: "Find all deployment methods and rank them by popularity"

Agent:
1. [calls query_procedure("deployment")]
2. [uses python_repl to count and rank methods]
3. Returns: "Based on your knowledge, here are deployment methods ranked..."
```

### Example 2: Multi-Procedure Lookup
```
User: "Compare Python vs Node.js deployment processes"

Agent:
1. [calls query_procedure("deploy Python application")]
2. [calls query_procedure("deploy Node.js application")]
3. [uses python_repl to compare results]
4. Returns: "Python deployments typically use... while Node.js uses..."
```

### Example 3: Store + Retrieve
```
User: "Remember I use AWS for cloud hosting"
Agent: [calls store_fact(...)]

(Later in conversation)

User: "How should I deploy my app?"
Agent: [calls query_procedure("deploy application")]
Agent: [calls query_memory("cloud hosting")]
Agent: "Since you use AWS for cloud hosting, here's how to deploy on AWS..."
```

---

## Tool Selection Logic

The agent **automatically decides** which tool to use based on your question:

| Your Question Type | Tool Used | Why |
|-------------------|-----------|-----|
| "What is X?" | `query_memory` | Factual recall |
| "How do I Y?" | `query_procedure` | Procedural lookup |
| "Remember Z" | `store_fact` | Storing new info |
| "Analyze A" | `python_repl` | Complex operation |
| "Compare B and C" | Multiple tools | Hybrid workflow |

---

## Conversation Memory

The agent **remembers within a session**:

```
User: "My name is Alice"
Agent: "Nice to meet you, Alice!"

(Later in same session)

User: "What's my name?"
Agent: "Your name is Alice."
```

**Note**: This is short-term conversation memory (per session), separate from long-term semantic memory (facts/procedures stored permanently).

---

## Special Capabilities

### 1. Dynamic Filtering
```
User: "Show me only high-level deployment procedures"
Agent: [python_repl]
  procedures = memory_system.query_procedure("deployment", limit=50)
  high_level = [p for p in procedures['methods'] if p.get('abstraction_level') == 3]
```

### 2. Cross-Domain Queries
```
User: "What connects Python and Docker in my knowledge?"
Agent: [python_repl with graph traversal logic]
```

### 3. Statistical Analysis
```
User: "What percentage of my knowledge is procedural vs factual?"
Agent: [python_repl with Counter and calculations]
```

### 4. Code Generation from Procedures
```
User: "Generate a Python script to deploy using the method I taught you"
Agent: [query_procedure → extract examples → format as script]
```

---

## Best Practices

### ✅ DO:
- Ask specific questions: "How do I send POST requests?" (not "Tell me about HTTP")
- Use action verbs for procedures: "deploy", "build", "test", "configure"
- Teach step-by-step: "First do A, then do B, finally do C"
- Request analysis: "Compare", "Analyze", "Count", "Find patterns"

### ❌ DON'T:
- Ask vague questions: "Tell me everything about X"
- Expect knowledge you didn't teach: Agent only knows what's in memory
- Forget session context: Agent remembers within session, not across sessions
- Mix unrelated questions: One topic per message works best

---

## Quick Start Examples

### Example 1: Teaching a Procedure
```
User: "To deploy a Flask app, you need to:
      1. Set up a virtual environment
      2. Install dependencies with pip install -r requirements.txt
      3. Run flask run --host=0.0.0.0
      Alternatively, you can use gunicorn for production."

Agent: [Automatically extracts and stores procedural knowledge]
```

### Example 2: Retrieving a Procedure
```
User: "How do I deploy a Flask app?"
Agent: [Retrieves the procedure you taught]
Agent: "Here's how to deploy a Flask app:
       1. Set up virtual environment
       2. Install dependencies
       3. Run flask run
       Alternative: Use gunicorn for production"
```

### Example 3: Complex Analysis
```
User: "What have I taught you about Python?"
Agent: [Combines query_memory + python_repl]
Agent: "You've taught me about:
       - Deployment (3 procedures)
       - HTTP requests (2 procedures)
       - Testing (1 procedure)
       Total: 23 triples related to Python"
```

---

## Debugging Tool Calls

If agent isn't using tools as expected:

1. **Check logs** in agent_server.py terminal:
   ```
   [TOOL] query_memory called: query='Docker', limit=10
   ```

2. **Be more explicit**:
   - Instead of: "Tell me about X"
   - Try: "What do you know about X?" (triggers query_memory)

3. **Check model supports function calling**:
   - ✅ gpt-4, gpt-4-turbo-preview
   - ✅ gpt-3.5-turbo
   - ❌ gpt-3.5-turbo-instruct (no function calling)

---

## Environment Variables

Key settings in `.env`:

```bash
# Model selection
OPENAI_MODEL=gpt-4-turbo-preview  # Use GPT-4 for best tool usage

# Temperature (creativity)
AGENT_TEMPERATURE=0.7  # Lower = more focused, Higher = more creative

# Memory location
MEMORY_DIR=./data/memory
```

---

## Endpoints

### HTTP Chat (for testing)
```bash
curl -X POST http://localhost:5001/chat/SESSION_ID \
  -H "Content-Type: application/json" \
  -d '{"content": "Your message here"}'
```

### WebSocket Chat (for real-time)
```javascript
const ws = new WebSocket('ws://localhost:5001/ws/chat/SESSION_ID');
ws.send(JSON.stringify({ content: "Your message here" }));
```

### Health Check
```bash
curl http://localhost:5001/health
```

### Clear Session
```bash
curl -X DELETE http://localhost:5001/session/SESSION_ID
```
