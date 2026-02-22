"""
Workspace initializer: generates sophia_memory.py shim in the agent's workspace.
The shim provides helper classes that call back to the FastAPI server's REST endpoints,
allowing agent-executed code to access the memory system.
"""

import os


_SHIM_TEMPLATE = '''"""
Sophia Memory API — auto-generated shim for agent workspace.
Calls back to the SophiaAMS FastAPI server at: {base_url}
"""

import json
import urllib.request
import urllib.error

_BASE = "{base_url}"


def _post(path, payload):
    """POST JSON to the server and return parsed response."""
    url = f"{{_BASE}}{{path}}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={{"Content-Type": "application/json"}})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {{"error": f"HTTP {{e.code}}: {{e.reason}}"}}
    except Exception as e:
        return {{"error": str(e)}}


def _get(path):
    """GET from the server and return parsed response."""
    url = f"{{_BASE}}{{path}}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {{"error": f"HTTP {{e.code}}: {{e.reason}}"}}
    except Exception as e:
        return {{"error": str(e)}}


class _Memory:
    """Semantic memory queries via REST."""

    @staticmethod
    def query(text, limit=10):
        """Search semantic memory for related information."""
        return _post("/query", {{"query": text, "limit": limit}})

    @staticmethod
    def query_procedure(goal, limit=10):
        """Look up learned procedures."""
        return _post("/query/procedure", {{"goal": goal, "limit": limit}})

    @staticmethod
    def store(fact):
        """Store a fact in semantic memory."""
        return _post("/ingest", {{"text": fact, "source": "agent_code"}})


class _Episodes:
    """Episodic memory queries via REST."""

    @staticmethod
    def search(query, limit=5):
        """Search past episodes by content."""
        return _post("/api/episodes/search", {{"query": query, "limit": limit}})

    @staticmethod
    def timeline(days=7):
        """Get recent activity timeline."""
        return _get(f"/api/episodes/timeline?days={{days}}")


class _Explorer:
    """Knowledge graph exploration via REST."""

    @staticmethod
    def overview(topic=""):
        """Get knowledge overview, optionally filtered by topic."""
        return _post("/explore/entity", {{"query": topic}})


memory = _Memory()
episodes = _Episodes()
explorer = _Explorer()
'''


def init_workspace(workspace_dir: str, server_base_url: str = "http://localhost:5001") -> str:
    """
    Generate sophia_memory.py in the workspace directory.

    Args:
        workspace_dir: Path to the agent's workspace directory.
        server_base_url: Base URL of the SophiaAMS FastAPI server.

    Returns:
        Path to the generated file.
    """
    os.makedirs(workspace_dir, exist_ok=True)
    output_path = os.path.join(workspace_dir, "sophia_memory.py")

    content = _SHIM_TEMPLATE.format(base_url=server_base_url.rstrip("/"))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return output_path
