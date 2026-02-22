"""SearXNG web search — extracted from agent_server.py / searxng_tool.py"""

import json
import os
import urllib.request
import urllib.error
import urllib.parse


def searxng_search(query, num_results=5):
    """
    Search the web using SearXNG.

    Args:
        query: Search query string
        num_results: Maximum number of results to return

    Returns:
        Formatted search results string
    """
    searxng_url = os.environ.get("SEARXNG_URL", "http://localhost:8088").rstrip("/")

    params = urllib.parse.urlencode({
        "q": query,
        "category": "general",
        "format": "json",
        "lang": "en",
    })

    url = f"{searxng_url}/search?{params}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = data.get("results", [])
        if not results:
            return f"No search results found for query: {query}"

        formatted = []
        for i, result in enumerate(results[:num_results], 1):
            title = result.get("title", "No title")
            result_url = result.get("url", "No URL")
            content = result.get("content", "No description")
            formatted.append(f"{i}. **{title}**\n   URL: {result_url}\n   Description: {content}\n")

        return f"Search results for '{query}':\n\n" + "\n".join(formatted)

    except Exception as e:
        return f"Error searching SearXNG: {e}"
