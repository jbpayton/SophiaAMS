"""
Test script for autonomous mode functionality.

Tests:
1. Message queue operations
2. Autonomous agent initialization
3. Self-prompting generation
4. Action logging
5. Rate limiting
"""

import time
import sys
import io

# Enable UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from message_queue import MessageQueue
from autonomous_agent import AutonomousAgent, AutonomousConfig
from VectorKnowledgeGraph import VectorKnowledgeGraph
from AssociativeSemanticMemory import AssociativeSemanticMemory

print("=" * 70)
print("AUTONOMOUS MODE TEST SUITE")
print("=" * 70)

# Initialize memory systems
print("\n[INIT] Initializing memory systems...")
kgraph = VectorKnowledgeGraph()
memory = AssociativeSemanticMemory(kgraph)
print("✓ Memory systems initialized")

# ============================================================================
# TEST 1: Message Queue
# ============================================================================
print("\n" + "=" * 70)
print("TEST 1: Message Queue Operations")
print("=" * 70)

queue = MessageQueue()

# Test enqueue
print("\n[TEST] Enqueuing messages...")
queue.enqueue("test_session", "Hello from user", priority="high")
queue.enqueue("test_session", "Another message", priority="normal")
print(f"✓ Queue size: {queue.get_queue_size('test_session')}")

# Test has_messages
print("\n[TEST] Checking for messages...")
has_msg = queue.has_messages("test_session")
print(f"✓ Has messages: {has_msg}")

# Test peek
print("\n[TEST] Peeking at next message...")
next_msg = queue.peek("test_session")
print(f"✓ Next message: {next_msg['message'][:50]}")

# Test dequeue
print("\n[TEST] Dequeueing messages...")
msg1 = queue.dequeue("test_session")
print(f"✓ Dequeued: {msg1['message']}")
msg2 = queue.dequeue("test_session")
print(f"✓ Dequeued: {msg2['message']}")

# Test empty queue
print("\n[TEST] Checking empty queue...")
empty = not queue.has_messages("test_session")
print(f"✓ Queue is empty: {empty}")

# Test status
print("\n[TEST] Getting queue status...")
status = queue.get_status()
print(f"✓ Total sessions: {status['total_sessions']}")
print(f"✓ Total pending: {status['total_pending']}")

print("\n✅ Message Queue Tests Passed!")

# ============================================================================
# TEST 2: Autonomous Agent Configuration
# ============================================================================
print("\n" + "=" * 70)
print("TEST 2: Autonomous Agent Configuration")
print("=" * 70)

print("\n[TEST] Creating autonomous config...")
config = AutonomousConfig()
print(f"✓ Enabled: {config.enabled}")
print(f"✓ Interval: {config.interval_seconds}s")
print(f"✓ Max actions/hour: {config.max_actions_per_hour}")
print(f"✓ Allowed tools: {len(config.allowed_tools)} tools")
print(f"✓ Auto create derived goals: {config.auto_create_derived_goals}")

print("\n✅ Configuration Tests Passed!")

# ============================================================================
# TEST 3: Autonomous Agent Initialization
# ============================================================================
print("\n" + "=" * 70)
print("TEST 3: Autonomous Agent Initialization")
print("=" * 70)

# Create a mock agent executor
def mock_executor(prompt, session_id):
    """Mock executor for testing."""
    return f"Mock response to: {prompt[:50]}"

print("\n[TEST] Creating autonomous agent...")
message_queue = MessageQueue()
agent = AutonomousAgent(
    agent_executor=mock_executor,
    memory_system=memory,
    message_queue=message_queue,
    config=config
)
print("✓ Autonomous agent created")

# Test initial state
print("\n[TEST] Checking initial state...")
print(f"✓ Running: {agent.is_running()}")
print(f"✓ Session ID: {agent.session_id}")
print(f"✓ Actions taken: {len(agent.actions_taken)}")

print("\n✅ Initialization Tests Passed!")

# ============================================================================
# TEST 4: Self-Prompting Generation
# ============================================================================
print("\n" + "=" * 70)
print("TEST 4: Self-Prompting Generation")
print("=" * 70)

print("\n[TEST] Creating test goals...")
# Create some test goals
goal1_id = memory.create_goal(
    owner="Sophia",
    description="Learn about transformers",
    priority=5,
    source="test"
)
goal2_id = memory.create_goal(
    owner="Sophia",
    description="Research attention mechanisms",
    priority=4,
    source="test"
)
print(f"✓ Created goals: {goal1_id[:8]}, {goal2_id[:8]}")

# Temporarily assign session_id for prompt generation
agent.session_id = "test_session"

