# SophiaAMS - Associative Memory System with Episodic Memory

An intelligent conversational AI system with dual-memory architecture: semantic knowledge graphs and episodic temporal memory.

## Features

### Dual Memory Architecture
- **Semantic Memory**: Persistent knowledge graph storing facts, relationships, and procedures
- **Episodic Memory**: Temporal conversation history with session isolation and timeline queries
- **Automatic Knowledge Extraction**: Triple-based fact extraction from conversations
- **Procedural Knowledge**: Step-by-step instructions and goal-based retrieval

### LangChain Agent System
- **Tool-Based Architecture**: Extensible agent with memory query, web search, and Python REPL tools
- **Observable Actions**: All tool calls are logged and visible
- **Session Management**: Isolated conversation contexts with cross-session semantic memory sharing
- **Web Interface**: Modern React-based chat UI

### Web Search Integration
- **SearXNG Integration**: Privacy-focused metasearch engine
- **Real-time Information**: Sophia can search the web for current information
- **Automatic Source Attribution**: Results include source URLs and descriptions

## Quick Start

### Prerequisites
- Python 3.12+
- Node.js 18+
- SearXNG instance (optional, for web search)
- Local LLM server (LM Studio, Ollama, etc.)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd SophiaAMS
   ```

2. **Set up Python environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your LLM and SearXNG settings
   ```

4. **Start the system**
   ```bash
   cd sophia-web
   ./start-all.bat  # On Windows
   # Or manually start each component (see below)
   ```

5. **Open the web interface**
   - Navigate to http://localhost:3000
   - Start chatting with Sophia!

## Manual Startup

If you prefer to start components individually:

```bash
# Terminal 1: Start the agent server
python agent_server.py

# Terminal 2: Start the web proxy server
cd sophia-web/server
npm start

# Terminal 3: Start the React client
cd sophia-web/client
npm run dev
```

## Architecture

### Core Components

```
SophiaAMS/
├── agent_server.py              # LangChain agent server (FastAPI)
├── AssociativeSemanticMemory.py # Semantic memory & knowledge graph
├── EpisodicMemory.py            # Temporal conversation memory
├── VectorKnowledgeGraph.py      # Vector-based triple storage (Qdrant)
├── PersistentConversationMemory.py # LangChain memory bridge
└── searxng_tool.py              # Web search tool
```

### Supporting Modules

```
├── prompts.py                   # LLM prompt templates
├── triple_extraction.py         # Knowledge extraction
├── MemoryExplorer.py           # Graph analysis & clustering
├── schemas.py                  # Data models
└── utils.py                    # Helper functions
```

### Web Interface

```
sophia-web/
├── server/                     # Node.js proxy server
│   └── server.js              # WebSocket & HTTP proxy
├── client/                    # React web UI
│   ├── src/
│   │   ├── App.jsx           # Main chat interface
│   │   └── components/       # UI components
│   └── package.json
└── start-all.bat             # Startup script
```

## Configuration

### Environment Variables (.env)

```bash
# LLM Configuration
LLM_API_BASE=http://localhost:1234/v1
LLM_API_KEY=not-needed
MODEL_NAME=your-model-name
EXTRACTION_MODEL=your-extraction-model

# Search Configuration (optional)
SEARXNG_URL=http://localhost:8080

# Memory Configuration
MEMORY_DATA_PATH=./data
VECTOR_DB_PATH=./VectorKnowledgeGraphData
```

### Memory System

The system uses two complementary memory types:

1. **Semantic Memory** (Global)
   - Stores facts as subject-verb-object triples
   - Vector-based similarity search (Qdrant)
   - Persists across all sessions
   - Supports procedural knowledge (steps, goals)

2. **Episodic Memory** (Session-Specific)
   - Stores conversation history with timestamps
   - Session-isolated (each session has separate episodes)
   - Timeline queries and temporal searches
   - Automatic episode creation and summarization

## Agent Tools

Sophia has access to the following tools:

- **store_fact**: Store facts in semantic memory
- **query_memory**: Search semantic memory by topic
- **query_recent_memory**: Get recent memories by timeframe
- **recall_conversation**: Find past conversations by keyword
- **get_timeline**: View conversation activity timeline
- **searxng_search**: Search the web via SearXNG
- **python_repl**: Execute Python code for calculations

## API Endpoints

### Agent Server (Port 5001)

