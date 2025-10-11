import React, { useState } from 'react'
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom'
import ChatPage from './pages/ChatPage'
import GraphPage from './pages/GraphPage'
import AdminPage from './pages/AdminPage'
import { Brain, MessageSquare, Network, Settings } from 'lucide-react'
import './App.css'

function App() {
  const [currentPath, setCurrentPath] = useState(window.location.pathname)

  return (
    <Router>
      <div className="app">
        <nav className="sidebar">
          <div className="sidebar-header">
            <Brain size={32} />
            <h1>SophiaAMS</h1>
          </div>

          <div className="nav-links">
            <Link
              to="/"
              className={`nav-link ${currentPath === '/' ? 'active' : ''}`}
              onClick={() => setCurrentPath('/')}
            >
              <MessageSquare size={20} />
              <span>Chat</span>
            </Link>

            <Link
              to="/graph"
              className={`nav-link ${currentPath === '/graph' ? 'active' : ''}`}
              onClick={() => setCurrentPath('/graph')}
            >
              <Network size={20} />
              <span>Graph</span>
            </Link>

            <Link
              to="/admin"
              className={`nav-link ${currentPath === '/admin' ? 'active' : ''}`}
              onClick={() => setCurrentPath('/admin')}
            >
              <Settings size={20} />
              <span>Admin</span>
            </Link>
          </div>
        </nav>

        <main className="main-content">
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/graph" element={<GraphPage />} />
            <Route path="/admin" element={<AdminPage />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App
