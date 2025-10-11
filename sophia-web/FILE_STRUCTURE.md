# SophiaAMS Web Interface - File Structure

## 📁 Complete File Tree

```
sophia-web/
│
├── 📄 README.md                    # Complete project documentation
├── 📄 QUICKSTART.md               # Quick start guide
├── 📄 FEATURES.md                 # Detailed feature descriptions
├── 📄 PROJECT_SUMMARY.md          # Project overview
├── 📄 IMPROVEMENTS.md             # Streamlit vs Node comparison
├── 📄 FILE_STRUCTURE.md           # This file
│
├── 📄 package.json                # Root package scripts
├── 📄 .gitignore                  # Git ignore rules
│
├── 🔧 setup.bat                   # Windows setup script
├── 🔧 setup.sh                    # Unix setup script
├── 🔧 start-all.bat               # All-in-one launcher (Windows)
│
├── 📂 server/                     # Node.js Backend
│   ├── 📄 server.js              # Main server (Express + WebSocket)
│   ├── 📄 package.json           # Server dependencies
│   ├── 📄 .env                   # Server configuration
│   └── 📄 package-lock.json      # Lock file
│
└── 📂 client/                     # React Frontend
    ├── 📄 index.html             # HTML entry point
    ├── 📄 vite.config.js         # Vite configuration
    ├── 📄 package.json           # Client dependencies
    ├── 📄 package-lock.json      # Lock file
    │
    └── 📂 src/                    # Source code
        ├── 📄 main.jsx           # React entry point
        ├── 📄 App.jsx            # Main app component
        ├── 📄 App.css            # App styles
        ├── 📄 index.css          # Global styles
        │
        ├── 📂 hooks/              # React hooks
        │   └── 📄 useWebSocket.js # WebSocket connection hook
        │
        ├── 📂 pages/              # Page components
        │   ├── 📄 ChatPage.jsx    # Streaming chat interface
        │   ├── 📄 ChatPage.css    # Chat styles
        │   ├── 📄 GraphPage.jsx   # D3 graph visualization
        │   ├── 📄 GraphPage.css   # Graph styles
        │   ├── 📄 AdminPage.jsx   # Admin dashboard
        │   └── 📄 AdminPage.css   # Admin styles
        │
        ├── 📂 components/         # Shared components (future)
        └── 📂 utils/              # Utility functions (future)
```

## 📋 File Descriptions

### Root Level

#### Documentation Files
- **README.md** (5.5KB)
  - Complete project documentation
  - Architecture overview
  - API endpoints
  - Configuration guide

- **QUICKSTART.md** (2.9KB)
  - Installation instructions
  - Running the application
  - Troubleshooting guide

- **FEATURES.md** (8.7KB)
  - Detailed feature descriptions
  - UI/UX walkthroughs
  - Technical stack details

- **PROJECT_SUMMARY.md** (9.2KB)
  - Project overview
  - Success metrics
  - Future enhancements

- **IMPROVEMENTS.md** (11.3KB)
  - Streamlit vs Node.js comparison
  - Performance improvements
  - Migration benefits

- **FILE_STRUCTURE.md** (This file)
  - Complete file tree
  - File descriptions
  - Line counts

#### Configuration Files
- **package.json** (565B)
  - Root level npm scripts
  - Project metadata
  - Convenience commands

- **.gitignore** (243B)
  - Git ignore patterns
  - Node modules
  - Build outputs

#### Setup Scripts
- **setup.bat** (1.2KB)
  - Windows setup automation
  - Dependency installation

- **setup.sh** (1.1KB)
  - Unix/Linux setup automation
  - Dependency installation

- **start-all.bat** (853B)
  - Windows all-in-one launcher
  - Starts all services

### Server Directory (`server/`)

- **server.js** (9.5KB)
  ```javascript
  // Main Node.js server
  // - Express HTTP server
  // - WebSocket server
  // - API proxy to Python
  // - Message handlers
  // - Session management
  ```

