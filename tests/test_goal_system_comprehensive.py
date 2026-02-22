"""
Comprehensive test suite for the enhanced goal system.
Tests goal types, dependencies, blocking behavior, and agent integration.
"""

import time
import sys
import io

# Set UTF-8 encoding for stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from VectorKnowledgeGraph import VectorKnowledgeGraph
from AssociativeSemanticMemory import AssociativeSemanticMemory

def print_section(title):
    """Print a formatted section header."""
    print("\n" + "="*80)
    print(f" {title}")
    print("="*80)

def print_test(test_name):
    """Print a formatted test name."""
    print(f"\n>>> TEST: {test_name}")

def print_result(success, message):
    """Print test result."""
    status = "✓ PASS" if success else "✗ FAIL"
    print(f"    {status}: {message}")

def print_goals(goals, title="Current Goals"):
    """Pretty print goals."""
    print(f"\n{title}:")
    if not goals:
        print("  (none)")
        return

    for triple, metadata in goals:
        goal_desc = triple[2]
        status = metadata.get('goal_status', 'unknown')
        priority = metadata.get('priority', 0)
        goal_type = metadata.get('goal_type', 'standard')
        is_forever = metadata.get('is_forever_goal', False)

        type_label = ""
        if is_forever:
            type_label = " [FOREVER]"
        elif goal_type == "derived":
            type_label = " [DERIVED]"
        elif goal_type == "instrumental":
            type_label = " [INSTRUMENTAL]"

        stars = "★" * priority
        print(f"  [{stars}] {goal_desc}{type_label} ({status})")

        if metadata.get('blocker_reason'):
            print(f"      BLOCKED: {metadata['blocker_reason']}")

def test_basic_goal_creation(memory):
    """Test creating basic goals of different types."""
    print_section("TEST 1: Basic Goal Creation")

    # Test standard goal
    print_test("Create standard goal")
    try:
        goal_id = memory.create_goal(
            owner="Sophia",
            description="Learn Python decorators",
            priority=3,
            goal_type="standard",
            source="test"
        )
        print_result(True, f"Created standard goal: {goal_id}")
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

    # Test instrumental goal
    print_test("Create instrumental/forever goal")
    try:
        goal_id = memory.create_goal(
            owner="Sophia",
            description="Continuously improve programming skills",
            priority=5,
            goal_type="instrumental",
            is_forever_goal=True,
            source="test"
        )
        print_result(True, f"Created instrumental goal: {goal_id}")
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

    # Test derived goal
    print_test("Create derived goal")
    try:
        goal_id = memory.create_goal(
            owner="Sophia",
            description="Practice advanced Python patterns",
            priority=4,
            goal_type="derived",
            parent_goal="Continuously improve programming skills",
            source="test"
        )
        print_result(True, f"Created derived goal: {goal_id}")
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

    # Verify goals were created
    print_test("Verify all goals were created")
    goals = memory.query_goals(owner="Sophia", active_only=True)
    print_goals(goals, "Active Goals")
    print_result(len(goals) >= 3, f"Found {len(goals)} active goals")

    return True

