import React, { useState, useEffect, useRef } from 'react'
import { useWebSocket } from '../hooks/useWebSocket'
import { Send, Brain, Loader, CheckCircle, AlertCircle, Settings2, Trash2, ChevronDown, ChevronRight, Sparkles, Wrench } from 'lucide-react'
import AutonomousControl from '../components/AutonomousControl'
import './ChatPage.css'

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
                  <div key={idx} className="reasoning-item">{text}</div>
                ))}
              </div>
            </div>
          )}

          {thoughts.toolCalls.length > 0 && (
            <div className="thoughts-section">
              <h4>Tool Calls:</h4>
              {thoughts.toolCalls.map((toolCall) => {
                const isToolExpanded = expandedTools.has(toolCall.id)
                return (
                  <div key={toolCall.id} className={`tool-call ${toolCall.status}`}>
                    <button
                      className="tool-call-header"
                      onClick={() => toggleTool(toolCall.id)}
                    >
                      {isToolExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      <Wrench size={14} />
                      <span className="tool-name">{toolCall.tool}</span>
                      <span className={`tool-status ${toolCall.status}`}>
                        {toolCall.status === 'running' && '⏳'}
                        {toolCall.status === 'completed' && '✓'}
                        {toolCall.status === 'error' && '✗'}
                      </span>
                    </button>

                    {isToolExpanded && (
                      <div className="tool-call-details">
                        <div className="tool-input">
                          <strong>Input:</strong>
                          <pre>{JSON.stringify(toolCall.input, null, 2)}</pre>
                        </div>
                        {toolCall.output && (
                          <div className="tool-output">
                            <strong>Output:</strong>
                            <pre>{typeof toolCall.output === 'string' ? toolCall.output : JSON.stringify(toolCall.output, null, 2)}</pre>
                          </div>
                        )}
                        {toolCall.error && (
                          <div className="tool-error">
                            <strong>Error:</strong>
                            <pre>{toolCall.error}</pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ChatPage() {
  const { isConnected, sessionId, messages, sendMessage, clearMessages } = useWebSocket()
  const [input, setInput] = useState('')
  const [chatMessages, setChatMessages] = useState(() => {
    // Load chat messages from localStorage on mount
    const saved = localStorage.getItem('sophiaams_chat_messages')
    return saved ? JSON.parse(saved) : []
  })
  const [currentStatus, setCurrentStatus] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [currentThoughts, setCurrentThoughts] = useState(null)
  const [autoRetrieve, setAutoRetrieve] = useState(() => {
    const saved = localStorage.getItem('sophiaams_auto_retrieve')
    return saved !== null ? JSON.parse(saved) : true
  })
  const [userName, setUserName] = useState(() => {
    return localStorage.getItem('sophiaams_user_name') || 'User'
  })
  const [assistantName, setAssistantName] = useState(() => {
    return localStorage.getItem('sophiaams_assistant_name') || 'Assistant'
  })
  const [showSettings, setShowSettings] = useState(false)
  const [bufferStatus, setBufferStatus] = useState(null)
  const [config, setConfig] = useState({ buffer_size: 5, min_buffer_time: 30 })
  const messagesEndRef = useRef(null)
  const processedMessageIds = useRef(new Set())

  useEffect(() => {
    // Only process new messages we haven't seen before
    messages.forEach((msg, index) => {
      const msgId = `${msg.type}-${index}-${msg.timestamp || Date.now()}`
      if (processedMessageIds.current.has(msgId)) {
        return // Skip already processed messages
      }
      processedMessageIds.current.add(msgId)

      // Process the message
      switch (msg.type) {
        case 'user_message':
          setChatMessages((prev) => [
            ...prev,
            {
              id: Date.now(),
              role: 'user',
              content: msg.content,
              timestamp: msg.timestamp
            }
          ])
          break

        case 'status':
          setCurrentStatus(msg.message)
          break

        case 'memory_retrieved':
          setChatMessages((prev) => [
            ...prev,
            {
              id: Date.now(),
              role: 'memory',
              data: msg.data,
              timestamp: msg.timestamp
            }
          ])
          setCurrentStatus('')
          break

        case 'assistant_message':
          setChatMessages((prev) => [
            ...prev,
            {
              id: Date.now(),
              role: 'assistant',
              content: msg.content,
              timestamp: msg.timestamp
            }
          ])
          setCurrentStatus('')
          break

        case 'tool_use':
          // Show that the assistant is looking up procedures
          setChatMessages((prev) => [
            ...prev,
            {
              id: Date.now(),
              role: 'tool',
              tool: msg.tool,
              goal: msg.goal,
              timestamp: new Date().toISOString()
            }
          ])
          break

        case 'conversation_saved':
          // Optionally show a subtle indicator
          break

        case 'error':
          setChatMessages((prev) => [
            ...prev,
            {
              id: Date.now(),
              role: 'error',
              content: msg.error,
              timestamp: new Date().toISOString()
            }
          ])
          setCurrentStatus('')
          break
      }
    })
  }, [messages])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages, currentStatus])

  // Save chat messages to localStorage whenever they change
  useEffect(() => {
    localStorage.setItem('sophiaams_chat_messages', JSON.stringify(chatMessages))
  }, [chatMessages])

  // Save settings to localStorage
  useEffect(() => {
    localStorage.setItem('sophiaams_auto_retrieve', JSON.stringify(autoRetrieve))
  }, [autoRetrieve])

  useEffect(() => {
    localStorage.setItem('sophiaams_user_name', userName)
  }, [userName])

  useEffect(() => {
    localStorage.setItem('sophiaams_assistant_name', assistantName)
  }, [assistantName])

  // Fetch config on mount
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const res = await fetch('/api/config')
        if (res.ok) {
          const data = await res.json()
          if (data.config) {
            setConfig(data.config)
          }
        }
      } catch (error) {
        console.error('Failed to fetch config:', error)
      }
    }
    fetchConfig()
  }, [])

  // Fetch buffer status periodically
  useEffect(() => {
    if (!sessionId) return

    const fetchBufferStatus = async () => {
      try {
        const res = await fetch(`/api/conversation/buffer/${sessionId}`)
        if (res.ok) {
          const data = await res.json()
          setBufferStatus(data)
        }
      } catch (error) {
        console.error('Failed to fetch buffer status:', error)
      }
    }

    fetchBufferStatus()
    const interval = setInterval(fetchBufferStatus, 3000) // Update every 3 seconds

    return () => clearInterval(interval)
  }, [sessionId])

  const handleSend = async () => {
    if (!input.trim() || !sessionId || isStreaming) return

    const userMessage = input
    setInput('')
    setIsStreaming(true)

    // Add user message immediately
    const userMsg = {
      id: Date.now(),
      role: 'user',
      content: userMessage,
      timestamp: new Date().toISOString()
    }
    setChatMessages(prev => [...prev, userMsg])

    // Initialize thoughts tracking for this response
    const thoughts = {
      reasoning: [],
      toolCalls: [],
      status: 'thinking'
    }
    setCurrentThoughts(thoughts)

    try {
      // Call streaming endpoint using fetch (EventSource doesn't support POST)
      const response = await fetch(`/api/chat/${sessionId}/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          content: userMessage
        })
      })

      if (!response.ok) {
        throw new Error('Streaming request failed')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // Keep last incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            try {
              const event = JSON.parse(data)
              handleStreamEvent(event, thoughts)
            } catch (e) {
              console.error('Failed to parse event:', e)
            }
          }
        }
      }

      // Finalize thoughts
      setCurrentThoughts(null)

    } catch (error) {
      console.error('Streaming error:', error)
      setChatMessages(prev => [...prev, {
        id: Date.now(),
        role: 'error',
        content: error.message,
        timestamp: new Date().toISOString()
      }])
    } finally {
      setIsStreaming(false)
    }
  }

  const handleStreamEvent = (event, thoughts) => {
    console.log('Stream event:', event.type, event.data)

    switch (event.type) {
      case 'auto_recall':
        // Store auto-recalled memories in thoughts
        thoughts.autoRecall = event.data.memories
        setCurrentThoughts({...thoughts})
        break

      case 'thinking':
        setCurrentStatus('Agent is thinking...')
        break

      case 'reasoning':
        thoughts.reasoning.push(event.data.text)
        setCurrentThoughts({...thoughts})
        break

      case 'tool_start':
        // Extract reasoning from log if available
        if (event.data.log && event.data.log.trim()) {
          // Parse the agent's reasoning from the log
          const logLines = event.data.log.split('\n').filter(line => line.trim())
          logLines.forEach(line => {
            if (line && !line.includes('Action:') && !line.includes('Action Input:')) {
              thoughts.reasoning.push(line.trim())
            }
          })
        }

        const toolCall = {
          id: Date.now() + Math.random(),
          tool: event.data.tool,
          input: event.data.input,
          status: 'running',
          startTime: event.timestamp
        }
        thoughts.toolCalls.push(toolCall)
        setCurrentThoughts({...thoughts})
        setCurrentStatus(`Using tool: ${event.data.tool}`)
        break

      case 'tool_end':
        const lastTool = thoughts.toolCalls[thoughts.toolCalls.length - 1]
        if (lastTool) {
          lastTool.output = event.data.output
          lastTool.status = 'completed'
          lastTool.endTime = event.timestamp
        }
        setCurrentThoughts({...thoughts})
        break

      case 'tool_error':
        const errorTool = thoughts.toolCalls[thoughts.toolCalls.length - 1]
        if (errorTool) {
          errorTool.error = event.data.error
          errorTool.status = 'error'
        }
        setCurrentThoughts({...thoughts})
        break

      case 'final_response':
        // Add assistant response with embedded thoughts
        setChatMessages(prev => [...prev, {
          id: Date.now(),
          role: 'assistant',
          content: event.data.response,
          thoughts: {...thoughts},
          timestamp: new Date().toISOString()
        }])
        setCurrentStatus('')
        break

      case 'error':
        setChatMessages(prev => [...prev, {
          id: Date.now(),
          role: 'error',
          content: event.data.message,
          timestamp: new Date().toISOString()
        }])
        setCurrentStatus('')
        break
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleClearChat = () => {
    if (confirm('Clear all chat messages? This cannot be undone.')) {
      setChatMessages([])
      processedMessageIds.current.clear()
      localStorage.removeItem('sophiaams_chat_messages')
    }
  }

  return (
    <div className="chat-page">
      <div className="chat-header">
        <div className="header-left">
          <Brain size={24} />
          <h2>Memory-Enabled Chat</h2>
        </div>
        <div className="header-right">
          <label className="toggle">
            <input
              type="checkbox"
              checked={autoRetrieve}
              onChange={(e) => setAutoRetrieve(e.target.checked)}
            />
            <span>Auto Memory Retrieval</span>
          </label>
          <button
            className="settings-button"
            onClick={() => setShowSettings(!showSettings)}
            title="Settings"
          >
            <Settings2 size={16} />
          </button>
          <button
            className="settings-button"
            onClick={handleClearChat}
            title="Clear Chat"
            style={{ marginLeft: '8px' }}
          >
            <Trash2 size={16} />
          </button>
          <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
            {isConnected ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
            <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
          </div>
          {sessionId && (
            <div className="session-id">Session: {sessionId.slice(0, 8)}...</div>
          )}
          {bufferStatus && bufferStatus.exists && bufferStatus.buffered_messages > 0 && (
            <div className="buffer-status" title={`Processing in ${Math.max(0, Math.ceil(config.min_buffer_time - bufferStatus.time_since_update))}s or after ${Math.max(0, config.buffer_size - bufferStatus.buffered_messages)} more messages`}>
              <Brain size={14} />
              <span>{bufferStatus.buffered_messages} buffered</span>
            </div>
          )}
        </div>
      </div>

      {/* Settings Panel */}
      {showSettings && (
        <div className="settings-panel">
          <h3>Chat Settings</h3>
          <div className="settings-form">
            <label>
              <span>Your Name:</span>
              <input
                type="text"
                value={userName}
                onChange={(e) => setUserName(e.target.value)}
                placeholder="User"
              />
            </label>
            <label>
              <span>Assistant Name:</span>
              <input
                type="text"
                value={assistantName}
                onChange={(e) => setAssistantName(e.target.value)}
                placeholder="Assistant"
              />
            </label>
          </div>

          {/* Autonomous Mode Control */}
          {sessionId && (
            <AutonomousControl sessionId={sessionId} />
          )}
        </div>
      )}

      <div className="chat-messages">
        {chatMessages.map((msg) => {
          if (msg.role === 'user') {
            return (
              <div key={msg.id} className="message user-message">
                <div className="message-content">
                  <strong>{userName}:</strong> {msg.content}
                </div>
              </div>
            )
          }

          if (msg.role === 'memory') {
            return (
              <div key={msg.id} className="message memory-message">
                <div className="memory-header">
                  <Brain size={16} />
                  <span>Retrieved Memories</span>
                </div>
                {msg.data.summary && (
                  <div className="memory-summary">{msg.data.summary}</div>
                )}
                {msg.data.triples && msg.data.triples.length > 0 && (
                  <details className="memory-details">
                    <summary>View {msg.data.triples.length} related facts</summary>
                    <ul>
                      {msg.data.triples.slice(0, 5).map((tripleData, idx) => {
                        if (Array.isArray(tripleData) && tripleData.length >= 2) {
                          const [triple, metadata] = tripleData
                          return (
                            <li key={idx}>
                              {triple[0]} {triple[1]} {triple[2]}
                              <span className="confidence">
                                ({(metadata.confidence * 100).toFixed(0)}%)
                              </span>
                            </li>
                          )
                        }
                        return null
                      })}
                    </ul>
                  </details>
                )}
              </div>
            )
          }

          if (msg.role === 'tool') {
            return (
              <div key={msg.id} className="message tool-message">
                <div className="tool-header">
                  <Settings2 size={16} />
                  <span>Looking up procedure: {msg.goal}</span>
                </div>
              </div>
            )
          }

          if (msg.role === 'assistant') {
            return (
              <div key={msg.id} className="message assistant-message">
                <div className="message-content">
                  <strong>{assistantName}:</strong> {msg.content}
                </div>
                {msg.thoughts && (msg.thoughts.reasoning.length > 0 || msg.thoughts.toolCalls.length > 0) && (
                  <ThoughtsDisplay thoughts={msg.thoughts} />
                )}
              </div>
            )
          }

          if (msg.role === 'error') {
            return (
              <div key={msg.id} className="message error-message">
                <AlertCircle size={16} />
                <span>Error: {msg.content}</span>
              </div>
            )
          }

          return null
        })}

        {currentStatus && (
          <div className="status-indicator">
            <Loader className="spinner" size={16} />
            <span>{currentStatus}</span>
          </div>
        )}

        {/* Show current thoughts while thinking */}
        {currentThoughts && (currentThoughts.reasoning.length > 0 || currentThoughts.toolCalls.length > 0) && (
          <div className="message assistant-message thinking">
            <div className="message-content">
              <strong>Agent is thinking...</strong>
            </div>
            <ThoughtsDisplay thoughts={currentThoughts} autoExpand={true} />
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-container">
        <textarea
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Type your message..."
          rows={3}
          disabled={!isConnected}
        />
        <button
          className="send-button"
          onClick={handleSend}
          disabled={!input.trim() || !isConnected}
        >
          <Send size={20} />
        </button>
      </div>
    </div>
  )
}

export default ChatPage
