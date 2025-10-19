# SophiaAMS Project Structure

This document describes the organized project structure after cleanup.

## Directory Structure

```
SophiaAMS/
├── README.md                 # Main project documentation
├── LICENSE                   # License file
├── .env                      # Environment configuration (not in git)
├── .gitignore               # Git ignore patterns
├── requirements.txt          # Python dependencies
├── requirements_api.txt      # Legacy API requirements
├── setup.py                  # Package setup
│
├── Core Python Modules (Root Level)
│   ├── agent_server.py                    # Main LangChain agent server (FastAPI)
│   ├── AssociativeSemanticMemory.py      # Semantic memory & knowledge graph
│   ├── EpisodicMemory.py                 # Temporal conversation memory
│   ├── VectorKnowledgeGraph.py           # Vector-based triple storage (Qdrant)
│   ├── PersistentConversationMemory.py   # LangChain memory bridge
│   ├── MemoryExplorer.py                 # Graph analysis & clustering
│   ├── prompts.py                        # LLM prompt templates
│   ├── triple_extraction.py              # Knowledge extraction logic
│   ├── searxng_tool.py                   # Web search tool
│   ├── schemas.py                        # Data models & schemas
│   └── utils.py                          # Helper functions
│
├── docs/                                  # Documentation
│   ├── PROJECT_STRUCTURE.md              # This file
│   ├── EPISODIC_MEMORY_IMPLEMENTATION.md # Episodic memory guide
│   ├── AGENT_QUICK_REFERENCE.md          # Agent tools reference
│   ├── AGENT_SERVER_GUIDE.md             # Agent server architecture
│   ├── PROCEDURAL_KNOWLEDGE_GUIDE.md     # Procedural knowledge docs
│   ├── IMPLEMENTATION_SUMMARY.md         # Implementation summary
│   ├── BACKWARD_COMPATIBILITY_RESULTS.md # Compatibility testing
│   ├── PROMPT_OVERLAP_ANALYSIS.md        # Prompt analysis
│   ├── DEVELOPMENT_NOTES.md              # Development notes
│   ├── API_README.md                     # Legacy API docs
│   ├── QUICKSTART_SOPHIA.md              # Quick start guide
│   ├── WEB_APP_PROCEDURAL_TESTING_GUIDE.md # Web testing guide
│   └── TEST_RESULTS*.md                  # Test results
│
├── tests/                                 # Test files
│   ├── test_episodic_memory.py           # Episodic memory tests
│   ├── test_sophia_agent.py              # Agent system tests
│   ├── test_sophia_core.py               # Core memory tests
│   ├── test_sophia_quick.py              # Quick smoke tests
│   ├── test_web_search.py                # Web search tests
│   ├── test_web_search_simple.py         # Simple search tests
│   ├── test_procedural_unit.py           # Procedural knowledge tests
│   ├── Test_ProceduralQuery/             # Procedural test data
│   ├── test_query.json                   # Test query data
│   └── test_request.json                 # Test request data
│
├── scripts/                               # Utility scripts
│   ├── install.py                        # Installation script
│   ├── process_url.py                    # URL processing tool
│   └── run_document_processor.py         # Document processor runner
│
├── legacy/                                # Deprecated/old code
│   ├── api_server.py                     # Old REST API server
│   ├── ChatMemoryInterface.py            # Old memory interface
│   ├── ContextSummarizers.py             # Old summarizers
│   ├── ConversationProcessor.py          # Old conversation processor
│   ├── DocumentProcessor.py              # Old document processor
│   ├── WikiGraph/                        # Old wiki graph feature
│   └── test-output/                      # Old test output
│
├── sophia-web/                            # Web interface
│   ├── server/                           # Node.js proxy server
│   │   ├── server.js                    # Main server file
│   │   └── package.json                 # Node dependencies
│   ├── client/                          # React web UI
│   │   ├── src/
│   │   │   ├── App.jsx                 # Main chat interface
│   │   │   ├── components/             # UI components
│   │   │   └── ...
│   │   ├── public/                     # Static assets
│   │   └── package.json                # React dependencies
│   └── start-all.bat                   # Windows startup script
│
├── data/                                  # Runtime data (gitignored)
│   └── episodic_memory/                  # Episode storage (TinyDB)
│       └── *.json                        # Episode files
│
├── VectorKnowledgeGraphData/             # Vector database (gitignored)
│   └── qdrant_data/                      # Qdrant storage
│       ├── collection/
│       └── meta.json
│
└── venv/                                  # Python virtual environment (gitignored)
    ├── Scripts/
    └── Lib/
```

