"""Quick web page reader — uses Crawl4AI for JS-rendered, encoding-safe extraction"""

import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator


async def _fetch_page(url, max_chars=10000):
    browser_config = BrowserConfig(headless=True)
    crawl_config = CrawlerRunConfig(
        page_timeout=30000,
        cache_mode=CacheMode.BYPASS,
        word_count_threshold=10,
        excluded_tags=["nav", "footer", "script", "style", "header"],
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter()
        ),
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=crawl_config)

        if not result.success:
            return f"Error: Could not fetch URL: {url} — {result.error_message}"

        md = result.markdown
        content = md.fit_markdown if md and md.fit_markdown else (md.raw_markdown if md else "")
        if not content or not content.strip():
            return f"Error: Could not extract content from: {url}"

        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n[Content truncated — {len(content)} total characters]"

        return f"Content from {url}:\n\n{content}"


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
        return asyncio.run(_fetch_page(url, max_chars))
    except Exception as e:
        return f"Error reading web page: {e}"
