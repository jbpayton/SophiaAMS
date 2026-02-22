# SophiaAMS v2 — Architecture Migration Spec

## For Claude Code Implementation

**Author:** Joey Payton + Claude
**Date:** 2026-02-21
**Repo:** https://github.com/jbpayton/SophiaAMS
**Reference:** https://github.com/jbpayton/jbpayton-agent-skills-monorepo/tree/main/agent-builder
**Goal:** Migrate SophiaAMS from LangChain to a zero-dependency agent loop with Claude Code-style skills, extract the memory pipeline as reusable middleware, and make memory navigation agentic and natural.

---

## Table of Contents

1. [Current Architecture Summary](#1-current-architecture-summary)
2. [Design Philosophy](#2-design-philosophy)
3. [Target Architecture Overview](#3-target-architecture-overview)
4. [Phase 1: The Agent Loop](#4-phase-1-the-agent-loop)
5. [Phase 2: Skills Architecture](#5-phase-2-skills-architecture)
6. [Phase 3: Stream Monitor — Reusable Memory Middleware](#6-phase-3-stream-monitor)
7. [Phase 4: Agentic Memory Navigation](#7-phase-4-agentic-memory-navigation)
8. [File-by-File Migration Map](#8-file-by-file-migration-map)
9. [Implementation Order](#9-implementation-order)
10. [Testing Strategy](#10-testing-strategy)
11. [Open Questions](#11-open-questions)

---

## 1. Current Architecture Summary

### Core Stack
- **Agent Framework:** LangChain 0.1.x (create_openai_tools_agent, AgentExecutor)
- **LLM:** OpenAI-compatible local LLM via ChatOpenAI (LM Studio / Ollama)
- **Vector Store:** Qdrant (local, file-backed)
- **Embeddings:** sentence-transformers/all-MiniLM-L6-v2 (384-dim)
- **Episodic Memory:** TinyDB (JSON file store)
- **Knowledge Graph:** NetworkX + Qdrant hybrid (VectorKnowledgeGraph.py)
- **Triple Extraction:** LLM-based via OpenAI-compatible API
- **Server:** FastAPI with WebSocket + SSE streaming
- **Web UI:** React + Node.js proxy

### Key Files & Migration Impact

| File | Lines | Role | Impact |
|------|-------|------|--------|
| agent_server.py | 2534 | LangChain agent, tool defs, FastAPI, streaming, auto-recall | **HEAVY** — epicenter |
| AssociativeSemanticMemory.py | 1288 | Semantic memory: ingest, query, goals, procedures | **KEEP** |
| VectorKnowledgeGraph.py | 1390 | Qdrant triple storage, vector search, NetworkX | **KEEP** |
| EpisodicMemory.py | 432 | TinyDB episode storage, temporal queries | **KEEP** |
| PersistentConversationMemory.py | 341 | LangChain memory bridge, background consolidation | **REPLACE** |
| triple_extraction.py | 254 | LLM triple extraction (raw OpenAI client) | **KEEP** |
| prompts.py | ~400 | Extraction prompt templates | **KEEP** |
| MemoryExplorer.py | ~500 | Graph clustering, knowledge trees | **KEEP** |
| autonomous_agent.py | 520 | Self-prompting goal execution | **REWRITE** |
| searxng_tool.py | ~80 | SearXNG wrapper | **REWRITE** as skill |

### Current Data Flow

```
User Message
    |
auto_recall_memories(input)  <-- vector search, inject into prompt
    |
LangChain AgentExecutor.invoke({input, current_time, auto_recall})
    |
Agent selects tools --> query_memory, searxng_search, python_repl, etc.
    |
Response generated
    |
PersistentConversationMemory.save_context()
    |
  +-- Saves to EpisodicMemory (immediate)
  +-- Queues for semantic extraction (background, 30s idle trigger)
        |
      triple_extraction --> AssociativeSemanticMemory.ingest_text()
        |
      VectorKnowledgeGraph stores triples in Qdrant
```

---

## 2. Design Philosophy

### Three Key Principles

**1. The memory system is middleware, not the agent.**

SophiaAMS's memory (semantic, episodic, stream monitoring) should be a standalone layer that wraps around ANY agent. Swap out the LLM, swap out the agent loop, the memory still works. This solves persistent memory for any agent.

**2. Skills are files, not function registrations.**

Following Claude Code's skill format: a skill is a SKILL.md file with optional scripts and references. The agent reads it when needed using normal file access — no special [SKILL LOAD] command, no @tool decorator. The agent has code execution; it can just open files and run scripts naturally.

**3. The agent loop is zero-dependency.**

Following the agent-builder pattern: the core agent loop uses only stdlib + a single HTTP call to any OpenAI-compatible endpoint. No LangChain, no framework lock-in.

### What This Means Concretely

The **agent-builder** from the skills monorepo provides the chassis:
- LLMClient — stdlib HTTP to any /v1/chat/completions endpoint
- Agent — action loop (LLM call -> parse response -> execute actions -> feed back -> repeat)
- CodeRunner — subprocess Python execution in a workspace
- Memory — short-term conversation window with LLM summarization

We **upgrade** it with:
- SophiaAMS's semantic/episodic memory (replacing simple key-value store)
- Claude Code-style skill discovery (replacing [SKILL LOAD] commands)
- The StreamMonitor middleware (auto-recall + background extraction)
- A smarter action model where skills are accessed naturally via code execution

---

## 3. Target Architecture Overview

```
+-------------------------------------------------------------+
|                    FastAPI Server                             |
|              (HTTP, WebSocket, SSE endpoints)                 |
+-----------------------------+-------------------------------+
                              |
+-----------------------------v-------------------------------+
|                      SophiaAgent                             |
|                                                              |
|  +---------------+  +------------+  +-------------------+    |
|  | StreamMonitor |  | AgentLoop  |  | SkillLoader       |    |
|  | (middleware)  |  | (core)     |  | (Claude Code fmt) |    |
|  |               |  |            |  |                   |    |
|  | pre_process   +-->  build     +-->  descriptions()   |    |
|  | (auto-recall  |  |  prompt    |  |  in system prompt |    |
|  |  + goals)     |  |            |  |                   |    |
|  |               |  |  LLM call  |  | Agent reads full  |    |
|  | post_process  <--+            |  | SKILL.md via code |    |
|  | (episodic +   |  |  parse     |  | when it decides   |    |
|  |  extraction)  |  |  response  |  | to use a skill    |    |
|  +-------+-------+  |            |  +-------------------+    |
|          |           |  execute   |                           |
|          |           |  ```run``` |  +-------------------+    |
|          |           |  blocks    |  | CodeRunner        |    |
|          |           |            |  | (subprocess exec) |    |
|          |           |  feed back |  +-------------------+    |
|          |           |  output    |                           |
|          |           |            |  +-------------------+    |
|          |           |  repeat    |  | LLMClient         |    |
|          |           |  (max 5)   |  | (stdlib HTTP)     |    |
|          |           +------------+  +-------------------+    |
+----------+---------------------------------------------------+
           |
+----------v---------------------------------------------------+
|              Memory Infrastructure                            |
|                                                               |
|  +--------------------+  +------------------------------+     |
|  | AssociativeMemory   |  | EpisodicMemory               |    |
|  | (semantic)          |  | (temporal)                    |    |
|  |                     |  | TinyDB episodes               |    |
|  | VectorKnowledgeGraph|  | Session isolation              |    |
|  | Qdrant + NetworkX   |  +------------------------------+     |
|  | + SentenceTransfmrs |                                       |
|  +--------------------+  +------------------------------+     |
|                          | TripleExtraction              |     |
|                          | (LLM-based, background)       |     |
|                          +------------------------------+     |
+---------------------------------------------------------------+
```

---

## 4. Phase 1: The Agent Loop

### 4.1 Components From agent-builder

| Component | Source | Modifications |
|-----------|--------|---------------|
| LLMClient | agent-builder llm_client.py | Keep as-is. Stdlib HTTP. |
| CodeRunner | agent-builder code_runner.py | Keep as-is. Subprocess in workspace. |
| ConversationMemory | agent-builder memory.py | Keep short-term window + summarization. Remove simple KV long-term (replaced by SophiaAMS memory). |
| SkillLoader | agent-builder skill_loader.py | Rework for Claude Code format. Remove [SKILL LOAD] commands. |
| AgentLoop | agent-builder agent.py | Major rework: new action model, StreamMonitor hooks. |

### 4.2 The New Action Model

The agent-builder uses text-parsed commands ([MEMORY SET], [SKILL LOAD], ```run```). The new model simplifies:

1. **Code execution stays text-parsed** — ```run``` blocks are natural and universal
2. **Skills are accessed naturally via code** — agent reads SKILL.md files via ```run``` blocks, no special command
3. **Memory is accessed through Python imports in code blocks** — agent writes Python that uses the memory API

The system prompt teaches the agent:

```
You can execute Python code by wrapping it in a ```run block.

Your workspace has access to the sophia_memory module:

  from sophia_memory import memory, episodes, explorer

  # Search semantic memory
  results = memory.query("transformers")

  # Store a fact
  memory.store("Joey prefers Python over Java")

  # Query procedures
  steps = memory.query_procedure("deploy flask app")

  # Get recent memories
  recent = episodes.get_recent(hours=24)

  # Search past conversations
  convos = episodes.search("machine learning discussion")

  # Browse knowledge graph connections
  neighbors = memory.browse("Python", depth=2)

  # Get knowledge overview
  overview = explorer.knowledge_tree()
```

**Why this is better than the current approach:**
- No special command syntax to teach the LLM
- Full Python expressiveness — filter, combine, loop over results
- Memory API is importable — works from ```run``` blocks, from skill scripts, everywhere
- Skills are just files the agent reads naturally when it decides to

### 4.3 Making Memory Available in Code Blocks

When CodeRunner executes code in a subprocess, it needs access to memory. We create a thin REST shim:

**workspace_init.py** generates a `sophia_memory.py` file in the workspace that calls back to the FastAPI server's endpoints. The agent's code blocks import this module:

```python
# Generated sophia_memory.py (in workspace)
import json, urllib.request, urllib.parse

_BASE = "http://localhost:5001"

class _Memory:
    def query(self, text, limit=10):
        url = f"{_BASE}/query?text={urllib.parse.quote(text)}&limit={limit}"
        with urllib.request.urlopen(url) as r:
            return json.loads(r.read())

    def store(self, fact, source="agent_code"):
        data = json.dumps({"text": fact, "source": source}).encode()
        req = urllib.request.Request(f"{_BASE}/ingest/document",
                                     data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    def query_procedure(self, goal, limit=10):
        url = f"{_BASE}/query/procedure?goal={urllib.parse.quote(goal)}&limit={limit}"
        with urllib.request.urlopen(url) as r:
            return json.loads(r.read())

    def browse(self, entity, depth=1):
        url = f"{_BASE}/explore/entity?name={urllib.parse.quote(entity)}&depth={depth}"
        with urllib.request.urlopen(url) as r:
            return json.loads(r.read())

class _Episodes:
    def get_recent(self, hours=24, limit=10):
        url = f"{_BASE}/api/episodes/recent?hours={hours}&limit={limit}"
        with urllib.request.urlopen(url) as r:
            return json.loads(r.read())

    def search(self, query, limit=5):
        url = f"{_BASE}/api/episodes/search?q={urllib.parse.quote(query)}&limit={limit}"
        with urllib.request.urlopen(url) as r:
            return json.loads(r.read())

    def timeline(self, days=7):
        url = f"{_BASE}/api/episodes/timeline?days={days}"
        with urllib.request.urlopen(url) as r:
            return json.loads(r.read())

class _Explorer:
    def knowledge_tree(self, max_topics=10):
        url = f"{_BASE}/explore/overview"
        with urllib.request.urlopen(url) as r:
            return json.loads(r.read())

memory = _Memory()
episodes = _Episodes()
explorer = _Explorer()
```

**OPTION B: In-Process exec()** — For trusted/autonomous mode, run code in the agent process with direct memory object access (no REST round-trip). Configurable via flag.

### 4.4 Agent Loop Implementation

See agent_loop.py in Phase 1 of implementation. Key structure:

```python
class AgentLoop:
    MAX_ACTION_ROUNDS = 5

    def __init__(self, llm, workspace, skill_paths, system_prompt, ...):
        self.llm = LLMClient(...)
        self.skills = SkillLoader(skill_paths)
        self.runner = CodeRunner(workspace)
        self.conversation = ConversationMemory(...)
        self.pre_process_hook = None   # StreamMonitor attaches here
        self.post_process_hook = None  # StreamMonitor attaches here

    def chat(self, user_input, session_id="default") -> str:
        # 1. Pre-process hook: auto-recall
        context = self.pre_process_hook(user_input, session_id) if self.pre_process_hook else ""

        # 2. Summarize conversation if needed
        if self.conversation.needs_summarization():
            summary = self.llm.chat([...summarization prompt...])
            self.conversation.apply_summary(summary)

        self.conversation.add_message("user", user_input)

        # 3. Action loop (max 5 rounds)
        response = ""
        for _ in range(self.MAX_ACTION_ROUNDS):
            messages = [{"role": "system", "content": self._build_system_prompt(context)}]
            messages += self.conversation.get_messages()

            response = self.llm.chat(messages)
            self.conversation.add_message("assistant", response)

            feedback = self._execute_run_blocks(response)
            if not feedback:
                break  # No code to execute -> done
            self.conversation.add_message("user", feedback)

        # 4. Post-process hook: episodic save + extraction queue
        if self.post_process_hook:
            self.post_process_hook(session_id, user_input, response)

        return response
```

### 4.5 What Gets Deleted

- ALL LangChain imports and dependencies
- PersistentConversationMemory.py (replaced by StreamMonitor)
- PythonREPLTool and ShellTool from langchain-experimental (replaced by ```run``` blocks)
- StreamingCallbackHandler class (replaced by native output parsing)
- The create_openai_tools_agent / AgentExecutor setup

---

## 5. Phase 2: Skills Architecture

### 5.1 Claude Code Skill Format

Skills follow the Claude Code format. Each is a directory with SKILL.md:

```
skills/
+-- memory-query/
|   +-- SKILL.md
+-- memory-store/
|   +-- SKILL.md
+-- web-search/
|   +-- SKILL.md
|   +-- scripts/
|       +-- searxng_search.py
+-- web-learn/
|   +-- SKILL.md
|   +-- scripts/
|       +-- learn_from_url.py
+-- goal-management/
|   +-- SKILL.md
|   +-- scripts/
|       +-- goals.py
+-- knowledge-overview/
|   +-- SKILL.md
+-- episodic-recall/
|   +-- SKILL.md
+-- memory-browser/
|   +-- SKILL.md
+-- memory-stats/
|   +-- SKILL.md
+-- skill-creator/
|   +-- SKILL.md
+-- learned/              <-- Agent-created skills live here
```

### 5.2 How Skills Work (No Special Commands)

**Discovery:** SkillLoader scans for SKILL.md files, extracts name + description from frontmatter. These go into the system prompt as a compact list:

```
## Available Skills

- **memory-query** -- Search semantic memory for facts and relationships.
  Path: skills/memory-query/SKILL.md
- **web-search** -- Search the web via SearXNG for current information.
  Path: skills/web-search/SKILL.md
- **memory-browser** -- Navigate the knowledge graph by following connections.
  Path: skills/memory-browser/SKILL.md
- ...

To use a skill, read its SKILL.md for full instructions, then follow them.
Scripts are in each skill's scripts/ directory.
```

**Invocation:** The agent naturally decides to use a skill, reads the SKILL.md via a ```run``` block, then follows the instructions:

```
I need to search the web. Let me check the instructions.

    ```run
    with open("skills/web-search/SKILL.md") as f:
        print(f.read())
    ```

[Gets back the full SKILL.md]

Now let me run the search:

    ```run
    import subprocess, json
    result = subprocess.run(
        ["python", "skills/web-search/scripts/searxng_search.py",
         "transformer neural networks"],
        capture_output=True, text=True
    )
    print(result.stdout)
    ```
```

**Progressive disclosure:** Only descriptions in system prompt -> full SKILL.md on demand -> scripts executed as needed. Context stays small.

### 5.3 Tool-to-Skill Migration Map

| Current Tool | New Skill | How Accessed |
|-------------|-----------|--------------|
| query_memory_tool() | skills/memory-query/ | memory.query() from code |
| query_procedure_tool() | skills/memory-query/ | memory.query_procedure() from code |
| store_fact_tool() | skills/memory-store/ | memory.store() from code |
| query_recent_memory_tool() | skills/episodic-recall/ | episodes.get_recent() from code |
| get_timeline_tool() | skills/episodic-recall/ | episodes.timeline() from code |
| recall_conversation_tool() | skills/episodic-recall/ | episodes.search() from code |
| get_knowledge_overview_tool() | skills/knowledge-overview/ | explorer.knowledge_tree() from code |
| read_web_page_tool() | skills/web-read/ | Script using trafilatura |
| learn_from_web_page_tool() | skills/web-learn/ | Script: fetch + chunk + ingest |
| searxng_tool | skills/web-search/ | Script wrapping SearXNG |
| set_goal_tool() etc. | skills/goal-management/ | Script with CRUD operations |
| PythonREPLTool | Built into agent loop | ```run``` blocks ARE the REPL |
| ShellTool | subprocess from code | Agent uses subprocess in ```run``` |

### 5.4 Example Skill: memory-query/SKILL.md

```
---
name: memory-query
description: "Search semantic memory for facts, relationships, and stored knowledge. Use when recalling information from past conversations, stored facts, or learned content."
---

# Memory Query

## When to Use
- User asks "what do you know about X?"
- You need background context before responding
- Looking up facts, relationships, or procedures

## How to Use

    from sophia_memory import memory

    # Basic search
    results = memory.query("machine learning")
    for triple in results.get("triples", [])[:5]:
        subj, verb, obj = triple[0]
        score = triple[1].get("score", 0)
        print(f"  [{score:.2f}] {subj} {verb} {obj}")

    # Procedure lookup
    procedures = memory.query_procedure("deploy a flask app")
    for method in procedures.get("methods", []):
        print(f"Method: {method['description']}")

## Tips
- Keep queries short (2-5 words)
- Procedure queries work best with goal-oriented language
- Results include relevance scores -- focus on high-scoring matches
```

### 5.5 New Skills

| Skill | Purpose |
|-------|---------|
| skills/memory-browser/ | Navigate knowledge graph -- follow edges, explore neighborhoods |
| skills/memory-stats/ | Quick stats: total triples, top topics, graph metrics |
| skills/skill-creator/ | Agent can create new skills by writing SKILL.md files to skills/learned/ |

---

## 6. Phase 3: Stream Monitor

### 6.1 Core Concept

The Stream Monitor wraps the agent loop's input/output cycle. Framework-agnostic middleware:

```
User Message
    |
StreamMonitor.pre_process(message, session_id)
    -> Semantic recall (vector search)
    -> Active goals injection
    -> Returns formatted context string
    |
[Agent Loop processes with enriched context]
    |
StreamMonitor.post_process(session_id, input, output)
    -> Save to episodic memory (immediate)
    -> Queue for semantic extraction (background, 30s idle)
    |
StreamMonitor._background_consolidation()
    -> triple_extraction.py -> AssociativeSemanticMemory.ingest_text()
```

### 6.2 Implementation Summary

StreamMonitor class with:
- pre_process(user_input, session_id) -> str: vector search + goals, returns formatted context
- post_process(session_id, user_input, assistant_output): episodic save + extraction queue
- _consolidate(session_id): background triple extraction on idle
- _rotate_episode(session_id): finalize episode after 50 messages
- ingest_text(text, source): direct ingestion for batch use
- flush(session_id): force immediate consolidation

### 6.3 Plugging Into Any Agent

```python
# With our AgentLoop:
monitor = StreamMonitor(semantic_memory, episodic_memory)
agent = AgentLoop(llm=llm, workspace=workspace, skill_paths=["./skills"])
agent.pre_process_hook = monitor.pre_process
agent.post_process_hook = monitor.post_process

# With Claude Agent SDK (swap later):
context = monitor.pre_process(user_message, session_id)
options = ClaudeAgentOptions(system_prompt=f"{base_prompt}\n\n{context}")
async for msg in client.query(prompt=user_message, options=options): ...
monitor.post_process(session_id, user_message, full_response)

# With raw Anthropic API:
context = monitor.pre_process(user_message, session_id)
response = anthropic.messages.create(system=f"{base}\n\n{context}", ...)
monitor.post_process(session_id, user_message, response.content[0].text)
```

---

## 7. Phase 4: Agentic Memory Navigation

### 7.1 memory-browser Skill

Instead of just vector search, the agent can traverse the knowledge graph:

```
---
name: memory-browser
description: "Navigate the knowledge graph by following connections between concepts. Browse neighborhoods, follow edges, discover related entities. Use when exploring what connects to something rather than just searching."
---

# Memory Browser

## When to Use
- See what connects to a concept (not just search)
- Explore relationships: "what does X relate to?"
- Follow chains: X -> Y -> Z
- Understand structure of stored knowledge

## How to Use

    from sophia_memory import memory

    # See immediate connections
    connections = memory.browse("Python", depth=1)
    # Returns: {"entity": "Python", "connections": {"is_used_for": ["web dev", ...], ...}}

    # Go deeper (2 hops)
    deep = memory.browse("Python", depth=2)

## Tips
- Start with depth=1, increase only if needed
- Use AFTER memory-query to explore around a result
- Think of it like clicking through a wiki
```

### 7.2 skill-creator Skill

The agent creates new skills by writing SKILL.md files:

```
---
name: skill-creator
description: "Create new skills by writing SKILL.md files. Use when you learn a procedure that should be saved for reuse."
---

# Skill Creator

## How to Create a Skill

    import os
    skill_name = "my-new-skill"
    skill_dir = f"skills/learned/{skill_name}"
    os.makedirs(skill_dir, exist_ok=True)

    skill_content = """---
    name: {name}
    description: "{desc}"
    ---
    # Instructions here...
    """
    with open(f"{skill_dir}/SKILL.md", "w") as f:
        f.write(skill_content)

    # Also store in memory for discoverability
    from sophia_memory import memory
    memory.store(f"Learned procedure: {skill_name} -- {desc}")

## Important
- Put learned skills in skills/learned/
- Keep descriptions specific
- Include concrete examples
```

---

## 8. File-by-File Migration Map

### CREATE

| File | Purpose |
|------|---------|
| sophia_agent.py | Top-level orchestrator |
| agent_loop.py | Zero-dep agent loop (from agent-builder) |
| llm_client.py | Stdlib HTTP client (from agent-builder) |
| code_runner.py | Subprocess executor (from agent-builder) |
| conversation_memory.py | Short-term window + summarization |
| skill_loader.py | Claude Code format discovery |
| stream_monitor.py | Reusable memory middleware |
| workspace_init.py | Generates sophia_memory.py shim |
| skills/memory-query/SKILL.md | Semantic search |
| skills/memory-store/SKILL.md | Fact storage |
| skills/episodic-recall/SKILL.md | Temporal memory |
| skills/knowledge-overview/SKILL.md | Knowledge trees |
| skills/web-search/ (SKILL.md + scripts/) | SearXNG |
| skills/web-read/ (SKILL.md + scripts/) | Quick page reading |
| skills/web-learn/ (SKILL.md + scripts/) | Permanent web learning |
| skills/goal-management/ (SKILL.md + scripts/) | Goal CRUD |
| skills/memory-browser/SKILL.md | Graph navigation |
| skills/memory-stats/SKILL.md | Quick stats |
| skills/skill-creator/SKILL.md | Dynamic skill creation |

### MODIFY

| File | Changes |
|------|---------|
| agent_server.py | Strip ALL LangChain. Keep FastAPI. Delegate to sophia_agent. Add REST endpoints for memory shim. |
| autonomous_agent.py | Use AgentLoop instead of LangChain AgentExecutor |
| requirements.txt | Remove langchain deps |

### DELETE

| File | Reason |
|------|--------|
| PersistentConversationMemory.py | Replaced by stream_monitor.py |

### UNCHANGED

| File | Reason |
|------|--------|
| AssociativeSemanticMemory.py | Core memory, no framework deps |
| VectorKnowledgeGraph.py | Storage layer |
| EpisodicMemory.py | Storage layer |
| triple_extraction.py | Raw OpenAI client |
| prompts.py | Pure strings |
| MemoryExplorer.py | Pure analysis |
| schemas.py, utils.py, message_queue.py | Utilities |
| sophia-web/ | Talks to FastAPI, unchanged |

---

## 9. Implementation Order

### Phase 1: Foundation (No Breaking Changes)

```
Step 1: Create stream_monitor.py
  Extract from PersistentConversationMemory + auto_recall_memories()
  Test standalone

Step 2: Port agent-builder components
  Copy llm_client.py, code_runner.py
  Create conversation_memory.py
  Create skill_loader.py (Claude Code format)
  Test each independently

Step 3: Create agent_loop.py
  Wire: LLMClient + CodeRunner + ConversationMemory + SkillLoader
  Add pre/post hooks
  Test standalone
```

### Phase 2: Skills

```
Step 4: Create skill directories
  First 3: memory-query, memory-store, web-search
  Create workspace_init.py (sophia_memory.py shim)
  Test: agent reads skill, executes code, queries memory

Step 5: Port remaining skills one at a time
  episodic-recall, knowledge-overview, web-read, web-learn
  goal-management (with scripts/goals.py)

Step 6: Create new skills
  memory-browser, skill-creator, memory-stats
```

### Phase 3: Integration

```
Step 7: Create sophia_agent.py
  Wire AgentLoop + StreamMonitor + memory systems
  Single entry: sophia_agent.chat(session_id, message)

Step 8: Rewrite agent_server.py
  Strip LangChain, keep FastAPI endpoints
  Delegate to sophia_agent
  Add REST endpoints for sophia_memory.py shim
  Test: web UI works unchanged

Step 9: Clean up
  Delete PersistentConversationMemory.py
  Remove langchain from requirements.txt
  Update autonomous_agent.py
  Update system prompt
```

---

## 10. Testing Strategy

### Unit Tests
- test_stream_monitor.py: pre_process, post_process, consolidation
- test_agent_loop.py: action loop, code execution, max rounds
- test_skill_loader.py: discovery, frontmatter, descriptions
- test_code_runner.py: execution, timeout, path escape rejection
- test_conversation_memory.py: window, summarization

### Integration Tests
- Agent + StreamMonitor end-to-end
- Agent + Skill: reads SKILL.md, follows instructions, calls memory
- Full loop: ingest -> query -> verify

### Regression
- Existing tests/test_sophia_core.py should pass (memory unchanged)
- API endpoints return same response shapes (web UI unchanged)

---

## 11. Open Questions

### Q1: Subprocess vs In-Process Code Execution?
- Subprocess + REST bridge: safer, needs network call to memory
- In-process exec(): direct memory access, faster, less isolated
- **Recommendation:** Start subprocess, add in-process as config flag

### Q2: Claude Agent SDK Compatibility?
Architecture designed for easy swap:
- Skills already in Claude Code format
- StreamMonitor plugs in via 3 lines
- AgentLoop can be replaced entirely
- sophia_memory.py shim works anywhere

### Q3: Attention-Based Extraction (Future)?
StreamMonitor._consolidate() is the insertion point for the dual-stream attention-based association builder. For now: LLM extraction. Interface stays the same.

### Q4: Web UI Changes?
None needed if API routes stay same. Optional: /api/skills endpoint.

---

## Appendix A: New requirements.txt

```
# Core (unchanged)
python-dotenv
openai
httpx
sentence-transformers
qdrant-client
networkx
matplotlib
numpy
tinydb
beautifulsoup4
requests
tiktoken
trafilatura

# Server (unchanged)
fastapi
uvicorn[standard]
websockets

# REMOVED:
# langchain==0.1.20
# langchain-openai==0.0.8
# langchain-community==0.0.38
# langchain-experimental==0.0.58
# langchain-core==0.1.52
```

## Appendix B: Target Directory Layout

```
SophiaAMS/
+-- sophia_agent.py              # NEW: Top-level orchestrator
+-- agent_loop.py                # NEW: Zero-dep agent loop
+-- llm_client.py                # NEW: Stdlib HTTP client
+-- code_runner.py               # NEW: Subprocess executor
+-- conversation_memory.py       # NEW: Short-term window
+-- skill_loader.py              # NEW: Claude Code format discovery
+-- stream_monitor.py            # NEW: Reusable memory middleware
+-- workspace_init.py            # NEW: Generates sophia_memory.py shim
|
+-- agent_server.py              # MODIFIED: FastAPI only
+-- autonomous_agent.py          # MODIFIED: Uses AgentLoop
|
+-- AssociativeSemanticMemory.py  # UNCHANGED
+-- VectorKnowledgeGraph.py       # UNCHANGED
+-- EpisodicMemory.py             # UNCHANGED
+-- MemoryExplorer.py             # UNCHANGED
+-- triple_extraction.py          # UNCHANGED
+-- prompts.py                    # UNCHANGED
+-- schemas.py                    # UNCHANGED
+-- utils.py                      # UNCHANGED
+-- message_queue.py              # UNCHANGED
|
+-- skills/                       # NEW
|   +-- memory-query/SKILL.md
|   +-- memory-store/SKILL.md
|   +-- episodic-recall/SKILL.md
|   +-- knowledge-overview/SKILL.md
|   +-- web-search/
|   |   +-- SKILL.md
|   |   +-- scripts/searxng_search.py
|   +-- web-read/
|   |   +-- SKILL.md
|   |   +-- scripts/read_page.py
|   +-- web-learn/
|   |   +-- SKILL.md
|   |   +-- scripts/learn_from_url.py
|   +-- goal-management/
|   |   +-- SKILL.md
|   |   +-- scripts/goals.py
|   +-- memory-browser/SKILL.md
|   +-- memory-stats/SKILL.md
|   +-- skill-creator/SKILL.md
|   +-- learned/                  # Agent-created skills
|
+-- workspace/                    # Agent execution workspace
|   +-- sophia_memory.py          # Auto-generated memory shim
|
+-- sophia-web/                   # UNCHANGED
+-- tests/
+-- docs/
+-- legacy/                       # PersistentConversationMemory.py moved here
+-- data/
```

---

## Appendix C: Model Configuration

### Recommended .env

```dotenv
# LLM Configuration
LLM_API_BASE=http://192.168.2.94:1234/v1
LLM_API_KEY=not-needed
LLM_MODEL=zai-org/glm-4.7-flash
LLM_MAX_TOKENS=16000

# Task-specific models
SUMMARY_MODEL=liquid/lfm2.5-1.2b
EXTRACTION_MODEL=zai-org/glm-4.7-flash
VERBOSE_SUMMARY_MODEL=liquid/lfm2.5-1.2b
EXTRACTION_MAX_TOKENS=16000
SUMMARY_MAX_TOKENS=16000

# Embedding (unchanged)
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIM=384

# Tool URLs
SEARXNG_URL=http://192.168.2.94:8088
```

### Model Roles & Rationale

| Task | Model | Size | Why |
|------|-------|------|-----|
| **Agent conversation** | GLM-4.7-Flash | Large | Reasoning, tool-use instincts, skill-following. User-facing quality matters. |
| **Triple extraction** | GLM-4.7-Flash | Large | Structured JSON output with subject/verb/object + topics + speaker attribution. Extraction quality = memory quality = recall quality. Cascading effect. Runs in background (30s idle), not blocking conversation. |
| **Summarization** | LFM 2.5 1.2B | 1.2B | Conversation compression, context summarization. Well-understood task, small model handles it fine. |
| **Verbose summaries** | LFM 2.5 1.2B | 1.2B | Human-readable summaries. Low-stakes output, small model sufficient. |
| **Embeddings** | all-MiniLM-L6-v2 | 22M | Vector similarity for Qdrant. Fast, proven, 384-dim. No change needed. |

### Key Insight

Using Flash for extraction means you only need to load two models in LM Studio simultaneously: the 1.2B (tiny VRAM footprint) and Flash. No model-swap latency between agent and extraction since they use the same model. The 1.2B handles the lightweight summarization tasks that run less frequently.

### What to Watch

- **Context budget with GLM-4.7-Flash at 16k tokens**: System prompt (~500-800 tokens) + auto-recall (~200-500) + conversation history + skill descriptions. Monitor with the conversation summarization — it should trigger before you hit the limit. If you find context pressure, reduce `max_short_term` from 20 to 15.
- **Extraction throughput**: Each conversation turn generates 2 extraction calls (user + assistant) during consolidation. With Flash running extraction, each call may take 2-5 seconds. For normal conversation pace this is invisible (30s idle buffer). For rapid-fire turns, the queue will batch naturally.

---

## Appendix D: Project Cleanup

The repo has accumulated significant cruft from multiple development phases. This migration is a natural time to clean house.

### D.1 Dead Code & References

| Item | Issue | Action |
|------|-------|--------|
| `env_example` references Milvus (MILVUS_HOST, etc.) | Milvus was replaced by Qdrant long ago | **Remove** Milvus references from env_example, .env.docker.example |
| `env_example` references `LOCAL_TEXTGEN_API_BASE` | Duplicate of LLM_API_BASE | **Remove**, consolidate to single LLM_API_BASE |
| `env_example` references `openai/gpt-oss-20b` | Outdated model name | **Update** to current model config |
| `legacy/` directory | Contains ChatMemoryInterface.py, ConversationProcessor.py, DocumentProcessor.py, api_server.py | **Keep** legacy/ but add a README noting these are pre-v2 |
| `searxng_tool.py` | LangChain tool wrapper, replaced by skill | **Move** to legacy/ |
| `start_demo.py` | References old setup | **Review** and update or remove |
| `streamlit_client.py` | Alternate UI, likely broken after migration | **Move** to legacy/ unless actively used |

### D.2 Stray Files at Root Level

These test files and artifacts should be organized:

| File | Action |
|------|--------|
| `test_autonomous_mode.py` | **Move** to tests/ |
| `test_goal_system.py` | **Move** to tests/ |
| `test_goal_system_comprehensive.py` | **Move** to tests/ |
| `test_output.txt` | **Delete** (empty/stale test artifact) |
| `test_query.json` | **Move** to tests/fixtures/ |
| `test_request.json` | **Move** to tests/fixtures/ |

### D.3 Root-Level Documentation Sprawl

There are 6 markdown files at root level (besides README.md) that should be consolidated into docs/:

| File | Action |
|------|--------|
| `AUTONOMOUS_MODE_IMPLEMENTATION.md` | **Move** to docs/ |
| `DEPLOYMENT_SUMMARY.md` | **Move** to docs/ |
| `DOCKER_NETWORKING.md` | **Move** to docs/ |
| `INSTALLATION.md` | **Move** to docs/ |
| `README-DOCKER.md` | **Move** to docs/ |

Root level should only have README.md.

### D.4 Tests That Reference Removed Code

These tests reference LangChain or legacy modules and need updating or removal:

| Test File | References | Action |
|-----------|-----------|--------|
| `test_agent.py` | LangChain agent | **Rewrite** for new AgentLoop |
| `test_backward_compatibility.py` | Legacy API server | **Move** to legacy/ |
| `test_chat_memory_interface.py` | ChatMemoryInterface (legacy) | **Move** to legacy/ |
| `test_chat_memory_interface_demo.py` | ChatMemoryInterface (legacy) | **Move** to legacy/ |
| `test_conversation_processor.py` | ConversationProcessor (legacy) | **Move** to legacy/ |
| `test_document_processor.py` | DocumentProcessor (legacy) | **Move** to legacy/ |
| `test_bibliography_filtering.py` | Legacy filtering | **Review** — may still be relevant for VectorKnowledgeGraph |
| `test_chunk_filtering.py` | Legacy filtering | **Review** — may still be relevant |
| `test_export_triples.py` | LangChain agent | **Update** to use new endpoints |
| `test_memory_explorer.py` | LangChain imports | **Update** — MemoryExplorer itself is unchanged, just fix imports |

Tests that should still work unchanged (core memory layer):
- `test_episodic_memory.py` — EpisodicMemory unchanged
- `test_sophia_core.py` — core memory tests
- `test_triple_extraction.py` — framework-agnostic
- `test_vector_knowledge_graph.py` — storage layer
- `test_procedural_*.py` — procedural knowledge tests
- `test_web_search.py` / `test_web_search_simple.py` — may need skill path updates

### D.5 Documentation to Update

| Document | Issue | Action |
|----------|-------|--------|
| `docs/AGENT_QUICK_REFERENCE.md` | References LangChain tools | **Rewrite** for skills |
| `docs/AGENT_SERVER_GUIDE.md` | References LangChain setup | **Rewrite** |
| `docs/SOPHIA_AGENT_GUIDE.md` | References Milvus, old architecture | **Rewrite** |
| `docs/QUICKSTART_SOPHIA.md` | References Milvus, old setup | **Rewrite** |
| `docs/PROJECT_STRUCTURE.md` | Outdated file layout | **Regenerate** from Appendix B |
| `docs/IMPLEMENTATION_SUMMARY.md` | Pre-v2 architecture | **Rewrite** or archive |
| `docs/PROMPT_OVERLAP_ANALYSIS.md` | LangChain prompt analysis | **Archive** to legacy/ |
| `docs/SOPHIA_IMPLEMENTATION_SUMMARY.md` | Pre-v2 | **Archive** |
| `docs/BACKWARD_COMPATIBILITY_RESULTS.md` | Pre-v2 test results | **Archive** |
| `docs/TEST_RESULTS.md` | Pre-v2 test results | **Archive** |
| `docs/TEST_RESULTS_SOPHIA.md` | Pre-v2 test results | **Archive** |
| `docs/SETUP_COMPLETE.md` | One-time setup note | **Delete** |
| `README.md` | References LangChain throughout | **Rewrite** after migration complete |

Keep and update:
- `docs/EPISODIC_MEMORY_IMPLEMENTATION.md` — still accurate
- `docs/PROCEDURAL_KNOWLEDGE_GUIDE.md` — still accurate
- `docs/GOAL_SYSTEM_GUIDE.md` — still accurate (goals unchanged)
- `docs/AUTONOMOUS_MODE_GUIDE.md` — update for new agent loop

### D.6 Docker / Deploy Cleanup

| File | Action |
|------|--------|
| `Dockerfile` | **Update** — remove LangChain pip installs, add skill directories |
| `docker-compose.yml` | **Update** — review volume mounts for skills/ and workspace/ |
| `docker-compose.dev.yml` | **Update** to match |
| `.env.docker.example` | **Rewrite** — remove Milvus, update model config |
| `install.sh` | **Review** — may reference old deps |
| `uninstall.sh` | **Review** |
| `update.sh` | **Review** |
| `start_agent_system.bat` | **Update** for new entry point |

### D.7 env_example Rewrite

Replace the current env_example with:

```dotenv
# ==============================================================================
# SophiaAMS v2 Configuration
# ==============================================================================

# LLM Configuration (any OpenAI-compatible endpoint)
LLM_API_BASE=http://localhost:1234/v1
LLM_API_KEY=not-needed
LLM_MODEL=zai-org/glm-4.7-flash
LLM_MAX_TOKENS=16000

# Task-specific models (optional — defaults to LLM_MODEL)
SUMMARY_MODEL=liquid/lfm2.5-1.2b
EXTRACTION_MODEL=zai-org/glm-4.7-flash
VERBOSE_SUMMARY_MODEL=liquid/lfm2.5-1.2b
EXTRACTION_MAX_TOKENS=16000
SUMMARY_MAX_TOKENS=16000

# Embedding Model
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIM=384

# Web Search (optional — SearXNG instance)
SEARXNG_URL=http://localhost:8088

# Server
AGENT_PORT=5001

# Agent Settings
AGENT_TEMPERATURE=0.7
WORKSPACE_PATH=./workspace
SKILLS_PATH=./skills

# Memory Settings
MEMORY_DATA_PATH=./data
VECTOR_DB_PATH=./VectorKnowledgeGraphData
STREAM_MONITOR_IDLE_SECONDS=30
AUTO_RECALL_LIMIT=10
```

### D.8 Cleanup Implementation Order

Do cleanup DURING the migration, not as a separate pass:

1. **Before Phase 1**: Move stray test files to tests/. Move root .md files to docs/. Clean env_example.
2. **During Phase 3 (Integration)**: Move legacy test files to legacy/tests/. Update Dockerfile.
3. **After Phase 3**: Rewrite README.md. Update remaining docs. Archive outdated docs to legacy/docs/.

This way the repo is clean by the time migration is complete, not left as a TODO.

---

## Appendix E: Implementation Checklist

Quick-reference checklist for Claude Code execution:

### Pre-Migration Cleanup
- [ ] Move test_autonomous_mode.py, test_goal_system*.py to tests/
- [ ] Delete test_output.txt
- [ ] Move test_query.json, test_request.json to tests/fixtures/
- [ ] Move AUTONOMOUS_MODE_IMPLEMENTATION.md, DEPLOYMENT_SUMMARY.md, DOCKER_NETWORKING.md, INSTALLATION.md, README-DOCKER.md to docs/
- [ ] Rewrite env_example (Appendix D.7)
- [ ] Remove Milvus references from .env.docker.example

### Phase 1: Foundation
- [ ] Create stream_monitor.py
- [ ] Copy llm_client.py from agent-builder
- [ ] Copy code_runner.py from agent-builder  
- [ ] Create conversation_memory.py (from agent-builder memory.py, minus KV store)
- [ ] Create skill_loader.py (Claude Code format)
- [ ] Create agent_loop.py
- [ ] Unit test each new module

### Phase 2: Skills
- [ ] Create skills/ directory structure
- [ ] Create workspace_init.py (sophia_memory.py shim generator)
- [ ] Write skills/memory-query/SKILL.md
- [ ] Write skills/memory-store/SKILL.md
- [ ] Write skills/web-search/SKILL.md + scripts/searxng_search.py
- [ ] Write skills/episodic-recall/SKILL.md
- [ ] Write skills/knowledge-overview/SKILL.md
- [ ] Write skills/web-read/SKILL.md + scripts/read_page.py
- [ ] Write skills/web-learn/SKILL.md + scripts/learn_from_url.py
- [ ] Write skills/goal-management/SKILL.md + scripts/goals.py
- [ ] Write skills/memory-browser/SKILL.md
- [ ] Write skills/memory-stats/SKILL.md
- [ ] Write skills/skill-creator/SKILL.md
- [ ] Add /explore/entity endpoint (for memory browse)
- [ ] Add /query/batch endpoint (for batch memory queries)
- [ ] Test: agent reads skill, executes code, queries memory via shim

### Phase 3: Integration
- [ ] Create sophia_agent.py (orchestrator)
- [ ] Rewrite agent_server.py (strip LangChain, keep FastAPI, delegate to sophia_agent)
- [ ] Rewrite autonomous_agent.py (use AgentLoop)
- [ ] Move PersistentConversationMemory.py to legacy/
- [ ] Move searxng_tool.py to legacy/
- [ ] Move streamlit_client.py to legacy/ (if not actively used)
- [ ] Remove langchain from requirements.txt
- [ ] Update Dockerfile
- [ ] Update docker-compose.yml
- [ ] Move legacy tests to legacy/tests/
- [ ] Update test_agent.py for new AgentLoop
- [ ] Verify: existing memory tests pass unchanged
- [ ] Verify: web UI works unchanged
- [ ] Write Sophia system prompt (personality + memory + skills)

### Post-Migration
- [ ] Rewrite README.md
- [ ] Update docs/AGENT_QUICK_REFERENCE.md
- [ ] Update docs/AGENT_SERVER_GUIDE.md
- [ ] Archive outdated docs to legacy/docs/
- [ ] Regenerate docs/PROJECT_STRUCTURE.md
- [ ] Full end-to-end test
