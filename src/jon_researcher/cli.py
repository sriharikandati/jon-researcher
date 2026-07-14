"""Command-line entry point for Jon the Researcher."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .interactive import run_interactive
from .ollama_agent import AgentError, JonResearcher
from .ui import MarkdownAnswer, error as print_error, tool_result, tool_start


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name or "jon-researcher",
        description="Ask Jon the Researcher a question using local Ollama and free web research tools.",
    )
    parser.add_argument(
        "question",
        nargs="*",
        help="Question to research and answer. Omit to open the you > prompt.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Ollama model to use. Defaults to saved config or JON_MODEL.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Ollama base URL. Defaults to saved config or JON_OLLAMA_BASE_URL.",
    )
    parser.add_argument(
        "--max-tool-rounds",
        type=int,
        default=None,
        help="Maximum model/tool iterations before asking for a final answer.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="HTTP timeout in seconds for Ollama and research requests.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Open the you > prompt even when a question is provided.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.interactive or not args.question:
        return run_interactive()

    config = load_config()
    question = " ".join(args.question).strip()
    if not question:
        parser.error("question is required")

    agent = JonResearcher(
        model=args.model or config.model,
        base_url=args.base_url or config.base_url,
        timeout=args.timeout if args.timeout is not None else config.timeout,
        max_tool_rounds=max(
            0,
            args.max_tool_rounds
            if args.max_tool_rounds is not None
            else config.max_tool_rounds,
        ),
        research_search_enabled=config.research_search_enabled,
        research_fetch_enabled=config.research_fetch_enabled,
        research_provider=config.research_provider,
        research_api_keys=config.research_api_keys or {},
    )
    renderer: MarkdownAnswer | None = None
    tools_used: list[str] = []
    wrote_token = False
    try:
        for event in agent.stream_answer(question):
            if event.kind == "tool_start":
                if renderer is not None and wrote_token:
                    renderer.end()
                    renderer = None
                    wrote_token = False
                if event.name and event.name not in tools_used:
                    tools_used.append(event.name)
                tool_start(event.name, event.arguments)
                continue
            if event.kind == "tool_result":
                if renderer is not None and wrote_token:
                    renderer.end()
                    renderer = None
                    wrote_token = False
                tool_result(event.name, event.text)
                continue
            if event.kind == "token":
                token = event.text if wrote_token else event.text.lstrip()
                if not token:
                    continue
                if renderer is None:
                    renderer = MarkdownAnswer(include_prefix=False)
                    renderer.start()
                renderer.token(token)
                wrote_token = True
    except AgentError as exc:
        if renderer is not None and wrote_token:
            renderer.end()
        print_error(str(exc))
        return 1
    if renderer is not None:
        if tools_used:
            renderer.token(_tools_used_footer(tools_used))
        renderer.end()
    return 0


def _tools_used_footer(tools_used: list[str]) -> str:
    labels = ", ".join(f"`{name}`" for name in tools_used)
    return f"\n\n---\nTools used: {labels}"


if __name__ == "__main__":
    raise SystemExit(main())
