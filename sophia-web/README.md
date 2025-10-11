# SophiaAMS Web Interface

A modern Node.js/React admin interface for SophiaAMS with real-time streaming, graph visualization, and backend monitoring.

## Features

### 💬 Chat Interface
- **Real-time streaming** - See messages, memory retrieval, and responses progressively
- **Auto memory retrieval** - Automatically pulls relevant context from knowledge base
- **WebSocket communication** - Instant updates without page refresh
- **Memory visualization** - Expandable view of retrieved facts and summaries

### 🕸️ Graph Visualization
- **Interactive D3.js graph** - Zoom, pan, and drag nodes
- **Knowledge exploration** - Visualize relationships between entities
- **Node details** - Click nodes to see connections
- **Fullscreen mode** - Maximize graph for detailed analysis

### ⚙️ Admin Dashboard
- **Real-time stats** - Auto-refreshing metrics (total triples, API status)
- **Topic exploration** - Browse top topics in knowledge base
- **Entity analysis** - View most connected entities
- **Document upload** - Add documents directly to memory
- **Knowledge overview** - Deep dive into the graph structure

## Architecture

```
sophia-web/
├── server/          # Node.js/Express WebSocket server
│   ├── server.js    # Main server with WS + HTTP endpoints
│   └── package.json
│
└── client/          # React/Vite frontend
    ├── src/
    │   ├── components/
    │   ├── pages/
    │   │   ├── ChatPage.jsx      # Streaming chat interface
    │   │   ├── GraphPage.jsx     # D3 graph visualization
    │   │   └── AdminPage.jsx     # Admin dashboard
    │   ├── hooks/
    │   │   └── useWebSocket.js   # WebSocket hook
    │   └── App.jsx
    └── package.json
```

## Prerequisites

- **Node.js** 18+ and npm
- **Python 3.8+** with SophiaAMS running
- **SophiaAMS API server** (`api_server.py`) running on port 8000

## Quick Start

### 1. Install Dependencies

```bash
# Install server dependencies
cd server
npm install

# Install client dependencies
cd ../client
npm install
```

### 2. Start Python API Server

Make sure your Python API server is running:

```bash
# In your SophiaAMS directory
python api_server.py
```

This should start the FastAPI server on `http://localhost:8000`

### 3. Start Node.js Server

```bash
cd server
npm start
```

Server runs on `http://localhost:3001`

### 4. Start React Client

```bash
cd client
npm run dev
```

Client runs on `http://localhost:3000`

### 5. Open Browser

Navigate to `http://localhost:3000`

## How It Works

### Real-Time Streaming Flow

1. **User sends message** → Instantly displayed in chat
2. **Memory retrieval** → Status: "Retrieving memories..."
3. **Memory results** → Displayed with summary and expandable facts
4. **LLM generation** → Status: "Generating response..."
5. **Assistant response** → Displayed in chat
6. **Save to memory** → Status: "Saving to memory..."
7. **Confirmation** → Conversation saved to knowledge base

### WebSocket Messages

**Client → Server:**
```json
{
  "type": "chat",
  "data": {
    "message": "user message",
    "autoRetrieve": true
  }
}
```

**Server → Client:**
```json
{
  "type": "user_message|memory_retrieved|assistant_message|status",
  "content": "...",
  "data": {...}
}
```

### Graph Visualization

- Queries Python API for triples related to search term
- Transforms to D3 graph format (nodes + links)
- Force-directed layout with drag interaction
- Node click reveals connections and details

## API Endpoints

### HTTP (Proxy to Python API)
- `GET /api/health` - Check API health
- `GET /api/stats` - Get knowledge base stats
- `GET /api/explore/topics` - Get top topics
- `GET /api/explore/entities` - Get top entities
- `POST /api/query` - Query memory
- `POST /api/ingest/document` - Upload document

### WebSocket
- `ws://localhost:3001` - Real-time communication
- Message types: `chat`, `query`, `graph`

## Development

### Server (with auto-reload)
```bash
cd server
npm run dev
```

### Client (with HMR)
```bash
cd client
npm run dev
```

## Configuration

### Server (.env)
```env
PORT=3001
PYTHON_API=http://localhost:8000
```

### Client (vite.config.js)
- Proxy configured to forward `/api/*` to Node.js server
- Dev server on port 3000

## Tech Stack

**Backend:**
- Node.js + Express
- WebSocket (ws library)
- Axios for HTTP proxy

**Frontend:**
- React 18
- Vite (dev/build)
- D3.js (graph visualization)
- Lucide React (icons)
- React Router (navigation)

## Troubleshooting

**WebSocket won't connect:**
- Ensure Node.js server is running on port 3001
- Check browser console for connection errors

**No memory retrieval:**
- Verify Python API is running on port 8000
- Check `/api/health` endpoint

**Graph not rendering:**
- Ensure D3.js loaded correctly
- Check search query returns triples

**Styles not loading:**
- Clear browser cache
- Rebuild client: `npm run build`

## Future Enhancements

- [ ] Streaming LLM responses (token by token)
- [ ] Advanced graph filters and clustering
- [ ] Session history and replay
- [ ] Export/import knowledge base
- [ ] Multi-user support with auth
- [ ] Graph analytics dashboard
- [ ] Custom entity/relationship types

## License

MIT
