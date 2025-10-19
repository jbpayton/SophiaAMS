# Testing Procedural Knowledge in the Web App

## Two Ways to Test

### Method 1: Document Upload (Teaching via Documents)
Upload a document with procedural knowledge → System extracts and stores it → Query later in chat

### Method 2: Chat with Tool Calls (Interactive Learning & Usage)
Teach procedures in chat → LLM uses `lookup_procedure` tool when planning tasks

---

## Method 1: Document Upload Testing

### Step 1: Start the Services

```bash
# Terminal 1: Python API Server
cd c:\Users\joeyp\SophiaAMS
python api_server.py

# Terminal 2: Node.js Server
cd sophia-web\server
npm start

# Terminal 3: React Client
cd sophia-web\client
npm run dev
```

### Step 2: Create a Test Document

Save this as `deployment_guide.txt`:

```
# Web Application Deployment Guide

To deploy a web application to production:

1. First, prepare the environment:
   - Create a virtual environment: python -m venv venv
   - Activate it: source venv/bin/activate (Linux/Mac) or venv\Scripts\activate (Windows)
   - Install dependencies: pip install -r requirements.txt

2. Then, build the application:
   - Run tests first: pytest tests/ -v
   - Build frontend assets: npm run build
   - This requires Node.js version 18 or higher

3. Next, configure the web server:
   - Update nginx configuration at /etc/nginx/sites-available/myapp
   - Test configuration: sudo nginx -t
   - Reload nginx: sudo systemctl reload nginx

4. Finally, deploy the code:
   - Pull latest code: git pull origin main
   - Restart application service: sudo systemctl restart myapp
   - Verify deployment: curl http://localhost:8000/health

Alternative deployment method:
You can use Docker for containerized deployment instead.
Example: docker-compose up -d --build

This deployment process enables zero-downtime updates when combined with blue-green deployment.
```

### Step 3: Upload Document in Web UI

1. Go to `http://localhost:3000`
2. Navigate to **Admin** page
3. Find "Document Upload" section
4. Paste the deployment guide text
5. Set source: `deployment_guide`
6. Click "Upload Document"

### Step 4: Verify Extraction

Check the console logs in Terminal 1 (Python API):
```
Should see: Extracted X triples
Look for procedural predicates like:
- accomplished_by
- requires
- has_step
- followed_by
- example_usage
```

### Step 5: Test Retrieval in Chat

Go to the **Chat** page and ask:

**Example 1:**
```
User: "How do I deploy a web application?"
```

The system should:
- Retrieve factual memories (if auto-retrieve is on)
- Show the deployment procedures you uploaded
- Response should reference the steps you taught

**Example 2 (Direct Query):**
```
User: "What are the steps to prepare an environment for deployment?"
```

Should retrieve the preparation steps (venv, pip install, etc.)

---

## Method 2: Chat with Tool Calls (Interactive)

This is MORE POWERFUL - the LLM will actively use the `lookup_procedure` tool!

### Step 1: Teach Procedures in Chat

In the **Chat** page, teach the system:

```
User: "To set up a Python development environment:
1. Install Python 3.10 or higher
2. Create a virtual environment with: python -m venv myenv
3. Activate it: source myenv/bin/activate on Linux/Mac, or myenv\Scripts\activate on Windows
4. Install packages: pip install -r requirements.txt

Example of installing a specific package:
pip install flask==2.3.0

Alternatively, you can use conda for package management.
Example: conda create -n myenv python=3.10"
```

The system will:
- Extract procedural triples automatically
- Store with procedural predicates
- Mark as "procedure" in topics

### Step 2: Ask It to Use What It Learned

Now ask the LLM to IMPLEMENT something:

```
User: "I need to set up a Python project for a Flask web app. Can you guide me through it?"
```

**What happens:**
1. LLM recognizes this is a procedural task
2. **LLM calls `lookup_procedure` tool** with goal: "set up Python environment"
3. Tool retrieves the procedures you taught
4. You'll see a **green indicator**: `🔧 Looking up procedure: set up Python environment`
5. LLM synthesizes a response using retrieved procedures

### Step 3: Test Hierarchical Composition

Teach multiple related procedures, then ask for a complex task:

**Teach API usage:**
```
User: "To make HTTP requests in Python:
Use the requests library: pip install requests
Then import it: import requests

For GET requests: response = requests.get(url)
For POST requests: response = requests.post(url, json=data)

Example:
response = requests.post('https://api.example.com/users', json={'name': 'Alice'})
```

**Teach data processing:**
```
User: "To process JSON data in Python:
Parse JSON string: data = json.loads(json_string)
Access fields: user_name = data['name']
Write to file: json.dump(data, file, indent=2)

Example:
import json
with open('data.json', 'w') as f:
    json.dump({'key': 'value'}, f, indent=2)
```

**Now ask for complex task:**
```
User: "Build me a script that fetches user data from an API and saves it to a JSON file"
```

The LLM should:
1. Call `lookup_procedure("make HTTP requests")`
2. Call `lookup_procedure("process JSON data")`
3. Synthesize both procedures into a complete solution!

---

## What to Look For

### Successful Document Upload (Method 1)

**In Python console:**
```
📄 Document upload request: {'source': 'deployment_guide', 'textLength': 1234}
Extracted 15 triples
Original triples: 15
✅ Document uploaded successfully
```

**In Admin UI:**
- Stats should show increased triple count
- Topics should include "procedure"
- Can explore entities and see deployment-related terms

### Successful Tool Calls (Method 2)

**In Browser (Chat UI):**
```
User: "How do I set up Python environment?"

[Shows green indicator]
🔧 Looking up procedure: set up Python environment