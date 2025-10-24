# Autonomous Mode Guide

## Overview

Autonomous Mode allows Sophia to work independently on her goals without requiring constant user prompts. When enabled, Sophia will periodically:

1. Review her active goals (especially instrumental/forever goals)
2. Decide what action to take next
3. Execute tools to make progress (research, create subgoals, etc.)
4. Queue and respond to user messages when they arrive

This creates a truly autonomous AI agent that can pursue long-term objectives while remaining responsive to user interactions.

## Architecture

### Core Components

#### 1. Message Queue (`message_queue.py`)

Thread-safe message queue system for managing user inputs during autonomous operation.

**Features:**
- Per-session queues using `collections.deque`
- Priority handling (user messages always processed first)
- Thread-safe operations with `threading.Lock()`
- Status tracking and queue size monitoring

**Key Methods:**
```python
queue.enqueue(session_id, message, priority="high")  # Add message
queue.dequeue(session_id)                            # Get next message
queue.has_messages(session_id)                       # Check for pending
queue.get_queue_size(session_id)                     # Count pending
queue.peek(session_id)                               # Look without removing
queue.clear(session_id)                              # Clear all messages
```

#### 2. Autonomous Agent (`autonomous_agent.py`)

Background thread that runs the autonomous loop.

**Features:**
- Self-prompting based on active goals
- Automatic goal execution
- User message queue integration
- Configurable intervals and safety controls
- Rate limiting (max actions per hour)
- Error handling (max consecutive errors)

**Key Classes:**

```python
class AutonomousConfig:
    enabled = False
    interval_seconds = 30
    max_actions_per_hour = 120
    allowed_tools = [...]
    auto_create_derived_goals = True
    max_consecutive_errors = 3

class AutonomousAgent:
    def start(session_id)          # Start autonomous mode
    def stop()                      # Stop autonomous mode
    def is_running()                # Check if running
    def get_status()                # Get current status
    def get_recent_actions(limit)   # Get action history
```

#### 3. API Endpoints (`agent_server.py`)

FastAPI endpoints for controlling autonomous mode:

**Endpoints:**
```
POST /api/autonomous/start?session_id=...
POST /api/autonomous/stop?session_id=...
GET  /api/autonomous/status?session_id=...
POST /api/autonomous/queue-message?session_id=...
GET  /api/autonomous/history?session_id=...&limit=10
```

#### 4. Frontend UI (`AutonomousControl.jsx`)

React component for autonomous mode control:

**Features:**
- ON/OFF toggle with visual indicators
- Real-time status display (uptime, iterations, actions)
- Recent actions history
- Queue size monitoring
- Current focus goal display

## How It Works

### Autonomous Loop Flow

```
1. Check rate limiting
   ↓
2. Check for user messages in queue
   ↓ (if no messages)
3. Generate self-prompt based on goals
   ↓
4. Execute agent with prompt
   ↓
5. Log action and results
   ↓
6. Sleep for interval_seconds
   ↓
7. Repeat
```

### Self-Prompting Logic

The autonomous agent generates prompts using:

1. **Active Goals**: Retrieved via `memory.get_active_goals_for_prompt()`
   - Instrumental/forever goals (always included)
   - High-priority goals (priority 4-5)
   - All ongoing/pending goals

2. **Goal Suggestions**: From `memory.suggest_next_goal()`
   - Considers priorities and dependencies
   - Boosts derived goals (+20 score)
   - Provides reasoning for suggestions

3. **Recent Actions**: Last 3-5 autonomous actions
   - Shows what was done recently
   - Prevents repetitive actions
   - Builds on previous progress

**Example Generated Prompt:**
```
I am working autonomously on my goals. Let me reflect on my current situation and decide what to do next.

MY ACTIVE GOALS:
- [★★★★★] Continuously improve programming skills [INSTRUMENTAL/ONGOING] (ONGOING)
- [★★★★★] Learn about transformers (PENDING)
- [★★★★] Research attention mechanisms (PENDING)

SUGGESTED NEXT GOAL: Learn about transformers
Reasoning: Highest priority pending goal with no dependencies

RECENT AUTONOMOUS ACTIONS:
- autonomous_action: Created subgoal for studying backpropagation...
- autonomous_action: Researched transformer architectures...

What should I do next to make progress on my goals? I can:
1. Create new derived goals from my instrumental objectives
2. Research topics related to my current goals
3. Update goal status as I make progress
4. Break down complex goals into smaller subgoals
5. Set new goals that align with my instrumental objectives

Let me think about the most valuable action to take right now and execute it.

IMPORTANT: Be concrete and take a specific action. Don't just think about it - actually do something (create a goal, research a topic, etc.).
```

### Message Queue Priority

