import React, { useState, useEffect, useRef } from 'react'
import { Bot, Brain, Loader, Settings2, Play, Pause, Trash2, ChevronDown, ChevronRight, Sparkles, Wrench, Clock, Target, Zap, MessageSquare } from 'lucide-react'
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

// Extract a short summary from activity entry for the collapsed row
function extractSummary(entry) {
  // For goal events, try to extract the goal name from the full content
  const content = entry.content_full || entry.content_preview || ''
  const response = entry.response_full || entry.response_preview || ''

  let goalName = null
  const goalMatch = content.match(/TARGET GOAL:\s*(.+)/i) || content.match(/Goal:\s*(.+)/i)
  if (goalMatch) {
    goalName = goalMatch[1].trim().substring(0, 80)
  }

  // Get first meaningful sentence of the response as preview
  let responseSummary = ''
  if (response) {
    // Strip code blocks and markdown headers
    const cleaned = response.replace(/```[\s\S]*?```/g, '').replace(/^#+\s+/gm, '').trim()
    // Take first sentence or first line
    const firstSentence = cleaned.match(/^[^.!?\n]+[.!?]/)
    responseSummary = firstSentence ? firstSentence[0].trim() : cleaned.split('\n')[0].substring(0, 120)
  }

  return { goalName, responseSummary }
}

// Activity entry for the unified feed
function ActivityEntry({ entry, index }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [showFullInput, setShowFullInput] = useState(false)

  const sourceIcons = {
    webui: <MessageSquare size={14} />,
    telegram: <Zap size={14} />,
    goal: <Target size={14} />,
    self: <Bot size={14} />,
    cron: <Clock size={14} />,
  }

  const formatTime = (ts) => {
    const d = new Date(ts * 1000)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  // Build thoughts object for ThoughtsDisplay if available
  const thoughts = entry.thoughts && entry.thoughts.length > 0 ? {
    reasoning: entry.thoughts.filter(t => t.type === 'reasoning').map(t => t.data.text),
    toolCalls: entry.thoughts.filter(t => t.type === 'tool_start').map((t, i) => {
      const endEvent = entry.thoughts.find(e => e.type === 'tool_end' || e.type === 'tool_error')
      return {
        id: `tool-${i}`,
        tool: t.data.tool,
        input: t.data.input,
        output: endEvent?.data?.output || '',
        status: endEvent?.type === 'tool_error' ? 'error' : 'completed',
      }
    }),
    autoRecall: entry.thoughts.find(t => t.type === 'auto_recall')?.data?.memories || null,
  } : null

  const hasThoughts = thoughts && (thoughts.reasoning.length > 0 || thoughts.toolCalls.length > 0 || thoughts.autoRecall)
  const { goalName, responseSummary } = extractSummary(entry)

  // Determine display label for event type
  const eventLabel = goalName
    ? goalName
    : entry.event_type === 'GOAL_PURSUIT'
      ? 'Goal Pursuit'
      : entry.event_type

  const fullContent = entry.content_full || entry.content_preview || ''
  const fullResponse = entry.response_full || entry.response_preview || ''

  return (
    <div className={`autonomous-iteration ${isExpanded ? 'expanded' : ''}`}>
      <div className="iteration-header" onClick={() => setIsExpanded(!isExpanded)}>
        {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <div className="iteration-meta">
          <span className="iteration-time">{formatTime(entry.timestamp)}</span>
          <span className={`iteration-source ${entry.source_channel}`}>
            {sourceIcons[entry.source_channel] || <Zap size={14} />}
            {entry.source_channel}
          </span>
          <span className="iteration-number">{eventLabel}</span>
          {hasThoughts && (
            <span className="thoughts-badge" title="Has agent thoughts">
              <Brain size={12} />
              {thoughts.toolCalls.length > 0 && ` ${thoughts.toolCalls.length} tool${thoughts.toolCalls.length !== 1 ? 's' : ''}`}
            </span>
          )}
        </div>
        {!isExpanded && responseSummary && (
          <div className="iteration-summary">{responseSummary}</div>
        )}
      </div>

      {isExpanded && (
        <div className="iteration-content">
          {/* Prompt / Input section */}
          <div className="iteration-section">
            <h4>
              <Sparkles size={14} /> Prompt / Input
              {fullContent.length > 200 && (
                <button
                  className="toggle-full-btn"
                  onClick={(e) => { e.stopPropagation(); setShowFullInput(!showFullInput) }}
                >
                  {showFullInput ? 'Show less' : 'Show full'}
                </button>
              )}
            </h4>
            <div className="iteration-prompt">
              <pre>{showFullInput ? fullContent : entry.content_preview}</pre>
            </div>
          </div>

          {/* Agent Thoughts */}
          {hasThoughts && (
            <ThoughtsDisplay thoughts={thoughts} autoExpand={true} />
          )}

          {/* Response */}
          <div className="iteration-section">
            <h4>Response:</h4>
            <div className="iteration-response">
              {fullResponse}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function AutonomousPage() {
  const [sessionId, setSessionId] = useState(null)
  const [isRunning, setIsRunning] = useState(false)
  const [status, setStatus] = useState(null)
  const [activityFeed, setActivityFeed] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [sourceFilter, setSourceFilter] = useState('all')

  // Load or create session ID
  useEffect(() => {
    let storedSessionId = localStorage.getItem('autonomous_session_id')
    if (!storedSessionId) {
      storedSessionId = generateSessionId()
      localStorage.setItem('autonomous_session_id', storedSessionId)
    }
    setSessionId(storedSessionId)
  }, [])

  // Poll activity feed
  useEffect(() => {
    if (sessionId) {
      fetchActivityFeed()
      const interval = setInterval(fetchActivityFeed, 3000)
      return () => clearInterval(interval)
    }
  }, [sessionId, sourceFilter])

  // Poll status
  useEffect(() => {
    if (sessionId) {
      fetchStatus()
      const interval = setInterval(fetchStatus, 5000)
      return () => clearInterval(interval)
    }
  }, [sessionId])


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

  const fetchActivityFeed = async () => {
    try {
      const params = new URLSearchParams({ limit: '50' })
      if (sourceFilter !== 'all') params.set('source', sourceFilter)
      const response = await fetch(`/api/activity/feed?${params}`)
      const data = await response.json()
      setActivityFeed(data.entries || [])
    } catch (err) {
      console.error('Error fetching activity feed:', err)
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
        fetchActivityFeed()
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

  const formatUptime = (seconds) => {
    if (!seconds) return '0s'
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const secs = Math.floor(seconds % 60)

    if (hours > 0) return `${hours}h ${minutes}m`
    if (minutes > 0) return `${minutes}m ${secs}s`
    return `${secs}s`
  }

  const filterOptions = [
    { key: 'all', label: 'All' },
    { key: 'webui', label: 'Chat' },
    { key: 'goal', label: 'Goals' },
    { key: 'cron', label: 'Scheduled' },
    { key: 'self', label: 'Autonomous' },
  ]

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
            <h1>Activity</h1>
            <p>Agent activity and autonomous operations</p>
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
      {status && isRunning && (
        <div className="status-bar">
          <div className="status-item">
            <span className={`status-indicator running`}></span>
            <span className="status-label">Status:</span>
            <span className="status-value">Running</span>
          </div>

          <div className="status-item">
            <Clock size={16} />
            <span className="status-label">Uptime:</span>
            <span className="status-value">{formatUptime(status.uptime_seconds)}</span>
          </div>

          {status.current_focus_goal && (
            <div className="status-item focus-goal">
              <Target size={16} />
              <span className="status-label">Focus:</span>
              <span className="status-value">{status.current_focus_goal}</span>
            </div>
          )}
        </div>
      )}

      {/* Filter Chips + Controls Bar */}
      <div className="controls-bar">
        <div className="filter-chips">
          {filterOptions.map(opt => (
            <button
              key={opt.key}
              className={`filter-chip ${sourceFilter === opt.key ? 'active' : ''}`}
              onClick={() => setSourceFilter(opt.key)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <button onClick={fetchActivityFeed} className="refresh-btn">
          Refresh
        </button>
      </div>

      {/* Activity Feed */}
      <div className="autonomous-history">
        {activityFeed.length === 0 ? (
          <div className="empty-state">
            <Bot size={64} />
            <h3>No activity yet</h3>
            <p>Send a chat message or start autonomous mode to see activity here</p>
          </div>
        ) : (
          <div className="iterations-list">
            {isRunning && status && (
              <div className="currently-working">
                <div className="working-header">
                  <Loader className="spinning" size={20} />
                  <h3>Currently Working...</h3>
                </div>
                <div className="working-details">
                  {status.current_focus_goal && (
                    <p className="focus">
                      <Target size={14} />
                      Focus: {status.current_focus_goal}
                    </p>
                  )}
                </div>
              </div>
            )}

            {activityFeed.map((entry, idx) => (
              <ActivityEntry
                key={entry.id || idx}
                entry={entry}
                index={idx}
              />
            ))}

          </div>
        )}
      </div>
    </div>
  )
}

export default AutonomousPage