## File Organization Principles

### Root Level
Only essential files are kept in the root:
- Core Python modules (the "production" code)
- Configuration files (.env, requirements.txt, etc.)
- README.md and LICENSE

### Organized Subdirectories

1. **docs/** - All documentation
   - Guides, references, and implementation notes
   - Test results and analysis documents
   - Keep root README focused on getting started

2. **tests/** - All test files
   - Unit tests, integration tests
   - Test data and fixtures
   - Separated from production code

3. **scripts/** - Utility and setup scripts
   - Installation and migration scripts
   - Data processing tools
   - One-off utilities

4. **legacy/** - Deprecated code
   - Old API server and processors
   - Superseded implementations
   - Kept for reference, not active development

5. **sophia-web/** - Complete web interface
   - Self-contained web app
   - Has its own structure (server/client)
   - Includes startup scripts

## Core Modules Overview

### Memory System
- **AssociativeSemanticMemory.py** - High-level memory interface
- **VectorKnowledgeGraph.py** - Low-level triple storage with Qdrant
- **EpisodicMemory.py** - Temporal conversation history
- **PersistentConversationMemory.py** - LangChain integration bridge

### Agent System
- **agent_server.py** - FastAPI server with LangChain agent
- **searxng_tool.py** - Web search tool
- **prompts.py** - Prompt templates for all operations
- **triple_extraction.py** - Knowledge extraction from text

### Analysis & Utilities
- **MemoryExplorer.py** - Graph analysis and topic clustering
- **schemas.py** - Pydantic models and data schemas
- **utils.py** - Common helper functions

## Running the System

### Quick Start
```bash
cd sophia-web
./start-all.bat  # Starts everything
```

### Manual Start
```bash
# Terminal 1: Agent server
python agent_server.py

# Terminal 2: Web server
cd sophia-web/server && npm start

# Terminal 3: React client
cd sophia-web/client && npm run dev
```

### Running Tests
```bash
# All tests
python -m pytest tests/

# Specific test
python tests/test_episodic_memory.py
```

## Data Storage

### Episodic Memory
- Location: `data/episodic_memory/`
- Format: TinyDB JSON files
- One file per episode
- Includes messages, timestamps, and metadata

### Semantic Memory
- Location: `VectorKnowledgeGraphData/qdrant_data/`
- Format: Qdrant vector database
- Stores knowledge triples with embeddings
- Persistent across sessions

### Configuration
- Location: `.env` (root)
- Contains LLM API settings, search config, etc.
- Not tracked in git (use `.env.example` as template)

## Development Workflow

### Adding New Features
1. Core logic goes in root-level Python modules
2. Tests go in `tests/`
3. Documentation goes in `docs/`
4. Utility scripts go in `scripts/`

### Deprecating Code
1. Move to `legacy/` directory
2. Update documentation to note deprecation
3. Keep for reference, but exclude from active development

### Documentation
1. Update relevant docs in `docs/`
2. Keep README.md concise - link to detailed docs
3. Document API changes in appropriate guide files

## Migration Notes

This structure was created on October 18, 2025, to organize a growing codebase. The key changes were:

1. **Separated concerns** - tests, docs, scripts, and legacy code now have dedicated directories
2. **Cleaned root** - only active production code remains at top level
3. **Preserved history** - old code moved to `legacy/` rather than deleted
4. **Improved discoverability** - clear organization makes it easier to find files
5. **Better gitignore** - runtime data directories explicitly ignored

The system remains fully functional after this reorganization!
