# SophiaAMS REST API

REST API server for the Associative Semantic Memory System.

## Quick Start

1. **Install additional dependencies:**
   ```bash
   pip install -r requirements_api.txt
   ```

2. **Start the demo:**
   ```bash
   python start_demo.py
   ```
   Choose option 3 to start both API server and Streamlit test client.

3. **Manual startup:**
   ```bash
   # Terminal 1 - API Server
   python api_server.py

   # Terminal 2 - Streamlit Client
   streamlit run streamlit_client.py
   ```

4. **Access:**
   - API Server: http://localhost:8000
   - API Docs: http://localhost:8000/docs (FastAPI auto-generated)
   - Streamlit Client: http://localhost:8501

## API Endpoints

### Ingestion
- `POST /ingest/conversation` - Ingest OpenAI-format conversations
- `POST /ingest/document` - Ingest text documents

### Retrieval
- `POST /query` - Query memory for related information
- `POST /retrieve/associative` - Get associatively related content

### Exploration
- `GET /explore/topics` - Get top topics overview
- `GET /explore/entities` - Get most connected entities
- `GET /explore/overview` - Full knowledge overview
- `POST /explore/cluster` - Cluster triples for a query

### Utility
- `GET /health` - Health check
- `GET /stats` - Basic statistics

## Example Usage

### Ingest a Conversation
```python
import requests

conversation = {
    "messages": [
        {"role": "user", "content": "What's the weather like?"},
        {"role": "assistant", "content": "I don't have access to current weather data."}
    ],
    "session_id": "chat-123"
}

response = requests.post("http://localhost:8000/ingest/conversation", json=conversation)
```

### Query Memory
```python
query = {
    "text": "weather information",
    "limit": 10,
    "return_summary": True
}

response = requests.post("http://localhost:8000/query", json=query)
results = response.json()
```

## Test Client Features

The Streamlit test client provides:

1. **Chat Interface** - Have conversations that automatically get stored
2. **Memory Query** - Search stored conversations and documents
3. **Knowledge Exploration** - Browse topics, entities, and relationships
4. **Raw API Testing** - Test endpoints directly with custom data

Perfect for testing the API functionality in a user-friendly interface!