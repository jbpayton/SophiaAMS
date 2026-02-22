import requests
from typing import Optional, List, Dict, Any
from langchain.tools import BaseTool
from pydantic import BaseModel, Field


class SearXNGSearchInput(BaseModel):
    query: str = Field(description="Search query to execute")


class SearXNGSearchTool(BaseTool):
    name: str = "searxng_search"
    description: str = "Search the web using SearXNG. Useful for finding current information, news, and general web content."
    args_schema: type[BaseModel] = SearXNGSearchInput
    searxng_url: str = "http://192.168.2.94:8088"

    def __init__(self, searxng_url: str = "http://192.168.2.94:8088"):
        super().__init__()
        self.searxng_url = searxng_url.rstrip('/')

    def _run(self, query: str) -> str:
        """Execute a search using SearXNG"""
        try:
            params = {
                'q': query,
                'category': 'general',
                'format': 'json',
                'lang': 'en'
            }

            response = requests.get(f"{self.searxng_url}/search", params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            results = data.get('results', [])

            if not results:
                return f"No search results found for query: {query}"

            formatted_results = []
            for i, result in enumerate(results[:5], 1):  # Limit to top 5 results
                title = result.get('title', 'No title')
                url = result.get('url', 'No URL')
                content = result.get('content', 'No description')

                formatted_results.append(f"{i}. **{title}**\n   URL: {url}\n   Description: {content}\n")

            return f"Search results for '{query}':\n\n" + "\n".join(formatted_results)

        except requests.exceptions.RequestException as e:
            return f"Error searching SearXNG: {str(e)}"
        except Exception as e:
            return f"Unexpected error during search: {str(e)}"

    async def _arun(self, query: str) -> str:
        """Async version of the search"""
        return self._run(query)