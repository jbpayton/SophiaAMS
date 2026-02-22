---
name: memory-stats
description: Get statistics about memory usage, triple counts, and knowledge base health
---

# Memory Stats

Get statistics about your memory systems.

## Usage

```run
from sophia_memory import memory, episodes
import json

# Query some stats
stats = memory.query("memory statistics overview")
print(json.dumps(stats, indent=2))
```

## When to Use
- "How much do you know?" / "How big is your memory?"
- Checking memory health and usage
- Understanding the scope of your knowledge base
