---
name: memory-browser
description: Browse and explore the knowledge graph interactively
---

# Memory Browser

Explore your knowledge graph interactively — browse entities, relationships, and clusters.

## Browse Entity Connections

```run
from sophia_memory import explorer
import json

result = explorer.overview("entity name or topic")
print(json.dumps(result, indent=2))
```

## When to Use
- Exploring what you know about a specific entity
- Understanding relationships between concepts
- Discovering knowledge clusters
