"""Permanent web page learning — extracted from agent_server.py learn_from_web_page_tool"""

import json
import time
import urllib.request
import urllib.error
import trafilatura


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

        chunks = _chunk_text_by_paragraphs(extracted, max_chunk_size=2000)
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
