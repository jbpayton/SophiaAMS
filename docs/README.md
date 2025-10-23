# SophiaAMS
**Associative Semantic Memory System with REST API**

## Overview

SophiaAMS is an intelligent memory system for LLM-based applications featuring conversation processing, document ingestion, and semantic retrieval. It transforms conversations and documents into a knowledge graph of semantic triples, enabling natural memory-aware AI interactions.

## ✨ Key Features

- **🗨️ Conversational Memory**: Automatically processes chat conversations into semantic knowledge
- **📄 Document Processing**: Ingests text files, web content, and documents into memory
- **🧠 Semantic Retrieval**: Finds relevant memories using vector similarity and topic matching
- **🎯 Goal Management**: Advanced goal system with dependencies, instrumental goals, and auto-prompt integration
- **🌐 REST API**: FastAPI server with comprehensive endpoints for integration
- **💻 Interactive Client**: Streamlit-based chat interface with memory visualization
- **📊 Knowledge Exploration**: Browse topics, entities, and relationships in your knowledge graph
- **⚡ Smart Buffering**: Server-side conversation batching for optimal performance

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/jbpayton/SophiaAMS.git
cd SophiaAMS

# Install dependencies
pip install -r requirements.txt
pip install -r requirements_api.txt

# Download spaCy model
python -m spacy download en_core_web_sm
```

### 2. Environment Setup

Create a `.env` file with your LLM configuration:

```bash
LLM_API_BASE=http://your-llm-server:1234/v1
LLM_API_KEY=your-api-key
EXTRACTION_MODEL=your-model-name
```

### 3. Launch the System

```bash
# Start the API server
python api_server.py

# In another terminal, start the Streamlit client
streamlit run streamlit_client.py
```

Open http://localhost:8501 in your browser to access the interactive interface!

## 🏗️ Architecture

### Components

- **API Server** (`api_server.py`): FastAPI REST endpoints for memory operations
- **Streamlit Client** (`streamlit_client.py`): Interactive web interface for chat and exploration
- **AssociativeSemanticMemory**: Core memory processing with LLM integration
- **VectorKnowledgeGraph**: Qdrant-powered vector storage for semantic triples
- **ConversationProcessor**: Transforms chat messages into knowledge triples

### Data Flow

```
Chat Input → Memory Retrieval → LLM Response → Knowledge Storage
     ↑                ↓                 ↓              ↓
User Interface ← Memory Context ← Response Gen. → Triple Extraction
```

## 💬 Usage Examples

### Interactive Chat Interface

The Streamlit client provides:
- **Real-time chat** with memory-aware responses
- **Memory visualization** showing retrieved context
- **File upload** for document ingestion
- **Knowledge exploration** of topics and entities

### REST API Usage

```python
import requests

# Query memory
response = requests.post("http://localhost:8000/query", json={
    "text": "What did we discuss about AI?",
    "limit": 10,
    "return_summary": True
})

# Ingest conversation
response = requests.post("http://localhost:8000/ingest/conversation", json={
    "messages": [
        {"role": "user", "content": "I love machine learning"},
        {"role": "assistant", "content": "That's great! What aspects interest you most?"}
    ],
    "session_id": "user123"
})

# Upload document
response = requests.post("http://localhost:8000/ingest/document", json={
    "text": "Your document content here...",
    "source": "research_paper.txt"
})
```

### Programmatic Usage

```python
from AssociativeSemanticMemory import AssociativeSemanticMemory
from VectorKnowledgeGraph import VectorKnowledgeGraph
from ConversationProcessor import ConversationProcessor

# Initialize system
kgraph = VectorKnowledgeGraph()
memory = AssociativeSemanticMemory(kgraph)
processor = ConversationProcessor(memory)

# Process conversation
messages = [
    {"role": "user", "content": "Tell me about quantum computing"},
    {"role": "assistant", "content": "Quantum computing uses quantum mechanics..."}
]

result = processor.process_conversation(messages, entity_name="Assistant")

# Query related information
info = memory.query_related_information("quantum computing applications")
print(info["summary"])
```

## 🎯 Goal Management System

SophiaAMS includes a sophisticated goal management system that enables the agent to maintain and work toward objectives autonomously.

### Goal Types

- **Standard Goals**: Regular, completable tasks
- **Instrumental Goals**: Ongoing strategic objectives that never complete
- **Derived Goals**: Action items spawned from instrumental goals (auto-prioritized)

### Key Features

- **Dependency Management**: Goals can depend on others with automatic blocking
- **Forever Goals**: Instrumental goals that remain "ongoing" indefinitely
- **Auto-Prompt Integration**: High-priority and instrumental goals automatically appear in agent context
- **Smart Suggestions**: System suggests next goal based on priority, dependencies, and type
- **Web Interface**: Full-featured UI for creating and managing goals
- **Hierarchical Structure**: Parent-child goal relationships

### Quick Example

```python
# Create an instrumental goal (never completes)
memory.create_goal(
    owner="Sophia",
    description="Continuously expand knowledge of AI",
    priority=5,
    goal_type="instrumental",
    is_forever_goal=True
)

