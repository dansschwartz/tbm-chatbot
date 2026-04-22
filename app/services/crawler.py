"""Feature 42: Web page content crawler for document auto-ingestion."""

import logging
import re

import httpx

logger = logging.getLogger(__name__)


def _strip_html(html: str) -> str:
    """Strip HTML tags and extract readable text content."""
    # Remove script and style elements
    html = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', html, flags=re.IGNORECASE)
    # Remove nav, header, footer
    html = re.sub(r'<(nav|header|footer)[^>]*>[\s\S]*?</\1>', '', html, flags=re.IGNORECASE)
    # Convert block elements to newlines
    html = re.sub(r'<(br|p|div|h[1-6]|li|tr)[^>]*/?>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</(p|div|h[1-6]|li|tr|ul|ol|table)>', '\n', html, flags=re.IGNORECASE)
    # Strip remaining tags
    html = re.sub(r'<[^>]+>', '', html)
    # Decode common HTML entities
    html = html.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    html = html.replace('&nbsp;', ' ').replace('&quot;', '"').replace('&#39;', "'")
    # Collapse whitespace
    html = re.sub(r'[ \t]+', ' ', html)
    html = re.sub(r'\n\s*\n', '\n\n', html)
    return html.strip()


def _extract_title(html: str) -> str:
    """Extract page title from HTML."""
    match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.IGNORECASE | re.DOTALL)
    if match:
        return re.sub(r'<[^>]+>', '', match.group(1)).strip()
    return "Untitled Page"


async def crawl_url(url: str) -> dict:
    """Fetch a URL and extract text content.

    Returns {"title": str, "content": str, "url": str}
    Raises on failure.
    """
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(url, headers={
            "User-Agent": "TBM-Chatbot-Crawler/1.0 (NFP Knowledge Base Builder)"
        })
        response.raise_for_status()

    html = response.text
    title = _extract_title(html)
    content = _strip_html(html)

    if len(content) < 50:
        raise ValueError(f"Extracted content too short ({len(content)} chars) — page may be JavaScript-rendered or empty")

    logger.info("Crawled %s: %d chars, title=%s", url, len(content), title[:60])
    return {"title": title, "content": content, "url": url}
