---
name: episodic-recall
description: Recall past conversations and recent activity timeline from episodic memory
---

# Episodic Recall

Search episodic memory for past conversations and get activity timelines.

## Search Past Conversations

```run
from sophia_memory import episodes
import json

results = episodes.search("topic to search for", limit=5)
print(json.dumps(results, indent=2))
```

## Get Activity Timeline

```run
from sophia_memory import episodes
import json

timeline = episodes.timeline(days=7)
print(json.dumps(timeline, indent=2))
```

## When to Use
- "What did we discuss yesterday/today/last week?"
- "When did we talk about X?"
- "What have I been doing recently?"
- Any question involving temporal context (when, how recently)
