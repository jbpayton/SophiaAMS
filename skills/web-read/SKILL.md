---
name: web-read
description: Quickly read and extract clean content from a web page (temporary, not stored)
---

# Web Read

Quickly read a web page for immediate context. Like "skimming" — fast but temporary.
Does NOT store anything in permanent memory.

## Usage

```run
exec(open("skills/web-read/scripts/read_page.py").read())
content = read_web_page("https://example.com/article")
print(content)
```

## When to Use
- Quick lookup of a specific URL
- Getting context from a link someone shared
- When you DON'T need to permanently remember the content
- For permanent learning, use the web-learn skill instead
