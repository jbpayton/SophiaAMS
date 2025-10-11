import React, { useState, useEffect, useRef } from 'react'
import { useWebSocket } from '../hooks/useWebSocket'
import { Send, Brain, Loader, CheckCircle, AlertCircle, Settings2, Trash2 } from 'lucide-react'
import './ChatPage.css'

function ChatPage() {
  const { isConnected, sessionId, messages, sendMessage, clearMessages } = useWebSocket()
  const [input, setInput] = useState('')
  const [chatMessages, setChatMessages] = useState(() => {
    // Load chat messages from localStorage on mount
    const saved = localStorage.getItem('sophiaams_chat_messages')
    return saved ? JSON.parse(saved) : []
  })
  const [currentStatus, setCurrentStatus] = useState('')
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

  const handleSend = () => {
    if (!input.trim() || !isConnected) return

    sendMessage({
      type: 'chat',
      data: {
        message: input,
        autoRetrieve,
        userName,
        assistantName
      }
    })

    setInput('')
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

          if (msg.role === 'assistant') {
            return (
              <div key={msg.id} className="message assistant-message">
                <div className="message-content">
                  <strong>{assistantName}:</strong> {msg.content}
                </div>
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