When autonomous mode is running and a user sends a message:

1. Message is added to queue with `priority="high"`
2. On next iteration, agent checks queue **before** self-prompting
3. User message is processed immediately
4. Autonomous mode continues after responding

This ensures **user messages always take priority** over autonomous actions.

## Usage

### Starting Autonomous Mode

**Via Web UI:**
1. Open the Chat page
2. Click the Settings icon
3. Toggle "Autonomous Mode" ON
4. Monitor status and activity in the expanded panel

**Via API:**
```bash
curl -X POST "http://localhost:3001/api/autonomous/start" \
  -H "Content-Type: application/json" \
  -d '{"sessionId": "your-session-id"}'
```

**Response:**
```json
{
  "success": true,
  "message": "Autonomous mode started",
  "session_id": "your-session-id",
  "status": {
    "running": true,
    "iteration_count": 0,
    "actions_taken": 0,
    "uptime_seconds": 0,
    "config": {
      "interval": 30,
      "max_actions_per_hour": 120
    }
  }
}
```

### Stopping Autonomous Mode

**Via Web UI:**
1. Toggle "Autonomous Mode" OFF in settings panel

**Via API:**
```bash
curl -X POST "http://localhost:3001/api/autonomous/stop" \
  -H "Content-Type: application/json" \
  -d '{"sessionId": "your-session-id"}'
```

### Checking Status

**Via API:**
```bash
curl "http://localhost:3001/api/autonomous/status?sessionId=your-session-id"
```

**Response:**
```json
{
  "success": true,
  "status": {
    "running": true,
    "session_id": "your-session-id",
    "current_focus_goal": "Learn about transformers",
    "iteration_count": 15,
    "actions_taken": 8,
    "actions_this_hour": 8,
    "uptime_seconds": 450,
    "queue_size": 0,
    "consecutive_errors": 0,
    "config": {
      "interval": 30,
      "max_actions_per_hour": 120
    }
  }
}
```

### Viewing Action History

**Via API:**
```bash
curl "http://localhost:3001/api/autonomous/history?sessionId=your-session-id&limit=5"
```

**Response:**
```json
{
  "success": true,
  "session_id": "your-session-id",
  "action_count": 5,
  "actions": [
    {
      "session_id": "your-session-id",
      "action_type": "autonomous_action",
      "prompt": "I am working autonomously on my goals...",
      "response": "I will research transformers using web search...",
      "source": "autonomous",
      "goals_affected": [],
      "tools_used": ["searxng_search", "learn_from_web_page"],
      "timestamp": 1729631534.123,
      "time_str": "2025-10-22 21:32:14"
    }
  ]
}
```

### Queueing Messages

When autonomous mode is running, user messages can be queued:

**Via API:**
```bash
curl -X POST "http://localhost:3001/api/autonomous/queue-message" \
  -H "Content-Type: application/json" \
  -d '{
    "sessionId": "your-session-id",
    "content": "How is your research going?"
  }'
```

**Response:**
```json
{
  "success": true,
  "message": "Message queued successfully",
  "session_id": "your-session-id",
  "queue_size": 1,
  "entry": {
    "message": "How is your research going?",
    "priority": "high",
    "timestamp": 1729631534.123,
    "status": "pending",
    "metadata": {"source": "user"}
  }
}
```

## Configuration

### Autonomous Config Parameters

Located in `autonomous_agent.py`:

```python
class AutonomousConfig:
    # Enable/disable autonomous mode
    enabled = False

    # How often to run autonomous iterations (seconds)
    interval_seconds = 30

    # Maximum actions per hour (rate limiting)
    max_actions_per_hour = 120

    # Tools allowed in autonomous mode
    allowed_tools = [
        "set_goal",
        "update_goal_status",
        "check_my_goals",
        "recall_memory",
        "query_related_information",
    ]

    # Auto-create derived goals from instrumental goals
    auto_create_derived_goals = True

    # Actions requiring user approval (empty = none)
    require_approval_for = []

    # Max consecutive errors before stopping
    max_consecutive_errors = 3
```

### Customizing Configuration

To create a custom configuration:

```python
from autonomous_agent import AutonomousConfig

custom_config = AutonomousConfig()
custom_config.interval_seconds = 60  # Run every minute
custom_config.max_actions_per_hour = 60  # Max 60 actions/hour
custom_config.allowed_tools.append("searxng_search")  # Allow web search

agent = AutonomousAgent(
    agent_executor=executor,
    memory_system=memory,
    message_queue=queue,
    config=custom_config
)
```

## Safety Controls

### 1. Rate Limiting

**Purpose:** Prevent runaway autonomous execution

**Implementation:**
- `max_actions_per_hour` limit (default: 120)
- Hourly counter resets every 3600 seconds
- Agent pauses when limit reached

