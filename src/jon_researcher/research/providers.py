"""Research provider registry for Jon."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

from .duckduckgo import DuckDuckGoResearchProvider
from .models import ResearchFetchedPage, ResearchSearchResult


@dataclass(frozen=True, slots=True)
class ResearchProviderSpec:
    name: str
    label: str
    api_key_name: str | None = None
    description: str = ""


RESEARCH_PROVIDER_SPECS: tuple[ResearchProviderSpec, ...] = (
    ResearchProviderSpec(
        name="duckduckgo",
        label="DuckDuckGo",
        description="Free DuckDuckGo HTML search. No API key required.",
    ),
    ResearchProviderSpec(
        name="brave",
        label="Brave Search",
        api_key_name="BRAVE_SEARCH_API_KEY",
        description="Privacy-oriented web search API.",
    ),
    ResearchProviderSpec(
        name="tavily",
        label="Tavily",
        api_key_name="TAVILY_API_KEY",
        description="Search API optimized for LLM research workflows.",
    ),
    ResearchProviderSpec(
        name="serpapi",
        label="SerpAPI",
        api_key_name="SERPAPI_API_KEY",
        description="Google SERP-backed search API.",
    ),
    ResearchProviderSpec(
        name="exa",
        label="Exa",
        api_key_name="EXA_API_KEY",
        description="Neural/web search API for semantic discovery.",
    ),
    ResearchProviderSpec(
        name="bing",
        label="Bing Web Search",
        api_key_name="BING_SEARCH_API_KEY",
        description="Microsoft Bing Web Search API.",
    ),
)


def provider_specs() -> tuple[ResearchProviderSpec, ...]:
    return RESEARCH_PROVIDER_SPECS


def provider_spec(name: str) -> ResearchProviderSpec | None:
    normalized = str(name or "").strip().lower()
    for spec in RESEARCH_PROVIDER_SPECS:
        if spec.name == normalized:
            return spec
    return None


def provider_label(name: str) -> str:
    spec = provider_spec(name)
    return spec.label if spec else str(name or "Unknown")


class ApiResearchProvider:
    requires_api_key = True

    def __init__(self, name: str, api_key: str, *, timeout: float = 10.0) -> None:
        self.name = name
        self.api_key = api_key
        self.timeout = timeout
        self._fetcher = DuckDuckGoResearchProvider(timeout=timeout)

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> list[ResearchSearchResult]:
        method = getattr(self, f"_search_{self.name}", None)
        if method is None:
            raise ValueError(f"Unsupported research provider: {self.name}")
        return method(query, max_results=max_results)

    def fetch(
        self,
        url: str,
        *,
        max_chars: int = 6000,
    ) -> ResearchFetchedPage:
        return self._fetcher.fetch(url, max_chars=max_chars)

    def _search_brave(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[ResearchSearchResult]:
        data = _get_json(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": max_results},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key,
            },
            timeout=self.timeout,
        )
        return _results_from_items(
            data.get("web", {}).get("results", []),
            title_key="title",
            url_key="url",
            snippet_key="description",
            source=self.name,
            max_results=max_results,
        )

    def _search_tavily(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[ResearchSearchResult]:
        data = _post_json(
            "https://api.tavily.com/search",
            payload={
                "api_key": self.api_key,
                "query": query,
                "max_results": max_results,
                "include_answer": False,
            },
            timeout=self.timeout,
        )
        return _results_from_items(
            data.get("results", []),
            title_key="title",
            url_key="url",
            snippet_key="content",
            source=self.name,
            max_results=max_results,
        )

    def _search_serpapi(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[ResearchSearchResult]:
        data = _get_json(
            "https://serpapi.com/search.json",
            params={"engine": "google", "q": query, "api_key": self.api_key},
            timeout=self.timeout,
        )
        return _results_from_items(
            data.get("organic_results", []),
            title_key="title",
            url_key="link",
            snippet_key="snippet",
            source=self.name,
            max_results=max_results,
        )

    def _search_exa(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[ResearchSearchResult]:
        data = _post_json(
            "https://api.exa.ai/search",
            payload={"query": query, "numResults": max_results},
            headers={"x-api-key": self.api_key},
            timeout=self.timeout,
        )
        return _results_from_items(
            data.get("results", []),
            title_key="title",
            url_key="url",
            snippet_key="text",
            source=self.name,
            max_results=max_results,
        )

    def _search_bing(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[ResearchSearchResult]:
        data = _get_json(
            "https://api.bing.microsoft.com/v7.0/search",
            params={"q": query, "count": max_results},
            headers={"Ocp-Apim-Subscription-Key": self.api_key},
            timeout=self.timeout,
        )
        return _results_from_items(
            data.get("webPages", {}).get("value", []),
            title_key="name",
            url_key="url",
            snippet_key="snippet",
            source=self.name,
            max_results=max_results,
        )


def build_research_provider(
    provider_name: str,
    *,
    api_keys: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> DuckDuckGoResearchProvider | ApiResearchProvider:
    normalized = str(provider_name or "duckduckgo").strip().lower() or "duckduckgo"
    if normalized == "duckduckgo" or provider_spec(normalized) is None:
        return DuckDuckGoResearchProvider(timeout=timeout)

    api_key = _api_key_for(normalized, api_keys or {})
    if not api_key:
        raise ValueError(
            f"{provider_label(normalized)} requires an API key. Run /researcher to configure it."
        )
    return ApiResearchProvider(normalized, api_key, timeout=timeout)


def _api_key_for(provider_name: str, api_keys: dict[str, str]) -> str:
    configured = str(api_keys.get(provider_name) or "").strip()
    if configured:
        return configured
    spec = provider_spec(provider_name)
    if spec and spec.api_key_name:
        return os.environ.get(spec.api_key_name, "").strip()
    return ""


def _get_json(
    url: str,
    *,
    params: dict[str, Any],
    timeout: float,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    query = parse.urlencode(params)
    return _request_json(
        f"{url}?{query}",
        method="GET",
        timeout=timeout,
        headers=headers,
    )


def _post_json(
    url: str,
    *,
    payload: dict[str, Any],
    timeout: float,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    merged_headers = {"Content-Type": "application/json", **(headers or {})}
    return _request_json(
        url,
        method="POST",
        timeout=timeout,
        headers=merged_headers,
        data=body,
    )


def _request_json(
    url: str,
    *,
    method: str,
    timeout: float,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
) -> dict[str, Any]:
    req = request.Request(
        url,
        data=data,
        headers=headers or {},
        method=method,
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Provider returned HTTP {exc.code}: {details}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Provider request failed: {exc.reason}") from exc
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise RuntimeError("Provider returned unexpected JSON.")
    return decoded


def _results_from_items(
    items: Any,
    *,
    title_key: str,
    url_key: str,
    snippet_key: str,
    source: str,
    max_results: int,
) -> list[ResearchSearchResult]:
    if not isinstance(items, list):
        return []
    results: list[ResearchSearchResult] = []
    for item in items[: max(1, min(int(max_results or 5), 10))]:
        if not isinstance(item, dict):
            continue
        title = str(item.get(title_key) or "").strip()
        url = str(item.get(url_key) or "").strip()
        if not title or not url:
            continue
        results.append(
            ResearchSearchResult(
                title=title,
                url=url,
                snippet=str(item.get(snippet_key) or "").strip(),
                source=source,
            )
        )
    return results
