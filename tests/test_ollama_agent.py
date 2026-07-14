from urllib import error

import pytest

from jon_researcher.config import JonConfig
from jon_researcher.ollama_agent import AgentError, JonResearcher, _latest_message_text


def test_validate_model_requires_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = JonResearcher(model="plain", base_url="http://localhost:11434")
    monkeypatch.setattr(
        JonResearcher,
        "_post_json",
        lambda self, path, payload: {"capabilities": ["completion"]},
    )

    with pytest.raises(AgentError, match="missing required capabilities: tools"):
        agent._validate_model()


def test_from_config_carries_research_tool_settings() -> None:
    config = JonConfig(
        research_search_enabled=False,
        research_fetch_enabled=True,
    )

    agent = JonResearcher.from_config(config)

    assert agent._allowed_tool_names() == {"research_fetch"}
    assert [tool.name for tool in agent._enabled_tools()] == ["research_fetch"]


def test_stream_config_adds_thread_id() -> None:
    agent = JonResearcher(model="m", base_url="http://localhost:11434")

    assert agent._stream_config(thread_id="thread-1") == {
        "recursion_limit": agent._recursion_limit(),
        "configurable": {"thread_id": "thread-1"},
    }


def test_latest_message_text_extracts_langchain_content() -> None:
    class Message:
        content = "answer"

    assert _latest_message_text({"messages": [Message()]}) == "answer"


def test_stream_answer_emits_tool_logs_and_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TokenMessage:
        content = "answer"
        tool_calls = []

    class ToolCallMessage:
        content = ""
        tool_calls = [
            {
                "id": "call-1",
                "name": "research_search",
                "args": {"query": "python"},
            }
        ]

    class ToolMessage:
        content = "Research results"
        name = "research_search"

    class FakeGraph:
        def stream(self, *args, **kwargs):
            yield ToolCallMessage(), {}
            yield ToolMessage(), {}
            yield TokenMessage(), {}

    agent = JonResearcher(model="m", base_url="http://localhost:11434")
    monkeypatch.setattr(JonResearcher, "_validate_model", lambda self: None)
    monkeypatch.setattr(JonResearcher, "_build_agent", lambda self: FakeGraph())

    events = list(agent.stream_answer("question"))

    assert [event.kind for event in events] == ["tool_start", "tool_result", "token"]
    assert events[0].name == "research_search"
    assert events[0].arguments == {"query": "python"}
    assert events[1].text == "Research results"
    assert events[2].text == "answer"


def test_search_prompt_prefetches_research_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TokenMessage:
        content = "answer"
        tool_calls = []

    class FakeGraph:
        def stream(self, payload, *args, **kwargs):
            content = payload["messages"][0]["content"]
            assert "Live research_search result:" in content
            assert "Research results" in content
            yield TokenMessage(), {}

    def fake_run_tool(name, arguments, **kwargs):
        assert name == "research_search"
        assert arguments == {
            "query": "search online and give me latest ai trends",
            "max_results": 5,
        }
        return "Research results"

    agent = JonResearcher(model="m", base_url="http://localhost:11434")
    monkeypatch.setattr(JonResearcher, "_validate_model", lambda self: None)
    monkeypatch.setattr(JonResearcher, "_build_agent", lambda self: FakeGraph())
    monkeypatch.setattr("jon_researcher.ollama_agent.run_research_tool", fake_run_tool)

    events = list(agent.stream_answer("search online and give me latest ai trends"))

    assert [event.kind for event in events] == ["tool_start", "tool_result", "token"]
    assert events[0].name == "research_search"
    assert events[0].arguments == {
        "query": "search online and give me latest ai trends",
        "max_results": 5,
    }
    assert events[1].name == "research_search"
    assert events[1].text == "Research results"


def test_url_error_mentions_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args, **kwargs):
        raise error.URLError("refused")

    monkeypatch.setattr("jon_researcher.ollama_agent.request.urlopen", fail)
    agent = JonResearcher(model="m", base_url="http://localhost:11434")

    with pytest.raises(AgentError, match="Could not reach Ollama"):
        agent._post_json("/api/show", {"model": "m"})
