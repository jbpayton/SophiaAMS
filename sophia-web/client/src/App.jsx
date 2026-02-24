import React, { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom'
import ChatPage from './pages/ChatPage'
import GraphPage from './pages/GraphPage'
import AdminPage from './pages/AdminPage'
import GoalsPage from './pages/GoalsPage'
import AutonomousPage from './pages/AutonomousPage'
import SettingsPage from './pages/SettingsPage'
import SetupPage from './pages/SetupPage'
import { Brain, MessageSquare, Network, Settings, Target, Activity, Sliders, Loader } from 'lucide-react'
import './App.css'

function App() {
  const [currentPath, setCurrentPath] = useState(window.location.pathname)
  const [setupState, setSetupState] = useState('checking') // 'checking' | 'needed' | 'complete' | 'restarting'

  useEffect(() => {
    fetch('/api/setup/status')
      .then(r => r.json())
      .then(data => {
        setSetupState(data.setup_complete ? 'complete' : 'needed')
      })
      .catch(() => {
        // If we can't reach the backend, assume setup is needed
        setSetupState('needed')
      })
  }, [])

  if (setupState === 'checking') {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#0a0a0a', color: '#888' }}>
        <Loader size={24} className="spin" style={{ marginRight: 12 }} />
        Loading...
      </div>
    )
  }

  if (setupState === 'needed') {
    return (
      <SetupPage onComplete={() => setSetupState('restarting')} />
    )
  }

  if (setupState === 'restarting') {
    return (
      <div className="setup-restart-overlay" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.95)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 20, color: '#fff', zIndex: 1000 }}>
        <Brain size={48} style={{ color: '#3b82f6' }} />
        <h2 style={{ fontSize: 24 }}>Setup Complete!</h2>
        <p style={{ color: '#888', fontSize: 16 }}>Restart SophiaAMS to begin: <code style={{ background: '#222', padding: '4px 8px', borderRadius: 4 }}>python main.py</code></p>
      </div>
    )
  }

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
              to="/goals"
              className={`nav-link ${currentPath === '/goals' ? 'active' : ''}`}
              onClick={() => setCurrentPath('/goals')}
            >
              <Target size={20} />
              <span>Goals</span>
            </Link>

            <Link
              to="/activity"
              className={`nav-link ${currentPath === '/activity' ? 'active' : ''}`}
              onClick={() => setCurrentPath('/activity')}
            >
              <Activity size={20} />
              <span>Activity</span>
            </Link>

            <Link
              to="/settings"
              className={`nav-link ${currentPath === '/settings' ? 'active' : ''}`}
              onClick={() => setCurrentPath('/settings')}
            >
              <Sliders size={20} />
              <span>Settings</span>
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
            <Route path="/goals" element={<GoalsPage />} />
            <Route path="/activity" element={<AutonomousPage />} />
            <Route path="/autonomous" element={<AutonomousPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/admin" element={<AdminPage />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App
