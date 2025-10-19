import React, { useState, useEffect } from 'react'
import {
  Database,
  Activity,
  FileText,
  Upload,
  RefreshCw,
  Tag,
  Users,
  BarChart3,
  Download
} from 'lucide-react'
import './AdminPage.css'

function AdminPage() {
  const [stats, setStats] = useState(null)
  const [health, setHealth] = useState(null)
  const [topics, setTopics] = useState([])
  const [entities, setEntities] = useState([])
  const [overview, setOverview] = useState(null)
  const [allTriples, setAllTriples] = useState(null)
  const [loading, setLoading] = useState(false)
  const [uploadText, setUploadText] = useState('')
  const [uploadSource, setUploadSource] = useState('')
  const [config, setConfig] = useState(null)
  const [bufferSize, setBufferSize] = useState(5)
  const [minBufferTime, setMinBufferTime] = useState(30)
  const [databasePath, setDatabasePath] = useState('./VectorKnowledgeGraphData')

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 5000) // Refresh every 5 seconds
    return () => clearInterval(interval)
  }, [])

  const fetchData = async () => {
    try {
      const [statsRes, healthRes, configRes] = await Promise.all([
        fetch('/api/stats'),
        fetch('/api/health'),
        fetch('/api/config')
      ])

      if (statsRes.ok) setStats(await statsRes.json())
      if (healthRes.ok) setHealth(await healthRes.json())
      if (configRes.ok) {
        const configData = await configRes.json()
        setConfig(configData)
        if (configData.config) {
          setBufferSize(configData.config.buffer_size)
          setMinBufferTime(configData.config.min_buffer_time)
          setDatabasePath(configData.config.database_path)
        }
      }
    } catch (error) {
      console.error('Failed to fetch data:', error)
    }
  }

  const updateConfig = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          buffer_size: parseInt(bufferSize),
          min_buffer_time: parseInt(minBufferTime),
          database_path: databasePath
        })
      })

      if (res.ok) {
        const data = await res.json()
        setConfig(data)
        alert('✅ Configuration updated successfully!\n\n' + (data.note || ''))
        fetchData()
      } else {
        const errorData = await res.json().catch(() => ({}))
        alert(`❌ Update failed: ${errorData.error || 'Unknown error'}`)
      }
    } catch (error) {
      console.error('Config update failed:', error)
      alert(`❌ Update failed: ${error.message}`)
    }
    setLoading(false)
  }

  const fetchTopics = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/explore/topics?top_k=15')
      if (res.ok) {
        const data = await res.json()
        setTopics(data.topics || [])
      }
    } catch (error) {
      console.error('Failed to fetch topics:', error)
    }
    setLoading(false)
  }

  const fetchEntities = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/explore/entities?top_k=20')
      if (res.ok) {
        const data = await res.json()
        setEntities(data.entities || [])
      }
    } catch (error) {
      console.error('Failed to fetch entities:', error)
    }
    setLoading(false)
  }

  const fetchOverview = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/explore/overview')
      if (res.ok) {
        const data = await res.json()
        setOverview(data)
      }
    } catch (error) {
      console.error('Failed to fetch overview:', error)
    }
    setLoading(false)
  }

  const fetchAllTriples = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/export/all_triples')
      if (res.ok) {
        const data = await res.json()
        setAllTriples(data)
      }
    } catch (error) {
      console.error('Failed to fetch all triples:', error)
    }
    setLoading(false)
  }

  const downloadTriples = () => {
    if (!allTriples) return

    const dataStr = JSON.stringify(allTriples, null, 2)
    const dataBlob = new Blob([dataStr], { type: 'application/json' })
    const url = URL.createObjectURL(dataBlob)
    const link = document.createElement('a')
    link.href = url
    link.download = `sophia_triples_${new Date().toISOString().split('T')[0]}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  const handleUpload = async () => {
    if (!uploadText.trim()) return

    setLoading(true)
    try {
      const res = await fetch('/api/ingest/document', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: uploadText,
          source: uploadSource || 'admin_upload',
          metadata: {
            uploaded_from: 'admin_interface',
            timestamp: new Date().toISOString()
          }
        })
      })

      if (res.ok) {
        setUploadText('')
        setUploadSource('')
        fetchData()
        alert('✅ Document uploaded successfully!')
      } else {
        const errorData = await res.json().catch(() => ({}))
        console.error('Upload failed:', errorData)
        alert(`❌ Upload failed: ${errorData.error || 'Unknown error'}`)
      }
    } catch (error) {
      console.error('Upload failed:', error)
      alert(`❌ Upload failed: ${error.message}`)
    }
    setLoading(false)
  }

  return (
    <div className="admin-page">
      <div className="admin-header">
        <h2>Admin Dashboard</h2>
        <button onClick={fetchData} className="refresh-button">
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      {/* Stats Cards */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon">
            <Database size={24} />
          </div>
          <div className="stat-content">
            <div className="stat-value">{stats?.total_triples || 0}</div>
            <div className="stat-label">Total Triples</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">
            <Activity size={24} />
          </div>
          <div className="stat-content">
            <div className="stat-value">
              {health?.status === 'healthy' ? 'Online' : 'Offline'}
            </div>
            <div className="stat-label">API Status</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">
            <Tag size={24} />
          </div>
          <div className="stat-content">
            <div className="stat-value">{topics.length || '-'}</div>
            <div className="stat-label">Topics</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">
            <Users size={24} />
          </div>
          <div className="stat-content">
            <div className="stat-value">{entities.length || '-'}</div>
            <div className="stat-label">Entities</div>
          </div>
        </div>
      </div>

      {/* Configuration Section */}
      <div className="action-section">
        <h3>Memory Processing Configuration</h3>
        <div className="config-grid">
          <div className="config-item">
            <label>
              <span>Buffer Size (messages):</span>
              <input
                type="number"
                min="1"
                max="50"
                value={bufferSize}
                onChange={(e) => setBufferSize(e.target.value)}
                className="config-input"
              />
            </label>
            <p className="config-hint">Process conversation every N messages</p>
          </div>
          <div className="config-item">
            <label>
              <span>Min Buffer Time (seconds):</span>
              <input
                type="number"
                min="1"
                max="300"
                value={minBufferTime}
                onChange={(e) => setMinBufferTime(e.target.value)}
                className="config-input"
              />
            </label>
            <p className="config-hint">Or process every N seconds (whichever comes first)</p>
          </div>
          <div className="config-item">
            <label>
              <span>Database Path:</span>
              <input
                type="text"
                value={databasePath}
                onChange={(e) => setDatabasePath(e.target.value)}
                className="config-input"
                placeholder="./VectorKnowledgeGraphData"
              />
            </label>
            <p className="config-hint">Note: Requires server restart to take effect</p>
          </div>
        </div>
        <button onClick={updateConfig} disabled={loading} className="config-save-button">
          Save Configuration
        </button>
        {config && (
          <p className="config-status">
            Active Sessions: {config.active_sessions || 0}
          </p>
        )}
      </div>

      {/* Action Buttons */}
      <div className="action-section">
        <h3>Knowledge Base Exploration</h3>
        <div className="action-buttons">
          <button onClick={fetchTopics} disabled={loading}>
            <Tag size={16} />
            Load Topics
          </button>
          <button onClick={fetchEntities} disabled={loading}>
            <Users size={16} />
            Load Entities
          </button>
          <button onClick={fetchOverview} disabled={loading}>
            <BarChart3 size={16} />
            Full Overview
          </button>
          <button onClick={fetchAllTriples} disabled={loading}>
            <Database size={16} />
            View All Triples
          </button>
          {allTriples && (
            <button onClick={downloadTriples} style={{ background: '#10b981' }}>
              <Download size={16} />
              Download JSON
            </button>
          )}
        </div>
      </div>

      {/* Topics Display */}
      {topics.length > 0 && (
        <div className="data-section">
          <h3>Top Topics</h3>
          <div className="topics-grid">
            {topics.map((topic, idx) => (
              <div key={idx} className="topic-card">
                <div className="topic-header">
                  <h4>{topic.topic}</h4>
                  <span className="topic-size">{topic.size} triples</span>
                </div>
                <ul className="topic-samples">
                  {topic.samples?.slice(0, 3).map((sample, sidx) => {
                    const triple = sample[0]
                    return (
                      <li key={sidx}>
                        {triple[0]} → {triple[1]} → {triple[2]}
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Entities Display */}
      {entities.length > 0 && (
        <div className="data-section">
          <h3>Most Connected Entities</h3>
          <div className="entities-list">
            {entities.map((entity, idx) => (
              <div key={idx} className="entity-item">
                <div className="entity-name">{entity.entity}</div>
                <div className="entity-connections">
                  {entity.connections} connections
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Overview Display */}
      {overview && (
        <div className="data-section">
          <h3>Knowledge Overview</h3>
          <pre className="overview-data">
            {JSON.stringify(overview, null, 2)}
          </pre>
        </div>
      )}

      {/* All Triples Display */}
      {allTriples && (
        <div className="data-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h3>All Knowledge Triples ({allTriples.triple_count})</h3>
            <button onClick={downloadTriples} style={{ background: '#10b981', padding: '8px 16px', border: 'none', borderRadius: '6px', color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Download size={16} />
              Download JSON
            </button>
          </div>
          <p style={{ fontSize: '13px', color: '#888', marginBottom: '12px' }}>
            Exported: {new Date(allTriples.export_time).toLocaleString()}
          </p>
          <pre className="overview-data" style={{ maxHeight: '500px', overflow: 'auto' }}>
            {JSON.stringify(allTriples.triples, null, 2)}
          </pre>
        </div>
      )}

      {/* Document Upload */}
      <div className="upload-section">
        <h3>
          <Upload size={20} />
          Upload Document
        </h3>
        <div className="upload-form">
          <input
            type="text"
            value={uploadSource}
            onChange={(e) => setUploadSource(e.target.value)}
            placeholder="Source name (optional)"
            className="upload-input"
          />
          <textarea
            value={uploadText}
            onChange={(e) => setUploadText(e.target.value)}
            placeholder="Paste document text here..."
            className="upload-textarea"
            rows={10}
          />
          <button
            onClick={handleUpload}
            disabled={!uploadText.trim() || loading}
            className="upload-button"
          >
            <Upload size={16} />
            Upload to Knowledge Base
          </button>
        </div>
      </div>
    </div>
  )
}

export default AdminPage
