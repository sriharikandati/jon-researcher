"""Interactive shell for Jon."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from .config import JonConfig, config_exists, config_path, load_config, save_config
from .ollama_discovery import inspect_model, list_tool_capable_models
from .ollama_agent import AgentError, JonResearcher
from .research.providers import provider_label, provider_specs, provider_spec
from .ui import (
    MarkdownAnswer,
    SelectOption,
    WorkingIndicator,
    confirm_prompt,
    error,
    help_panel,
    jon,
    line,
    prompt_line,
    secret_prompt,
    select_prompt,
    status_panel,
    success,
    text_prompt,
    tool_result,
    tool_start,
    warning,
)


def run_interactive() -> int:
    config = load_config()
    if not config_exists():
        jon("First-time setup: choose a local Ollama model with tool support.")
        config = _configure_model(config, first_run=True)
    _print_status_dialog(config)
    jon("Type /help for commands.")
    line()
    _research_loop(config)
    return 0


def _research_loop(config: JonConfig) -> None:
    checkpointer = InMemorySaver()
    thread_id = f"jon-{uuid4()}"
    agent = JonResearcher.from_config(config, checkpointer=checkpointer)
    while True:
        try:
            question = prompt_line().strip()
        except (EOFError, KeyboardInterrupt):
            line()
            return
        if not question:
            continue
        if question.startswith("/"):
            config = _handle_command(question, config)
            agent = JonResearcher.from_config(config, checkpointer=checkpointer)
            if question.strip().lower() == "/exit":
                return
            continue

        _stream_agent_answer(agent, question, thread_id=thread_id)


def _handle_command(raw_command: str, config: JonConfig) -> JonConfig:
    command = raw_command.strip().lower()
    if command == "/help":
        _print_help(config)
        return config
    if command == "/status":
        _print_status_dialog(config)
        return config
    if command == "/configure":
        return _configure_model(config)
    if command == "/researcher":
        return _configure_researcher(config)
    if command == "/exit":
        jon("bye")
        return config
    warning("Unknown command. Try /help.")
    return config


def _stream_agent_answer(agent: JonResearcher, question: str, *, thread_id: str) -> None:
    renderer: MarkdownAnswer | None = None
    working = WorkingIndicator()
    working.start()
    tools_used: list[str] = []
    wrote_token = False
    try:
        for event in agent.stream_answer(question, thread_id=thread_id):
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
                    working.stop()
                    renderer = MarkdownAnswer(include_prefix=True)
                    renderer.start()
                renderer.token(token)
                wrote_token = True
    except AgentError as exc:
        working.stop()
        if renderer is not None and wrote_token:
            renderer.end()
        error(str(exc))
        return
    working.stop()
    if renderer is not None:
        if tools_used:
            renderer.token(_tools_used_footer(tools_used))
        renderer.end()


def _tools_used_footer(tools_used: list[str]) -> str:
    labels = ", ".join(f"`{name}`" for name in tools_used)
    return f"\n\n---\nTools used: {labels}"


def _configure_model(config: JonConfig, *, first_run: bool = False) -> JonConfig:
    jon("Configure model")
    base_url = _prompt_text("Ollama URL", default=config.base_url)
    timeout = _prompt_float("Timeout seconds", default=config.timeout)
    model = _prompt_model(
        current_model=config.model,
        base_url=base_url,
        timeout=timeout,
        required=first_run,
    )
    config = replace(
        config,
        model=model,
        base_url=base_url,
        timeout=timeout,
        max_tool_rounds=max(
            0,
            _prompt_int("Max research tool rounds", default=config.max_tool_rounds),
        ),
    )
    save_config(config)
    success(f"Saved model configuration to {config_path()}")
    return config


def _prompt_model(
    *,
    current_model: str,
    base_url: str,
    timeout: float,
    required: bool,
) -> str:
    models, error_text = list_tool_capable_models(base_url, timeout=min(timeout, 20.0))
    if models:
        options = [
            SelectOption(
                value=model,
                label=model,
                description="current" if model == current_model else "",
            )
            for model in models
        ]
        default = current_model if current_model in models else models[0]
        return str(
            select_prompt(
                "Model with tool support",
                options,
                default=default if (not required or default) else None,
            )
        )

    warning("No installed Ollama models with both completion and tools were found.")
    if error_text:
        warning(f"Ollama discovery note: {error_text}")
    while True:
        raw = text_prompt("Model", default=current_model).strip() or current_model
        status = inspect_model(raw, base_url=base_url, timeout=min(timeout, 20.0))
        if status.tool_capable:
            return raw
        warning(
            "Model is not tool-capable or unavailable. "
            "Pull a model with tools support in Ollama, then try again."
        )
        if not required:
            return current_model


def _configure_researcher(config: JonConfig) -> JonConfig:
    jon("Configure researcher")
    selected_spec = _prompt_provider(default=config.research_provider)
    api_keys = dict(config.research_api_keys or {})
    if selected_spec.api_key_name:
        current_key = api_keys.get(selected_spec.name, "")
        entered = _prompt_secret(
            f"{selected_spec.label} API key",
            configured=bool(current_key),
        )
        if entered:
            api_keys[selected_spec.name] = entered
    config = replace(
        config,
        research_provider=selected_spec.name,
        research_api_keys=api_keys,
        research_search_enabled=_prompt_bool(
            "Enable research_search",
            default=config.research_search_enabled,
        ),
        research_fetch_enabled=_prompt_bool(
            "Enable research_fetch",
            default=config.research_fetch_enabled,
        ),
    )
    save_config(config)
    success(f"Research provider set to {selected_spec.label}")
    success(f"Saved researcher configuration to {config_path()}")
    return config


def _prompt_provider(*, default: str):
    specs = list(provider_specs())
    options = [
        SelectOption(
            value=spec.name,
            label=spec.label,
            description=spec.api_key_name or "free",
        )
        for spec in specs
    ]
    selected_name = str(select_prompt("Research provider", options, default=default))
    selected = provider_spec(selected_name)
    if selected is None:
        return provider_spec(default) or specs[0]
    return selected


def _prompt_text(label: str, *, default: str) -> str:
    return text_prompt(label, default=default).strip() or default


def _prompt_secret(label: str, *, configured: bool) -> str:
    return secret_prompt(label, configured=configured).strip()


def _prompt_bool(label: str, *, default: bool) -> bool:
    return confirm_prompt(label, default=default)


def _prompt_int(label: str, *, default: int) -> int:
    return _prompt_value(label, default=default, parser=int)


def _prompt_float(label: str, *, default: float) -> float:
    return _prompt_value(label, default=default, parser=float)


def _prompt_value(label: str, *, default, parser: Callable[[str], object]):
    while True:
        raw = text_prompt(label, default=str(default)).strip()
        if not raw:
            return default
        try:
            return parser(raw)
        except ValueError:
            warning("Enter a valid value.")


def _print_help(config: JonConfig) -> None:
    help_panel(
        provider=provider_label(config.research_provider),
        search_enabled=config.research_search_enabled,
        fetch_enabled=config.research_fetch_enabled,
    )


def _print_status_dialog(config: JonConfig) -> None:
    status = inspect_model(
        config.model,
        base_url=config.base_url,
        timeout=min(config.timeout, 20.0),
    )
    if status.tool_capable:
        model_state = "ready"
    elif status.available:
        model_state = "missing tool support"
    else:
        model_state = f"unavailable: {status.error}"
    status_panel(
        config_path=str(config_path()),
        base_url=config.base_url,
        model=config.model,
        model_state=model_state,
        capabilities=status.capabilities,
        provider=provider_label(config.research_provider),
        search_enabled=config.research_search_enabled,
        fetch_enabled=config.research_fetch_enabled,
    )
