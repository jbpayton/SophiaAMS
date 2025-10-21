import express from 'express';
import { WebSocketServer } from 'ws';
import cors from 'cors';
import axios from 'axios';
import { v4 as uuidv4 } from 'uuid';
import dotenv from 'dotenv';
import { OpenAI } from 'openai';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load .env from parent directory (SophiaAMS root)
dotenv.config({ path: path.join(__dirname, '..', '..', '.env') });
// Also load local .env for server-specific config
dotenv.config();

const app = express();
const PORT = process.env.PORT || 3001;
const PYTHON_API = process.env.PYTHON_API || 'http://localhost:8000';
const AGENT_API = process.env.AGENT_API || 'http://localhost:5001';

// Initialize OpenAI client with LLM config from .env
const llmClient = new OpenAI({
  baseURL: process.env.LLM_API_BASE || 'http://192.168.2.94:1234/v1',
  apiKey: process.env.LLM_API_KEY || 'not-needed'
});

const LLM_MODEL = process.env.EXTRACTION_MODEL || 'openai/gpt-oss-20b';

app.use(cors());
app.use(express.json());

// HTTP Server
const server = app.listen(PORT, () => {
  console.log(`🚀 Server running on http://localhost:${PORT}`);
  console.log(`🐍 Python API: ${PYTHON_API}`);
  console.log(`🤖 Agent API: ${AGENT_API}`);
  console.log(`🧠 LLM: ${llmClient.baseURL} (${LLM_MODEL})`);
});

// WebSocket Server
const wss = new WebSocketServer({ server });

// Store active sessions
const sessions = new Map();

// Proxy endpoints to Python API
app.get('/api/health', async (req, res) => {
  try {
    const response = await axios.get(`${PYTHON_API}/health`);
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: 'Python API unavailable' });
  }
});

app.get('/api/stats', async (req, res) => {
  try {
    const response = await axios.get(`${AGENT_API}/stats`);
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/config', async (req, res) => {
  try {
    const response = await axios.get(`${PYTHON_API}/config`);
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/config', async (req, res) => {
  try {
    const response = await axios.post(`${PYTHON_API}/config`, req.body);
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message, details: error.response?.data });
  }
});