```
POST   /chat/{session_id}           # Send message to agent
GET    /health                       # Health check
DELETE /session/{session_id}         # Clear session
GET    /api/episodes/recent          # Get recent episodes
GET    /api/episodes/{episode_id}    # Get specific episode
GET    /api/episodes/search          # Search episodes
GET    /api/episodes/timeline        # Get activity timeline
GET    /api/episodes/time-range      # Get episodes in time range
```

### Web Server (Port 3001)

```
WebSocket  /                         # Chat WebSocket
GET        /api/health               # Health check
POST       /api/ingest/document      # Upload document (not implemented)
POST       /api/query/procedure      # Query procedural knowledge
```

## Testing

Run the test suite:

```bash
# Episodic memory tests
python tests/test_episodic_memory.py

# Sophia agent tests
python tests/test_sophia_agent.py

# Core memory tests
python tests/test_sophia_core.py

# Web search tests
python tests/test_web_search.py
```

## Project Structure

```
SophiaAMS/
├── README.md                 # This file
├── requirements.txt          # Python dependencies
├── .env                      # Configuration (not in git)
├── .gitignore               # Git ignore patterns
│
├── Core Python Modules
│   ├── agent_server.py
│   ├── AssociativeSemanticMemory.py
│   ├── EpisodicMemory.py
│   ├── VectorKnowledgeGraph.py
│   ├── PersistentConversationMemory.py
│   ├── MemoryExplorer.py
│   ├── prompts.py
│   ├── triple_extraction.py
│   ├── searxng_tool.py
│   ├── schemas.py
│   └── utils.py
│
├── docs/                    # Documentation
│   ├── EPISODIC_MEMORY_IMPLEMENTATION.md
│   ├── AGENT_QUICK_REFERENCE.md
│   ├── AGENT_SERVER_GUIDE.md
│   ├── PROCEDURAL_KNOWLEDGE_GUIDE.md
│   └── ... (other guides)
│
├── tests/                   # Test files
│   ├── test_episodic_memory.py
│   ├── test_sophia_agent.py
│   ├── test_sophia_core.py
│   └── test_web_search.py
│
├── scripts/                 # Utility scripts
│   ├── install.py
│   ├── process_url.py
│   └── run_document_processor.py
│
├── legacy/                  # Deprecated code
│   ├── api_server.py       # Old REST API
│   ├── DocumentProcessor.py
│   └── ... (old modules)
│
├── sophia-web/             # Web interface
│   ├── server/            # Node.js server
│   ├── client/            # React UI
│   └── start-all.bat      # Startup script
│
├── data/                   # Runtime data
│   └── episodic_memory/   # Episode storage
│
├── VectorKnowledgeGraphData/  # Qdrant database
│   └── qdrant_data/
│
└── venv/                   # Python virtual environment
```

## Documentation

Detailed documentation is available in the `docs/` directory:

- [Episodic Memory Implementation](docs/EPISODIC_MEMORY_IMPLEMENTATION.md)
- [Agent Quick Reference](docs/AGENT_QUICK_REFERENCE.md)
- [Agent Server Guide](docs/AGENT_SERVER_GUIDE.md)
- [Procedural Knowledge Guide](docs/PROCEDURAL_KNOWLEDGE_GUIDE.md)

## Development Notes

### Dependencies Removed for Windows Compatibility

The following packages were removed from requirements due to C++ compiler requirements on Windows:

- `scikit-learn` (optional clustering in MemoryExplorer)
- `hdbscan` (optional clustering in MemoryExplorer)
- `spacy` (document processing - feature disabled)

The core functionality works without these packages. They're only needed for optional clustering features.

### LangChain Version

This project uses LangChain 0.3.x for compatibility. The imports are compatible with the classic LangChain API.

## Troubleshooting

### Qdrant Database Locked
If you see "Storage folder already accessed":
```bash
# Kill all Python processes
taskkill /F /IM python.exe

# Delete the lock file
del /F VectorKnowledgeGraphData\qdrant_data\.lock

# Restart the agent server
```

### Missing FastAPI/Dependencies
Make sure you're using the venv Python:
```bash
# Activate venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### Web Interface Not Loading
Check that all services are running:
- Agent Server: http://localhost:5001/health
- Web Server: http://localhost:3001/api/health
- React Client: http://localhost:3000

## License

See [LICENSE](LICENSE) file for details.

## Contributing

This is a research project. Contributions, suggestions, and feedback are welcome!

## Acknowledgments

- Built with LangChain, FastAPI, React, and Qdrant
- Uses SearXNG for privacy-focused web search
- Designed for local LLM deployment (LM Studio, Ollama, etc.)
