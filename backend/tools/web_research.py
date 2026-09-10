"""
Generic Web Research tool.
Accesses the real public internet using live search providers (DuckDuckGo / Tavily).
Retrieves real sources, snippets, and page contents. ZERO mock data.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS
from backend.agent.tool_registry import BaseTool
from backend.config import settings
from backend.logging import logger
from backend.security import sanitize_web_content


class WebResearchTool(BaseTool):
    @property
    def name(self) -> str:
        return "web_research"

    @property
    def description(self) -> str:
        return (
            "Searches and retrieves current, real-time information from the live public internet. "
            "Use this tool whenever the user asks about current events, news, weather, stock prices, "
            "scores, recent announcements, facts after your training cut-off, or when freshness is needed."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The targeted search query optimized for information retrieval."
                },
                "freshness": {
                    "type": "string",
                    "enum": ["day", "week", "month", "year"],
                    "description": "Optional freshness constraint: 'day' for today's breaking news, 'week' for recent events."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of search results to return (default 5, max 10)."
                }
            },
            "required": ["query"]
        }

    async def execute(
        self,
        query: str,
        freshness: Optional[str] = None,
        max_results: int = 5,
        **kwargs
    ) -> Dict[str, Any]:
        retrieved_at = datetime.now(timezone.utc).isoformat()
        clean_query = query.strip()
        limit = min(max(1, max_results), 10)

        logger.info(f"Executing web research for query: '{clean_query}' (freshness={freshness}, limit={limit})")

        # Append freshness keyword to search query for natural relevance
        effective_query = clean_query
        if freshness == "day" and "today" not in effective_query.lower():
            effective_query = f"{effective_query} today"
        elif freshness == "week" and "recent" not in effective_query.lower():
            effective_query = f"{effective_query} recent this week"

        results_list: List[Dict[str, Any]] = []

        # 1. Primary: DuckDuckGo live search
        try:
            ddgs = DDGS(timeout=settings.WEB_TIMEOUT_SECONDS)
            raw_results = await asyncio.to_thread(
                ddgs.text,
                query=effective_query,
                max_results=limit
            )

            for item in raw_results:
                title = sanitize_web_content(item.get("title", ""))
                url = item.get("href", "") or item.get("url", "")
                snippet = sanitize_web_content(item.get("body", "") or item.get("snippet", ""))
                source = url.split("//")[-1].split("/")[0] if "//" in url else ""

                results_list.append({
                    "title": title,
                    "url": url,
                    "source": source,
                    "published_at": item.get("date", None),
                    "snippet": snippet,
                    "content": snippet[:400]
                })

        except Exception as e:
            logger.warning(f"DuckDuckGo DDGS search encountered an issue: {e}. Falling back to direct HTML query.")

        # 2. Fallback: Direct DuckDuckGo HTML parser via httpx
        if not results_list:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                }
                async with httpx.AsyncClient(timeout=settings.WEB_TIMEOUT_SECONDS, follow_redirects=True) as client:
                    resp = await client.post(
                        "https://html.duckduckgo.com/html/",
                        data={"q": clean_query},
                        headers=headers
                    )
                    if resp.is_success:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        search_results = soup.find_all("div", class_="result")
                        for r in search_results[:limit]:
                            title_elem = r.find("a", class_="result__url") or r.find("a", class_="result__snippet") or r.find("h2")
                            link_elem = r.find("a", class_="result__snippet") or r.find("a", class_="result__url")
                            snippet_elem = r.find("a", class_="result__snippet") or r.find("div", class_="result__snippet")

                            title = sanitize_web_content(title_elem.get_text() if title_elem else "")
                            raw_href = link_elem.get("href", "") if link_elem else ""
                            # Unquote DuckDuckGo redirect if present
                            if "uddg=" in raw_href:
                                import urllib.parse
                                try:
                                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
                                    url = parsed.get("uddg", [raw_href])[0]
                                except Exception:
                                    url = raw_href
                            else:
                                url = raw_href

                            snippet = sanitize_web_content(snippet_elem.get_text() if snippet_elem else "")
                            source = url.split("//")[-1].split("/")[0] if "//" in url else ""

                            if title or snippet:
                                results_list.append({
                                    "title": title or snippet[:50],
                                    "url": url,
                                    "source": source,
                                    "published_at": None,
                                    "snippet": snippet,
                                    "content": snippet[:400]
                                })
            except Exception as html_err:
                logger.warning(f"Direct DuckDuckGo HTML query fallback failed: {html_err}")

        # 3. Fallback: Tavily API if key configured
        if not results_list and settings.TAVILY_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=settings.WEB_TIMEOUT_SECONDS) as client:
                    resp = await client.post(
                        "https://api.tavily.com/search",
                        json={
                            "api_key": settings.TAVILY_API_KEY,
                            "query": clean_query,
                            "search_depth": "basic",
                            "max_results": limit
                        }
                    )
                    if resp.is_success:
                        data = resp.json()
                        for r in data.get("results", []):
                            results_list.append({
                                "title": sanitize_web_content(r.get("title", "")),
                                "url": r.get("url", ""),
                                "source": r.get("url", "").split("//")[-1].split("/")[0],
                                "published_at": r.get("published_date"),
                                "snippet": sanitize_web_content(r.get("content", "")),
                                "content": sanitize_web_content(r.get("content", ""))[:400]
                            })
            except Exception as tavily_err:
                logger.error(f"Tavily search fallback failed: {tavily_err}")

        # If zero results found due to network failure or empty query
        if not results_list:
            logger.warning(f"Web research returned 0 results for: '{clean_query}'")
            return {
                "query": clean_query,
                "retrieved_at": retrieved_at,
                "results": [],
                "status": "failed",
                "error": "Could not retrieve live web search results from external providers at this time."
            }

        return {
            "query": clean_query,
            "retrieved_at": retrieved_at,
            "results": results_list,
            "status": "success"
        }
