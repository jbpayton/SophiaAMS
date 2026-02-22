---
name: knowledge-overview
description: Get a structured thematic overview of all knowledge or a specific topic
---

# Knowledge Overview

Get a structured view of your knowledge organized by topics.

## General Overview

```run
from sophia_memory import explorer
import json

overview = explorer.overview()
print(json.dumps(overview, indent=2))
```

## Topic-Specific Overview

```run
from sophia_memory import explorer
import json

overview = explorer.overview("neural networks")
print(json.dumps(overview, indent=2))
```

## When to Use
- "What do you know?" → general overview
- "What do you know about X?" → topic-specific
- "What have you learned?" → general overview
- Any question about the breadth/structure of your knowledge
