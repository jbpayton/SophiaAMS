import React, { useState, useEffect } from 'react'
import { Sliders, User, Wand2, Save, RefreshCw, Loader, ChevronDown, ChevronRight, Key, Package, Zap, CheckCircle, XCircle, AlertCircle } from 'lucide-react'
import './SettingsPage.css'

// ============================================================================
// Personality Editor Section
// ============================================================================

function PersonalityEditor() {
  const [presets, setPresets] = useState([])
  const [currentPersonality, setCurrentPersonality] = useState('')
  const [selectedPreset, setSelectedPreset] = useState('')
  const [editText, setEditText] = useState('')
  const [refining, setRefining] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)

  useEffect(() => {
    fetchPresets()
    fetchCurrent()
  }, [])

  const fetchPresets = async () => {
    try {
      const res = await fetch('/api/personality/presets')
      const data = await res.json()
      setPresets(data.presets || [])
    } catch (err) {
      console.error('Failed to fetch presets:', err)
    }
  }

  const fetchCurrent = async () => {
    try {
      const res = await fetch('/api/personality/current')
      const data = await res.json()
      setCurrentPersonality(data.personality || '')
      setEditText(data.personality || '')
    } catch (err) {
      console.error('Failed to fetch current personality:', err)
    }
  }

  const handleRefine = async () => {
    if (!selectedPreset) return
    setRefining(true)
    setMessage(null)

    try {
      const res = await fetch('/api/personality/refine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          archetype_id: selectedPreset,
          agent_name: 'Sophia'
        })
      })
      const data = await res.json()
      if (data.refined) {
        setEditText('Your personality:\n' + data.refined)
        setMessage({ type: 'success', text: 'Personality refined! Review and save below.' })
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Failed to refine: ' + err.message })
    } finally {
      setRefining(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setMessage(null)

    try {
      const res = await fetch('/api/personality/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ personality_text: editText })
      })
      const data = await res.json()
      if (data.success) {
        setCurrentPersonality(editText)
        setMessage({ type: 'success', text: 'Personality saved and applied!' })
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Failed to save: ' + err.message })
    } finally {
      setSaving(false)
    }
  }

  const handlePresetSelect = (presetId) => {
    setSelectedPreset(presetId)
    const preset = presets.find(p => p.id === presetId)
    if (preset && preset.system_prompt_snippet) {
      setEditText('Your personality:\n' + preset.system_prompt_snippet)
    }
  }

  return (
    <div className="settings-section">
      <div className="section-header">
        <User size={20} />
        <h2>Personality</h2>
      </div>

      <div className="personality-editor">
        <div className="preset-selector">
          <label>Start from archetype:</label>
          <div className="preset-options">
            {presets.filter(p => p.id !== 'custom').map(preset => (
              <button
                key={preset.id}
                className={`preset-btn ${selectedPreset === preset.id ? 'active' : ''}`}
                onClick={() => handlePresetSelect(preset.id)}
              >
                <strong>{preset.name}</strong>
                <span>{preset.description}</span>
              </button>
            ))}
          </div>

          {selectedPreset && (
            <button
              className="refine-btn"
              onClick={handleRefine}
              disabled={refining}
            >
              {refining ? (
                <><Loader className="spinning" size={16} /> Refining...</>
              ) : (
                <><Wand2 size={16} /> Refine with AI</>
              )}
            </button>
          )}
        </div>

        <div className="personality-text-editor">
          <label>Personality instructions:</label>
          <textarea
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            rows={12}
            placeholder="Your personality:&#10;- Trait 1&#10;- Trait 2&#10;..."
          />
        </div>

        {message && (
          <div className={`settings-message ${message.type}`}>
            {message.text}
          </div>
        )}

        <div className="personality-actions">
          <button
            className="save-btn"
            onClick={handleSave}
            disabled={saving || editText === currentPersonality}
          >
            {saving ? (
              <><Loader className="spinning" size={16} /> Saving...</>
            ) : (
              <><Save size={16} /> Save & Apply</>
            )}
          </button>
          <button
            className="reset-btn"
            onClick={() => setEditText(currentPersonality)}
            disabled={editText === currentPersonality}
          >
            Reset
          </button>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Skills Configuration Section
// ============================================================================

function SkillsConfig() {
  const [skills, setSkills] = useState([])
  const [loading, setLoading] = useState(true)
  const [expandedSkills, setExpandedSkills] = useState(new Set())
  const [envValues, setEnvValues] = useState({})
  const [scanning, setScanning] = useState(null)
  const [testing, setTesting] = useState(null)
  const [testResults, setTestResults] = useState({})
  const [message, setMessage] = useState(null)

  useEffect(() => {
    fetchSkills()
  }, [])

  const fetchSkills = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/skills')
      const data = await res.json()
      setSkills(data.skills || [])

      // Build initial env values map
      const values = {}
      for (const skill of (data.skills || [])) {
        for (const [varName, value] of Object.entries(skill.configured_values || {})) {
          values[varName] = value
        }
      }
      setEnvValues(values)
    } catch (err) {
      console.error('Failed to fetch skills:', err)
    } finally {
      setLoading(false)
    }
  }

  const toggleSkill = (name) => {
    setExpandedSkills(prev => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const handleRescan = async (skillName) => {
    setScanning(skillName)
    try {
      await fetch(`/api/skills/${skillName}/scan`)
      await fetchSkills()
      setMessage({ type: 'success', text: `Rescanned ${skillName}` })
    } catch (err) {
      setMessage({ type: 'error', text: `Scan failed: ${err.message}` })
    } finally {
      setScanning(null)
    }
  }

  const handleSaveEnvVar = async (varName) => {
    try {
      await fetch('/api/skills/env', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ var_name: varName, value: envValues[varName] || '' })
      })
      setMessage({ type: 'success', text: `Saved ${varName}` })
      // Clear test results for skills using this var and refresh to pick up status reset
      setTestResults({})
      await fetchSkills()
    } catch (err) {
      setMessage({ type: 'error', text: `Failed to save: ${err.message}` })
    }
  }

  const handleTestSkill = async (skillName) => {
    setTesting(skillName)
    try {
      const res = await fetch(`/api/skills/${skillName}/test`)
      const data = await res.json()
      setTestResults(prev => ({ ...prev, [skillName]: data.results || {} }))
      await fetchSkills()
      setMessage({
        type: data.status === 'verified' ? 'success' : 'error',
        text: data.status === 'verified'
          ? `${skillName}: All checks passed`
          : `${skillName}: Health check failed`
      })
    } catch (err) {
      setMessage({ type: 'error', text: `Test failed: ${err.message}` })
    } finally {
      setTesting(null)
    }
  }

  // Collect all env vars across skills to detect shared ones
  const varToSkills = {}
  for (const skill of skills) {
    for (const v of (skill.env_vars || [])) {
      if (!varToSkills[v]) varToSkills[v] = []
      varToSkills[v].push(skill.name)
    }
  }

  const statusLabels = {
    no_env: null,
    unconfigured: 'Needs config',
    configured: 'Not tested',
    verified: 'Verified',
    error: 'Error',
  }

  const renderStatusBadge = (skill) => {
    if (!skill.status || skill.status === 'no_env') return null
    return (
      <span className={`skill-status skill-status-${skill.status}`}>
        <span className="skill-status-dot" />
        {statusLabels[skill.status]}
      </span>
    )
  }

  if (loading) {
    return (
      <div className="settings-section">
        <div className="section-header">
          <Package size={20} />
          <h2>Skills</h2>
        </div>
        <div className="loading-state"><Loader className="spinning" size={24} /> Loading skills...</div>
      </div>
    )
  }

  return (
    <div className="settings-section">
      <div className="section-header">
        <Package size={20} />
        <h2>Skills</h2>
        <span className="section-count">{skills.length} skills</span>
      </div>

      {message && (
        <div className={`settings-message ${message.type}`}>
          {message.text}
        </div>
      )}

      <div className="skills-list">
        {skills.map(skill => (
          <div key={skill.name} className="skill-card">
            <div className="skill-header" onClick={() => toggleSkill(skill.name)}>
              {expandedSkills.has(skill.name) ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              <div className="skill-info">
                <strong>{skill.name}</strong>
                <span className="skill-desc">{skill.description}</span>
              </div>
              {renderStatusBadge(skill)}
              {skill.env_vars && skill.env_vars.length > 0 && (
                <span className="env-badge">
                  <Key size={12} /> {skill.env_vars.length} env var{skill.env_vars.length !== 1 ? 's' : ''}
                </span>
              )}
            </div>

            {expandedSkills.has(skill.name) && (
              <div className="skill-details">
                {skill.env_vars && skill.env_vars.length > 0 ? (
                  <div className="env-vars-list">
                    {skill.env_vars.map(varName => {
                      const varResult = testResults[skill.name]?.[varName]
                      return (
                        <div key={varName} className="env-var-row">
                          <div className="env-var-name">
                            <Key size={14} />
                            <code>{varName}</code>
                            {varToSkills[varName] && varToSkills[varName].length > 1 && (
                              <span className="shared-badge" title={`Used by: ${varToSkills[varName].join(', ')}`}>
                                shared
                              </span>
                            )}
                            {varResult && (
                              varResult.ok
                                ? <span className="var-check var-check-ok"><CheckCircle size={14} /></span>
                                : <span className="var-check var-check-fail" title={varResult.error}><XCircle size={14} /></span>
                            )}
                          </div>
                          <div className="env-var-input">
                            <input
                              type={varName.toLowerCase().includes('key') || varName.toLowerCase().includes('secret') || varName.toLowerCase().includes('token') ? 'password' : 'text'}
                              value={envValues[varName] || ''}
                              onChange={(e) => setEnvValues(prev => ({ ...prev, [varName]: e.target.value }))}
                              placeholder="Not set"
                            />
                            <button
                              className="save-var-btn"
                              onClick={() => handleSaveEnvVar(varName)}
                            >
                              <Save size={14} />
                            </button>
                          </div>
                          {varResult && !varResult.ok && varResult.error && (
                            <div className="var-error-msg">
                              <AlertCircle size={12} /> {varResult.error}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <p className="no-env-vars">No environment variables detected</p>
                )}

                <div className="skill-actions">
                  {skill.env_vars && skill.env_vars.length > 0 && (
                    <button
                      className="test-btn"
                      onClick={() => handleTestSkill(skill.name)}
                      disabled={testing === skill.name}
                    >
                      {testing === skill.name ? (
                        <><Loader className="spinning" size={14} /> Testing...</>
                      ) : (
                        <><Zap size={14} /> Test Connection</>
                      )}
                    </button>
                  )}
                  <button
                    className="rescan-btn"
                    onClick={() => handleRescan(skill.name)}
                    disabled={scanning === skill.name}
                  >
                    {scanning === skill.name ? (
                      <><Loader className="spinning" size={14} /> Scanning...</>
                    ) : (
                      <><RefreshCw size={14} /> Rescan</>
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}

        {skills.length === 0 && (
          <div className="empty-skills">
            <Package size={48} style={{ opacity: 0.3 }} />
            <p>No skills found. Add skills to the <code>./skills</code> directory.</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ============================================================================
// Settings Page
// ============================================================================

function SettingsPage() {
  return (
    <div className="settings-page">
      <div className="settings-header">
        <Sliders size={32} />
        <div>
          <h1>Settings</h1>
          <p>Configure personality, skills, and agent behavior</p>
        </div>
      </div>

      <div className="settings-content">
        <PersonalityEditor />
        <SkillsConfig />
      </div>
    </div>
  )
}

export default SettingsPage
