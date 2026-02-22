import React, { useState, useEffect } from 'react'
import { Brain, ChevronRight, ChevronLeft, Check, Loader, AlertCircle, Sparkles, BookOpen, Heart, Pencil, Wifi } from 'lucide-react'
import './SetupPage.css'

const API_BASE = ''

const STEPS = ['Welcome', 'Identity', 'LLM Configuration', 'Personality', 'Review & Launch']

function SetupPage({ onComplete }) {
  const [step, setStep] = useState(0)
  const [config, setConfig] = useState({
    agent_name: 'Sophia',
    user_name: '',
    llm_base_url: 'http://localhost:1234/v1',
    llm_api_key: 'not-needed',
    llm_model: '',
    llm_max_tokens: 16000,
    personality_preset: 'magician',
    custom_personality: '',
    telegram_token: '',
    searxng_url: '',
  })
  const [presets, setPresets] = useState([])
  const [llmStatus, setLlmStatus] = useState(null) // null | 'testing' | 'success' | 'error'
  const [llmError, setLlmError] = useState('')
  const [llmReply, setLlmReply] = useState('')
  const [availableModels, setAvailableModels] = useState([])
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')

  useEffect(() => {
    fetch(`${API_BASE}/api/setup/presets`)
      .then(r => r.json())
      .then(data => setPresets(data.presets || []))
      .catch(() => {})
  }, [])

  const updateConfig = (key, value) => {
    setConfig(prev => ({ ...prev, [key]: value }))
  }

  const testLLM = async () => {
    setLlmStatus('testing')
    setLlmError('')
    setLlmReply('')
    try {
      const resp = await fetch(`${API_BASE}/api/setup/validate-llm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: config.llm_base_url,
          api_key: config.llm_api_key,
          model: config.llm_model,
        }),
      })
      const data = await resp.json()
      if (data.success) {
        setLlmStatus('success')
        setLlmReply(data.reply)
        if (data.models && data.models.length > 0) {
          setAvailableModels(data.models)
          if (!config.llm_model) {
            updateConfig('llm_model', data.models[0])
          }
        }
      } else {
        setLlmStatus('error')
        setLlmError(data.error || 'Connection failed')
      }
    } catch (e) {
      setLlmStatus('error')
      setLlmError(e.message)
    }
  }

  const handleSubmit = async () => {
    setSubmitting(true)
    setSubmitError('')
    try {
      const resp = await fetch(`${API_BASE}/api/setup/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      const data = await resp.json()
      if (data.success) {
        onComplete()
      } else {
        setSubmitError(data.error || 'Setup failed')
        setSubmitting(false)
      }
    } catch (e) {
      setSubmitError(e.message)
      setSubmitting(false)
    }
  }

  const canAdvance = () => {
    switch (step) {
      case 1: return config.agent_name.trim() && config.user_name.trim()
      case 2: return config.llm_base_url.trim()
      case 3: return config.personality_preset !== 'custom' || config.custom_personality.trim()
      default: return true
    }
  }

  const presetIcons = {
    magician: <Sparkles size={24} />,
    scholar: <BookOpen size={24} />,
    companion: <Heart size={24} />,
    custom: <Pencil size={24} />,
  }

  const renderStep = () => {
    switch (step) {
      case 0:
        return (
          <div className="setup-step welcome-step">
            <Brain size={64} className="welcome-icon" />
            <h2>Welcome to SophiaAMS</h2>
            <p>
              Let's set up your AI agent. This wizard will walk you through
              configuring your LLM connection, choosing a personality, and
              personalizing your experience.
            </p>
            <p className="setup-note">
              This should only take a couple of minutes.
            </p>
          </div>
        )

      case 1:
        return (
          <div className="setup-step">
            <h2>Identity</h2>
            <p>What should your agent be called, and what's your name?</p>
            <div className="form-group">
              <label>Agent Name</label>
              <input
                type="text"
                value={config.agent_name}
                onChange={e => updateConfig('agent_name', e.target.value)}
                placeholder="Sophia"
              />
            </div>
            <div className="form-group">
              <label>Your Name</label>
              <input
                type="text"
                value={config.user_name}
                onChange={e => updateConfig('user_name', e.target.value)}
                placeholder="Your name"
              />
            </div>
          </div>
        )

      case 2:
        return (
          <div className="setup-step">
            <h2>LLM Configuration</h2>
            <p>Connect to any OpenAI-compatible API (LM Studio, Ollama, OpenAI, etc.)</p>
            <div className="form-group">
              <label>API Base URL</label>
              <input
                type="text"
                value={config.llm_base_url}
                onChange={e => updateConfig('llm_base_url', e.target.value)}
                placeholder="http://localhost:1234/v1"
              />
            </div>
            <div className="form-group">
              <label>API Key</label>
              <input
                type="text"
                value={config.llm_api_key}
                onChange={e => updateConfig('llm_api_key', e.target.value)}
                placeholder="not-needed (for local LLMs)"
              />
            </div>
            <div className="form-group">
              <label>Model {availableModels.length > 0 && `(${availableModels.length} available)`}</label>
              {availableModels.length > 0 ? (
                <select
                  value={config.llm_model}
                  onChange={e => updateConfig('llm_model', e.target.value)}
                >
                  {availableModels.map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={config.llm_model}
                  onChange={e => updateConfig('llm_model', e.target.value)}
                  placeholder="Model name (test connection to auto-detect)"
                />
              )}
            </div>
            <div className="form-group">
              <label>Max Tokens</label>
              <input
                type="number"
                value={config.llm_max_tokens}
                onChange={e => updateConfig('llm_max_tokens', parseInt(e.target.value) || 4096)}
                min={256}
                max={128000}
              />
            </div>
            <button
              className={`test-btn ${llmStatus === 'success' ? 'success' : llmStatus === 'error' ? 'error' : ''}`}
              onClick={testLLM}
              disabled={llmStatus === 'testing'}
            >
              {llmStatus === 'testing' ? (
                <><Loader size={16} className="spin" /> Testing...</>
              ) : llmStatus === 'success' ? (
                <><Check size={16} /> Connected</>
              ) : llmStatus === 'error' ? (
                <><AlertCircle size={16} /> Retry</>
              ) : (
                <><Wifi size={16} /> Test Connection</>
              )}
            </button>
            {llmStatus === 'success' && llmReply && (
              <div className="test-result success">
                LLM responded: "{llmReply}"
              </div>
            )}
            {llmStatus === 'error' && (
              <div className="test-result error">
                {llmError}
              </div>
            )}
          </div>
        )

      case 3:
        return (
          <div className="setup-step">
            <h2>Personality</h2>
            <p>Choose an archetype that defines your agent's conversational style.</p>
            <div className="preset-grid">
              {presets.map(p => (
                <div
                  key={p.id}
                  className={`preset-card ${config.personality_preset === p.id ? 'selected' : ''}`}
                  onClick={() => updateConfig('personality_preset', p.id)}
                >
                  <div className="preset-icon">{presetIcons[p.id] || <Sparkles size={24} />}</div>
                  <h3>{p.name}</h3>
                  <p>{p.description}</p>
                  {p.capabilities.length > 0 && (
                    <div className="preset-caps">
                      {p.capabilities.map(c => <span key={c} className="cap-tag">{c}</span>)}
                    </div>
                  )}
                </div>
              ))}
            </div>
            {config.personality_preset === 'custom' && (
              <div className="form-group" style={{ marginTop: 20 }}>
                <label>Custom Personality Description</label>
                <textarea
                  value={config.custom_personality}
                  onChange={e => updateConfig('custom_personality', e.target.value)}
                  placeholder="Describe your agent's personality traits, communication style, and behavior..."
                  rows={6}
                />
              </div>
            )}
          </div>
        )

      case 4:
        const selectedPreset = presets.find(p => p.id === config.personality_preset)
        return (
          <div className="setup-step">
            <h2>Review & Launch</h2>
            <p>Here's a summary of your configuration:</p>
            <div className="review-grid">
              <div className="review-item">
                <span className="review-label">Agent Name</span>
                <span className="review-value">{config.agent_name}</span>
              </div>
              <div className="review-item">
                <span className="review-label">Your Name</span>
                <span className="review-value">{config.user_name}</span>
              </div>
              <div className="review-item">
                <span className="review-label">LLM Endpoint</span>
                <span className="review-value">{config.llm_base_url}</span>
              </div>
              <div className="review-item">
                <span className="review-label">Model</span>
                <span className="review-value">{config.llm_model || '(auto-detect)'}</span>
              </div>
              <div className="review-item">
                <span className="review-label">Personality</span>
                <span className="review-value">{selectedPreset?.name || config.personality_preset}</span>
              </div>
            </div>
            {submitError && (
              <div className="test-result error">{submitError}</div>
            )}
          </div>
        )

      default:
        return null
    }
  }

  return (
    <div className="setup-container">
      <div className="setup-card">
        {/* Progress bar */}
        <div className="setup-progress">
          {STEPS.map((s, i) => (
            <div key={s} className={`progress-step ${i <= step ? 'active' : ''} ${i < step ? 'done' : ''}`}>
              <div className="progress-dot">
                {i < step ? <Check size={12} /> : i + 1}
              </div>
              <span className="progress-label">{s}</span>
            </div>
          ))}
        </div>

        {/* Step content */}
        <div className="setup-content">
          {renderStep()}
        </div>

        {/* Navigation */}
        <div className="setup-nav">
          {step > 0 && (
            <button className="nav-btn back" onClick={() => setStep(step - 1)}>
              <ChevronLeft size={16} /> Back
            </button>
          )}
          <div className="nav-spacer" />
          {step < STEPS.length - 1 ? (
            <button
              className="nav-btn next"
              onClick={() => setStep(step + 1)}
              disabled={!canAdvance()}
            >
              Next <ChevronRight size={16} />
            </button>
          ) : (
            <button
              className="nav-btn launch"
              onClick={handleSubmit}
              disabled={submitting}
            >
              {submitting ? (
                <><Loader size={16} className="spin" /> Saving...</>
              ) : (
                <><Sparkles size={16} /> Start {config.agent_name}</>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default SetupPage