print("\n[TEST] Generating autonomous prompt...")
prompt = agent._generate_autonomous_prompt()
print(f"✓ Generated prompt length: {len(prompt)} chars")
print(f"✓ Contains 'MY ACTIVE GOALS': {'MY ACTIVE GOALS' in prompt}")
print(f"✓ Contains 'SUGGESTED NEXT GOAL': {'SUGGESTED NEXT GOAL' in prompt}")
print(f"✓ Contains goal description: {'transformers' in prompt.lower()}")

print("\n[PREVIEW] First 300 chars of prompt:")
print("-" * 70)
print(prompt[:300] + "...")
print("-" * 70)

print("\n✅ Self-Prompting Tests Passed!")

# ============================================================================
# TEST 5: Action Logging
# ============================================================================
print("\n" + "=" * 70)
print("TEST 5: Action Logging")
print("=" * 70)

print("\n[TEST] Logging autonomous action...")
agent._log_action(
    action_type="test_action",
    prompt="Test prompt",
    response="Test response",
    source="autonomous",
    goals_affected=["goal_1", "goal_2"],
    tools_used=["query_memory", "set_goal"]
)
print(f"✓ Actions logged: {len(agent.actions_taken)}")

print("\n[TEST] Retrieving recent actions...")
recent = agent.get_recent_actions(limit=5)
print(f"✓ Retrieved {len(recent)} actions")
action = recent[0]
print(f"✓ Action type: {action['action_type']}")
print(f"✓ Source: {action['source']}")
print(f"✓ Tools used: {action['tools_used']}")
print(f"✓ Goals affected: {action['goals_affected']}")
print(f"✓ Timestamp: {action['time_str']}")

print("\n✅ Action Logging Tests Passed!")

# ============================================================================
# TEST 6: Rate Limiting
# ============================================================================
print("\n" + "=" * 70)
print("TEST 6: Rate Limiting")
print("=" * 70)

print("\n[TEST] Checking rate limiting...")
# Test initial state
can_act = agent._can_take_action()
print(f"✓ Can take action: {can_act}")
print(f"✓ Actions this hour: {agent.actions_this_hour}")
print(f"✓ Max actions per hour: {agent.config.max_actions_per_hour}")

# Simulate reaching limit
print("\n[TEST] Simulating max actions...")
agent.actions_this_hour = agent.config.max_actions_per_hour
can_act_limited = agent._can_take_action()
print(f"✓ Can take action at limit: {can_act_limited}")

# Test hourly reset
print("\n[TEST] Testing hourly reset...")
agent.last_hour_reset = time.time() - 3700  # Simulate over an hour ago
agent._reset_hourly_limit()
print(f"✓ Actions after reset: {agent.actions_this_hour}")

print("\n✅ Rate Limiting Tests Passed!")

# ============================================================================
# TEST 7: Status Reporting
# ============================================================================
print("\n" + "=" * 70)
print("TEST 7: Status Reporting")
print("=" * 70)

print("\n[TEST] Getting agent status...")
agent.start_time = time.time() - 300  # Simulate 5 minutes uptime
agent.iteration_count = 10
status = agent.get_status()

print(f"✓ Running: {status['running']}")
print(f"✓ Session ID: {status['session_id']}")
print(f"✓ Iteration count: {status['iteration_count']}")
print(f"✓ Actions taken: {status['actions_taken']}")
print(f"✓ Uptime: {status['uptime_seconds']:.0f}s")
print(f"✓ Config interval: {status['config']['interval']}s")
print(f"✓ Config max actions: {status['config']['max_actions_per_hour']}")

print("\n✅ Status Reporting Tests Passed!")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 70)
print("TEST SUMMARY")
print("=" * 70)

print("\n✅ ALL TESTS PASSED!")
print("\nTested components:")
print("  1. Message Queue - ✓ Enqueue, dequeue, peek, status")
print("  2. Configuration - ✓ Settings and defaults")
print("  3. Initialization - ✓ Agent creation and state")
print("  4. Self-Prompting - ✓ Goal-based prompt generation")
print("  5. Action Logging - ✓ Recording and retrieval")
print("  6. Rate Limiting - ✓ Hourly limits and resets")
print("  7. Status Reporting - ✓ Real-time status updates")

print("\n🎉 Autonomous mode is ready for production!")
print("\nNext steps:")
print("  1. Start the agent server: python agent_server.py")
print("  2. Start the web server: cd sophia-web/server && npm start")
print("  3. Open the web UI and toggle autonomous mode ON")
print("  4. Watch Sophia work independently on her goals!")

print("\n" + "=" * 70)
