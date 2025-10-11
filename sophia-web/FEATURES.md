# SophiaAMS Web Interface - Features

## 🎨 Interface Overview

### Navigation Sidebar
- **Chat** - Memory-augmented conversation interface
- **Graph** - Interactive knowledge graph visualization
- **Admin** - Backend monitoring and management

---

## 💬 Chat Interface

### Real-Time Streaming Flow

**Progressive Updates** - Watch each step happen in real-time:

1. **Your Message** ✉️
   - Instantly appears in chat
   - No waiting for full response

2. **Memory Retrieval** 🧠
   - Status: "Retrieving memories..."
   - Searches knowledge base for relevant context

3. **Memory Display** 📚
   - Shows summary of retrieved information
   - Expandable details with related facts
   - Confidence scores for each fact

4. **Response Generation** 💭
   - Status: "Generating response..."
   - LLM processes with memory context

5. **Assistant Response** 🤖
   - Appears in real-time
   - Context-aware using retrieved memories

6. **Save to Memory** 💾
   - Status: "Saving to memory..."
   - Conversation stored in knowledge graph

### Features
- **Auto Memory Retrieval** - Toggle to enable/disable automatic context retrieval
- **Connection Status** - Visual indicator (green = connected, red = disconnected)
- **Session ID** - Unique identifier for conversation tracking
- **Message History** - Scrollable chat history with all interactions

### Memory Display Format

```
🧠 Retrieved Memories
Summary: [AI-generated summary of relevant context]

▶ View 5 related facts
  • entity → relationship → object (95%)
  • entity → relationship → object (87%)
  ...
```

---

## 🕸️ Graph Visualization

### Interactive Features

**Search & Visualize**
- Enter any topic or query
- Click "Visualize" to generate graph
- Nodes and relationships rendered in real-time

**Graph Interactions**
- **Zoom**: Mouse wheel to zoom in/out
- **Pan**: Click and drag background to move around
- **Drag Nodes**: Click and drag nodes to reposition
- **Node Details**: Click node to view connections

**Fullscreen Mode**
- Toggle fullscreen for immersive exploration
- Maximize graph analysis space

### Graph Layout

**Force-Directed Simulation**
- Nodes repel each other for clarity
- Links maintain optimal distance
- Collision detection prevents overlap
- Center gravity keeps graph focused

**Visual Elements**
- **Nodes**: Purple circles (blue when selected)
- **Links**: Gray lines (thickness = confidence)
- **Labels**: Entity names (truncated if >20 chars)
- **Relationships**: Shown on link hover

### Node Info Panel

When clicking a node, shows:
- **Entity Name** - Full label
- **Type** - Entity classification
- **Connections** - All relationships
  - Incoming: ← relationship other_entity
  - Outgoing: → relationship other_entity

### Statistics Bar
- **Nodes** - Total entities in current graph
- **Relationships** - Total links between entities

---

## ⚙️ Admin Dashboard

### Real-Time Statistics

**Auto-Refreshing Cards** (every 5 seconds):
- **Total Triples** - Knowledge base size
- **API Status** - Online/Offline indicator
- **Topics** - Number of loaded topics
- **Entities** - Number of loaded entities

### Knowledge Base Exploration

**Action Buttons:**

1. **Load Topics** 🏷️
   - Shows top topics in knowledge base
   - Sample triples for each topic
   - Topic size (number of triples)

2. **Load Entities** 👥
   - Most connected entities
   - Connection count per entity
   - Sorted by importance

3. **Full Overview** 📊
   - Comprehensive knowledge structure
   - JSON view of entire system
   - For deep analysis

### Topics Display

```
Topic: Artificial Intelligence (45 triples)
  • neural_network → is_part_of → deep_learning
  • machine_learning → enables → prediction
  • AI → requires → data
```

### Entities Display

```
Entity                    Connections
neural_network           23 connections
machine_learning         18 connections
deep_learning            15 connections
```

### Document Upload

**Features:**
- Source name (optional identifier)
- Text area for document content
- Upload button
- Auto-refresh stats after upload

**Supported Content:**
- Plain text
- Markdown
- Code snippets
- Articles
- Notes

