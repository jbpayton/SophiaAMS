"""Permanent web page learning — uses Crawl4AI for JS-rendered, encoding-safe extraction"""

import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator


def _chunk_text_by_paragraphs(text, max_chunk_size=2000):
    """Split text into chunks by paragraphs, combining small paragraphs."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if not paragraphs:
        return [text]

    chunks = []
    current_chunk = []
    current_size = 0

    for para in paragraphs:
        para_size = len(para)
        if current_size + para_size > max_chunk_size and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [para]
            current_size = para_size
        else:
            current_chunk.append(para)
            current_size += para_size

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


async def _fetch_page(url):
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
            return None, f"Could not fetch URL: {url} — {result.error_message}"

        md = result.markdown
        content = md.fit_markdown if md and md.fit_markdown else (md.raw_markdown if md else "")
        if not content or not content.strip():
            return None, f"Could not extract content from: {url}"

        return content, None


def learn_from_url(url):
    """
    Read a web page, chunk it, and permanently store knowledge in semantic memory.

    Args:
        url: The web page URL to learn from

    Returns:
        Summary of what was learned
    """
    from sophia_memory import memory

    try:
        content, error = asyncio.run(_fetch_page(url))
        if error:
            return f"Error: {error}"

        chunks = _chunk_text_by_paragraphs(content, max_chunk_size=2000)
        total_stored = 0

        for i, chunk in enumerate(chunks):
            try:
                result = memory.store(chunk)
                if not isinstance(result, dict) or "error" not in result:
                    total_stored += 1
            except Exception as e:
                print(f"Error processing chunk {i + 1}: {e}")
                continue

        return (
            f"Successfully learned from {url}\n\n"
            f"Processed: {len(chunks)} chunks\n"
            f"Stored: {total_stored} chunks\n\n"
            f"This knowledge is now permanently stored and can be recalled anytime!"
        )

    except Exception as e:
        return f"Error learning from web page: {e}"