# Create a derived goal (auto-prioritized)
memory.create_goal(
    owner="Sophia",
    description="Study transformer architecture",
    priority=4,
    goal_type="derived",
    parent_goal="Continuously expand knowledge of AI"
)

# Create goal with dependencies (blocked until deps met)
memory.create_goal(
    owner="Sophia",
    description="Implement full training pipeline",
    priority=4,
    depends_on=["Set up data processing", "Configure model architecture"]
)
```

**See [GOAL_SYSTEM_GUIDE.md](GOAL_SYSTEM_GUIDE.md) for comprehensive documentation.**

## 🌐 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server health check |
| `/stats` | GET | Knowledge graph statistics |
| `/query` | POST | Search memory for relevant information |
| `/ingest/conversation` | POST | Process conversation messages |
| `/ingest/document` | POST | Add document to memory |
| `/explore/topics` | GET | Browse knowledge topics |
| `/explore/entities` | GET | View connected entities |
| `/conversation/buffer/{session_id}` | GET | Check conversation buffer status |
| `/api/goals/create` | POST | Create a new goal |
| `/api/goals/update` | POST | Update goal status or metadata |
| `/api/goals` | GET | Query goals with filters |
| `/api/goals/progress` | GET | Get goal statistics |
| `/api/goals/suggestion` | GET | Get suggested next goal |

See [API_README.md](API_README.md) for detailed API documentation.

## 🔧 Configuration

### Environment Variables

- `LLM_API_BASE`: Base URL for your LLM API
- `LLM_API_KEY`: Authentication key for LLM access
- `EXTRACTION_MODEL`: Model name for triple extraction and summarization

### Memory Settings

Configure in your initialization code:

```python
# Conversation buffer settings (in api_server.py)
BUFFER_SIZE = 5        # Process every N messages
MIN_BUFFER_TIME = 30   # Or every 30 seconds

# Query limits
DEFAULT_LIMIT = 10     # Default retrieval limit
CHAT_LIMIT = 10        # Auto-retrieval in chat
```

## 📊 Knowledge Graph

SophiaAMS represents knowledge as semantic triples:

```
(Subject, Predicate, Object)
("User", "likes", "machine learning")
("Python", "is_used_for", "AI development")
("Assistant", "explained", "neural networks")
```

Each triple includes:
- **Vector embeddings** for semantic similarity
- **Topics** for categorical organization
- **Metadata** (timestamps, sources, confidence scores)
- **Speaker attribution** for conversation context

## 🔍 Memory Retrieval

The system uses multiple retrieval strategies:

1. **Text Similarity**: Vector search against stored content
2. **Topic Matching**: Keyword-based topic filtering
3. **Associative Expansion**: Multi-hop relationship traversal
4. **LLM Summarization**: Intelligent summary generation

## 🛠️ Development

### Project Structure

```
SophiaAMS/
├── api_server.py              # FastAPI REST server
├── streamlit_client.py        # Interactive web interface
├── AssociativeSemanticMemory.py  # Core memory system
├── VectorKnowledgeGraph.py    # Vector storage layer
├── ConversationProcessor.py   # Chat message processing
├── MemoryExplorer.py         # Knowledge graph exploration
├── tests/                    # Test suite
└── docs/                     # Additional documentation
```

### Testing

```bash
# Run test suite
python -m pytest tests/

# Test specific components
python -m pytest tests/test_conversation_processor.py
```

## 📚 Dependencies

### Core Dependencies
- `fastapi`: REST API framework
- `streamlit`: Interactive web interface
- `sentence-transformers`: Embedding generation
- `qdrant-client`: Vector database
- `openai`: LLM integration
- `spacy`: Natural language processing

### Optional Dependencies
- `trafilatura`: Web content extraction
- `tiktoken`: Token counting and chunking
- `networkx`: Graph analysis
- `matplotlib`: Visualization

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/jbpayton/SophiaAMS/issues)
- **Documentation**: [API_README.md](API_README.md)
- **Development Notes**: [DEVELOPMENT_NOTES.md](DEVELOPMENT_NOTES.md)

---

*SophiaAMS - Intelligent memory for the age of AI* 🧠✨