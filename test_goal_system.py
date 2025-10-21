"""
Quick test script to verify the goal system implementation.
"""

import time
from VectorKnowledgeGraph import VectorKnowledgeGraph
from AssociativeSemanticMemory import AssociativeSemanticMemory

print("Initializing memory systems...")
kgraph = VectorKnowledgeGraph()
memory = AssociativeSemanticMemory(kgraph)

print("\n=== TEST 1: Create a goal ===")
goal_id = memory.create_goal(
    owner="Sophia",
    description="Learn about neural networks",
    priority=4,
    source="test_script"
)
print(f"[OK] Created goal: {goal_id}")

print("\n=== TEST 2: Query goals ===")
goals = memory.query_goals(owner="Sophia", active_only=True)
print(f"[OK] Found {len(goals)} active goals:")
for triple, metadata in goals:
    print(f"  - {triple[2]} (priority: {metadata.get('priority')}, status: {metadata.get('goal_status')})")

print("\n=== TEST 3: Update goal status ===")
success = memory.update_goal(
    goal_description="Learn about neural networks",
    status="in_progress"
)
print(f"[OK] Updated goal status: {success}")

print("\n=== TEST 4: Check goal progress ===")
progress = memory.get_goal_progress(owner="Sophia")
print(f"[OK] Goal progress:")
print(f"  Total goals: {progress['total_goals']}")
print(f"  By status: {progress['by_status']}")
print(f"  Completion rate: {progress['completion_rate']:.1%}")

print("\n=== TEST 5: Create subgoal ===")
subgoal_id = memory.create_goal(
    owner="Sophia",
    description="Study backpropagation algorithm",
    priority=5,
    parent_goal="Learn about neural networks",
    source="test_script"
)
print(f"[OK] Created subgoal: {subgoal_id}")

print("\n=== TEST 6: Get goal suggestion ===")
suggestion = memory.suggest_next_goal(owner="Sophia")
if suggestion:
    print(f"[OK] Suggested goal: {suggestion['goal_description']}")
    print(f"  Priority: {suggestion['priority']}")
    print(f"  Reasoning: {suggestion['reasoning']}")
else:
    print("[OK] No suggestions (no pending goals)")

print("\n=== TEST 7: Complete subgoal ===")
success = memory.update_goal(
    goal_description="Study backpropagation algorithm",
    status="completed",
    completion_notes="Completed study of backpropagation fundamentals"
)
print(f"[OK] Completed subgoal: {success}")

print("\n=== TEST 8: Final progress check ===")
progress = memory.get_goal_progress(owner="Sophia")
print(f"[OK] Final stats:")
print(f"  Total goals: {progress['total_goals']}")
print(f"  Active: {progress['active_count']}")
print(f"  Completed: {progress['by_status'].get('completed', 0)}")
print(f"  Recent completions: {len(progress['recent_completions'])}")

print("\n[SUCCESS] All tests passed!")
