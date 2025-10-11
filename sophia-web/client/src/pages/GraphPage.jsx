import React, { useState, useEffect, useRef } from 'react'
import { useWebSocket } from '../hooks/useWebSocket'
import * as d3 from 'd3'
import { Search, Maximize2, Minimize2 } from 'lucide-react'
import './GraphPage.css'

function GraphPage() {
  const { isConnected, sendMessage, messages } = useWebSocket()
  const [query, setQuery] = useState('')
  const [rawGraphData, setRawGraphData] = useState({ nodes: [], links: [] })
  const [graphData, setGraphData] = useState({ nodes: [], links: [] })
  const [selectedNode, setSelectedNode] = useState(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [showTopics, setShowTopics] = useState(true)
  const [loading, setLoading] = useState(false)

  // Confidence thresholds
  const [tripleThreshold, setTripleThreshold] = useState(0.0)
  const [topicThreshold, setTopicThreshold] = useState(0.0)
  const [showControls, setShowControls] = useState(false)

  const svgRef = useRef(null)
  const simulationRef = useRef(null)

  useEffect(() => {
    messages.forEach((msg) => {
      if (msg.type === 'graph_data') {
        setRawGraphData(msg.data)
      }
    })
  }, [messages])

  // Filter graph data based on confidence thresholds
  useEffect(() => {
    if (!rawGraphData.links || rawGraphData.links.length === 0) {
      setGraphData(rawGraphData)
      return
    }

    // Filter links based on their type and confidence
    const filteredLinks = rawGraphData.links.filter(link => {
      if (link.type === 'topic_link') {
        return (link.confidence || 0) >= topicThreshold
      } else {
        return (link.confidence || 0) >= tripleThreshold
      }
    })

    // Get all node IDs that are connected by filtered links
    const connectedNodeIds = new Set()
    filteredLinks.forEach(link => {
      const sourceId = typeof link.source === 'object' ? link.source.id : link.source
      const targetId = typeof link.target === 'object' ? link.target.id : link.target
      connectedNodeIds.add(sourceId)
      connectedNodeIds.add(targetId)
    })

    // Filter nodes to only include those with connections
    const filteredNodes = rawGraphData.nodes.filter(node =>
      connectedNodeIds.has(node.id)
    )

    setGraphData({
      nodes: filteredNodes,
      links: filteredLinks
    })
  }, [rawGraphData, tripleThreshold, topicThreshold])

  // Auto-load some initial data when component mounts
  const hasLoadedInitialData = useRef(false)

  useEffect(() => {
    if (!isConnected || hasLoadedInitialData.current || graphData.nodes.length > 0) return

    const loadInitialData = async () => {
      try {
        // Try to get some initial data from the overview endpoint
        const res = await fetch('/api/explore/overview')
        if (res.ok) {
          const data = await res.json()

          // If we have topics, use the first topic to visualize
          if (data.topics && data.topics.length > 0) {
            const firstTopic = data.topics[0]
            setQuery(firstTopic.topic)

            // Trigger a graph request with the first topic
            sendMessage({
              type: 'graph',
              data: {
                query: firstTopic.topic,
                limit: 30
              }
            })

            hasLoadedInitialData.current = true
          }
        }
      } catch (error) {
        console.error('Failed to load initial graph data:', error)
      }
    }

    loadInitialData()
  }, [isConnected, graphData.nodes.length, sendMessage])

  useEffect(() => {
    if (!graphData.nodes.length || !svgRef.current) return

    const svg = d3.select(svgRef.current)
    const width = svgRef.current.clientWidth
    const height = svgRef.current.clientHeight

    // Clear previous graph
    svg.selectAll('*').remove()

    // Create graph container
    const g = svg.append('g')

    // Add zoom behavior
    const zoom = d3.zoom()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform)
      })

    svg.call(zoom)

    // Create force simulation
    const simulation = d3.forceSimulation(graphData.nodes)
      .force('link', d3.forceLink(graphData.links)
        .id(d => d.id)
        .distance(100))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(30))

    simulationRef.current = simulation

    // Create links with different styling for topic links vs triple links
    const link = g.append('g')
      .selectAll('line')
      .data(graphData.links)
      .join('line')
      .attr('stroke', d => d.type === 'topic_link' ? '#f59e0b' : '#444')
      .attr('stroke-width', d => {
        if (d.type === 'topic_link') return 1
        return Math.sqrt(d.confidence * 3) || 1
      })
      .attr('stroke-opacity', d => d.type === 'topic_link' ? 0.3 : 0.6)
      .attr('stroke-dasharray', d => d.type === 'topic_link' ? '3,3' : '0')

    // Create link labels
    const linkLabel = g.append('g')
      .selectAll('text')
      .data(graphData.links)
      .join('text')
      .attr('class', 'link-label')
      .attr('font-size', 10)
      .attr('fill', '#888')
      .text(d => d.label)

    // Create nodes with different styling for topics vs entities
    const node = g.append('g')
      .selectAll('circle')
      .data(graphData.nodes)
      .join('circle')
      .attr('r', d => d.type === 'topic' ? 12 : 8)
      .attr('fill', d => {
        if (selectedNode && d.id === selectedNode.id) return '#3b82f6'
        if (d.type === 'topic') return '#f59e0b' // Orange for topics
        return '#8b5cf6' // Purple for entities
      })
      .attr('stroke', '#fff')
      .attr('stroke-width', d => d.type === 'topic' ? 2 : 1.5)
      .style('cursor', 'pointer')
      .call(d3.drag()
        .on('start', dragstarted)
        .on('drag', dragged)
        .on('end', dragended))
      .on('click', (event, d) => {
        event.stopPropagation()
        setSelectedNode(d)
      })

    // Create node labels
    const nodeLabel = g.append('g')
      .selectAll('text')
      .data(graphData.nodes)
      .join('text')
      .attr('class', 'node-label')
      .attr('font-size', 12)
      .attr('fill', '#e0e0e0')
      .attr('dx', 12)
      .attr('dy', 4)
      .text(d => d.label.length > 20 ? d.label.slice(0, 20) + '...' : d.label)

    // Update positions on simulation tick
    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y)

      linkLabel
        .attr('x', d => (d.source.x + d.target.x) / 2)
        .attr('y', d => (d.source.y + d.target.y) / 2)

      node
        .attr('cx', d => d.x)
        .attr('cy', d => d.y)

      nodeLabel
        .attr('x', d => d.x)
        .attr('y', d => d.y)
    })

    // Drag functions
    function dragstarted(event) {
      if (!event.active) simulation.alphaTarget(0.3).restart()
      event.subject.fx = event.subject.x
      event.subject.fy = event.subject.y
    }

    function dragged(event) {
      event.subject.fx = event.x
      event.subject.fy = event.y
    }

    function dragended(event) {
      if (!event.active) simulation.alphaTarget(0)
      event.subject.fx = null
      event.subject.fy = null
    }

    // Click on SVG to deselect
    svg.on('click', () => setSelectedNode(null))

    return () => {
      simulation.stop()
    }
  }, [graphData, selectedNode])

  const handleSearch = async () => {
    if (!query.trim()) return
    setLoading(true)

    try {
      if (showTopics) {
        // Use enhanced endpoint that includes topics
        const res = await fetch('/api/query/with_topics', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: query,
            limit: 30,
            return_summary: false
          })
        })

        if (res.ok) {
          const data = await res.json()
          if (data.topic_graph) {
            setRawGraphData(data.topic_graph)
          }
        }
      } else {
        // Use websocket for regular graph (triples only)
        if (isConnected) {
          sendMessage({
            type: 'graph',
            data: {
              query,
              limit: 50
            }
          })
        }
      }
    } catch (error) {
      console.error('Failed to fetch graph data:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  return (
    <div className={`graph-page ${isFullscreen ? 'fullscreen' : ''}`}>
      <div className="graph-header">
        <div className="search-container">
          <Search size={20} />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Search to visualize knowledge graph..."
            className="graph-search"
          />
          <button onClick={handleSearch} disabled={loading || !query.trim()}>
            {loading ? 'Loading...' : 'Visualize'}
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px', color: '#e0e0e0', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={showTopics}
              onChange={(e) => setShowTopics(e.target.checked)}
              style={{ cursor: 'pointer' }}
            />
            <span>Show Topic Clusters</span>
          </label>

          <button
            onClick={() => setShowControls(!showControls)}
            style={{
              padding: '6px 12px',
              background: showControls ? '#3b82f6' : '#2d2d2d',
              color: '#e0e0e0',
              border: '1px solid #444',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '13px'
            }}
          >
            {showControls ? 'Hide' : 'Show'} Filters
          </button>

          <button
            className="fullscreen-toggle"
            onClick={() => setIsFullscreen(!isFullscreen)}
          >
            {isFullscreen ? <Minimize2 size={20} /> : <Maximize2 size={20} />}
          </button>
        </div>
      </div>

      {showControls && (
        <div style={{
          background: '#1e1e1e',
          border: '1px solid #444',
          borderRadius: '8px',
          padding: '16px',
          margin: '12px 0',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0, fontSize: '16px', color: '#e0e0e0' }}>Confidence Thresholds</h3>
            <button
              onClick={() => {
                setTripleThreshold(0.0)
                setTopicThreshold(0.0)
              }}
              style={{
                padding: '4px 10px',
                background: '#2d2d2d',
                color: '#e0e0e0',
                border: '1px solid #444',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '12px'
              }}
            >
              Reset
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            {/* Triple link threshold */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <label style={{ fontSize: '14px', color: '#8b5cf6', fontWeight: 'bold' }}>
                  Triple Links
                </label>
                <span style={{ fontSize: '14px', color: '#e0e0e0', fontFamily: 'monospace' }}>
                  {tripleThreshold.toFixed(2)}
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={tripleThreshold}
                onChange={(e) => setTripleThreshold(parseFloat(e.target.value))}
                style={{ width: '100%', cursor: 'pointer' }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#888' }}>
                <span>0.00 (show all)</span>
                <span>1.00 (highest only)</span>
              </div>
            </div>

            {/* Topic link threshold */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <label style={{ fontSize: '14px', color: '#f59e0b', fontWeight: 'bold' }}>
                  Topic Links
                </label>
                <span style={{ fontSize: '14px', color: '#e0e0e0', fontFamily: 'monospace' }}>
                  {topicThreshold.toFixed(2)}
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={topicThreshold}
                onChange={(e) => setTopicThreshold(parseFloat(e.target.value))}
                style={{ width: '100%', cursor: 'pointer' }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#888' }}>
                <span>0.00 (show all)</span>
                <span>1.00 (highest only)</span>
              </div>
            </div>
          </div>

          {/* Stats showing filtering effect */}
          <div style={{
            background: '#2d2d2d',
            borderRadius: '6px',
            padding: '12px',
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: '12px',
            fontSize: '13px'
          }}>
            <div>
              <div style={{ color: '#888' }}>Total Nodes</div>
              <div style={{ color: '#e0e0e0', fontWeight: 'bold', fontSize: '16px' }}>
                {rawGraphData.nodes.length}
              </div>
            </div>
            <div>
              <div style={{ color: '#888' }}>Visible Nodes</div>
              <div style={{ color: '#3b82f6', fontWeight: 'bold', fontSize: '16px' }}>
                {graphData.nodes.length}
              </div>
            </div>
            <div>
              <div style={{ color: '#888' }}>Total Links</div>
              <div style={{ color: '#e0e0e0', fontWeight: 'bold', fontSize: '16px' }}>
                {rawGraphData.links.length}
              </div>
            </div>
            <div>
              <div style={{ color: '#888' }}>Visible Links</div>
              <div style={{ color: '#3b82f6', fontWeight: 'bold', fontSize: '16px' }}>
                {graphData.links.length}
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="graph-container">
        <svg ref={svgRef} className="graph-svg"></svg>

        {selectedNode && (
          <div className="node-info">
            <h3>{selectedNode.label}</h3>
            <p className="node-type" style={{
              color: selectedNode.type === 'topic' ? '#f59e0b' : '#8b5cf6'
            }}>
              {selectedNode.type === 'topic' ? 'Topic Cluster' : 'Entity'}
              {selectedNode.triple_count && ` (${selectedNode.triple_count} triples)`}
              {selectedNode.appearances && ` (${selectedNode.appearances} appearances)`}
            </p>
            <div className="connections">
              <h4>{selectedNode.type === 'topic' ? 'Related Entities:' : 'Connections:'}</h4>
              <ul>
                {graphData.links
                  .filter(l => l.source.id === selectedNode.id || l.target.id === selectedNode.id)
                  .map((link, idx) => {
                    const isSource = link.source.id === selectedNode.id
                    const otherNode = isSource ? link.target : link.source
                    return (
                      <li key={idx} style={{
                        color: link.type === 'topic_link' ? '#f59e0b' : '#e0e0e0'
                      }}>
                        {isSource ? '→' : '←'} {link.label} {otherNode.label}
                      </li>
                    )
                  })}
              </ul>
            </div>
          </div>
        )}

        {graphData.nodes.length === 0 && (
          <div className="graph-empty">
            <Search size={48} />
            <p>Search for a topic to visualize the knowledge graph</p>
          </div>
        )}
      </div>

      <div className="graph-stats">
        <div className="stat">
          <span className="stat-value">{graphData.nodes.length}</span>
          <span className="stat-label">Nodes</span>
        </div>
        <div className="stat">
          <span className="stat-value">{graphData.links.length}</span>
          <span className="stat-label">Relationships</span>
        </div>
      </div>
    </div>
  )
}

export default GraphPage
