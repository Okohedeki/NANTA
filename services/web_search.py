"""Thin async wrapper around the `ddgs` package (DuckDuckGo).

Combines three DDG backends — general web, news, videos — so auto-research
surfaces articles, news items, and video sources (YouTube etc.) in one pass.
`ingest_url` already dispatches by URL pattern so videos flow through the
standard transcription pipeline.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


def _ddg_multi(query: str, max_results: int) -> list[dict]:
    """Synchronous DDG call — runs inside asyncio.to_thread. Deduped by URL."""
    from ddgs import DDGS
    out = []
    seen = set()

    def _push(url: str, title: str, snippet: str, kind: str):
        if not url or url.lower() in seen:
            return
        seen.add(url.lower())
        out.append({"url": url, "title": title, "snippet": snippet, "kind": kind})

    ddg = DDGS()
    try:
        for r in ddg.text(query, max_results=max_results):
            _push(r.get("href") or r.get("url") or "", r.get("title") or "",
                  r.get("body") or r.get("snippet") or "", "text")
    except Exception as e:
        logger.warning("DDGS text %r failed: %s", query, e)

    try:
        for r in ddg.news(query, max_results=max(3, max_results // 2)):
            _push(r.get("url") or r.get("href") or "", r.get("title") or "",
                  r.get("body") or r.get("excerpt") or "", "news")
    except Exception as e:
        logger.debug("DDGS news %r failed: %s", query, e)

    try:
        for r in ddg.videos(query, max_results=max(2, max_results // 3)):
            _push(r.get("content") or r.get("url") or "", r.get("title") or "",
                  r.get("description") or "", "video")
    except Exception as e:
        logger.debug("DDGS videos %r failed: %s", query, e)

    return out


async def search_web(query: str, max_results: int = 10) -> list[dict]:
    """Return a list of {url, title, snippet, kind} dicts. Empty list on failure."""
    if not query or not query.strip():
        return []
    try:
        return await asyncio.to_thread(_ddg_multi, query, max_results)
    except Exception as e:
        logger.warning("search_web wrapper failure for %r: %s", query, e)
        return []
