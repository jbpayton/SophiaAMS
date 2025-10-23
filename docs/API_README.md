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

### Goal Management
- `POST /api/goals/create` - Create a new goal
- `POST /api/goals/update` - Update goal status or metadata
- `GET /api/goals` - Query goals with various filters
- `GET /api/goals/progress` - Get goal completion statistics
- `GET /api/goals/suggestion` - Get suggested next goal

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

### Create a Goal
```python
goal = {
    "owner": "Sophia",
    "description": "Learn about transformer architectures",
    "priority": 4,
    "goal_type": "standard",
    "is_forever_goal": False
}

response = requests.post("http://localhost:8000/api/goals/create", json=goal)
result = response.json()
```

### Create an Instrumental Goal with Derived Goals
```python
# Create instrumental goal (never completes)
instrumental = {
    "owner": "Sophia",
    "description": "Continuously expand AI knowledge",
    "priority": 5,
    "goal_type": "instrumental",
    "is_forever_goal": True
}
requests.post("http://localhost:8000/api/goals/create", json=instrumental)

# Create derived goal (auto-prioritized)
derived = {
    "owner": "Sophia",
    "description": "Study attention mechanisms",
    "priority": 4,
    "goal_type": "derived",
    "parent_goal": "Continuously expand AI knowledge"
}
requests.post("http://localhost:8000/api/goals/create", json=derived)
```

### Create Goal with Dependencies
```python
# Goals will be blocked until dependencies are met
goal_with_deps = {
    "owner": "Sophia",
    "description": "Deploy trained model",
    "priority": 5,
    "depends_on": [
        "Train final model",
        "Set up production environment"
    ]
}

response = requests.post("http://localhost:8000/api/goals/create", json=goal_with_deps)
```

### Query and Update Goals
```python
# Get all active goals
response = requests.get("http://localhost:8000/api/goals", params={
    "owner": "Sophia",
    "active_only": True
})
goals = response.json()["goals"]

# Update goal status
update = {
    "goal_description": "Study attention mechanisms",
    "status": "completed",
    "completion_notes": "Finished reading key papers"
}
requests.post("http://localhost:8000/api/goals/update", json=update)

# Get next suggested goal
response = requests.get("http://localhost:8000/api/goals/suggestion")
suggestion = response.json()["suggestion"]
print(f"Next goal: {suggestion['goal_description']}")
```

## Test Client Features

The Streamlit test client provides:

1. **Chat Interface** - Have conversations that automatically get stored
2. **Memory Query** - Search stored conversations and documents
3. **Knowledge Exploration** - Browse topics, entities, and relationships
4. **Raw API Testing** - Test endpoints directly with custom data

Perfect for testing the API functionality in a user-friendly interface!