def test_dependency_blocking(memory):
    """Test dependency blocking behavior."""
    print_section("TEST 2: Dependency Blocking")

    # Create prerequisite goals
    print_test("Create prerequisite goals")
    try:
        memory.create_goal(
            owner="Sophia",
            description="Set up test environment",
            priority=3,
            source="test"
        )
        memory.create_goal(
            owner="Sophia",
            description="Write unit tests",
            priority=3,
            source="test"
        )
        print_result(True, "Created prerequisite goals")
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

    # Create goal with dependencies
    print_test("Create goal with dependencies")
    try:
        goal_id = memory.create_goal(
            owner="Sophia",
            description="Run full test suite",
            priority=4,
            depends_on=["Set up test environment", "Write unit tests"],
            source="test"
        )
        print_result(True, f"Created dependent goal: {goal_id}")
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

    # Try to complete goal with unmet dependencies
    print_test("Attempt to complete goal with unmet dependencies")
    try:
        success = memory.update_goal(
            goal_description="Run full test suite",
            status="completed",
            completion_notes="Trying to complete early"
        )

        # Check if it was blocked
        result = memory.kgraph.query_goal_by_description("Run full test suite", return_metadata=True)
        if result:
            _, metadata = result
            status = metadata.get('goal_status')
            blocker = metadata.get('blocker_reason')

            if status == "blocked" and blocker:
                print_result(True, f"Goal correctly blocked: {blocker}")
            else:
                print_result(False, f"Goal not blocked (status={status})")
        else:
            print_result(False, "Could not find goal")
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

    # Complete one dependency
    print_test("Complete first dependency")
    try:
        memory.update_goal(
            goal_description="Set up test environment",
            status="completed",
            completion_notes="Environment ready"
        )
        print_result(True, "Completed 'Set up test environment'")
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

    # Try again (should still be blocked)
    print_test("Attempt completion with one dependency remaining")
    try:
        memory.update_goal(
            goal_description="Run full test suite",
            status="completed"
        )

        result = memory.kgraph.query_goal_by_description("Run full test suite", return_metadata=True)
        if result:
            _, metadata = result
            status = metadata.get('goal_status')
            blocker = metadata.get('blocker_reason')

            if status == "blocked" and "Write unit tests" in blocker:
                print_result(True, f"Still blocked by remaining dependency")
            else:
                print_result(False, f"Should still be blocked (status={status})")
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

    # Complete second dependency
    print_test("Complete second dependency")
    try:
        memory.update_goal(
            goal_description="Write unit tests",
            status="completed",
            completion_notes="Tests written"
        )
        print_result(True, "Completed 'Write unit tests'")
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

    # Now should be able to complete
    print_test("Complete goal with all dependencies met")
    try:
        memory.update_goal(
            goal_description="Run full test suite",
            status="completed",
            completion_notes="All tests passing"
        )

        result = memory.kgraph.query_goal_by_description("Run full test suite", return_metadata=True)
        if result:
            _, metadata = result
            status = metadata.get('goal_status')

            if status == "completed":
                print_result(True, "Goal successfully completed after dependencies met")
            else:
                print_result(False, f"Goal not completed (status={status})")
        else:
            print_result(False, "Could not find goal")
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

    return True

def test_forever_goal_prevention(memory):
    """Test that forever goals cannot be completed."""
    print_section("TEST 3: Forever Goal Completion Prevention")

    print_test("Attempt to complete forever goal")
    try:
        memory.update_goal(
            goal_description="Continuously improve programming skills",
            status="completed",
            completion_notes="Trying to complete a forever goal"
        )

        # Check that it's still ongoing
        result = memory.kgraph.query_goal_by_description(
            "Continuously improve programming skills",
            return_metadata=True
        )

        if result:
            _, metadata = result
            status = metadata.get('goal_status')
            blocker = metadata.get('blocker_reason')

            if status == "ongoing" and "forever goal" in blocker.lower():
                print_result(True, f"Forever goal correctly prevented from completion")
                print(f"      Status: {status}")
                print(f"      Blocker: {blocker}")
            else:
                print_result(False, f"Forever goal changed status to {status}")
        else:
            print_result(False, "Could not find forever goal")
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

    return True

def test_goal_suggestions(memory):
    """Test goal suggestion system."""
    print_section("TEST 4: Goal Suggestion System")

    # Create goals with different priorities and types
    print_test("Create goals for suggestion testing")
    try:
        memory.create_goal(
            owner="Sophia",
            description="Low priority task",
            priority=2,
            source="test"
        )
        memory.create_goal(
            owner="Sophia",
            description="High priority standard goal",
            priority=5,
            source="test"
        )
        memory.create_goal(
            owner="Sophia",
            description="Derived goal from instrumental",
            priority=4,
            goal_type="derived",
            parent_goal="Continuously improve programming skills",
            source="test"
        )
        print_result(True, "Created test goals")
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

    # Get suggestion
    print_test("Get next goal suggestion")
    try:
        suggestion = memory.suggest_next_goal(owner="Sophia")

        if suggestion:
            print_result(True, "Got suggestion")
            print(f"      Goal: {suggestion['goal_description']}")
            print(f"      Priority: {suggestion['priority']}")
            print(f"      Score: {suggestion['score']}")
            print(f"      Type: {suggestion.get('goal_type', 'unknown')}")
            print(f"      Reasoning: {suggestion['reasoning']}")

            # Derived goals should get priority boost
            if suggestion.get('goal_type') == 'derived':
                print_result(True, "Derived goal got priority (expected due to +20 boost)")
            elif suggestion['priority'] == 5:
                print_result(True, "High priority goal suggested")
            else:
                print(f"      Note: Suggested {suggestion.get('goal_type', 'standard')} goal")
        else:
            print_result(False, "No suggestion returned")
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

    return True

