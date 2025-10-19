# Procedural Knowledge System - User Guide

## Overview

SophiaAMS now supports **procedural knowledge** - the ability to teach the AI **how to accomplish tasks** through hierarchical methods, alternatives, dependencies, and examples. The LLM actively queries this knowledge when planning and reasoning, not just for direct answers.

## Key Concepts

### What is Procedural Knowledge?

Procedural knowledge represents **HOW-TO information**:
- Methods to accomplish goals
- Alternative approaches
- Dependencies and prerequisites
- Step-by-step procedures
- Code examples and usage patterns

Unlike factual knowledge ("Python is a programming language"), procedural knowledge teaches **methods** ("To send an HTTP request, use `requests.post(url, json=data)`").

### How It Works

1. **Automatic Detection**: When you teach the AI how to do something, it automatically detects procedural patterns and stores them with special predicates
2. **Tool-Based Retrieval**: The LLM has a `lookup_procedure` tool it can call when planning tasks
3. **Hierarchical Composition**: High-level tasks can decompose into learned sub-procedures
4. **Multiple Solutions**: Captures that "not all things have one way" through alternatives

## Teaching Procedures

### Basic Syntax

The system automatically detects procedural knowledge from natural teaching patterns:

#### Method Declaration
```
"To [goal], use [method]"
"You can [goal] by [method]"
"[Method] for [purpose]"
```

**Example:**
```
User: "To send a POST request to an API, use requests.post(url, json=data)"
```

**Result:** Creates triple with `accomplished_by` predicate:
```
("send POST request to API", "accomplished_by", "requests.post")
```

#### Dependencies
```
"[Method] requires [dependency]"
"You need [X] to [goal]"
"First [step1], then [step2]"
```

**Example:**
```
User: "You need to import requests first before using requests.post"
```

**Result:** Creates triple with `requires` predicate:
```
("requests.post", "requires", "import requests")
```

#### Alternatives
```
"Instead of [X], use [Y]"
"Another way is [method]"
"You can also use [alternative]"
```

**Example:**
```
User: "You can send HTTP requests using the requests library or urllib. Another option is httpx for async support."
```

**Result:** Creates multiple triples with `alternatively_by` predicate:
```
("send HTTP requests", "accomplished_by", "requests library")
("send HTTP requests", "alternatively_by", "urllib")
("send HTTP requests", "alternatively_by", "httpx")
```

#### Examples (Code Examples Preserved Verbatim)
```
"Example: [code]"
"For instance: [code]"
"Like this: [code]"
```

**Example:**
```
User: "Example: requests.post('http://api.example.com', json={'key': 'value'})"
```

**Result:** Creates triple with `example_usage` predicate:
```
("requests.post", "example_usage", "requests.post('http://api.example.com', json={'key': 'value'})")
```

## Procedural Predicates

The system uses these special predicates for procedural knowledge:

| Predicate | Meaning | Example |
|-----------|---------|---------|
| `accomplished_by` | How to achieve a goal | ("deploy app", accomplished_by, "Docker") |
| `alternatively_by` | Alternative method | ("deploy app", alternatively_by, "Kubernetes") |
| `requires` | Dependency | ("Docker deploy", requires, "Dockerfile") |
| `requires_prior` | Sequential dependency | ("deploy", requires_prior, "run tests") |
| `enables` | Capability provided | ("Docker", enables, "containerization") |
| `is_method_for` | Purpose of tool | ("kubectl", is_method_for, "managing Kubernetes") |
| `example_usage` | Code example | ("kubectl", example_usage, "kubectl apply -f config.yaml") |
| `has_step` | Procedural step | ("deployment", has_step, "build image") |
| `followed_by` | Sequential step | ("build", followed_by, "test") |

## Using Procedural Knowledge

### In Conversations

The LLM automatically uses the `lookup_procedure` tool when:
- You ask it to implement or build something
- It needs to plan a multi-step procedure
- It wants to check for alternative approaches
- It's unsure about a specific method

### Example Session

```
User: "To send a weather API request, use requests.get with the URL and params.
       You need to import requests first.
       Example: requests.get('http://api.weather.com', params={'city': 'Boston'})"
```

The system extracts:
```json
{
  "triples": [
    {
      "subject": "send weather API request",
      "verb": "accomplished_by",
      "object": "requests.get",
      "topics": ["HTTP Requests", "API Usage", "procedure"]
    },
    {
      "subject": "requests.get",
      "verb": "requires",
      "object": "import requests",
      "topics": ["Dependencies", "Python Libraries", "procedure"]
    },
    {
      "subject": "requests.get",
      "verb": "example_usage",
      "object": "requests.get('http://api.weather.com', params={'city': 'Boston'})",
      "topics": ["Code Examples", "procedure"]
    }
  ]
}
```

Later, when you say:
```
User: "Build me a weather dashboard that fetches data from the weather API"
```

The LLM:
1. Thinks: "I need to know how to fetch weather API data"
2. Calls: `lookup_procedure("send weather API request")`
3. Retrieves: The methods, dependencies, and examples you taught
4. Responds: "Based on what you taught me, I'll use requests.get to fetch weather data. First, I'll import requests, then..."

### Hierarchical Procedures

You can teach high-level tasks that decompose into sub-tasks:

```
User: "To deploy an application:
1. First, run the tests
2. Then, build the Docker image
3. Finally, push to the registry

To run tests, use pytest. Example: pytest tests/
To build Docker image, use docker build. Example: docker build -t myapp:latest .
To push to registry, use docker push. Example: docker push myapp:latest"
```

