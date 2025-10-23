# SophiaAMS Goal Management System

**Comprehensive Guide to Goal Types, Dependencies, and Agent Integration**

---

## 📋 Table of Contents

- [Overview](#overview)
- [Goal Types](#goal-types)
- [Dependencies and Blocking](#dependencies-and-blocking)
- [Agent Integration](#agent-integration)
- [API Reference](#api-reference)
- [Web Interface Guide](#web-interface-guide)
- [Best Practices](#best-practices)
- [Examples](#examples)

---

## Overview

The SophiaAMS Goal Management System provides a sophisticated framework for creating, tracking, and managing goals with dependencies, hierarchies, and automatic agent awareness. Goals are stored as semantic triples in the knowledge graph and automatically appear in the agent's context during conversations.

### Key Features

- **🎯 Multiple Goal Types**: Standard, Instrumental, and Derived goals
- **🔗 Dependency Management**: Goals can depend on other goals with automatic blocking
- **♾️ Forever Goals**: Ongoing instrumental goals that never complete
- **🤖 Auto-Prompt Inclusion**: High-priority and instrumental goals automatically refresh in agent context
- **📊 Priority System**: 1-5 priority levels with visual indicators
- **🌳 Hierarchical Structure**: Parent-child goal relationships
- **🚫 Smart Blocking**: Goals with unmet dependencies automatically blocked from completion

---

## Goal Types

### 1. Standard Goals

Regular goals with a defined completion state.

**Characteristics:**
- Can be completed, cancelled, or blocked
- Default priority: 3
- Status flow: `pending` → `in_progress` → `completed`
- Use for: Specific, achievable tasks

**Example:**
```json
{
  "description": "Learn backpropagation algorithm",
  "goal_type": "standard",
  "priority": 4,
  "is_forever_goal": false
}
```

### 2. Instrumental Goals

High-level, ongoing goals that never complete. These are strategic objectives that spawn derived goals.

**Characteristics:**
- Status: `ongoing` (cannot be completed)
- Always included in agent prompt
- Typically high priority (4-5)
- Use for: Long-term objectives, continuous improvement areas

**Example:**
```json
{
  "description": "Continuously expand knowledge of neural networks",
  "goal_type": "instrumental",
  "priority": 5,
  "is_forever_goal": true
}
```

**UI Indicator:** Purple gradient badge showing "FOREVER"

### 3. Derived Goals

Goals that emerge from instrumental/forever goals. Automatically prioritized by the suggestion system.

**Characteristics:**
- Linked to parent instrumental goal via `derived_from` relationship
- Receive +20 priority boost in suggestions
- Can be completed normally
- Use for: Actionable steps toward instrumental goals

**Example:**
```json
{
  "description": "Study transformer architecture papers",
  "goal_type": "derived",
  "parent_goal": "Continuously expand knowledge of neural networks",
  "priority": 4,
  "is_forever_goal": false
}
```

**UI Indicator:** Green badge showing "DERIVED"

---

## Dependencies and Blocking

### Dependency System

Goals can depend on other goals being completed first. This creates a dependency chain that prevents premature completion.

#### Creating Dependencies

**Via API:**
```json
{
  "description": "Implement neural network training loop",
  "depends_on": [
    "Learn backpropagation algorithm",
    "Set up training data pipeline"
  ],
  "priority": 4
}
```

**Via Web UI:**
Coming soon - dependency selector in create form

#### Dependency Behavior

1. **Completion Blocking**: Attempting to complete a goal with unmet dependencies automatically:
   - Changes status to `blocked`
   - Sets `blocker_reason` to list pending dependencies
   - Prevents completion until dependencies are met

2. **Dependency Resolution**: Dependencies are met when they are:
   - Marked as `completed`, OR
   - Marked as `cancelled` (abandoned)

3. **Goal Suggestion**: The suggestion system automatically:
   - Skips goals with unmet dependencies
   - Prioritizes goals with all dependencies met

#### Example Flow

```
Goal: "Deploy model to production"
  depends_on: ["Train final model", "Set up production environment"]

Status: pending
  → Attempt to complete
  → Status: blocked
  → Blocker: "Blocked by pending dependencies: Train final model, Set up production environment"

Complete: "Train final model"
  → Still blocked by "Set up production environment"

Complete: "Set up production environment"
  → Now can be completed successfully
```

### Forever Goal Behavior

Forever/instrumental goals **cannot** be completed:

```python
# Attempting to complete a forever goal
update_goal(
    goal_description="Continuously expand knowledge",
    status="completed"
)

# Result:
# - Status remains "ongoing"
# - Blocker reason: "This is an instrumental/forever goal - it cannot be completed"
```

---

## Agent Integration

### Auto-Prompt Inclusion

Goals automatically appear in the agent's context on every turn via the `auto_recall_memories()` function.

#### Which Goals Are Included?

1. **All Instrumental/Forever Goals** (regardless of priority)
2. **All Priority 4-5 Active Goals** (pending, in_progress, or ongoing)

Up to 10 goals total (configurable via `limit` parameter).

#### Prompt Format

Goals appear in a dedicated section:

```
=== YOUR ACTIVE GOALS ===
- [★★★★★] Continuously expand knowledge of neural networks [INSTRUMENTAL/ONGOING] (ONGOING)
- [★★★★] Study transformer architecture papers [DERIVED]
- [★★★★] Implement attention mechanism
- [★★★] Debug training loop issues (IN_PROGRESS)
=== END GOALS ===
```

**Format Elements:**
- `[★★★★★]` - Priority stars (1-5)
- Goal description
- `[INSTRUMENTAL/ONGOING]` - Type badge for forever goals
- `[DERIVED]` - Type badge for derived goals
- `(STATUS)` - Status indicator (if not pending)

#### Agent Awareness

The agent sees these goals **automatically** before processing each user message. This enables:

- Proactive goal-oriented behavior
- Context-aware responses aligned with objectives
- Autonomous progress toward instrumental goals
- Natural goal setting during conversations

---

## API Reference

### Create Goal

**Endpoint:** `POST /api/goals/create`

**Request Body:**
```json
{
  "owner": "Sophia",
  "description": "Learn about neural networks",
  "priority": 4,
  "parent_goal": null,
  "target_date": null,
  "goal_type": "standard",
  "is_forever_goal": false,
  "depends_on": null
}
```

**Fields:**
- `owner` (string, default: "Sophia"): Goal owner
- `description` (string, required): Goal description
- `priority` (int, 1-5, default: 3): Priority level
- `parent_goal` (string, optional): Parent goal description
- `target_date` (float, optional): Unix timestamp for target completion
- `goal_type` (string, default: "standard"): "standard", "instrumental", or "derived"
- `is_forever_goal` (bool, default: false): Whether this is an ongoing goal
- `depends_on` (array, optional): List of goal descriptions this depends on

**Response:**
```json
{
  "success": true,
  "goal_id": "Learn about neural networks",
  "message": "Goal created: Learn about neural networks",
  "goal_type": "standard",
  "is_forever_goal": false
}
```

### Update Goal

**Endpoint:** `POST /api/goals/update`

**Request Body:**
```json
{
  "goal_description": "Learn about neural networks",
  "status": "completed",
  "priority": null,
  "blocker_reason": null,
  "completion_notes": "Completed study of basic concepts"
}
```

**Status Values:**
- `pending` - Not started
- `in_progress` - Currently working on
- `completed` - Finished (if dependencies met)
- `blocked` - Blocked by dependencies or other issues
- `cancelled` - Abandoned
- `ongoing` - Forever goals only

**Response:**
```json
{
  "success": true,
  "message": "Goal updated: Learn about neural networks"
}
```

**Note:** If dependencies are unmet, status will be set to `blocked` instead of `completed`.

### Query Goals

**Endpoint:** `GET /api/goals`

**Query Parameters:**
- `status` (string, optional): Filter by status
- `min_priority` (int, default: 1): Minimum priority
- `max_priority` (int, default: 5): Maximum priority
- `owner` (string, default: "Sophia"): Goal owner
- `active_only` (bool, default: false): Only pending/in_progress/ongoing
- `limit` (int, default: 100): Maximum results

**Response:**
```json
{
  "goals": [
    {
      "description": "Learn about neural networks",
      "status": "in_progress",
      "priority": 4,
      "created": 1234567890.0,
      "updated": 1234567900.0,
      "completed": null,
      "target_date": null,
      "parent_goal": null,
      "source": "web_ui",
      "blocker_reason": null,
      "completion_notes": null,
      "topics": ["goal", "planning"],
      "goal_type": "standard",
      "is_forever_goal": false
    }
  ],
  "count": 1
}
```

### Get Goal Progress

**Endpoint:** `GET /api/goals/progress`

**Query Parameters:**
- `owner` (string, default: "Sophia"): Goal owner

**Response:**
```json
{
  "total_goals": 10,
  "by_status": {
    "pending": 3,
    "in_progress": 2,
    "completed": 4,
    "blocked": 1,
    "cancelled": 0
  },
  "by_priority": {
    "1": 0,
    "2": 1,
    "3": 4,
    "4": 3,
    "5": 2
  },
  "completion_rate": 0.4,
  "active_count": 5,
  "recent_completions": [
    {
      "description": "Study backpropagation",
      "completed_at": 1234567890.0
    }
  ]
}
```

### Get Goal Suggestion

**Endpoint:** `GET /api/goals/suggestion`

**Query Parameters:**
- `owner` (string, default: "Sophia"): Goal owner

**Response:**
```json
{
  "suggestion": {
    "goal_description": "Study transformer architecture papers",
    "priority": 4,
    "score": 60,
    "goal_type": "derived",
    "reasoning": "Priority 4/5, derived from instrumental goal - dependencies met"
  }
}
```

**Scoring System:**
- Base: Priority × 10
- Derived goals: +20 bonus
- Target date < 7 days: +15
- Target date < 30 days: +5
- Unmet dependencies: Excluded from suggestions

---

## Web Interface Guide

### Creating Goals

1. Navigate to the Goals page
2. Click "New Goal" button
3. Fill out the form:
   - **Description**: What you want to accomplish
   - **Priority (1-5)**: How important (5 = highest)
   - **Goal Type**:
     - Standard - Regular goal
     - Instrumental - Ongoing strategic objective
     - Derived - Emerged from instrumental goal
   - **Parent Goal**: Select from dropdown (optional)
   - **Forever/Ongoing Goal**: Check for instrumental goals

4. Click "Create Goal"

### Visual Indicators

**Priority Badges:**
- Color-coded by priority (red = highest, gray = lowest)
- Shows as `P1`, `P2`, `P3`, `P4`, `P5`

**Type Badges:**
- 🟣 **FOREVER** - Purple gradient for instrumental goals
- 🟡 **INSTRUMENTAL** - Yellow for instrumental type
- 🟢 **DERIVED** - Green for derived goals

### Managing Goals

**Expand Goal Card:** Click on any goal to see details:
- Created/Updated timestamps
- Target date (if set)
- Blocker reason (if blocked)
- Completion notes
- Topics

**Change Status:** Click action buttons in expanded view:
- **Reset** - Back to pending
- **Start** - Mark as in_progress
- **Complete** - Mark as completed (if dependencies met)
- **Block** - Mark as blocked
- **Cancel** - Mark as cancelled

**Filter Goals:** Use tabs to filter by status:
- All, Pending, In Progress, Completed, Blocked

---

## Best Practices

### 1. Goal Hierarchy Design

**✅ Good:**
```
[INSTRUMENTAL] Become expert in deep learning
  └─ [DERIVED] Study transformer architecture
      └─ [STANDARD] Read "Attention is All You Need" paper
```

**❌ Avoid:**
```
[STANDARD] Learn everything about AI
```
*Too broad - make it instrumental instead*

### 2. Using Dependencies

**✅ Good:**
```
Goal: "Deploy model"
  depends_on: ["Train model", "Set up infrastructure"]
```

**❌ Avoid:**
```
Goal: "Train and deploy model"
```
*Break into separate goals with dependencies*

### 3. Priority Levels

- **Priority 5**: Critical, urgent tasks
- **Priority 4**: Important, high-value goals
- **Priority 3**: Standard goals (default)
- **Priority 2**: Nice-to-have improvements
- **Priority 1**: Low priority, future considerations

**Remember:** Only priority 4-5 goals appear in agent prompt automatically!

### 4. Forever Goals

Use instrumental/forever goals for:
- ✅ Continuous learning areas
- ✅ Long-term strategic objectives
- ✅ Ongoing improvement initiatives

Don't use for:
- ❌ Specific, completable tasks
- ❌ Short-term projects
- ❌ One-time activities

### 5. Derived Goals

Create derived goals to:
- ✅ Break down instrumental goals into actionable steps
- ✅ Track progress toward strategic objectives
- ✅ Get automatic prioritization in suggestions

Link to parent:
```json
{
  "description": "Implement specific technique",
  "goal_type": "derived",
  "parent_goal": "Master deep learning architectures"
}
```

---

## Examples

### Example 1: Research Project with Dependencies

```python
# Create instrumental goal
memory_system.create_goal(
    owner="Sophia",
    description="Advance understanding of attention mechanisms",
    priority=5,
    goal_type="instrumental",
    is_forever_goal=True
)

# Create derived goals
memory_system.create_goal(
    owner="Sophia",
    description="Read foundational papers on attention",
    priority=4,
    goal_type="derived",
    parent_goal="Advance understanding of attention mechanisms"
)

# Create dependent implementation goal
memory_system.create_goal(
    owner="Sophia",
    description="Implement multi-head attention from scratch",
    priority=4,
    depends_on=["Read foundational papers on attention"],
    parent_goal="Advance understanding of attention mechanisms"
)
```

**Result:**
- Instrumental goal always visible to agent
- Derived goals prioritized in suggestions
- Implementation blocked until papers are read

### Example 2: Project with Multiple Dependencies

```python
# Create all prerequisite goals
memory_system.create_goal(
    owner="Sophia",
    description="Set up training data pipeline",
    priority=4
)

memory_system.create_goal(
    owner="Sophia",
    description="Implement model architecture",
    priority=4
)

memory_system.create_goal(
    owner="Sophia",
    description="Configure hyperparameters",
    priority=3
)

# Create dependent goal
memory_system.create_goal(
    owner="Sophia",
    description="Run full training experiment",
    priority=5,
    depends_on=[
        "Set up training data pipeline",
        "Implement model architecture",
        "Configure hyperparameters"
    ]
)
```

**Behavior:**
- Training experiment cannot be completed until all 3 prerequisites are done
- If attempted early, automatically blocked with clear message
- Suggestion system skips it until dependencies met

### Example 3: Using the Web Interface

1. **Create Instrumental Goal:**
   - Description: "Continuously improve coding skills"
   - Priority: 5
   - Goal Type: Instrumental
   - Forever/Ongoing Goal: ✓ Checked
   - Click "Create Goal"

2. **Create Derived Goal:**
   - Description: "Learn advanced Python patterns"
   - Priority: 4
   - Goal Type: Derived
   - Parent Goal: "Continuously improve coding skills"
   - Click "Create Goal"

3. **Monitor Progress:**
   - View goals page - instrumental goal shows purple "FOREVER" badge
   - Derived goal shows green "DERIVED" badge
   - Both appear in agent's context automatically

---

## Python API Examples

### Creating Goals Programmatically

```python
from AssociativeSemanticMemory import AssociativeSemanticMemory
from VectorKnowledgeGraph import VectorKnowledgeGraph

# Initialize
kgraph = VectorKnowledgeGraph()
memory = AssociativeSemanticMemory(kgraph)

# Create standard goal
goal_id = memory.create_goal(
    owner="Sophia",
    description="Learn NumPy advanced indexing",
    priority=3,
    goal_type="standard"
)

# Create forever goal
forever_goal = memory.create_goal(
    owner="Sophia",
    description="Master machine learning fundamentals",
    priority=5,
    goal_type="instrumental",
    is_forever_goal=True
)

# Create derived goal with dependency
derived_goal = memory.create_goal(
    owner="Sophia",
    description="Implement gradient descent from scratch",
    priority=4,
    goal_type="derived",
    parent_goal="Master machine learning fundamentals",
    depends_on=["Learn NumPy advanced indexing"]
)
```

### Querying Goals

```python
# Get all active goals
active_goals = memory.query_goals(
    owner="Sophia",
    active_only=True
)

# Get high-priority goals
high_priority = memory.query_goals(
    owner="Sophia",
    min_priority=4,
    max_priority=5
)

# Get instrumental goals specifically
instrumental = memory.kgraph.query_instrumental_goals(limit=50)

# Get goals for agent prompt
prompt_goals = memory.get_active_goals_for_prompt(owner="Sophia", limit=10)
print(prompt_goals)
# Output:
# - [★★★★★] Master machine learning fundamentals [INSTRUMENTAL/ONGOING] (ONGOING)
# - [★★★★] Implement gradient descent from scratch [DERIVED]
```

### Updating Goals

```python
# Start working on goal
memory.update_goal(
    goal_description="Learn NumPy advanced indexing",
    status="in_progress"
)

# Try to complete dependent goal (will be blocked)
success = memory.update_goal(
    goal_description="Implement gradient descent from scratch",
    status="completed"
)
# Returns True, but status set to "blocked" instead

# Complete prerequisite
memory.update_goal(
    goal_description="Learn NumPy advanced indexing",
    status="completed",
    completion_notes="Finished NumPy documentation and exercises"
)

# Now can complete dependent goal
memory.update_goal(
    goal_description="Implement gradient descent from scratch",
    status="completed",
    completion_notes="Successfully implemented and tested"
)
```

### Getting Suggestions

```python
# Get next suggested goal
suggestion = memory.suggest_next_goal(owner="Sophia")

if suggestion:
    print(f"Suggested: {suggestion['goal_description']}")
    print(f"Priority: {suggestion['priority']}")
    print(f"Type: {suggestion['goal_type']}")
    print(f"Reasoning: {suggestion['reasoning']}")
    # Output:
    # Suggested: Study reinforcement learning basics
    # Priority: 4
    # Type: derived
    # Reasoning: Priority 4/5, derived from instrumental goal - dependencies met
```

---

## Troubleshooting

### Goal Won't Complete

**Problem:** Clicking "Complete" doesn't work, goal becomes "blocked"

**Solution:** Check the blocker reason - you likely have unmet dependencies:
1. Expand the goal card
2. Look at "Blocker" field
3. Complete or cancel the listed dependencies first

### Forever Goal Shows as "Blocked"

**Problem:** Trying to complete an instrumental goal

**Solution:** Forever goals cannot be completed by design:
- They should remain in "ongoing" status
- Create derived goals to track progress toward the instrumental goal
- Use the suggestion system to identify next actionable steps

### Goal Not Appearing in Agent Prompt

**Problem:** Goal doesn't show up in agent context

**Solution:** Check that it meets inclusion criteria:
- Is it priority 4 or 5? OR
- Is it marked as forever/instrumental goal?
- Is the status active (pending, in_progress, or ongoing)?

If no, either:
- Increase priority to 4-5, OR
- Mark as instrumental/forever goal, OR
- Ask the agent explicitly about the goal

### Dependencies Not Working

**Problem:** Can complete a goal despite pending dependencies

**Solution:** Verify:
1. Dependencies are specified correctly in `depends_on` list
2. Dependency goal descriptions match exactly (use exact strings)
3. Backend has been restarted after code changes
4. Check logs for dependency checking errors

---

## Integration with Agent Tools

### Agent Tool: `set_goal`

The agent can create goals autonomously using the `set_goal` tool:

```python
def set_goal(goal_description: str, priority: int = 3, parent_goal: str = None) -> str:
    """
    Set a new goal for myself.

    Args:
        goal_description: What I want to accomplish
        priority: 1-5, where 5 is highest priority
        parent_goal: Parent goal description if this is a subgoal
    """
```

**Note:** Update this tool to support new parameters (`goal_type`, `is_forever_goal`, `depends_on`).

### Agent Tool: `check_my_goals`

The agent can view all goals:

```python
def check_my_goals() -> str:
    """Check all my current goals and their status."""
```

This provides a detailed view beyond what's in the auto-prompt.

### Agent Tool: `update_goal_status`

The agent can update goal status:

```python
def update_goal_status(goal_description: str, status: str = "in_progress", notes: str = "") -> str:
    """
    Update the status of one of my goals.

    Args:
        goal_description: The exact description of the goal
        status: New status (pending, in_progress, completed, blocked, cancelled)
        notes: Notes about the update
    """
```

---

## Future Enhancements

Potential improvements to the goal system:

1. **Dependency UI**: Visual dependency selector in web interface
2. **Goal Templates**: Predefined goal structures for common scenarios
3. **Progress Tracking**: Percentage completion for goals with subgoals
4. **Time Estimation**: Add estimated time to completion
5. **Goal Analytics**: Visualizations of goal completion trends
6. **Smart Suggestions**: ML-based goal recommendations
7. **Recurring Goals**: Goals that reset periodically
8. **Goal Tags**: Additional categorization beyond topics
9. **Collaboration**: Multi-agent goal coordination
10. **Notifications**: Alert when goals become unblocked

---

## Summary

The SophiaAMS Goal Management System provides:

✅ **Three goal types** for different use cases
✅ **Dependency management** with automatic blocking
✅ **Forever goals** for ongoing objectives
✅ **Auto-prompt inclusion** for agent awareness
✅ **Priority system** with visual indicators
✅ **Hierarchical structure** with parent-child relationships
✅ **Smart suggestions** respecting dependencies
✅ **Web interface** for easy management
✅ **Comprehensive API** for programmatic access

Use this system to give your agent clear, structured objectives that it automatically works toward in every conversation!

---

*For more information, see [API_README.md](API_README.md) and [AGENT_SERVER_GUIDE.md](AGENT_SERVER_GUIDE.md)*
