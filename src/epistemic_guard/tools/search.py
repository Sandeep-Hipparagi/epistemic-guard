from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, Sequence
from pydantic import BaseModel, ConfigDict, Field

from epistemic_guard.config import Settings, get_settings
from epistemic_guard.schemas import ExtractedClaim

logger = logging.getLogger(__name__)


class SearchHit(BaseModel):
    """An individual search engine result."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(description="Title of the search result page.")
    url: str = Field(description="Canonical URL of the search result.")
    snippet: str = Field(description="Text snippet or abstract from the page.")
    published_date: Optional[str] = Field(
        default=None,
        description="Publication date string if provided by search engine (e.g. '2026-11-19' or ISO string).",
    )
    source_query: str = Field(description="The search query that generated this result.")


class SearchProvider(ABC):
    """Abstract base protocol for search providers."""

    @abstractmethod
    def search(self, query: str, max_results: int = 8) -> list[SearchHit]:
        """Execute a search query and return a list of SearchHit items."""
        pass


class DuckDuckGoSearchProvider(SearchProvider):
    """DuckDuckGo search provider.

    Zero-API-key default enabling out-of-the-box open-source operation.
    """

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def search(self, query: str, max_results: int = 8) -> list[SearchHit]:
        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        try:
            from duckduckgo_search import DDGS

            hits: list[SearchHit] = []
            with DDGS(timeout=int(self.timeout)) as ddgs:
                results = ddgs.text(cleaned_query, max_results=max_results)
                for item in results:
                    url = item.get("href") or item.get("link") or ""
                    title = item.get("title") or ""
                    body = item.get("body") or item.get("snippet") or ""
                    # DuckDuckGo occasionally provides date in extra fields
                    pub_date = item.get("date") or None

                    if url:
                        hits.append(
                            SearchHit(
                                title=title,
                                url=url,
                                snippet=body,
                                published_date=pub_date,
                                source_query=cleaned_query,
                            )
                        )
            return hits
        except Exception as e:
            logger.warning("DuckDuckGo search query '%s' failed: %s", cleaned_query, e)
            return []


class TavilySearchProvider(SearchProvider):
    """Tavily search provider for deep agentic search.

    Active when search_provider='tavily' and search_api_key is set.
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = 15.0) -> None:
        settings = get_settings()
        self.api_key = (
            api_key
            or (settings.search_api_key.get_secret_value() if settings.search_api_key else None)
        )
        self.timeout = timeout

    def search(self, query: str, max_results: int = 8) -> list[SearchHit]:
        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        if not self.api_key:
            logger.warning("Tavily search requested but no API key configured.")
            return []

        import httpx

        try:
            resp = httpx.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.api_key,
                    "query": cleaned_query,
                    "max_results": max_results,
                    "search_depth": "advanced",
                    "include_answer": False,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])

            hits: list[SearchHit] = []
            for item in results:
                url = item.get("url", "")
                title = item.get("title", "")
                content = item.get("content", "")
                pub_date = item.get("published_date")

                if url:
                    hits.append(
                        SearchHit(
                            title=title,
                            url=url,
                            snippet=content,
                            published_date=pub_date,
                            source_query=cleaned_query,
                        )
                    )
            return hits
        except Exception as e:
            logger.warning("Tavily search query '%s' failed: %s", cleaned_query, e)
            return []


class MockSearchProvider(SearchProvider):
    """Deterministic, offline mock search provider for unit tests and benchmarks."""

    def __init__(
        self,
        canned_results: Optional[dict[str, list[SearchHit]]] = None,
        default_hits: Optional[list[SearchHit]] = None,
    ) -> None:
        # Map of lowercase query substrings or exact queries to hits
        self._canned: dict[str, list[SearchHit]] = canned_results or {}
        self._default_hits: list[SearchHit] = default_hits or []
        self.recorded_queries: list[str] = []

    def register_response(self, query_key: str, hits: list[SearchHit]) -> None:
        """Register a canned response for a query key (case-insensitive substring)."""
        self._canned[query_key.lower()] = hits

    def search(self, query: str, max_results: int = 8) -> list[SearchHit]:
        cleaned = query.strip()
        self.recorded_queries.append(cleaned)
        cleaned_lower = cleaned.lower()

        # Check exact or substring matches in registered canned responses
        for key, hits in self._canned.items():
            if key in cleaned_lower or cleaned_lower in key:
                return hits[:max_results]

        return self._default_hits[:max_results]


def build_provenance_queries(claim: ExtractedClaim) -> list[str]:
    """Construct targeted, deterministic search queries to answer the 3 provenance questions.

    Queries generated:
      1. Exact Quote / Verbatim Match: "<verbatim_quote>" <speaker>
      2. Primary Media / Official Venue: <speaker> <normalized_claim> (video OR transcript OR "press conference" OR official)
      3. Named Outlet Corroboration: <speaker> <normalized_claim> (reuters OR apnews OR bbc OR statement)
    """
    queries: list[str] = []
    speaker_part = f"{claim.speaker.strip()} " if claim.speaker and claim.speaker.strip() else ""
    norm_claim = claim.normalized_claim.strip()

    # Query 1: Exact Quote Match (if verbatim quote exists)
    if claim.verbatim_quote and claim.verbatim_quote.strip():
        quote_clean = claim.verbatim_quote.strip().strip('"\'')
        if quote_clean:
            q1 = f'"{quote_clean}" {speaker_part}'.strip()
            queries.append(q1)

    # Query 2: Primary Media / Official Venue Search
    q2 = f'{speaker_part}{norm_claim} (video OR transcript OR "press conference" OR official)'.strip()
    queries.append(q2)

    # Query 3: Named Outlet Corroboration Search
    q3 = f'{speaker_part}{norm_claim} (reuters OR apnews OR bbc OR statement)'.strip()
    queries.append(q3)

    # Deduplicate while preserving order
    unique_queries: list[str] = []
    for q in queries:
        if q and q not in unique_queries:
            unique_queries.append(q)

    return unique_queries
