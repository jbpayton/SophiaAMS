TRIPLE_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "triples": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "verb": {"type": "string"},
                    "object": {"type": "string"},
                    "source_text": {"type": "string"},
                    "speaker": {"type": ["string", "null"]},
                    "topics": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["subject", "verb", "object", "source_text", "topics"]
            }
        }
    },
    "required": ["triples"]
}

# TOPIC_EXTRACTION_SCHEMA has been removed as topics are now
# directly integrated into the TRIPLE_EXTRACTION_PROMPT and
# CONVERSATION_TRIPLE_EXTRACTION_PROMPT.

# ============================================================================
# GOAL SYSTEM SCHEMAS AND CONSTANTS
# ============================================================================

# Goal predicates for creating goal-related triples
GOAL_PREDICATES = {
    "has_goal": "Entity has a goal to accomplish",
    "subgoal_of": "This goal is a subgoal of a larger goal",
    "goal_status": "Current status of a goal",
    "goal_priority": "Priority level of a goal (1-5)",
    "blocks": "This goal blocks another goal from completion",
    "depends_on": "This goal depends on another goal being completed first",
    "enables": "Completing this goal enables another goal",
    "created_by": "Who/what created this goal",
    "completed_at": "When this goal was completed"
}

# Valid goal status values
GOAL_STATUS = {
    "pending": "Goal is defined but not yet started",
    "in_progress": "Actively working on this goal",
    "completed": "Goal has been achieved",
    "blocked": "Goal is blocked by another goal or issue",
    "cancelled": "Goal has been cancelled/abandoned"
}

# Priority levels (1 = lowest, 5 = highest)
GOAL_PRIORITY_LEVELS = {
    1: "very_low",
    2: "low",
    3: "medium",
    4: "high",
    5: "critical"
}

# Standard goal metadata fields
GOAL_METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "goal_status": {"type": "string", "enum": list(GOAL_STATUS.keys())},
        "priority": {"type": "integer", "minimum": 1, "maximum": 5},
        "created_timestamp": {"type": "number"},
        "status_updated_timestamp": {"type": "number"},
        "completion_timestamp": {"type": ["number", "null"]},
        "target_date": {"type": ["number", "null"]},
        "source": {"type": "string"},  # "sophia_autonomous", "user_suggested", etc.
        "episode_id": {"type": ["string", "null"]},
        "blocker_reason": {"type": ["string", "null"]},
        "completion_notes": {"type": ["string", "null"]},
        "parent_goal_id": {"type": ["string", "null"]},
        "topics": {"type": "array", "items": {"type": "string"}}
    }
}