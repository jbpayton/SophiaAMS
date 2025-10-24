import React, { useState, useEffect, useRef } from 'react'
import { Bot, Brain, Loader, Settings2, Play, Pause, Trash2, ChevronDown, ChevronRight, Sparkles, Wrench, Clock, Target, Zap } from 'lucide-react'
import './AutonomousPage.css'

// Component to display collapsable thoughts (reasoning + tool calls + auto-recall)
function ThoughtsDisplay({ thoughts, autoExpand = false }) {
  const [isExpanded, setIsExpanded] = useState(autoExpand)
  const [expandedTools, setExpandedTools] = useState(new Set())

  const toggleTool = (toolId) => {
    setExpandedTools(prev => {
      const next = new Set(prev)
      if (next.has(toolId)) {
        next.delete(toolId)
      } else {
        next.add(toolId)
      }
      return next
    })
  }

  return (
    <div className="thoughts-container">
      <button
        className="thoughts-toggle"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <Sparkles size={14} />
        <span>Agent Thoughts ({thoughts.toolCalls.length} tool{thoughts.toolCalls.length !== 1 ? 's' : ''} used)</span>
      </button>

      {isExpanded && (
        <div className="thoughts-content">
          {/* Auto-recalled memories section */}
          {thoughts.autoRecall && (
            <div className="thoughts-section">
              <h4><Brain size={14} /> Automatic Memory Recall:</h4>
              <div className="auto-recall-content">
                <pre>{thoughts.autoRecall}</pre>
              </div>
            </div>
          )}

          {thoughts.reasoning.length > 0 && (
            <div className="thoughts-section">
              <h4>Reasoning:</h4>
              <div className="reasoning-list">
                {thoughts.reasoning.map((text, idx) => (
                  <div key={idx} className="reasoning-item">
                    <span className="reasoning-bullet">•</span>
                    <span className="reasoning-text">{text}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {thoughts.toolCalls.length > 0 && (
            <div className="thoughts-section">
              <h4><Wrench size={14} /> Tool Usage:</h4>
              <div className="tool-calls-list">
                {thoughts.toolCalls.map((tool, idx) => {
                  const toolId = `tool-${idx}`
                  const isToolExpanded = expandedTools.has(toolId)

                  return (
                    <div key={idx} className="tool-call-item">
                      <button
                        className="tool-call-header"
                        onClick={() => toggleTool(toolId)}
                      >
                        {isToolExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        <Wrench size={12} />
                        <span className="tool-name">{tool.tool}</span>
                        <span className="tool-status">{tool.status || 'completed'}</span>
                      </button>

                      {isToolExpanded && (
                        <div className="tool-call-details">
                          <div className="tool-input">
                            <strong>Input:</strong>
                            <pre>{JSON.stringify(tool.input, null, 2)}</pre>
                          </div>
                          {tool.output && (
                            <div className="tool-output">
                              <strong>Output:</strong>
                              <pre>{tool.output}</pre>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Single autonomous iteration display
function AutonomousIteration({ iteration, index }) {
  const [isExpanded, setIsExpanded] = useState(index === 0) // Auto-expand latest

  return (
    <div className="autonomous-iteration">
      <div className="iteration-header" onClick={() => setIsExpanded(!isExpanded)}>
        {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <div className="iteration-meta">
          <span className="iteration-number">Iteration #{iteration.iteration_count}</span>
          <span className="iteration-time">{iteration.time_str}</span>
          <span className={`iteration-source ${iteration.source}`}>
            {iteration.source === 'autonomous' ? <Bot size={14} /> : <span>👤</span>}
            {iteration.source}
          </span>
        </div>
      </div>

      {isExpanded && (
        <div className="iteration-content">
          {/* Self-Generated Prompt */}
          <div className="iteration-section">
            <h4><Sparkles size={14} /> Autonomous Prompt:</h4>
            <div className="iteration-prompt">
              <pre>{iteration.prompt}</pre>
            </div>
          </div>

          {/* Thoughts (if available) */}
          {iteration.thoughts && (
            <ThoughtsDisplay thoughts={iteration.thoughts} autoExpand={true} />
          )}

          {/* Response */}
          <div className="iteration-section">
            <h4>Response:</h4>
            <div className="iteration-response">
              {iteration.response}
            </div>
          </div>

          {/* Goals Affected */}
          {iteration.goals_affected && iteration.goals_affected.length > 0 && (
            <div className="iteration-section">
              <h4><Target size={14} /> Goals Affected:</h4>
              <div className="goals-affected">
                {iteration.goals_affected.map((goal, idx) => (
                  <span key={idx} className="goal-badge">{goal}</span>
                ))}
              </div>
            </div>
          )}

          {/* Tools Used */}
          {iteration.tools_used && iteration.tools_used.length > 0 && (
            <div className="iteration-section">
              <h4><Wrench size={14} /> Tools Used:</h4>
              <div className="tools-used">
                {iteration.tools_used.map((tool, idx) => (
                  <span key={idx} className="tool-badge">{tool}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function AutonomousPage() {
  const [sessionId, setSessionId] = useState(null)
  const [isRunning, setIsRunning] = useState(false)
  const [status, setStatus] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const historyEndRef = useRef(null)

  // Load or create session ID
  useEffect(() => {
    let storedSessionId = localStorage.getItem('autonomous_session_id')
    if (!storedSessionId) {
      storedSessionId = generateSessionId()
      localStorage.setItem('autonomous_session_id', storedSessionId)
    }
    setSessionId(storedSessionId)
  }, [])

  // Poll status when running
  useEffect(() => {
    if (sessionId && isRunning) {
      const interval = setInterval(() => {
        fetchStatus()
        fetchHistory()
      }, 1000) // Poll every 1 second for near real-time updates
      return () => clearInterval(interval)
    }
  }, [sessionId, isRunning])

  // Initial fetch
  useEffect(() => {
    if (sessionId) {
      fetchStatus()
      fetchHistory()
    }
  }, [sessionId])

  // Auto-scroll to bottom
  useEffect(() => {
    if (autoScroll && historyEndRef.current) {
      historyEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [history, autoScroll])

  const generateSessionId = () => {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = Math.random() * 16 | 0
      const v = c === 'x' ? r : (r & 0x3 | 0x8)
      return v.toString(16)
    })
  }

  const fetchStatus = async () => {
    try {
      const response = await fetch(`/api/autonomous/status?sessionId=${sessionId}`)
      const data = await response.json()

      if (data.success && data.status) {
        setStatus(data.status)
        setIsRunning(data.status.running)
      }
    } catch (err) {
      console.error('Error fetching status:', err)
    }
  }

  const fetchHistory = async () => {
    try {
      const response = await fetch(`/api/autonomous/history?sessionId=${sessionId}&limit=50`)
      const data = await response.json()

      if (data.success) {
        setHistory(data.actions || [])
      }
    } catch (err) {
      console.error('Error fetching history:', err)
    }
  }

  const handleStart = async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await fetch('/api/autonomous/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId })
      })

      const data = await response.json()

      if (data.success) {
        setIsRunning(true)
        setStatus(data.status)
        fetchHistory()
      } else {
        setError(data.message || 'Failed to start')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleStop = async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await fetch('/api/autonomous/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId })
      })

      const data = await response.json()

      if (data.success) {
        setIsRunning(false)
        await fetchStatus()
      } else {
        setError(data.message || 'Failed to stop')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleClearHistory = () => {
    if (confirm('Clear all autonomous history? This cannot be undone.')) {
      setHistory([])
    }
  }

  const formatUptime = (seconds) => {
    if (!seconds) return '0s'
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const secs = Math.floor(seconds % 60)

    if (hours > 0) return `${hours}h ${minutes}m`
    if (minutes > 0) return `${minutes}m ${secs}s`
    return `${secs}s`
  }

  if (!sessionId) {
    return <div className="autonomous-page loading">Loading...</div>
  }

  return (
    <div className="autonomous-page">
      {/* Header */}
      <div className="autonomous-header">
        <div className="header-left">
          <Bot size={32} />
          <div className="header-title">
            <h1>Autonomous Mode</h1>
            <p>Sophia working independently on her goals</p>
          </div>
        </div>
        <div className="header-actions">
          <button
            onClick={isRunning ? handleStop : handleStart}
            disabled={loading}
            className={`control-btn ${isRunning ? 'stop' : 'start'}`}
          >
            {loading ? (
              <Loader className="spinning" size={20} />
            ) : isRunning ? (
              <>
                <Pause size={20} />
                Stop
              </>
            ) : (
              <>
                <Play size={20} />
                Start
              </>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}

      {/* Status Bar */}
      {status && (
        <div className="status-bar">
          <div className="status-item">
            <span className={`status-indicator ${isRunning ? 'running' : 'stopped'}`}></span>
            <span className="status-label">Status:</span>
            <span className="status-value">{isRunning ? 'Running' : 'Stopped'}</span>
          </div>

          {isRunning && (
            <>
              <div className="status-item">
                <Clock size={16} />
                <span className="status-label">Uptime:</span>
                <span className="status-value">{formatUptime(status.uptime_seconds)}</span>
              </div>

              <div className="status-item">
                <Zap size={16} />
                <span className="status-label">Iterations:</span>
                <span className="status-value">{status.iteration_count}</span>
              </div>

              <div className="status-item">
                <Target size={16} />
                <span className="status-label">Actions:</span>
                <span className="status-value">{status.actions_taken}</span>
              </div>

              <div className="status-item">
                <span className="status-label">Rate:</span>
                <span className="status-value">
                  {status.actions_this_hour} / {status.config?.max_actions_per_hour || 120} per hour
                </span>
              </div>

              {status.current_focus_goal && (
                <div className="status-item focus-goal">
                  <Target size={16} />
                  <span className="status-label">Focus:</span>
                  <span className="status-value">{status.current_focus_goal}</span>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Controls Bar */}
      <div className="controls-bar">
        <label className="control-option">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
          />
          Auto-scroll to latest
        </label>
        <button onClick={fetchHistory} className="refresh-btn">
          Refresh History
        </button>
        <button onClick={handleClearHistory} className="clear-btn" disabled={history.length === 0}>
          <Trash2 size={16} />
          Clear History
        </button>
      </div>

      {/* History */}
      <div className="autonomous-history">
        {history.length === 0 && !isRunning ? (
          <div className="empty-state">
            <Bot size={64} />
            <h3>No autonomous activity yet</h3>
            <p>Click "Start" to begin autonomous mode</p>
          </div>
        ) : (
          <div className="iterations-list">
            {/* Show "Currently Working" banner when running */}
            {isRunning && status && (
              <div className="currently-working">
                <div className="working-header">
                  <Loader className="spinning" size={20} />
                  <h3>Currently Working...</h3>
                </div>
                <div className="working-details">
                  <p>
                    <strong>Iteration #{status.iteration_count + 1}</strong> in progress
                  </p>
                  {status.current_focus_goal && (
                    <p className="focus">
                      <Target size={14} />
                      Focus: {status.current_focus_goal}
                    </p>
                  )}
                  <p className="hint">
                    Sophia is thinking, using tools, and making progress...
                    <br />
                    Results will appear below once this iteration completes (~30 seconds)
                  </p>
                </div>
              </div>
            )}

            {/* Show completed iterations */}
            {history.length > 0 && history.map((iteration, idx) => (
              <AutonomousIteration
                key={idx}
                iteration={iteration}
                index={history.length - 1 - idx} // Reverse index for latest first
              />
            ))}

            {history.length === 0 && isRunning && (
              <div className="waiting-first">
                <Loader className="spinning" size={32} />
                <p>Waiting for first iteration to complete...</p>
              </div>
            )}

            <div ref={historyEndRef} />
          </div>
        )}
      </div>
    </div>
  )
}

export default AutonomousPage
