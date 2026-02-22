---
name: web-search
description: Search the web using SearXNG for current information
---

# Web Search

Search the web for current information using SearXNG.

## Usage

```run
exec(open("skills/web-search/scripts/searxng_search.py").read())
results = searxng_search("your search query")
print(results)
```

## When to Use
- When you need current/recent information not in memory
- News, events, and time-sensitive topics
- ALWAYS check memory first before searching the web