**Example:**
```python
# Check if can take action
if not agent._can_take_action():
    time.sleep(60)  # Wait a minute
    continue
```

### 2. Error Handling

**Purpose:** Stop autonomous mode if persistent errors occur

**Implementation:**
- `max_consecutive_errors` limit (default: 3)
- Counter resets on successful action
- Agent stops automatically when limit reached

**Example:**
```python
try:
    response = agent_executor(prompt, session_id)
    agent.consecutive_errors = 0  # Reset on success
except Exception as e:
    agent.consecutive_errors += 1
    if agent.consecutive_errors >= config.max_consecutive_errors:
        agent.running = False  # Stop autonomous mode
```

### 3. Tool Restrictions

**Purpose:** Limit autonomous agent to safe operations

**Implementation:**
- `allowed_tools` whitelist
- Tools not in list cannot be used autonomously
- Default: goal management and memory queries only

**Expanding Allowed Tools:**
```python
config.allowed_tools.extend([
    "searxng_search",          # Web search
    "learn_from_web_page",     # Learn from URLs
    "query_procedure",         # Query procedures
])
```

### 4. User Message Priority

**Purpose:** Ensure user can always interrupt

**Implementation:**
- User messages queued with `priority="high"`
- Queue checked **before** self-prompting
- User messages processed immediately

**Flow:**
```python
if queue.has_messages(session_id):
    # Process user message (priority)
    message = queue.dequeue(session_id)
    response = agent_executor(message["message"], session_id)
else:
    # Self-prompt (autonomous)
    prompt = agent._generate_autonomous_prompt()
    response = agent_executor(prompt, session_id)
```

## Integration with Goal System

Autonomous mode is tightly integrated with the enhanced goal system:

### Instrumental Goals

**Forever goals** that continuously extend and derive other goals:

```python
goal_id = memory.create_goal(
    owner="Sophia",
    description="Continuously improve programming skills",
    priority=5,
    goal_type="instrumental",
    is_forever_goal=True
)
```

**How autonomous mode uses them:**
- Always included in self-prompts
- Inspire creation of derived goals
- Cannot be completed (status returns to "ongoing")

### Derived Goals

Goals created from instrumental objectives:

```python
subgoal_id = memory.create_goal(
    owner="Sophia",
    description="Learn Python decorators",
    priority=4,
    parent_goal="Continuously improve programming skills",
    goal_type="derived"
)
```

**How autonomous mode uses them:**
- Get +20 score boost in suggestions
- Tracked as `goals_affected` in actions
- Automatically linked to parent goals

### Goal Dependencies

Dependencies that block completion:

```python
goal_id = memory.create_goal(
    owner="Sophia",
    description="Build Flask app",
    priority=5,
    depends_on=["Learn Flask basics", "Set up database"]
)
```

**How autonomous mode uses them:**
- Goals with unmet dependencies are skipped in suggestions
- Agent works on dependencies first
- Parent goals cannot complete until all dependencies met

## Best Practices

### 1. Set Clear Instrumental Goals

Create high-level, ongoing objectives:

```python
# Good: Clear, ongoing, measurable
memory.create_goal(
    owner="Sophia",
    description="Stay current with AI research",
    priority=5,
    goal_type="instrumental",
    is_forever_goal=True
)

# Bad: Too specific, not ongoing
memory.create_goal(
    owner="Sophia",
    description="Read one paper about transformers",
    priority=5,
    goal_type="instrumental",  # Should be standard
    is_forever_goal=True        # Should be False
)
```

### 2. Use Appropriate Priorities

Priority levels guide autonomous decision-making:

- **5 (Critical)**: Core objectives, instrumental goals
- **4 (High)**: Important derived goals, urgent tasks
- **3 (Medium)**: Standard goals, nice-to-haves
- **2 (Low)**: Optional improvements
- **1 (Minimal)**: Future considerations

### 3. Monitor Autonomous Activity

Check the autonomous control panel regularly:

- Review recent actions
- Monitor queue size
- Check for error patterns
- Adjust config if needed

### 4. Use Dependencies Wisely

Create logical dependency chains:

```python
# Create foundation goals first
basics = memory.create_goal(
    owner="Sophia",
    description="Learn Flask basics",
    priority=4
)

# Then create dependent goals
app = memory.create_goal(
    owner="Sophia",
    description="Build REST API with Flask",
    priority=5,
    depends_on=["Learn Flask basics"]
)
```

### 5. Adjust Rate Limiting

Tune based on LLM speed and costs:

