# Quick Start Guide

## Installation (One-Time Setup)

### Windows
```batch
setup.bat
```

### Linux/Mac
```bash
chmod +x setup.sh
./setup.sh
```

## Running the Application

### Option 1: All-in-One (Windows)
```batch
start-all.bat
```

This will automatically start:
1. Python API server (port 8000)
2. Node.js server (port 3001)
3. React client (port 3000)

Then open: **http://localhost:3000**

### Option 2: Manual Start (All Platforms)

**Terminal 1 - Python API:**
```bash
python api_server.py
```

**Terminal 2 - Node.js Server:**
```bash
cd server
npm start
```

**Terminal 3 - React Client:**
```bash
cd client
npm run dev
```

Then open: **http://localhost:3000**

## Features Overview

### 💬 Chat Page
- Send messages and get memory-augmented responses
- Watch real-time progress:
  1. Your message appears instantly
  2. "Retrieving memories..." status
  3. Retrieved memories displayed
  4. "Generating response..." status
  5. Assistant response appears
  6. Conversation saved to memory

**Toggle "Auto Memory Retrieval"** to enable/disable context retrieval

### 🕸️ Graph Page
- Enter a search query (e.g., "artificial intelligence")
- Click "Visualize" to see the knowledge graph
- **Zoom**: Mouse wheel
- **Pan**: Click and drag background
- **Move nodes**: Click and drag nodes
- **View details**: Click a node to see connections

### ⚙️ Admin Page
- View real-time statistics
- Click "Load Topics" to see top topics in knowledge base
- Click "Load Entities" to see most connected entities
- Upload documents to add to memory
- Monitor API health and status

## Troubleshooting

**"WebSocket disconnected"**
→ Make sure Node.js server is running on port 3001

**"API Server Disconnected"**
→ Make sure Python API is running on port 8000

**No responses in chat**
→ Check that all 3 services are running (Python API, Node server, React client)

**Graph won't load**
→ Enter a search query and click "Visualize"

## Architecture

```
User Browser (localhost:3000)
        ↓
React Client (Vite dev server)
        ↓ WebSocket
Node.js Server (localhost:3001)
        ↓ HTTP/REST
Python API (localhost:8000)
        ↓
SophiaAMS Memory System
```

## What's Different from Streamlit?

✅ **Real-time streaming** - See each step as it happens
✅ **No page reloads** - Instant updates via WebSocket
✅ **Interactive graph** - Zoom, pan, drag, explore
✅ **Better UX** - Status indicators, smooth animations
✅ **Admin tools** - Backend monitoring and management

## Next Steps

- Explore the graph visualization with different queries
- Upload documents through the Admin page
- Monitor memory statistics in real-time
- Customize the UI by editing files in `client/src/`

Enjoy exploring your knowledge graph! 🧠✨
