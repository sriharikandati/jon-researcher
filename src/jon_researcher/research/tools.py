"""LangChain tool definitions and execution for Jon's free research tools."""

from __future__ import annotations

from typing import Any, Callable

from langchain.tools import tool

from .providers import build_research_provider

RESEARCH_TOOL_NAMES = ("research_search", "research_fetch")


def build_research_tools(
    *,
    timeout: float,
    provider_name: str = "duckduckgo",
    api_keys: dict[str, str] | None = None,
    allowed_tools: set[str] | None = None,
) -> list[Any]:
    """Build LangChain research tools enabled by configuration."""
    selected = set(RESEARCH_TOOL_NAMES if allowed_tools is None else allowed_tools)
    tools: list[Any] = []

    if "research_search" in selected:

        @tool
        def research_search(query: str, max_results: int = 5) -> str:
            """Search the public web for current information."""
            return _research_search(
                {"query": query, "max_results": max_results},
                timeout,
                provider_name=provider_name,
                api_keys=api_keys or {},
            )

        tools.append(research_search)

    if "research_fetch" in selected:

        @tool
        def research_fetch(url: str, max_chars: int = 6000) -> str:
            """Fetch readable text from a public URL for research."""
            return _research_fetch(
                {"url": url, "max_chars": max_chars},
                timeout,
                provider_name=provider_name,
                api_keys=api_keys or {},
            )

        tools.append(research_fetch)

    return tools


def run_research_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    timeout: float,
    provider_name: str = "duckduckgo",
    api_keys: dict[str, str] | None = None,
    allowed_tools: set[str] | None = None,
) -> str:
    if allowed_tools is not None and name not in allowed_tools:
        return f"Research tool is disabled: {name}"
    tools: dict[str, Callable[[dict[str, Any], float], str]] = {
        "research_search": _research_search,
        "research_fetch": _research_fetch,
    }
    selected_tool = tools.get(name)
    if selected_tool is None:
        return f"Unknown research tool: {name}"
    try:
        return selected_tool(
            arguments,
            timeout,
            provider_name=provider_name,
            api_keys=api_keys or {},
        )
    except Exception as exc:  # noqa: BLE001
        return f"Research tool failed: {exc}"


def _research_search(
    arguments: dict[str, Any],
    timeout: float,
    *,
    provider_name: str = "duckduckgo",
    api_keys: dict[str, str] | None = None,
) -> str:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return "Research search failed: query is required."
    max_results = _bounded_int(
        arguments.get("max_results"),
        default=5,
        minimum=1,
        maximum=10,
    )
    provider = build_research_provider(
        provider_name,
        api_keys=api_keys or {},
        timeout=min(timeout, 20.0),
    )
    results = provider.search(query, max_results=max_results)
    if not results:
        return "No research results found."

    lines = ["Research results:"]
    for index, result in enumerate(results, start=1):
        lines.append(f"{index}. {result.title}")
        lines.append(f"   URL: {result.url}")
        if result.snippet:
            lines.append(f"   Snippet: {result.snippet}")
        if result.source:
            lines.append(f"   Source: {result.source}")
    return "\n".join(lines)


def _research_fetch(
    arguments: dict[str, Any],
    timeout: float,
    *,
    provider_name: str = "duckduckgo",
    api_keys: dict[str, str] | None = None,
) -> str:
    url = str(arguments.get("url") or "").strip()
    if not url:
        return "Research fetch failed: url is required."
    max_chars = _bounded_int(
        arguments.get("max_chars"),
        default=6000,
        minimum=500,
        maximum=20000,
    )
    provider = build_research_provider(
        provider_name,
        api_keys=api_keys or {},
        timeout=min(timeout, 20.0),
    )
    page = provider.fetch(url, max_chars=max_chars)
    lines = ["Fetched research page:"]
    if page.title:
        lines.append(f"Title: {page.title}")
    lines.append(f"URL: {page.url}")
    lines.append("")
    lines.append(page.text.strip() or "No readable text found.")
    return "\n".join(lines)


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))
