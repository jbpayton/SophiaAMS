import React, { useState, useEffect } from 'react'
import './AutonomousControl.css'

function AutonomousControl({ sessionId }) {
  const [isRunning, setIsRunning] = useState(false)
  const [status, setStatus] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Poll status every 5 seconds when running
  useEffect(() => {
    if (isRunning) {
      const interval = setInterval(fetchStatus, 5000)
      return () => clearInterval(interval)
    }
  }, [isRunning, sessionId])

  // Fetch initial status on mount
  useEffect(() => {
    fetchStatus()
  }, [sessionId])

  const fetchStatus = async () => {
    try {
      const response = await fetch(`/api/autonomous/status?sessionId=${sessionId}`)
      const data = await response.json()

      if (data.success && data.status) {
        setStatus(data.status)
        setIsRunning(data.status.running)
      }
    } catch (err) {
      console.error('Error fetching autonomous status:', err)
    }
  }

  const fetchHistory = async () => {
    try {
      const response = await fetch(`/api/autonomous/history?sessionId=${sessionId}&limit=10`)
      const data = await response.json()

      if (data.success) {
        setHistory(data.actions || [])
      }
    } catch (err) {
      console.error('Error fetching autonomous history:', err)
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
        console.log('✅ Autonomous mode started')
      } else {
        setError(data.message || 'Failed to start autonomous mode')
      }
    } catch (err) {
      setError(err.message)
      console.error('Error starting autonomous mode:', err)
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
        console.log('✅ Autonomous mode stopped')
        await fetchStatus()
      } else {
        setError(data.message || 'Failed to stop autonomous mode')
      }
    } catch (err) {
      setError(err.message)
      console.error('Error stopping autonomous mode:', err)
    } finally {
      setLoading(false)
    }
  }

  const toggleAutonomous = () => {
    if (isRunning) {
      handleStop()
    } else {
      handleStart()
    }
  }

  const formatUptime = (seconds) => {
    if (!seconds) return '0s'
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const secs = Math.floor(seconds % 60)

    if (hours > 0) return `${hours}h ${minutes}m ${secs}s`
    if (minutes > 0) return `${minutes}m ${secs}s`
    return `${secs}s`
  }

  const formatTimestamp = (timestamp) => {
    const date = new Date(timestamp * 1000)
    return date.toLocaleTimeString()
  }

  return (
    <div className="autonomous-control">
      <div className="autonomous-header">
        <h3>Autonomous Mode</h3>
        <div className="autonomous-toggle">
          <button
            onClick={toggleAutonomous}
            disabled={loading}
            className={`toggle-btn ${isRunning ? 'active' : ''}`}
          >
            {loading ? (
              'Loading...'
            ) : isRunning ? (
              <>
                <span className="status-indicator running"></span>
                ON
              </>
            ) : (
              <>
                <span className="status-indicator stopped"></span>
                OFF
              </>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      {status && (
        <div className="autonomous-status">
          <div className="status-grid">
            <div className="status-item">
              <span className="label">Status:</span>
              <span className={`value ${status.running ? 'running' : 'stopped'}`}>
                {status.running ? 'Running' : 'Stopped'}
              </span>
            </div>

            {status.running && (
              <>
                <div className="status-item">
                  <span className="label">Uptime:</span>
                  <span className="value">{formatUptime(status.uptime_seconds)}</span>
                </div>

                <div className="status-item">
                  <span className="label">Iterations:</span>
                  <span className="value">{status.iteration_count}</span>
                </div>

                <div className="status-item">
                  <span className="label">Actions:</span>
                  <span className="value">{status.actions_taken}</span>
                </div>

                <div className="status-item">
                  <span className="label">Actions/Hour:</span>
                  <span className="value">
                    {status.actions_this_hour} / {status.config?.max_actions_per_hour || 120}
                  </span>
                </div>

                <div className="status-item">
                  <span className="label">Queue Size:</span>
                  <span className="value">{status.queue_size}</span>
                </div>

                {status.current_focus_goal && (
                  <div className="status-item full-width">
                    <span className="label">Current Focus:</span>
                    <span className="value">{status.current_focus_goal}</span>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {isRunning && (
        <div className="autonomous-actions">
          <div className="actions-header">
            <h4>Recent Actions</h4>
            <button onClick={fetchHistory} className="refresh-btn">
              Refresh
            </button>
          </div>

          {history.length === 0 ? (
            <div className="no-actions">No actions yet...</div>
          ) : (
            <div className="actions-list">
              {history.map((action, idx) => (
                <div key={idx} className="action-item">
                  <div className="action-header">
                    <span className={`action-type ${action.source}`}>
                      {action.action_type}
                    </span>
                    <span className="action-time">
                      {action.time_str}
                    </span>
                  </div>
                  <div className="action-response">
                    {action.response.substring(0, 200)}
                    {action.response.length > 200 && '...'}
                  </div>
                  {action.tools_used && action.tools_used.length > 0 && (
                    <div className="action-tools">
                      Tools: {action.tools_used.join(', ')}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="autonomous-help">
        <p>
          When autonomous mode is ON, Sophia will periodically work on her goals independently.
          You can still send messages - they will be queued and answered when ready.
        </p>
      </div>
    </div>
  )
}

export default AutonomousControl
