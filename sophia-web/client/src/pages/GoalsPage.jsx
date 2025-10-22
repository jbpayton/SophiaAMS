import React, { useState, useEffect } from 'react'
import {
  Target,
  CheckCircle2,
  Circle,
  AlertCircle,
  XCircle,
  Clock,
  TrendingUp,
  Plus,
  RefreshCw,
  Lightbulb
} from 'lucide-react'
import './GoalsPage.css'

function GoalsPage() {
  const [goals, setGoals] = useState([])
  const [progress, setProgress] = useState(null)
  const [suggestion, setSuggestion] = useState(null)
  const [loading, setLoading] = useState(false)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [filterStatus, setFilterStatus] = useState('all')

  // Form state
  const [newGoalDescription, setNewGoalDescription] = useState('')
  const [newGoalPriority, setNewGoalPriority] = useState(3)
  const [newGoalParent, setNewGoalParent] = useState('')
  const [newGoalType, setNewGoalType] = useState('standard')
  const [newIsForeverGoal, setNewIsForeverGoal] = useState(false)
  const [newDependsOn, setNewDependsOn] = useState([])

  useEffect(() => {
    fetchGoals()
    fetchProgress()
    fetchSuggestion()
  }, [filterStatus])

  const fetchGoals = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (filterStatus !== 'all') {
        params.append('status', filterStatus)
      } else {
        params.append('active_only', 'false')
      }

      const res = await fetch(`/api/goals?${params}`)
      if (res.ok) {
        const data = await res.json()
        setGoals(data.goals || [])
      }
    } catch (error) {
      console.error('Failed to fetch goals:', error)
    }
    setLoading(false)
  }

  const fetchProgress = async () => {
    try {
      const res = await fetch('/api/goals/progress')
      if (res.ok) {
        const data = await res.json()
        setProgress(data)
      }
    } catch (error) {
      console.error('Failed to fetch progress:', error)
    }
  }

  const fetchSuggestion = async () => {
    try {
      const res = await fetch('/api/goals/suggestion')
      if (res.ok) {
        const data = await res.json()
        setSuggestion(data.suggestion ? data : null)
      }
    } catch (error) {
      console.error('Failed to fetch suggestion:', error)
    }
  }

  const createGoal = async (e) => {
    e.preventDefault()
    if (!newGoalDescription.trim()) return

    setLoading(true)
    try {
      const res = await fetch('/api/goals/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description: newGoalDescription,
          priority: newGoalPriority,
          parent_goal: newGoalParent || null,
          goal_type: newGoalType,
          is_forever_goal: newIsForeverGoal,
          depends_on: newDependsOn.length > 0 ? newDependsOn : null
        })
      })

      if (res.ok) {
        setNewGoalDescription('')
        setNewGoalPriority(3)
        setNewGoalParent('')
        setNewGoalType('standard')
        setNewIsForeverGoal(false)
        setNewDependsOn([])
        setShowCreateForm(false)
        fetchGoals()
        fetchProgress()
        fetchSuggestion()
      } else {
        const error = await res.json()
        alert(`Failed to create goal: ${error.detail}`)
      }
    } catch (error) {
      console.error('Failed to create goal:', error)
      alert(`Failed to create goal: ${error.message}`)
    }
    setLoading(false)
  }

  const updateGoalStatus = async (goalDescription, newStatus) => {
    let notes = ''
    if (newStatus === 'completed' || newStatus === 'blocked') {
      notes = prompt(`Please add notes for marking this goal as ${newStatus}:`)
      if (notes === null) return // User cancelled
    }

    setLoading(true)
    try {
      const res = await fetch('/api/goals/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal_description: goalDescription,
          status: newStatus,
          ...(notes && { completion_notes: notes, blocker_reason: notes })
        })
      })

      if (res.ok) {
        fetchGoals()
        fetchProgress()
        fetchSuggestion()
      } else {
        const error = await res.json()
        alert(`Failed to update goal: ${error.detail}`)
      }
    } catch (error) {
      console.error('Failed to update goal:', error)
      alert(`Failed to update goal: ${error.message}`)
    }
    setLoading(false)
  }

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 size={18} className="status-icon completed" />
      case 'in_progress':
        return <Clock size={18} className="status-icon in-progress" />
      case 'blocked':
        return <AlertCircle size={18} className="status-icon blocked" />
      case 'cancelled':
        return <XCircle size={18} className="status-icon cancelled" />
      default:
        return <Circle size={18} className="status-icon pending" />
    }
  }

  const getPriorityColor = (priority) => {
    if (priority >= 5) return '#ef4444' // red
    if (priority >= 4) return '#f97316' // orange
    if (priority >= 3) return '#eab308' // yellow
    if (priority >= 2) return '#3b82f6' // blue
    return '#6b7280' // gray
  }

  const groupGoalsByStatus = () => {
    const grouped = {
      pending: [],
      in_progress: [],
      completed: [],
      blocked: [],
      cancelled: []
    }

    goals.forEach(goal => {
      const status = goal.status || 'pending'
      if (grouped[status]) {
        grouped[status].push(goal)
      }
    })

    return grouped
  }

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A'
    const date = new Date(timestamp * 1000)
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString()
  }

  const groupedGoals = filterStatus === 'all' ? groupGoalsByStatus() : null

  return (
    <div className="goals-page">
      <div className="goals-header">
        <h2>
          <Target size={28} style={{ verticalAlign: 'middle', marginRight: '8px' }} />
          Sophia's Goals
        </h2>
        <div className="header-actions">
          <button onClick={() => setShowCreateForm(!showCreateForm)} className="create-button">
            <Plus size={18} />
            New Goal
          </button>
          <button onClick={() => { fetchGoals(); fetchProgress(); fetchSuggestion(); }} className="refresh-button">
            <RefreshCw size={18} />
            Refresh
          </button>
        </div>
      </div>

      {/* Progress Stats */}
      {progress && (
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-icon">
              <Target size={24} />
            </div>
            <div className="stat-content">
              <div className="stat-value">{progress.total_goals}</div>
              <div className="stat-label">Total Goals</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon" style={{ background: 'rgba(34, 197, 94, 0.1)', color: '#22c55e' }}>
              <CheckCircle2 size={24} />
            </div>
            <div className="stat-content">
              <div className="stat-value">{progress.by_status?.completed || 0}</div>
              <div className="stat-label">Completed</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon" style={{ background: 'rgba(59, 130, 246, 0.1)', color: '#3b82f6' }}>
              <Clock size={24} />
            </div>
            <div className="stat-content">
              <div className="stat-value">{progress.active_count}</div>
              <div className="stat-label">Active</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon" style={{ background: 'rgba(234, 179, 8, 0.1)', color: '#eab308' }}>
              <TrendingUp size={24} />
            </div>
            <div className="stat-content">
              <div className="stat-value">{(progress.completion_rate * 100).toFixed(0)}%</div>
              <div className="stat-label">Completion Rate</div>
            </div>
          </div>
        </div>
      )}

      {/* Suggestion Card */}
      {suggestion && suggestion.goal_description && (
        <div className="suggestion-card">
          <div className="suggestion-header">
            <Lightbulb size={20} />
            <h3>Suggested Next Goal</h3>
          </div>
          <div className="suggestion-content">
            <div className="suggestion-goal">{suggestion.goal_description}</div>
            <div className="suggestion-meta">
              <span className="priority-badge" style={{ background: getPriorityColor(suggestion.priority) }}>
                Priority {suggestion.priority}
              </span>
              <span className="suggestion-reasoning">{suggestion.reasoning}</span>
            </div>
          </div>
        </div>
      )}

      {/* Create Goal Form */}
      {showCreateForm && (
        <div className="create-form-card">
          <h3>Create New Goal</h3>
          <form onSubmit={createGoal}>
            <div className="form-group">
              <label>Description</label>
              <input
                type="text"
                value={newGoalDescription}
                onChange={(e) => setNewGoalDescription(e.target.value)}
                placeholder="What do you want to accomplish?"
                className="form-input"
                required
              />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Priority (1-5)</label>
                <input
                  type="number"
                  min="1"
                  max="5"
                  value={newGoalPriority}
                  onChange={(e) => setNewGoalPriority(parseInt(e.target.value))}
                  className="form-input"
                />
              </div>
              <div className="form-group">
                <label>Goal Type</label>
                <select
                  value={newGoalType}
                  onChange={(e) => setNewGoalType(e.target.value)}
                  className="form-input"
                >
                  <option value="standard">Standard</option>
                  <option value="instrumental">Instrumental</option>
                  <option value="derived">Derived</option>
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Parent Goal (optional)</label>
                <select
                  value={newGoalParent}
                  onChange={(e) => setNewGoalParent(e.target.value)}
                  className="form-input"
                >
                  <option value="">None</option>
                  {goals.filter(g => g.status !== 'completed' && g.status !== 'cancelled').map((goal, idx) => (
                    <option key={idx} value={goal.description}>
                      {goal.description.substring(0, 50)}{goal.description.length > 50 ? '...' : ''}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group" style={{ display: 'flex', alignItems: 'center', paddingTop: '20px' }}>
                <label style={{ marginBottom: 0, marginRight: '10px' }}>
                  <input
                    type="checkbox"
                    checked={newIsForeverGoal}
                    onChange={(e) => setNewIsForeverGoal(e.target.checked)}
                    style={{ marginRight: '5px' }}
                  />
                  Forever/Ongoing Goal
                </label>
              </div>
            </div>
            <div className="form-actions">
              <button type="submit" className="submit-button" disabled={loading}>
                <Plus size={18} />
                Create Goal
              </button>
              <button type="button" onClick={() => setShowCreateForm(false)} className="cancel-button">
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Filter Tabs */}
      <div className="filter-tabs">
        <button
          className={filterStatus === 'all' ? 'active' : ''}
          onClick={() => setFilterStatus('all')}
        >
          All
        </button>
        <button
          className={filterStatus === 'pending' ? 'active' : ''}
          onClick={() => setFilterStatus('pending')}
        >
          Pending
        </button>
        <button
          className={filterStatus === 'in_progress' ? 'active' : ''}
          onClick={() => setFilterStatus('in_progress')}
        >
          In Progress
        </button>
        <button
          className={filterStatus === 'completed' ? 'active' : ''}
          onClick={() => setFilterStatus('completed')}
        >
          Completed
        </button>
        <button
          className={filterStatus === 'blocked' ? 'active' : ''}
          onClick={() => setFilterStatus('blocked')}
        >
          Blocked
        </button>
      </div>

      {/* Goals Display */}
      {loading && <div className="loading">Loading goals...</div>}

      {!loading && filterStatus === 'all' && groupedGoals && (
        <div className="goals-sections">
          {Object.entries(groupedGoals).map(([status, statusGoals]) => (
            statusGoals.length > 0 && (
              <div key={status} className="goals-section">
                <h3 className="section-title">
                  {getStatusIcon(status)}
                  {status.replace('_', ' ').toUpperCase()}
                  <span className="count">({statusGoals.length})</span>
                </h3>
                <div className="goals-list">
                  {statusGoals.map((goal, index) => (
                    <GoalCard
                      key={index}
                      goal={goal}
                      onStatusChange={updateGoalStatus}
                      getPriorityColor={getPriorityColor}
                      formatTimestamp={formatTimestamp}
                    />
                  ))}
                </div>
              </div>
            )
          ))}
        </div>
      )}

      {!loading && filterStatus !== 'all' && (
        <div className="goals-list">
          {goals.length === 0 ? (
            <div className="empty-state">No {filterStatus.replace('_', ' ')} goals found</div>
          ) : (
            goals.map((goal, index) => (
              <GoalCard
                key={index}
                goal={goal}
                onStatusChange={updateGoalStatus}
                getPriorityColor={getPriorityColor}
                formatTimestamp={formatTimestamp}
              />
            ))
          )}
        </div>
      )}
    </div>
  )
}

function GoalCard({ goal, onStatusChange, getPriorityColor, formatTimestamp }) {
  const [showDetails, setShowDetails] = useState(false)

  const getGoalTypeBadge = (type, isForever) => {
    if (isForever) {
      return <span className="type-badge forever">FOREVER</span>
    }
    if (type === 'instrumental') {
      return <span className="type-badge instrumental">INSTRUMENTAL</span>
    }
    if (type === 'derived') {
      return <span className="type-badge derived">DERIVED</span>
    }
    return null
  }

  return (
    <div className="goal-card">
      <div className="goal-main" onClick={() => setShowDetails(!showDetails)}>
        <div className="goal-header">
          <div className="goal-title">{goal.description}</div>
          <div className="goal-meta">
            <span
              className="priority-badge"
              style={{ background: getPriorityColor(goal.priority) }}
            >
              P{goal.priority}
            </span>
            {getGoalTypeBadge(goal.goal_type, goal.is_forever_goal)}
          </div>
        </div>
        {goal.parent_goal && (
          <div className="goal-parent">
            Subgoal of: {goal.parent_goal}
          </div>
        )}
      </div>

      {showDetails && (
        <div className="goal-details">
          <div className="detail-row">
            <span className="detail-label">Created:</span>
            <span className="detail-value">{formatTimestamp(goal.created)}</span>
          </div>
          {goal.updated && (
            <div className="detail-row">
              <span className="detail-label">Updated:</span>
              <span className="detail-value">{formatTimestamp(goal.updated)}</span>
            </div>
          )}
          {goal.target_date && (
            <div className="detail-row">
              <span className="detail-label">Target:</span>
              <span className="detail-value">{formatTimestamp(goal.target_date)}</span>
            </div>
          )}
          {goal.blocker_reason && (
            <div className="detail-row">
              <span className="detail-label">Blocker:</span>
              <span className="detail-value">{goal.blocker_reason}</span>
            </div>
          )}
          {goal.completion_notes && (
            <div className="detail-row">
              <span className="detail-label">Notes:</span>
              <span className="detail-value">{goal.completion_notes}</span>
            </div>
          )}
          {goal.topics && goal.topics.length > 0 && (
            <div className="detail-row">
              <span className="detail-label">Topics:</span>
              <span className="detail-value">{goal.topics.join(', ')}</span>
            </div>
          )}

          <div className="goal-actions">
            <button
              onClick={() => onStatusChange(goal.description, 'pending')}
              className="action-btn"
              disabled={goal.status === 'pending'}
            >
              Reset
            </button>
            <button
              onClick={() => onStatusChange(goal.description, 'in_progress')}
              className="action-btn primary"
              disabled={goal.status === 'in_progress'}
            >
              Start
            </button>
            <button
              onClick={() => onStatusChange(goal.description, 'completed')}
              className="action-btn success"
              disabled={goal.status === 'completed'}
            >
              Complete
            </button>
            <button
              onClick={() => onStatusChange(goal.description, 'blocked')}
              className="action-btn warning"
              disabled={goal.status === 'blocked'}
            >
              Block
            </button>
            <button
              onClick={() => onStatusChange(goal.description, 'cancelled')}
              className="action-btn danger"
              disabled={goal.status === 'cancelled'}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default GoalsPage
