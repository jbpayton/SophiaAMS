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

## Update Goal Status

```run
exec(open("skills/goal-management/scripts/goals.py").read())
print(update_goal("Learn about transformer models", status="completed", notes="Learned about attention mechanisms"))
```

## Goal Workflow
1. `check_goals()` — see current goals
2. Pick a goal (don't create duplicates!)
3. `update_goal(desc, status="in_progress")` — mark in progress
4. Do the work (search, read, learn)
5. `update_goal(desc, status="completed", notes="...")` — mark COMPLETED with notes!
