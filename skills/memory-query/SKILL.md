---
name: memory-query
description: Search semantic memory for facts, relationships, and learned procedures
---

# Memory Query

Search your long-term semantic memory for facts and relationships.

## Usage

```run
from sophia_memory import memory
import json

# Search for facts about a topic
results = memory.query("topic to search for", limit=10)
print(json.dumps(results, indent=2))
```

## Procedure Lookup

Look up learned procedures for accomplishing specific tasks:

```run
from sophia_memory import memory
import json

results = memory.query_procedure("goal or task description", limit=10)
print(json.dumps(results, indent=2))
```

## When to Use
- When asked "what do you know about X?"
- When recalling facts, relationships, or learned information
- When looking up how to do something you've learned before
- After checking automatic recall for more detail