When you later say "deploy the application", the LLM will:
1. Look up "deploy application" → finds the 3-step process
2. Look up each sub-step (run tests, build image, push)
3. Synthesize a complete plan with all details

## API Access

### Query Procedures Directly

**Endpoint:** `POST /api/query/procedure`

**Request:**
```json
{
  "goal": "send POST request",
  "include_alternatives": true,
  "include_examples": true,
  "include_dependencies": true,
  "limit": 20
}
```

**Response:**
```json
{
  "goal": "send POST request",
  "procedures": {
    "methods": [
      [["send POST request", "accomplished_by", "requests.post"], {"confidence": 0.95}]
    ],
    "alternatives": [
      [["send POST request", "alternatively_by", "urllib.request"], {"confidence": 0.85}]
    ],
    "dependencies": [
      [["requests.post", "requires", "import requests"], {"confidence": 0.90}]
    ],
    "examples": [
      [["requests.post", "example_usage", "requests.post('http://...', json={})"], {"confidence": 0.95}]
    ],
    "steps": [],
    "total_found": 4
  }
}
```

### Python API

```python
from AssociativeSemanticMemory import AssociativeSemanticMemory

# Query for procedures
result = memory.query_procedure(
    goal="send HTTP request",
    include_alternatives=True,
    include_examples=True,
    include_dependencies=True,
    limit=20
)

print(f"Found {result['total_found']} procedural facts")
print(f"Methods: {len(result['methods'])}")
print(f"Alternatives: {len(result['alternatives'])}")
```

## Advanced Features

### Abstraction Levels

Procedures are automatically tagged with abstraction levels:
- **Level 1 (Atomic)**: Basic commands/tools (e.g., "import requests")
- **Level 2 (Basic)**: Simple procedures (e.g., "send POST request")
- **Level 3 (High-level)**: Complex workflows (e.g., "deploy application")

### Confidence Scoring

Each procedural fact has a confidence score based on:
- Semantic similarity to the query
- Predicate type (e.g., `accomplished_by` is weighted higher)
- Topic relevance
- Source reliability

### Dependency Chains

The system follows dependency chains automatically:
```
Query: "deploy application"
→ Finds: ("deploy app", accomplished_by, "Docker")
→ Auto-follows: ("Docker", requires, "Dockerfile")
→ Auto-follows: ("Docker", requires, "Docker daemon running")
```

## UI Indicators

When the LLM uses the `lookup_procedure` tool, you'll see:

```
🔧 Looking up procedure: send POST request
```

This shows the AI is actively consulting its learned knowledge during planning.

## Best Practices

### Teaching Effectively

1. **Be Explicit**: Use clear "to X, use Y" language
2. **Include Examples**: Always provide code examples
3. **State Dependencies**: Mention prerequisites clearly
4. **Offer Alternatives**: Show multiple ways when applicable
5. **Use Hierarchies**: Break complex tasks into steps

### Example Teaching Session

❌ **Poor:**
```
User: "You can use requests"
```

✅ **Good:**
```
User: "To make HTTP requests in Python, use the requests library.
      You need to install it first with: pip install requests
      Then import it with: import requests

      To send a GET request, use requests.get(url)
      Example: response = requests.get('https://api.example.com/data')

      To send a POST request, use requests.post(url, json=data)
      Example: response = requests.post('https://api.example.com/create', json={'name': 'test'})

      Alternatively, you can use urllib (built-in) or httpx (async support)."
```

### Querying Effectively

The LLM will query procedures when:
- ✅ You ask it to implement something ("Build a REST API")
- ✅ You ask about methods ("How should I deploy this?")
- ✅ You're planning complex tasks ("Set up a CI/CD pipeline")

The LLM will NOT query procedures for:
- ❌ Simple facts ("What is Python?")
- ❌ Explanations ("Explain how HTTP works")
- ❌ General knowledge questions

## Troubleshooting

### Procedures Not Being Detected

If your teaching isn't being captured as procedures:
1. Use explicit patterns: "To X, use Y"
2. Include procedural keywords: "method", "use", "requires", "example"
3. Check that you have 3+ procedural indicators in your text

### LLM Not Using lookup_procedure

If the LLM isn't querying procedures:
1. Make sure you're asking it to **implement** or **build** something
2. Be explicit: "Using what I taught you, build X"
3. The LLM might not have procedural knowledge on that topic yet

### Wrong Procedures Retrieved

If irrelevant procedures are returned:
1. Be more specific in goal descriptions
2. Use consistent terminology when teaching
3. Include topical keywords in your teaching

## Technical Details

### Automatic Detection Score

Text needs a **procedural score ≥ 3** to use procedural extraction. Score comes from:
- Keywords: "to", "use", "using", "requires", "first", "then", "example", etc.
- Code indicators: "import", ".post(", ".get(", "def", "function"
- Step indicators: numbered lists, shell commands

### Storage Format

Procedural triples are stored identically to factual triples, but with:
- Procedural predicates (accomplished_by, requires, etc.)
- "procedure" in topics list
- Optional abstraction_level in metadata

### Retrieval Algorithm

1. Vector similarity search on goal text
2. Topic-based search for "procedure", "method", "how-to"
3. Predicate boosting (accomplished_by gets 2.0x weight)
4. Dependency chain following for top 3 methods
5. Organized by category (methods, alternatives, dependencies, examples)

---

**Start teaching your AI how to do things, not just what things are!** 🚀