```python
# For slower/expensive LLMs
config.interval_seconds = 60          # Every minute
config.max_actions_per_hour = 30      # 30 actions/hour

# For faster/cheaper LLMs
config.interval_seconds = 15          # Every 15 seconds
config.max_actions_per_hour = 200     # 200 actions/hour
```

## Troubleshooting

### Autonomous Mode Won't Start

**Symptoms:**
- Toggle doesn't activate
- Error message in UI

**Solutions:**
1. Check agent server is running (`python agent_server.py`)
2. Verify session ID is valid
3. Check browser console for errors
4. Try restarting both servers

### No Actions Being Taken

**Symptoms:**
- Running but iteration count not increasing
- No recent actions in history

**Solutions:**
1. Check if rate limit reached (actions_this_hour >= max)
2. Verify goals exist (`check_my_goals` tool)
3. Check for consecutive errors in status
4. Review agent server logs for errors

### Actions Too Frequent/Infrequent

**Symptoms:**
- Agent acting too often or not often enough

**Solutions:**
1. Adjust `interval_seconds` in config
2. Modify `max_actions_per_hour` limit
3. Check LLM response time
4. Monitor system resources

### User Messages Not Being Processed

**Symptoms:**
- Messages queued but not answered
- Queue size keeps growing

**Solutions:**
1. Check autonomous mode is running
2. Verify message queue status
3. Check for agent errors
4. Restart autonomous mode

### Errors Stop Autonomous Mode

**Symptoms:**
- Mode stops after few iterations
- Error count reaches max

**Solutions:**
1. Review error logs in agent server
2. Check LLM availability
3. Verify memory system is working
4. Increase `max_consecutive_errors` if transient issues

## API Reference

### Start Autonomous Mode

```
POST /api/autonomous/start
```

**Parameters:**
- `session_id` (query): Session identifier

**Response:**
```json
{
  "success": true,
  "message": "Autonomous mode started",
  "session_id": "...",
  "status": { ... }
}
```

### Stop Autonomous Mode

```
POST /api/autonomous/stop
```

**Parameters:**
- `session_id` (query): Session identifier

**Response:**
```json
{
  "success": true,
  "message": "Autonomous mode stopped",
  "session_id": "..."
}
```

### Get Status

```
GET /api/autonomous/status
```

**Parameters:**
- `session_id` (query): Session identifier

**Response:**
```json
{
  "success": true,
  "status": {
    "running": true,
    "session_id": "...",
    "current_focus_goal": "...",
    "iteration_count": 15,
    "actions_taken": 8,
    "actions_this_hour": 8,
    "uptime_seconds": 450,
    "queue_size": 0,
    "consecutive_errors": 0,
    "config": {
      "interval": 30,
      "max_actions_per_hour": 120
    }
  }
}
```

### Queue Message

```
POST /api/autonomous/queue-message
```

**Parameters:**
- `session_id` (query): Session identifier

**Body:**
```json
{
  "content": "Your message here"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Message queued successfully",
  "session_id": "...",
  "queue_size": 1,
  "entry": { ... }
}
```

### Get History

```
GET /api/autonomous/history
```

**Parameters:**
- `session_id` (query): Session identifier
- `limit` (query, optional): Max actions to return (default: 10)

**Response:**
```json
{
  "success": true,
  "session_id": "...",
  "action_count": 5,
  "actions": [
    {
      "session_id": "...",
      "action_type": "autonomous_action",
      "prompt": "...",
      "response": "...",
      "source": "autonomous",
      "goals_affected": [],
      "tools_used": [...],
      "timestamp": 1729631534.123,
      "time_str": "2025-10-22 21:32:14"
    }
  ]
}
```

## Future Enhancements

### Planned Features

1. **Tool Approval Workflow**
   - User approval required for certain tools
   - Notification system for pending approvals
   - Timeout handling

2. **Goal Progress Tracking**
   - Automatic progress updates
   - Estimated completion times
   - Progress visualization

3. **Learning from Outcomes**
   - Track which actions lead to goal completion
   - Optimize action selection over time
   - Build procedural knowledge

4. **Multi-Session Coordination**
   - Share goals across sessions
   - Coordinate autonomous agents
   - Prevent duplicate work

5. **Advanced Scheduling**
   - Time-based goal activation
   - Dependency-aware scheduling
   - Priority-based work queues

### Contributing

To contribute to autonomous mode:

1. Test thoroughly with `test_autonomous_mode.py`
2. Update documentation
3. Add new test cases
4. Submit pull request

## Conclusion

Autonomous Mode transforms Sophia from a reactive chatbot into a proactive AI agent that pursues long-term objectives while remaining responsive to user needs. By combining goal management, memory systems, and intelligent self-prompting, it creates a truly autonomous system that can work independently towards improvement and knowledge acquisition.

Happy autonomous exploration! 🤖