**Upload Flow:**
1. Paste or type content
2. Optionally name source
3. Click "Upload to Knowledge Base"
4. Automatic processing and triple extraction
5. Stats update to reflect new data

---

## 🔄 WebSocket Communication

### Connection Management
- Auto-connect on page load
- Auto-reconnect on disconnect (3s delay)
- Visual connection status indicator
- Session persistence across reconnects

### Message Types

**Sent to Server:**
- `chat` - Send chat message with auto-retrieve option
- `query` - Direct memory query
- `graph` - Request graph data for visualization

**Received from Server:**
- `connected` - Initial connection with session ID
- `user_message` - Echo of user's message
- `status` - Progress updates ("Retrieving memories...")
- `memory_retrieved` - Retrieved context data
- `assistant_message` - LLM response
- `conversation_saved` - Confirmation of storage
- `graph_data` - Graph nodes and links
- `error` - Error messages

### Progressive Updates

Unlike Streamlit's all-at-once approach, WebSocket enables:
- **Instant feedback** - User sees their message immediately
- **Step visibility** - Each process step shown as it happens
- **Better UX** - No waiting for complete response
- **Transparency** - User knows what's happening behind the scenes

---

## 🎨 Design System

### Color Scheme
- **Background**: Dark (#0a0a0a)
- **Cards**: Dark gray (#111)
- **Borders**: Subtle gray (#222)
- **Primary**: Blue (#1e40af)
- **Accent**: Purple (#8b5cf6)
- **Success**: Green (#22c55e)
- **Error**: Red (#ef4444)

### Typography
- **System Font Stack**: -apple-system, Segoe UI, Roboto
- **Monospace**: Courier New (for session IDs, code)
- **Sizes**: 12px-24px range
- **Weights**: 400 (normal), 500 (medium), 600 (semibold)

### Animations
- **Slide In**: Messages fade and slide up
- **Spinner**: Loading indicators rotate
- **Hover**: Smooth transitions on interactive elements
- **Smooth Scroll**: Auto-scroll to latest message

---

## 🚀 Performance

### Optimizations
- **WebSocket**: Single persistent connection, no polling
- **Lazy Loading**: Components load on demand
- **Virtual DOM**: React's efficient rendering
- **D3 Simulation**: Hardware-accelerated force layout
- **Debouncing**: Smart update batching

### Scalability
- Handles 1000+ nodes in graph
- Unlimited message history
- Auto-cleanup of old sessions
- Efficient triple rendering

---

## 🔐 Future Enhancements

### Planned Features
- [ ] **Token-by-token streaming** - Stream LLM responses word by word
- [ ] **Graph clustering** - Auto-group related entities
- [ ] **Export/Import** - Save and load graph states
- [ ] **Multi-session** - Support multiple concurrent conversations
- [ ] **Authentication** - User login and permissions
- [ ] **Advanced filters** - Filter graph by confidence, type, date
- [ ] **Analytics** - Usage statistics and insights
- [ ] **Custom themes** - Light/dark/custom color schemes
- [ ] **Voice input** - Speech-to-text for chat
- [ ] **Mobile responsive** - Optimized for tablets and phones

### Experimental Ideas
- AR/VR graph visualization
- Collaborative editing
- AI-suggested queries
- Automatic summarization
- Knowledge base versioning
- Real-time collaboration

---

## 📚 Technical Stack

**Frontend:**
- React 18 (UI framework)
- Vite (build tool, HMR)
- D3.js (graph visualization)
- Lucide React (icon library)
- React Router (navigation)

**Backend:**
- Node.js (runtime)
- Express (web framework)
- ws (WebSocket library)
- Axios (HTTP client)

**Integration:**
- WebSocket for real-time communication
- REST API proxy to Python backend
- Shared session management

---

## 🎯 Use Cases

### Research & Development
- Explore knowledge relationships
- Analyze conversation patterns
- Visualize complex topics
- Test memory retrieval

### Content Management
- Upload documents
- Monitor knowledge growth
- Review extracted triples
- Manage topics

### System Administration
- Monitor API health
- View system statistics
- Manage memory buffer
- Debug conversations

### Interactive Learning
- Ask questions with context
- See how memory retrieval works
- Understand relationship extraction
- Explore knowledge visually
