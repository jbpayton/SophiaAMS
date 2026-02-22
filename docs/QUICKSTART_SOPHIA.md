# Sophia Agent - Quick Start Guide

Get Sophia up and running in 5 minutes!

## Prerequisites

- Python 3.8+
- SearXNG instance (optional, for web search)
- LLM server running (e.g., LM Studio at http://192.168.2.94:1234)
- Qdrant or Milvus for vector storage

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 2: Configure Environment

Verify your `.env` file has these settings:

```bash
# LLM Configuration
LLM_API_BASE=http://192.168.2.94:1234/v1
LLM_API_KEY=not-needed
EXTRACTION_MODEL=zai-org/glm-4.7-flash

# Web Tools
SEARXNG_URL=http://192.168.2.94:8088

# Agent Settings
AGENT_PORT=5001
AGENT_TEMPERATURE=0.7
```

## Step 3: Start Sophia

### Option A: Start Just the Agent
```bash
python agent_server.py
```

### Option B: Start All Services (Recommended)
```bash
start_agent_system.bat
```

This starts:
- FastAPI Server (port 5000)
- Agent Server (port 5001)
- Node.js Server (port 3001)

## Step 4: Verify Sophia is Running

Open a new terminal:

```bash
curl http://localhost:5001/health
```

Expected response:
```json
{
  "status": "healthy",
  "active_sessions": 0,
  "memory_loaded": true
}
```

## Step 5: Test Sophia

### Quick Test (Recommended)
```bash
python test_sophia_quick.py
```

This runs basic tests and offers interactive chat mode.

### Comprehensive Test
```bash
python test_sophia_agent.py
```

This tests all capabilities thoroughly.

## Step 6: Start Chatting!

### Using Python
```python
import requests

response = requests.post(
    "http://localhost:5001/chat/my_session",
    json={"content": "Hi Sophia!"}
)

print(response.json()["response"])
```

### Using curl
```bash
curl -X POST http://localhost:5001/chat/my_session \
  -H "Content-Type: application/json" \
  -d '{"content": "Hi Sophia!"}'
```

### Interactive Mode
```bash
python test_sophia_quick.py
# Choose 'y' when prompted for interactive mode
```

## Example First Conversation

```
You: Hi Sophia!
Sophia: Hey! How can I help you today?

You: What can you do?
Sophia: I can search the web, read pages, remember things you teach me,
        and help with research. Want to try something?

You: Search for Python tutorials
Sophia: [Searches web] Found several great Python tutorials. Want me to
        read one for you?

You: Yes, read the top result
Sophia: [Reads page] This tutorial covers basics: variables, functions,
        and data structures. Pretty comprehensive.

You: Remember that I'm learning Python
Sophia: Got it. Noted that you're learning Python.

You: What am I learning?
Sophia: Python! Want help finding more resources?
```

## Troubleshooting

### "Could not connect to agent server"
- Make sure you ran `python agent_server.py`
- Check that port 5001 is not in use
- Verify firewall isn't blocking the port

### "Web search fails"
- SearXNG must be running at configured URL
- Test: `curl http://192.168.2.94:8088/search?q=test&format=json`
- Update `SEARXNG_URL` in `.env` if needed

### "LLM errors"
- Ensure your LLM server is running
- Verify `LLM_API_BASE` URL is correct
- Check that the model name matches your LLM server

### "Memory/vector database errors"
- Ensure Qdrant/Milvus is installed and running
- Check `data/memory` directory exists
- Clear and rebuild: delete `data/memory` and restart

## Next Steps

1. **Read the Guide**: [SOPHIA_AGENT_GUIDE.md](SOPHIA_AGENT_GUIDE.md)
2. **Learn Architecture**: [SOPHIA_IMPLEMENTATION_SUMMARY.md](SOPHIA_IMPLEMENTATION_SUMMARY.md)
3. **Teach Sophia**: Share information and watch her learn
4. **Explore Tools**: Try web search, page reading, document ingestion
5. **Build Workflows**: Create research assistants, learning companions, etc.

## Quick Reference: Sophia's Tools

| Tool | Purpose | Speed | Example |
|------|---------|-------|---------|
| **query_memory** | Recall facts | Fast | "What do you know about X?" |
| **query_procedure** | Recall how-to | Fast | "How do I deploy Flask?" |
| **store_fact** | Remember new info | Fast | "Remember I prefer Docker" |
| **searxng_search** | Find on web | Medium | "Search for Python news" |
| **read_web_page** | Skim page | Medium | "Read this: [URL]" |
| **ingest_web_document** | Deep learn | Slow | "Study this tutorial: [URL]" |
| **python_repl** | Complex analysis | Varies | "Analyze my memory stats" |

## Tips for Best Results

1. **Be conversational** - Sophia understands natural language
2. **Guide her learning** - Tell her what's important to remember
3. **Use her memory** - She remembers past conversations
4. **Leverage the web** - She can search and learn from the internet
5. **Trust her judgment** - She'll pick the right tool for the job

## Example Workflows

### Research Assistant
```
"Search for information about vector databases"
"Read the top result"
"This is important, remember it"
"What did you learn?"
```

### Learning Companion
```
"I'm learning FastAPI. Find a tutorial."
"Study the official docs for me"
"How do I create a route?"
```

### Knowledge Manager
```
"Remember my favorite color is blue"
"What do you know about my preferences?"
"Search for blue-themed wallpapers"
```

---

**You're all set! Start chatting with Sophia and watch her learn and grow!** 🎉

For detailed information, see:
- **User Guide**: [SOPHIA_AGENT_GUIDE.md](SOPHIA_AGENT_GUIDE.md)
- **Implementation Details**: [SOPHIA_IMPLEMENTATION_SUMMARY.md](SOPHIA_IMPLEMENTATION_SUMMARY.md)
