from jon_researcher.research.duckduckgo import _DuckDuckGoHTMLParser, _TextExtractor
from jon_researcher.research.tools import (
    RESEARCH_TOOL_NAMES,
    build_research_tools,
    run_research_tool,
)


def test_research_tool_definitions_are_langchain_tools() -> None:
    tools = build_research_tools(timeout=1.0)
    names = [tool.name for tool in tools]

    assert tuple(names) == RESEARCH_TOOL_NAMES


def test_duckduckgo_parser_extracts_result() -> None:
    parser = _DuckDuckGoHTMLParser()
    parser.feed(
        """
        <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fpage">Example title</a>
        <a class="result__snippet">Example snippet</a>
        """
    )
    parser.close()

    assert len(parser.results) == 1
    assert parser.results[0].title == "Example title"
    assert parser.results[0].url == "https://example.com/page"
    assert parser.results[0].snippet == "Example snippet"


def test_text_extractor_ignores_scripts_and_keeps_title() -> None:
    parser = _TextExtractor()
    parser.feed(
        """
        <html><head><title>Page title</title><script>bad()</script></head>
        <body><p>Hello</p><style>.x{}</style><p>World</p></body></html>
        """
    )

    assert parser.title == "Page title"
    assert parser.text == "Hello\nWorld"


def test_unknown_tool_returns_error() -> None:
    assert run_research_tool("missing", {}, timeout=1.0) == "Unknown research tool: missing"