- **package.json** (490B)
  ```json
  {
    "dependencies": {
      "express": "^4.18.2",
      "ws": "^8.14.2",
      "axios": "^1.6.2",
      "cors": "^2.8.5",
      "uuid": "^9.0.1",
      "dotenv": "^16.3.1"
    }
  }
  ```

- **.env** (45B)
  ```env
  PORT=3001
  PYTHON_API=http://localhost:8000
  ```

### Client Directory (`client/`)

#### Root Files
- **index.html** (~250B)
  - HTML entry point
  - Root div
  - Script imports

- **vite.config.js** (~200B)
  - Vite configuration
  - Dev server settings
  - Proxy configuration

- **package.json** (~700B)
  ```json
  {
    "dependencies": {
      "react": "^18.2.0",
      "react-dom": "^18.2.0",
      "react-router-dom": "^6.20.1",
      "d3": "^7.8.5",
      "lucide-react": "^0.294.0"
    }
  }
  ```

#### Source Files (`src/`)

**Core Files:**
- **main.jsx** (241B)
  - React entry point
  - Root render

- **App.jsx** (1.9KB)
  - Main app component
  - Router configuration
  - Navigation sidebar

- **App.css** (903B)
  - App layout styles
  - Sidebar styles
  - Navigation styles

- **index.css** (760B)
  - Global styles
  - CSS reset
  - Scrollbar customization

**Hooks (`hooks/`):**
- **useWebSocket.js** (2.0KB)
  - WebSocket connection hook
  - Auto-reconnection logic
  - Message handling
  - Session management

**Pages (`pages/`):**
- **ChatPage.jsx** (7.8KB)
  - Streaming chat interface
  - Real-time message display
  - Memory visualization
  - Progressive status updates

- **ChatPage.css** (3.7KB)
  - Chat layout
  - Message bubbles
  - Status indicators
  - Animations

- **GraphPage.jsx** (7.5KB)
  - D3 graph visualization
  - Force-directed layout
  - Interactive controls
  - Node info panel

- **GraphPage.css** (2.8KB)
  - Graph container
  - Node/link styles
  - Controls
  - Info panel

- **AdminPage.jsx** (6.5KB)
  - Admin dashboard
  - Stats display
  - Knowledge exploration
  - Document upload

- **AdminPage.css** (4.2KB)
  - Dashboard layout
  - Stat cards
  - Data grids
  - Upload form

## 📊 Code Statistics

### Total Files: 29

#### By Type
- **JavaScript/JSX**: 10 files (~35KB)
- **CSS**: 5 files (~12KB)
- **Markdown**: 6 files (~38KB)
- **JSON**: 3 files (~2KB)
- **Config**: 3 files (~0.5KB)
- **Scripts**: 3 files (~3KB)

#### By Directory
- **Root**: 9 files (~42KB docs)
- **Server**: 3 files (~10KB code)
- **Client**: 17 files (~50KB code + config)

### Lines of Code (Estimated)

```
Server:
  server.js           ~270 lines

Client:
  Pages               ~600 lines
  Hooks               ~85 lines
  App/Main            ~100 lines
  Styles              ~500 lines

Total Code:          ~1,555 lines
Documentation:       ~1,800 lines
Configuration:       ~50 lines
```

## 🎯 Key Components Breakdown

### Server Architecture (server.js)

```javascript
// Imports & Setup        (lines 1-20)
// Express Configuration  (lines 21-30)
// WebSocket Server       (lines 31-50)
// HTTP Proxy Endpoints   (lines 51-110)
// WebSocket Handlers     (lines 111-300)
//   - handleChatMessage
//   - handleQuery
//   - handleGraphRequest
```

### Client Architecture

**Router Flow:**
```
App.jsx
  ├── ChatPage (/)
  ├── GraphPage (/graph)
  └── AdminPage (/admin)
```

**WebSocket Flow:**
```
useWebSocket hook
  ├── Connection management
  ├── Auto-reconnection
  ├── Message queue
  └── Session state
```

