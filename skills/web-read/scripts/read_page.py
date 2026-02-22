"""Quick web page reader — extracted from agent_server.py read_web_page_tool"""

import trafilatura


def read_web_page(url, max_chars=10000):
    """
    Quickly read and extract clean content from a web page.
    Fast and temporary — does not store in memory.

    Args:
        url: The web page URL to read
        max_chars: Maximum characters to return

    Returns:
        Extracted text content from the page
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return f"Error: Could not fetch URL: {url}"

        extracted = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            favor_precision=True,
        )

        if not extracted:
            return f"Error: Could not extract content from: {url}"

        if len(extracted) > max_chars:
            extracted = extracted[:max_chars] + f"\n\n[Content truncated - {len(extracted)} total characters]"

        return f"Content from {url}:\n\n{extracted}"

    except Exception as e:
        return f"Error reading web page: {e}"
