"""
Tavily API client for web search and content extraction.

Used by Research Agent (M2-03) for gathering external information.
"""

import logging
from typing import Dict, List, Optional

from tavily import TavilyClient as BaseTavilyClient

from ..config.settings import get_settings
from ..models.research import SourceData


logger = logging.getLogger(__name__)


class TavilyClient:
    """
    Wrapper around Tavily API for research operations.

    Provides:
    - Web search with configurable results
    - Full page content extraction
    - Source deduplication and numbering
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Tavily client.

        Args:
            api_key: Tavily API key. If not provided, reads from settings.
        """
        settings = get_settings()
        self._api_key = api_key or settings.tavily_api_key

        if not self._api_key:
            raise ValueError(
                "Tavily API key not configured. "
                "Set TAVILY_API_KEY environment variable."
            )

        self._client = BaseTavilyClient(api_key=self._api_key)
        logger.info("Tavily client initialized")

    def search(
        self,
        query: str,
        max_results: int = 3,
        search_depth: str = "basic",
    ) -> List[Dict]:
        """
        Perform web search via Tavily API.

        Args:
            query: Search query string
            max_results: Maximum number of results (1-10)
            search_depth: "basic" or "advanced"

        Returns:
            List of search result dicts with url, title, content
        """
        logger.info(f"Tavily search: '{query}' (max_results={max_results})")

        try:
            response = self._client.search(
                query=query,
                max_results=max_results,
                search_depth=search_depth,
            )

            results = response.get("results", [])
            logger.info(f"Tavily search found {len(results)} results")

            return results

        except Exception as e:
            logger.error(f"Tavily search error: {e}")
            return []

    def extract(self, url: str) -> str:
        """
        Extract full page content from URL.

        Args:
            url: URL to extract content from

        Returns:
            Extracted text content (limited to 5000 chars)
        """
        logger.info(f"Tavily extract: {url}")

        try:
            response = self._client.extract(urls=[url])
            results = response.get("results", [])

            if results:
                content = results[0].get("raw_content", "")
                # Limit content size
                truncated = content[:5000]
                logger.info(
                    f"Extracted {len(content)} chars "
                    f"(stored: {len(truncated)})"
                )
                return truncated

            logger.warning(f"No content extracted from {url}")
            return ""

        except Exception as e:
            logger.error(f"Tavily extract error for {url}: {e}")
            return ""

    def search_and_create_sources(
        self,
        query: str,
        existing_sources: Dict[str, SourceData],
        max_results: int = 3,
    ) -> Dict[str, SourceData]:
        """
        Search and create SourceData objects with proper numbering.

        Handles deduplication by URL.

        Args:
            query: Search query
            existing_sources: Current sources dict for numbering
            max_results: Maximum results

        Returns:
            Dict of new sources (URL -> SourceData)
        """
        results = self.search(query, max_results)

        new_sources = {}
        next_number = len(existing_sources) + 1

        for result in results:
            url = result.get("url", "")

            # Skip duplicates
            if url in existing_sources:
                logger.debug(f"Skipping duplicate URL: {url}")
                continue

            source = SourceData(
                number=next_number,
                title=result.get("title", "No title"),
                url=url,
                snippet=result.get("content", "")[:200],
                char_count=len(result.get("content", "")),
            )

            new_sources[url] = source
            logger.debug(f"[{next_number}] {source.title[:60]}...")
            next_number += 1

        logger.info(f"Created {len(new_sources)} new sources from search")
        return new_sources

    def extract_source_content(
        self,
        source_number: int,
        sources: Dict[str, SourceData],
    ) -> Optional[SourceData]:
        """
        Extract full content for a source by its citation number.

        Args:
            source_number: Citation number [1], [2], etc.
            sources: Current sources dict

        Returns:
            Updated SourceData with full_content, or None if not found
        """
        # Find source by number
        target_source = None
        target_url = None

        for url, source in sources.items():
            if source.number == source_number:
                target_source = source
                target_url = url
                break

        if not target_source:
            logger.warning(f"Source [{source_number}] not found")
            return None

        # Extract content
        content = self.extract(target_url)

        if not content:
            return None

        # Update source
        updated_source = target_source.model_copy()
        updated_source.full_content = content
        updated_source.char_count = len(content)

        logger.info(
            f"Extracted content for source [{source_number}]: "
            f"{updated_source.char_count} chars"
        )

        return updated_source