**Component Hierarchy:**
```
App
├── Sidebar
│   └── NavLinks
└── Routes
    ├── ChatPage
    │   ├── ChatHeader
    │   ├── MessageList
    │   │   ├── UserMessage
    │   │   ├── MemoryMessage
    │   │   ├── AssistantMessage
    │   │   └── StatusIndicator
    │   └── ChatInput
    ├── GraphPage
    │   ├── SearchBar
    │   ├── GraphSVG (D3)
    │   ├── NodeInfo
    │   └── StatsBar
    └── AdminPage
        ├── StatsGrid
        ├── ActionButtons
        ├── TopicsDisplay
        ├── EntitiesDisplay
        └── UploadForm
```

## 🔗 File Dependencies

### Import Graph

```
main.jsx
  └── App.jsx
      ├── ChatPage.jsx
      │   └── useWebSocket.js
      ├── GraphPage.jsx
      │   ├── useWebSocket.js
      │   └── d3
      └── AdminPage.jsx
```

### External Dependencies

**Server:**
```
express (HTTP server)
ws (WebSocket)
axios (HTTP client)
cors (CORS handling)
uuid (Session IDs)
dotenv (Config)
```

**Client:**
```
react (UI framework)
react-dom (DOM rendering)
react-router-dom (Routing)
d3 (Graph viz)
lucide-react (Icons)
vite (Build tool)
```

## 🚀 Build Output

### Development
```
npm run dev (client)
→ Vite dev server: localhost:3000
→ Hot Module Replacement
→ Source maps
→ Fast refresh

npm start (server)
→ Node.js server: localhost:3001
→ WebSocket: ws://localhost:3001
→ API proxy
```

### Production
```
npm run build (client)
→ dist/
  ├── index.html
  ├── assets/
  │   ├── index-[hash].js
  │   └── index-[hash].css
  └── ...

Optimized:
- Minified JS/CSS
- Tree shaking
- Code splitting
- Asset optimization
```

## 📝 Configuration Chain

```
.env (server)
  → server.js (reads config)
    → Express server starts
    → WebSocket server starts
      → Listens on PORT

vite.config.js (client)
  → Dev server config
  → Proxy /api → localhost:3001
  → HMR enabled
    → React app runs
    → WebSocket connects
```

## 🎨 Styling Architecture

```
index.css           (Global)
  ├── CSS reset
  ├── Base styles
  └── Scrollbar

App.css            (Layout)
  ├── Sidebar
  ├── Navigation
  └── Main content

ChatPage.css       (Feature)
  ├── Messages
  ├── Input
  └── Status

GraphPage.css      (Feature)
  ├── Canvas
  ├── Controls
  └── Info panel

AdminPage.css      (Feature)
  ├── Stats grid
  ├── Data sections
  └── Upload form
```

## 🔍 Finding Files

### By Feature

**Chat Feature:**
- `client/src/pages/ChatPage.jsx`
- `client/src/pages/ChatPage.css`
- `client/src/hooks/useWebSocket.js`

**Graph Feature:**
- `client/src/pages/GraphPage.jsx`
- `client/src/pages/GraphPage.css`

**Admin Feature:**
- `client/src/pages/AdminPage.jsx`
- `client/src/pages/AdminPage.css`

**Server:**
- `server/server.js`
- `server/.env`

### By Type

**Components:** `client/src/pages/*.jsx`
**Styles:** `client/src/**/*.css`
**Hooks:** `client/src/hooks/*.js`
**Config:** `*.config.js`, `.env`, `package.json`
**Docs:** `*.md`

## 📦 Installation Files

Created during `npm install`:
```
server/
  └── node_modules/     (113 packages)
      └── package-lock.json

client/
  └── node_modules/     (175 packages)
      └── package-lock.json
```

Ignored in `.gitignore` ✓

---

**Total Project Size:**
- Source Code: ~60KB
- Documentation: ~50KB
- Configuration: ~5KB
- **Total: ~115KB** (excluding node_modules)

With node_modules: ~150MB
