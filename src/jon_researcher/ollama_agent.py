"""LangChain agent wrapper for Jon."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterator, Literal
from urllib import error, request

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from langchain_ollama import ChatOllama

from .config import JonConfig
from .research.tools import build_research_tools, run_research_tool


class AgentError(RuntimeError):
    """Raised when Jon cannot complete a request."""


@dataclass(frozen=True, slots=True)
class AgentStreamEvent:
    kind: Literal["token", "tool_start", "tool_result"]
    text: str = ""
    name: str = ""
    arguments: dict[str, Any] | None = None


SYSTEM_PROMPT = """You are Jon the Researcher, a concise AI research agent.
Use research_search for current or factual web research.
For requests that mention search, online, web, latest, current, recent, news, or trends, use live research context before answering.
Use research_fetch when a search result needs more detail.
Prefer free public sources. Cite URLs inline when web research informs the answer.
If tool results are weak, say what could not be verified.
Return only the answer to the user's question."""


@dataclass(slots=True)
class JonResearcher:
    model: str
    base_url: str
    timeout: float = 60.0
    max_tool_rounds: int = 5
    research_search_enabled: bool = True
    research_fetch_enabled: bool = True
    research_provider: str = "duckduckgo"
    research_api_keys: dict[str, str] | None = None
    checkpointer: Any | None = None

    @classmethod
    def from_config(
        cls,
        config: JonConfig,
        *,
        checkpointer: Any | None = None,
    ) -> "JonResearcher":
        return cls(
            model=config.model,
            base_url=config.base_url,
            timeout=config.timeout,
            max_tool_rounds=config.max_tool_rounds,
            research_search_enabled=config.research_search_enabled,
            research_fetch_enabled=config.research_fetch_enabled,
            research_provider=config.research_provider,
            research_api_keys=config.research_api_keys or {},
            checkpointer=checkpointer,
        )

    @classmethod
    def with_memory(cls, config: JonConfig) -> "JonResearcher":
        return cls.from_config(config, checkpointer=InMemorySaver())

    def answer(self, question: str, *, thread_id: str | None = None) -> str:
        chunks: list[str] = []
        for event in self.stream_answer(question, thread_id=thread_id):
            if event.kind == "token":
                chunks.append(event.text)
        answer = "".join(chunks).strip()
        if answer:
            return answer
        raise AgentError("LangChain agent returned an empty answer.")

    def stream_answer(
        self,
        question: str,
        *,
        thread_id: str | None = None,
    ) -> Iterator[AgentStreamEvent]:
        self._validate_model()
        agent = self._build_agent()
        agent_question = question
        seen_tool_calls: set[str] = set()
        try:
            if self._should_prefetch_research(question):
                arguments = {"query": question, "max_results": 5}
                yield AgentStreamEvent(
                    kind="tool_start",
                    name="research_search",
                    arguments=arguments,
                )
                research_result = run_research_tool(
                    "research_search",
                    arguments,
                    timeout=self.timeout,
                    provider_name=self.research_provider,
                    api_keys=self.research_api_keys or {},
                    allowed_tools=self._allowed_tool_names(),
                )
                yield AgentStreamEvent(
                    kind="tool_result",
                    name="research_search",
                    text=research_result,
                )
                agent_question = _question_with_research_context(
                    question,
                    research_result,
                )

            stream = agent.stream(
                {"messages": [{"role": "user", "content": agent_question}]},
                config=self._stream_config(thread_id=thread_id),
                stream_mode="messages",
            )
            for message, _metadata in stream:
                tool_calls = getattr(message, "tool_calls", None) or []
                for tool_call in tool_calls:
                    call_id = str(tool_call.get("id") or "")
                    name = str(tool_call.get("name") or "").strip()
                    if not name or call_id in seen_tool_calls:
                        continue
                    if call_id:
                        seen_tool_calls.add(call_id)
                    args = tool_call.get("args")
                    yield AgentStreamEvent(
                        kind="tool_start",
                        name=name,
                        arguments=args if isinstance(args, dict) else {},
                    )

                if type(message).__name__ == "ToolMessage":
                    yield AgentStreamEvent(
                        kind="tool_result",
                        name=str(getattr(message, "name", "") or "tool"),
                        text=_message_content_text(getattr(message, "content", "")),
                    )
                    continue

                content = _message_content_text(getattr(message, "content", ""))
                if content:
                    yield AgentStreamEvent(kind="token", text=content)
        except Exception as exc:  # noqa: BLE001
            raise AgentError(f"LangChain agent failed: {exc}") from exc

    def _build_agent(self):
        return create_agent(
            model=ChatOllama(
                model=self.model,
                base_url=self.base_url,
                temperature=0,
            ),
            tools=self._enabled_tools(),
            system_prompt=SYSTEM_PROMPT,
            name="jon_researcher",
            checkpointer=self.checkpointer,
        )

    def _stream_config(self, *, thread_id: str | None = None) -> dict[str, Any]:
        config: dict[str, Any] = {"recursion_limit": self._recursion_limit()}
        if thread_id:
            config["configurable"] = {"thread_id": thread_id}
        return config

    def _validate_model(self) -> None:
        payload = self._post_json("/api/show", {"model": self.model})
        capabilities = {
            str(item).strip().lower()
            for item in payload.get("capabilities", [])
            if str(item).strip()
        }
        missing = {"completion", "tools"} - capabilities
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise AgentError(
                f"Ollama model '{self.model}' is missing required capabilities: {missing_text}. "
                "Use a model whose capabilities include both completion and tools."
            )

    def _enabled_tools(self) -> list[Any]:
        return build_research_tools(
            timeout=self.timeout,
            provider_name=self.research_provider,
            api_keys=self.research_api_keys or {},
            allowed_tools=self._allowed_tool_names(),
        )

    def _allowed_tool_names(self) -> set[str]:
        names: set[str] = set()
        if self.research_search_enabled:
            names.add("research_search")
        if self.research_fetch_enabled:
            names.add("research_fetch")
        return names

    def _recursion_limit(self) -> int:
        return max(3, (self.max_tool_rounds * 2) + 3)

    def _should_prefetch_research(self, question: str) -> bool:
        if not self.research_search_enabled:
            return False
        normalized = f" {question.lower()} "
        triggers = (
            " search ",
            " online ",
            " web ",
            " latest ",
            " current ",
            " recent ",
            " news ",
            " trend ",
            " trends ",
            " today ",
        )
        return any(trigger in normalized for trigger in triggers)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise AgentError(f"Ollama returned HTTP {exc.code} for {path}: {details}") from exc
        except error.URLError as exc:
            raise AgentError(
                f"Could not reach Ollama at {self.base_url}. Start Ollama or pass --base-url."
            ) from exc
        except TimeoutError as exc:
            raise AgentError(f"Ollama request timed out after {self.timeout:g}s.") from exc

        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AgentError(f"Ollama returned invalid JSON for {path}.") from exc
        if not isinstance(decoded, dict):
            raise AgentError(f"Ollama returned an unexpected response for {path}.")
        return decoded


def _latest_message_text(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    messages = result.get("messages")
    if not isinstance(messages, list) or not messages:
        return ""
    return _message_content_text(getattr(messages[-1], "content", ""))


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if isinstance(value, str):
                    parts.append(value)
        return "\n".join(part for part in parts if part)
    return str(content or "")


def _question_with_research_context(question: str, research_result: str) -> str:
    return (
        "Answer the user's question using the live research context below. "
        "If the context is weak, say what could not be verified.\n\n"
        f"User question:\n{question}\n\n"
        f"Live research_search result:\n{research_result}"
    )
