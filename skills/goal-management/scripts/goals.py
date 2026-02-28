"""Goal management — extracted from agent_server.py goal tools"""

import json
import urllib.request
import urllib.error

_BASE = None


def _get_base():
    global _BASE
    if _BASE is None:
        import os
        _BASE = os.environ.get("SOPHIA_SERVER_URL", "http://localhost:5001").rstrip("/")
    return _BASE


def _post(path, payload):
    url = f"{_get_base()}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(path):
    url = f"{_get_base()}{path}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_goals(active_only=True):
    """Review current goals."""
    params = f"?active_only={'true' if active_only else 'false'}"
    result = _get(f"/api/goals{params}")
    return json.dumps(result, indent=2)


def set_goal(description, priority=3, parent_goal=""):
    """Create a new goal."""
    result = _post("/api/goals/create", {
        "description": description,
        "priority": priority,
        "parent_goal": parent_goal,
    })
    return json.dumps(result, indent=2)


def update_goal(description, status="in_progress", notes=""):
    """Update goal status (pending, in_progress, completed, blocked, cancelled)."""
    payload = {"goal_description": description, "status": status}
    if notes:
        payload["completion_notes"] = notes
    result = _post("/api/goals/update", payload)
    return json.dumps(result, indent=2)


def mark_in_progress(description):
    """Mark a goal as in progress."""
    return update_goal(description, status="in_progress")


def mark_completed(description, notes=""):
    """Mark a goal as completed."""
    return update_goal(description, status="completed", notes=notes)


def suggest_next_goal():
    """Get suggestion for which goal to work on next."""
    result = _get("/api/goals/suggestion")
    return json.dumps(result, indent=2)


def check_subgoals(parent_description):
    """Check sub-goal status for a parent goal."""
    import urllib.parse
    encoded = urllib.parse.quote(parent_description)
    result = _get(f"/api/goals/subgoals?parent={encoded}")
    return json.dumps(result, indent=2)
