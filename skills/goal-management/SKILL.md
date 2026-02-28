---
name: goal-management
description: Create, update, and track personal goals with priority levels
---

# Goal Management

Manage your personal goals for autonomous self-improvement.

## Check Goals

```run
exec(open("skills/goal-management/scripts/goals.py").read())
print(check_goals(active_only=True))
```

## Set a New Goal

```run
exec(open("skills/goal-management/scripts/goals.py").read())
print(set_goal("Learn about transformer models", priority=3))
```

## Mark Goal In Progress

```run
exec(open("skills/goal-management/scripts/goals.py").read())
print(mark_in_progress("Learn about transformer models"))
```

## Mark Goal Completed

```run
exec(open("skills/goal-management/scripts/goals.py").read())
print(mark_completed("Learn about transformer models", notes="Learned about attention mechanisms"))
```

## Update Goal Status (advanced)

```run
exec(open("skills/goal-management/scripts/goals.py").read())
print(update_goal("Learn about transformer models", status="blocked", notes="Need GPU access"))
```

## Decompose a Broad Goal

For broad goals like "Learn about X", break them into specific sub-goals first:

```run
exec(open("skills/goal-management/scripts/goals.py").read())
print(set_goal("Research the founding of Rome", parent_goal="Learn about the Roman Empire"))
```

## Check Sub-Goals

```run
exec(open("skills/goal-management/scripts/goals.py").read())
print(check_subgoals("Learn about the Roman Empire"))
```

## Goal Workflow
1. `check_goals()` — see current goals
2. If the goal is broad, **decompose** it into 3-5 sub-goals using `set_goal(desc, parent_goal="...")`
3. Pick a specific goal (don't create duplicates!)
4. `mark_in_progress(desc)` — mark in progress
5. Do the work (search, read, learn)
6. `mark_completed(desc, notes="...")` — mark COMPLETED with notes!

**IMPORTANT**: Parent goals cannot be completed until all sub-goals are done. Always call `mark_completed()` when you finish a goal.