def test_prompt_inclusion(memory):
    """Test goal auto-inclusion in agent prompt."""
    print_section("TEST 5: Auto-Prompt Inclusion")

    print_test("Get goals for agent prompt")
    try:
        prompt_goals = memory.get_active_goals_for_prompt(owner="Sophia", limit=10)

        print("\nGoals that will appear in agent prompt:")
        print("-" * 60)
        print(prompt_goals)
        print("-" * 60)

        if prompt_goals:
            # Check for instrumental goals
            has_instrumental = "INSTRUMENTAL" in prompt_goals or "ONGOING" in prompt_goals
            # Check for priority stars
            has_stars = "★" in prompt_goals
            # Check for derived goals
            has_derived = "DERIVED" in prompt_goals

            print_result(has_instrumental, "Instrumental goals included")
            print_result(has_stars, "Priority stars shown")
            print_result(has_derived, "Derived goals included")

            if has_instrumental and has_stars:
                print_result(True, "Prompt formatting correct")
            else:
                print_result(False, "Prompt formatting issues")
        else:
            print_result(False, "No goals in prompt")
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

    return True

def test_goal_hierarchy(memory):
    """Test parent-child goal relationships."""
    print_section("TEST 6: Goal Hierarchy")

    print_test("Query goals with parent-child relationships")
    try:
        all_goals = memory.query_goals(owner="Sophia", limit=100)

        parent_goals = {}
        for triple, metadata in all_goals:
            parent = metadata.get('parent_goal_id')
            if parent:
                if parent not in parent_goals:
                    parent_goals[parent] = []
                parent_goals[parent].append(triple[2])

        if parent_goals:
            print("\nGoal Hierarchy:")
            for parent, children in parent_goals.items():
                print(f"\n  {parent}")
                for child in children:
                    print(f"    └─ {child}")
            print_result(True, f"Found {len(parent_goals)} parent goals with children")
        else:
            print_result(False, "No hierarchical relationships found")
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

    return True

def test_goal_progress(memory):
    """Test goal progress statistics."""
    print_section("TEST 7: Goal Progress Statistics")

    print_test("Get goal progress")
    try:
        progress = memory.get_goal_progress(owner="Sophia")

        print("\nGoal Statistics:")
        print(f"  Total Goals: {progress['total_goals']}")
        print(f"  Active: {progress['active_count']}")
        print(f"  Completion Rate: {progress['completion_rate']*100:.1f}%")
        print(f"\n  By Status:")
        for status, count in progress['by_status'].items():
            if count > 0:
                print(f"    {status}: {count}")
        print(f"\n  By Priority:")
        for priority, count in progress['by_priority'].items():
            if count > 0:
                print(f"    Priority {priority}: {count}")

        print_result(True, "Progress statistics retrieved")

        if progress['total_goals'] > 0:
            print_result(True, f"Tracking {progress['total_goals']} total goals")
        else:
            print_result(False, "No goals found")
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

    return True

def main():
    """Run all tests."""
    print("\n" + "="*80)
    print(" COMPREHENSIVE GOAL SYSTEM TEST SUITE")
    print("="*80)

    # Initialize system
    print("\nInitializing memory systems...")
    kgraph = VectorKnowledgeGraph()
    memory = AssociativeSemanticMemory(kgraph)
    print("✓ Memory systems initialized")

    # Run tests
    results = {}

    results["Basic Creation"] = test_basic_goal_creation(memory)
    results["Dependency Blocking"] = test_dependency_blocking(memory)
    results["Forever Goal Prevention"] = test_forever_goal_prevention(memory)
    results["Goal Suggestions"] = test_goal_suggestions(memory)
    results["Prompt Inclusion"] = test_prompt_inclusion(memory)
    results["Goal Hierarchy"] = test_goal_hierarchy(memory)
    results["Progress Statistics"] = test_goal_progress(memory)

    # Summary
    print_section("TEST SUMMARY")

    passed = sum(1 for result in results.values() if result)
    total = len(results)

    print(f"\nResults: {passed}/{total} test suites passed\n")

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {test_name}")

    print("\n" + "="*80)

    if passed == total:
        print(" ALL TESTS PASSED!")
        print("="*80)
        return 0
    else:
        print(f" {total - passed} TEST(S) FAILED")
        print("="*80)
        return 1

if __name__ == "__main__":
    sys.exit(main())
