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
  console.log(`🤖 LLM: ${llmClient.baseURL} (${LLM_MODEL})`);
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
    const response = await axios.get(`${PYTHON_API}/stats`);
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
    const response = await axios.get(`${PYTHON_API}/explore/topics`, {
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
    const response = await axios.get(`${PYTHON_API}/explore/entities`, {
      params: { top_k }
    });
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/explore/overview', async (req, res) => {
  try {
    const response = await axios.get(`${PYTHON_API}/explore/overview`);
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/query', async (req, res) => {
  try {
    const response = await axios.post(`${PYTHON_API}/query`, req.body);
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/query/with_topics', async (req, res) => {
  try {
    const response = await axios.post(`${PYTHON_API}/query/with_topics`, req.body);
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
    const response = await axios.post(`${PYTHON_API}/ingest/document`, req.body);
    console.log('✅ Document uploaded successfully');
    res.json(response.data);
  } catch (error) {
    console.error('❌ Document upload failed:', error.message);
    res.status(500).json({ error: error.message, details: error.response?.data });
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
  const session = sessions.get(sessionId);

  console.log(`[${sessionId}] Chat message received from ${userName}:`, message);

  // Step 1: Echo user message immediately
  ws.send(JSON.stringify({
    type: 'user_message',
    content: message,
    timestamp: new Date().toISOString()
  }));

  // Step 2: Retrieve memories if enabled
  let memoryContext = null;
  if (autoRetrieve) {
    ws.send(JSON.stringify({
      type: 'status',
      message: 'Retrieving memories...'
    }));

    try {
      const queryResponse = await axios.post(`${PYTHON_API}/query`, {
        text: message,
        limit: 10,
        session_id: sessionId,
        return_summary: true
      });

      if (queryResponse.data && queryResponse.data.results) {
        memoryContext = queryResponse.data.results;

        ws.send(JSON.stringify({
          type: 'memory_retrieved',
          data: memoryContext,
          timestamp: new Date().toISOString()
        }));
      }
    } catch (error) {
      console.error('Memory retrieval error:', error.message);
    }
  }

  // Step 3: Generate LLM response (with tool support)
  ws.send(JSON.stringify({
    type: 'status',
    message: 'Generating response...'
  }));

  try {
    // Build messages for LLM
    const llmMessages = [
      {
        role: 'system',
        content: 'You are a helpful AI assistant with a reliable memory system and procedural knowledge lookup capability.\n\nMEMORY SYSTEM:\n- You have access to retrieved factual memories from previous conversations\n- ONLY use facts that are explicitly stated in the "Retrieved Memories" section\n- If information is NOT in your retrieved memories, you must say so\n- NEVER echo, confirm, or assume information unless it appears in your memories\n\nPROCEDURAL KNOWLEDGE TOOL:\n- You have access to a "lookup_procedure" tool to retrieve learned methods and instructions\n- Use this tool when you need to know HOW to accomplish a task (e.g., "how to send API request", "how to deploy code")\n- Use it during PLANNING when figuring out how to implement something\n- The tool returns: methods, alternatives, dependencies, and code examples\n- Combine multiple procedure lookups to build complex solutions\n\nWhen to use lookup_procedure:\n- User asks you to implement or build something\n- You need to know a specific method or technique\n- You\'re planning multi-step procedures\n- You want to check if there are alternative approaches\n\nDo NOT use lookup_procedure for:\n- Simple factual questions (use retrieved memories instead)\n- General knowledge or explanations'
      }
    ];

    // Add memory context if available
    if (memoryContext && memoryContext.summary) {
      console.log(`[${sessionId}] Including memory context in LLM prompt`);
      llmMessages.push({
        role: 'system',
        content: `=== RETRIEVED MEMORIES ===\n${memoryContext.summary}\n=== END RETRIEVED MEMORIES ===\n\nIMPORTANT: The above section contains ALL the facts you remember. If something is not mentioned above, you do not remember it. Only use facts from this section.`
      });
    } else {
      console.log(`[${sessionId}] No memory context available`);
      llmMessages.push({
        role: 'system',
        content: '=== RETRIEVED MEMORIES ===\n(No relevant memories found for this query)\n=== END RETRIEVED MEMORIES ===\n\nYou have no prior knowledge about this topic. Respond helpfully but acknowledge you don\'t have specific memories about what the user is asking.'
      });
    }

    llmMessages.push({
      role: 'user',
      content: message
    });

    // Define tools available to the LLM
    const tools = [{
      type: "function",
      function: {
        name: "lookup_procedure",
        description: "Retrieve learned procedures and methods for accomplishing tasks. Use when planning how to implement something you've been taught. Returns methods, alternatives, dependencies, and examples.",
        parameters: {
          type: "object",
          properties: {
            goal: {
              type: "string",
              description: "The task or goal to accomplish (e.g., 'send POST request', 'deploy application', 'schedule recurring tasks')"
            }
          },
          required: ["goal"]
        }
      }
    }];

    // Call LLM with tools enabled
    console.log(`[${sessionId}] Calling LLM with tool support...`);
    let completion = await llmClient.chat.completions.create({
      model: LLM_MODEL,
      messages: llmMessages,
      tools: tools,
      tool_choice: "auto",  // LLM decides when to use tools
      temperature: 0.7,
      max_tokens: 800
    });

    let assistantMessage = completion.choices[0].message;

    // Handle tool calls if the LLM requested them
    if (assistantMessage.tool_calls && assistantMessage.tool_calls.length > 0) {
      console.log(`[${sessionId}] LLM requested ${assistantMessage.tool_calls.length} tool call(s)`);

      // Add the assistant's message with tool calls to history
      llmMessages.push(assistantMessage);

      // Execute each tool call
      for (const toolCall of assistantMessage.tool_calls) {
        if (toolCall.function.name === 'lookup_procedure') {
          const args = JSON.parse(toolCall.function.arguments);
          console.log(`[${sessionId}] Looking up procedure: ${args.goal}`);

          // Notify user via WebSocket
          ws.send(JSON.stringify({
            type: 'tool_use',
            tool: 'lookup_procedure',
            goal: args.goal
          }));

          try {
            // Call our procedure lookup endpoint
            const procResponse = await axios.post(`http://localhost:${PORT}/api/query/procedure`, {
              goal: args.goal,
              include_alternatives: true,
              include_examples: true,
              include_dependencies: true,
              limit: 10
            });

            // Format procedure results for LLM
            const procedures = procResponse.data.procedures;
            const formattedResult = {
              goal: args.goal,
              methods: procedures.methods?.map(([triple, meta]) => ({
                method: triple[2],
                relationship: triple[1],
                confidence: meta.confidence
              })),
              alternatives: procedures.alternatives?.map(([triple, meta]) => ({
                method: triple[2],
                confidence: meta.confidence
              })),
              dependencies: procedures.dependencies?.map(([triple, meta]) => ({
                requires: triple[2],
                confidence: meta.confidence
              })),
              examples: procedures.examples?.map(([triple, meta]) => ({
                example: triple[2],
                confidence: meta.confidence
              }))
            };

            // Add tool response to messages
            llmMessages.push({
              role: "tool",
              tool_call_id: toolCall.id,
              content: JSON.stringify(formattedResult, null, 2)
            });

            console.log(`[${sessionId}] Procedure lookup completed: ${procedures.total_found} results`);
          } catch (error) {
            console.error(`[${sessionId}] Procedure lookup failed:`, error.message);
            llmMessages.push({
              role: "tool",
              tool_call_id: toolCall.id,
              content: JSON.stringify({ error: "Procedure lookup failed" })
            });
          }
        }
      }

      // Call LLM again with tool results
      console.log(`[${sessionId}] Calling LLM with tool results...`);
      completion = await llmClient.chat.completions.create({
        model: LLM_MODEL,
        messages: llmMessages,
        temperature: 0.7,
        max_tokens: 800
      });

      assistantMessage = completion.choices[0].message.content;
    } else {
      assistantMessage = assistantMessage.content;
    }

    console.log(`[${sessionId}] Final LLM response received:`, assistantMessage?.substring(0, 50) + '...');

    // Send assistant response
    ws.send(JSON.stringify({
      type: 'assistant_message',
      content: assistantMessage,
      timestamp: new Date().toISOString()
    }));

    // Step 4: Ingest conversation (buffer for later processing)
    console.log(`[${sessionId}] Adding conversation to buffer...`);
    const ingestResponse = await axios.post(`${PYTHON_API}/ingest/conversation`, {
      messages: [
        { role: 'user', content: message, name: userName },
        { role: 'assistant', content: assistantMessage, name: assistantName }
      ],
      session_id: sessionId,
      speaker_names: { user: userName, assistant: assistantName },
      force_process: false
    });

    const wasProcessed = ingestResponse.data.processed;
    const bufferedCount = ingestResponse.data.buffered_messages;

    console.log(`[${sessionId}] Buffer status: ${bufferedCount} messages buffered, processed: ${wasProcessed}`);

    // Send appropriate status message
    if (wasProcessed) {
      ws.send(JSON.stringify({
        type: 'status',
        message: `Memory processed! (${bufferedCount} messages)`
      }));
    } else {
      ws.send(JSON.stringify({
        type: 'status',
        message: `Buffered (${bufferedCount} messages)`
      }));
    }

    ws.send(JSON.stringify({
      type: 'conversation_saved',
      data: ingestResponse.data
    }));

  } catch (error) {
    console.error('LLM generation error:', error.message);
    ws.send(JSON.stringify({
      type: 'error',
      error: 'Failed to generate response'
    }));
  }
}

async function handleQuery(ws, data) {
  const { text, limit = 10 } = data;

  try {
    const response = await axios.post(`${PYTHON_API}/query`, {
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
    const response = await axios.post(`${PYTHON_API}/query`, {
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