app.get('/api/explore/topics', async (req, res) => {
  try {
    const { top_k = 10, per_topic = 4 } = req.query;
    const response = await axios.get(`${AGENT_API}/explore/topics`, {
      params: { top_k, per_topic }
    });
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/explore/entities', async (req, res) => {
  try {
    const { top_k = 10 } = req.query;
    const response = await axios.get(`${AGENT_API}/explore/entities`, {
      params: { top_k }
    });
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/explore/overview', async (req, res) => {
  try {
    const response = await axios.get(`${AGENT_API}/explore/overview`);
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/export/all_triples', async (req, res) => {
  try {
    const response = await axios.get(`${AGENT_API}/export/all_triples`);
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/query', async (req, res) => {
  try {
    const response = await axios.post(`${AGENT_API}/query`, req.body);
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/query/with_topics', async (req, res) => {
  try {
    const response = await axios.post(`${AGENT_API}/query/with_topics`, req.body);
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/ingest/document', async (req, res) => {
  try {
    console.log('📄 Document upload request:', {
      source: req.body.source,
      textLength: req.body.text?.length
    });

    const response = await axios.post(`${AGENT_API}/ingest/document`, req.body);

    console.log('✅ Document uploaded successfully:', response.data);
    res.json(response.data);
  } catch (error) {
    console.error('❌ Document upload failed:', error.message);
    res.status(500).json({
      error: error.message,
      details: error.response?.data
    });
  }
});

// Streaming chat endpoint - proxies Server-Sent Events from agent server
app.post('/api/chat/:sessionId/stream', async (req, res) => {
  const { sessionId } = req.params;

  console.log(`🌊 Streaming chat request for session ${sessionId}`);

  try {
    // Forward request to agent server's streaming endpoint
    const response = await axios.post(
      `${AGENT_API}/chat/${sessionId}/stream`,
      req.body,
      {
        responseType: 'stream',
        headers: {
          'Content-Type': 'application/json'
        }
      }
    );

    // Set headers for Server-Sent Events
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no'); // Disable nginx buffering

    // Pipe the stream directly to the response
    response.data.pipe(res);

    // Handle stream errors
    response.data.on('error', (error) => {
      console.error('❌ Stream error:', error.message);
      res.end();
    });

    // Handle client disconnect
    req.on('close', () => {
      console.log(`📴 Client disconnected from stream: ${sessionId}`);
      response.data.destroy();
    });

  } catch (error) {
    console.error('❌ Streaming request failed:', error.message);
    res.status(500).json({
      error: error.message,
      details: error.response?.data
    });
  }
});

app.post('/api/query/procedure', async (req, res) => {
  try {
    console.log('🔍 Procedure lookup request:', { goal: req.body.goal });
    const response = await axios.post(`${PYTHON_API}/query/procedure`, req.body);
    console.log('✅ Procedure lookup successful:', {
      methods: response.data.procedures?.methods?.length || 0,
      alternatives: response.data.procedures?.alternatives?.length || 0
    });
    res.json(response.data);
  } catch (error) {
    console.error('❌ Procedure lookup failed:', error.message);
    res.status(500).json({ error: error.message, details: error.response?.data });
  }
});

app.get('/api/conversation/buffer/:sessionId', async (req, res) => {
  try {
    const response = await axios.get(`${PYTHON_API}/conversation/buffer/${req.params.sessionId}`);
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/conversation/process/:sessionId', async (req, res) => {
  try {
    const response = await axios.post(`${PYTHON_API}/conversation/process/${req.params.sessionId}`, req.body);
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Goals API endpoints - proxy to agent server
app.post('/api/goals/create', async (req, res) => {
  try {
    const response = await axios.post(`${AGENT_API}/api/goals/create`, req.body);
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/goals/update', async (req, res) => {
  try {
    const response = await axios.post(`${AGENT_API}/api/goals/update`, req.body);
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/goals', async (req, res) => {
  try {
    const response = await axios.get(`${AGENT_API}/api/goals`, { params: req.query });
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/goals/progress', async (req, res) => {
  try {
    const response = await axios.get(`${AGENT_API}/api/goals/progress`, { params: req.query });
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/goals/suggestion', async (req, res) => {
  try {
    const response = await axios.get(`${AGENT_API}/api/goals/suggestion`, { params: req.query });
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// WebSocket connection handler
wss.on('connection', (ws) => {
  const sessionId = uuidv4();
  sessions.set(sessionId, { ws, messages: [] });

  console.log(`📱 Client connected: ${sessionId}`);

  ws.send(JSON.stringify({
    type: 'connected',
    sessionId,
    message: 'Connected to SophiaAMS'
  }));

  ws.on('message', async (data) => {
    try {
      const message = JSON.parse(data);
      await handleWebSocketMessage(ws, sessionId, message);
    } catch (error) {
      ws.send(JSON.stringify({
        type: 'error',
        error: error.message
      }));
    }
  });

  ws.on('close', () => {
    console.log(`📴 Client disconnected: ${sessionId}`);
    sessions.delete(sessionId);
  });
});

async function handleWebSocketMessage(ws, sessionId, message) {
  const { type, data } = message;

  switch (type) {
    case 'chat':
      await handleChatMessage(ws, sessionId, data);
      break;

    case 'query':
      await handleQuery(ws, data);
      break;

    case 'graph':
      await handleGraphRequest(ws, data);
      break;

    default:
      ws.send(JSON.stringify({ type: 'error', error: 'Unknown message type' }));
  }
}

async function handleChatMessage(ws, sessionId, data) {
  const { message, autoRetrieve = true, userName = 'User', assistantName = 'Assistant' } = data;

  console.log(`[${sessionId}] Chat message received from ${userName}:`, message);

  // Step 1: Echo user message immediately
  ws.send(JSON.stringify({
    type: 'user_message',
    content: message,
    timestamp: new Date().toISOString()
  }));

  // Step 2: Forward to Python agent server
  ws.send(JSON.stringify({
    type: 'status',
    message: 'Thinking...'
  }));

  try {
    // Call Python agent via HTTP (could also use WebSocket for streaming)
    console.log(`[${sessionId}] Forwarding to Python agent at ${AGENT_API}`);
    const agentResponse = await axios.post(`${AGENT_API}/chat/${sessionId}`, {
      content: message
    });

    const assistantMessage = agentResponse.data.response;

    console.log(`[${sessionId}] Agent response received:`, assistantMessage?.substring(0, 50) + '...');

    // Send assistant response
    ws.send(JSON.stringify({
      type: 'assistant_message',
      content: assistantMessage,
      timestamp: new Date().toISOString()
    }));

    // Step 3: Conversation is already stored by the agent server
    // The agent server with episodic memory handles all conversation storage automatically
    console.log(`[${sessionId}] Conversation stored by agent (episodic memory)...`);

    // Notify client that conversation was saved
    ws.send(JSON.stringify({
      type: 'conversation_saved',
      data: { session_id: sessionId }
    }));

  } catch (error) {
    console.error('Agent communication error:', error.message);
    ws.send(JSON.stringify({
      type: 'error',
      error: 'Failed to communicate with agent: ' + error.message
    }));
  }
}

async function handleQuery(ws, data) {
  const { text, limit = 10 } = data;

  try {
    const response = await axios.post(`${AGENT_API}/query`, {
      text,
      limit,
      return_summary: true
    });

    ws.send(JSON.stringify({
      type: 'query_result',
      data: response.data
    }));
  } catch (error) {
    ws.send(JSON.stringify({
      type: 'error',
      error: error.message
    }));
  }
}

async function handleGraphRequest(ws, data) {
  const { query, limit = 50 } = data;

  try {
    // Get triples related to query
    const response = await axios.post(`${AGENT_API}/query`, {
      text: query,
      limit,
      return_summary: false
    });

    // Transform to graph format
    const nodes = new Map();
    const links = [];

    // The query endpoint returns results as an array of [triple, metadata] directly
    if (response.data.results && Array.isArray(response.data.results)) {
      response.data.results.forEach((tripleData, idx) => {
        if (Array.isArray(tripleData) && tripleData.length >= 2) {
          const [triple, metadata] = tripleData;
          if (Array.isArray(triple) && triple.length >= 3) {
            const [subject, predicate, object] = triple;

            // Add nodes
            if (!nodes.has(subject)) {
              nodes.set(subject, { id: subject, label: subject, type: 'entity' });
            }
            if (!nodes.has(object)) {
              nodes.set(object, { id: object, label: object, type: 'entity' });
            }

            // Add link
            links.push({
              source: subject,
              target: object,
              label: predicate,
              confidence: metadata.confidence || 0
            });
          }
        }
      });
    }

    console.log(`[Graph] Generated ${nodes.size} nodes and ${links.length} links for query: ${query}`);

    ws.send(JSON.stringify({
      type: 'graph_data',
      data: {
        nodes: Array.from(nodes.values()),
        links
      }
    }));
  } catch (error) {
    console.error('Graph request error:', error.message);
    ws.send(JSON.stringify({
      type: 'error',
      error: error.message
    }));
  }
}

export default app;
