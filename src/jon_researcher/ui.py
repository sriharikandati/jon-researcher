"""Terminal UI helpers for Jon."""

from __future__ import annotations

import getpass
import json
import sys
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

try:  # pragma: no cover - exercised through interactive use.
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice
except Exception:  # pragma: no cover - dependency or terminal import fallback.
    Choice = None  # type: ignore[assignment]
    inquirer = None  # type: ignore[assignment]

try:  # pragma: no cover - exercised through interactive use.
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.styles import Style
except Exception:  # pragma: no cover - dependency or terminal import fallback.
    HTML = None  # type: ignore[assignment]
    PromptSession = None  # type: ignore[assignment]
    Style = None  # type: ignore[assignment]


console = Console(
    theme=Theme(
        {
            "jon.brand": "bold green",
            "jon.accent": "cyan",
            "jon.success": "bold green",
            "jon.warn": "bold yellow",
            "jon.error": "bold red",
            "jon.dim": "dim",
            "jon.prompt": "bold cyan",
            "jon.answer": "default",
            "jon.answer_prefix": "bold",
            "jon.tool": "dim cyan",
            "jon.path": "cyan",
        }
    ),
    highlight=False,
)

_PROMPT_STYLE = (
    Style.from_dict(
        {
            "you": "bold #00afff",
            "arrow": "bold #ff5fd7",
        }
    )
    if Style is not None
    else None
)


@dataclass(frozen=True, slots=True)
class SelectOption:
    value: Any
    label: str
    description: str = ""


class MarkdownAnswer:
    """Stream an answer as Markdown when the terminal can render it."""

    def __init__(self, *, include_prefix: bool) -> None:
        self.include_prefix = include_prefix
        self._buffer = ""
        self._live: Live | None = None
        self._plain = not interactive_terminal()

    def start(self) -> None:
        if self._plain:
            if self.include_prefix:
                answer_start()
            return
        self._live = Live(
            _answer_box(""),
            console=console,
            refresh_per_second=12,
            transient=False,
        )
        self._live.start()

    def token(self, text: str) -> None:
        self._buffer += text
        if self._plain:
            answer_token(text)
            return
        if self._live is not None:
            self._live.update(_answer_box(self._buffer))

    def end(self) -> None:
        if self._plain:
            answer_end()
            return
        if self._live is not None:
            self._live.update(_answer_box(self._buffer))
            self._live.stop()
            self._live = None


class WorkingIndicator:
    """Show a small live working indicator until response rendering starts."""

    def __init__(self) -> None:
        self._live: Live | None = None
        self._plain = not interactive_terminal()
        self._printed_plain = False

    def start(self) -> None:
        if self._plain:
            jon("working...")
            self._printed_plain = True
            return
        self._live = Live(
            Text("jon > working...", style="jon.answer_prefix"),
            console=console,
            refresh_per_second=8,
            transient=True,
        )
        self._live.start()

    def stop(self) -> None:
        if self._plain:
            return
        if self._live is not None:
            self._live.stop()
            self._live = None


def interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def line(message: str = "", *, style: str | None = None) -> None:
    console.print(message, style=style)


def jon(message: str, *, style: str | None = None) -> None:
    console.print(
        Text("jon > ", style="jon.answer_prefix") + Text(message, style=style or "")
    )


def success(message: str) -> None:
    jon(message, style="jon.success")


def warning(message: str) -> None:
    jon(message, style="jon.warn")


def error(message: str) -> None:
    jon(message, style="jon.error")


def tool_start(name: str, arguments: dict[str, Any] | None = None) -> None:
    console.print(f"tool > using {name}", style="jon.tool")
    if not interactive_terminal():
        if arguments:
            console.print(f"tool > args {_compact_json(arguments)}", style="jon.tool")
        return

    table = Table.grid(padding=(0, 2))
    table.add_column(style="jon.dim", no_wrap=True)
    table.add_column()
    table.add_row("Tool", f"[jon.accent]{name}[/]")
    if arguments:
        table.add_row("Args", _compact_json(arguments))
    else:
        table.add_row("Args", "none")
    console.print(
        Panel(
            table,
            title="[jon.tool]Tool call[/]",
            border_style="cyan",
            padding=(0, 1),
        )
    )


def tool_result(name: str, text: str) -> None:
    detail = _result_summary(text)
    if not interactive_terminal():
        console.print(f"tool > {name} completed{detail}", style="jon.tool")
        return

    table = Table.grid(padding=(0, 2))
    table.add_column(style="jon.dim", no_wrap=True)
    table.add_column()
    table.add_row("Tool", f"[jon.accent]{name}[/]")
    table.add_row("Status", "[jon.success]completed[/]")
    if detail:
        table.add_row("Result", detail.removeprefix(" - "))
    console.print(
        Panel(
            table,
            title="[jon.tool]Tool result[/]",
            border_style="cyan",
            padding=(0, 1),
        )
    )


def answer_start() -> None:
    console.print(Text("jon > ", style="jon.answer_prefix"), end="")


def answer_token(text: str) -> None:
    console.print(Text(text, style="jon.answer"), end="")
    console.file.flush()


def answer_end() -> None:
    console.print()


def prompt_line() -> str:
    if interactive_terminal() and PromptSession is not None and HTML is not None:
        session = PromptSession(style=_PROMPT_STYLE)
        return session.prompt(HTML("<you>you</you> <arrow>&gt;</arrow> "))
    return input("you > ")


def text_prompt(message: str, *, default: str = "") -> str:
    if interactive_terminal() and inquirer is not None:
        return inquirer.text(
            message=message,
            default=default,
            qmark=">",
            amark=">",
            transformer=lambda value: value or default,
        ).execute()
    raw = input(_default_prompt(message, default)).strip()
    return raw or default


def secret_prompt(message: str, *, configured: bool = False) -> str:
    suffix = " [configured, press Enter to keep]" if configured else ""
    if interactive_terminal() and inquirer is not None:
        return inquirer.secret(
            message=f"{message}{suffix}",
            qmark=">",
            amark=">",
        ).execute()
    if sys.stdin.isatty():
        return getpass.getpass(f"{message}{suffix}: ").strip()
    return input(f"{message}{suffix}: ").strip()


def confirm_prompt(message: str, *, default: bool = True) -> bool:
    if interactive_terminal() and inquirer is not None:
        return bool(
            inquirer.confirm(
                message=message,
                default=default,
                qmark=">",
                amark=">",
            ).execute()
        )
    marker = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{message} [{marker}]: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes", "true", "1"}:
            return True
        if raw in {"n", "no", "false", "0"}:
            return False
        warning("Enter yes or no.")


def select_prompt(
    message: str,
    options: Sequence[SelectOption],
    *,
    default: Any | None = None,
) -> Any:
    if not options:
        raise ValueError("select_prompt requires at least one option")
    if interactive_terminal() and inquirer is not None and Choice is not None:
        choices = [
            Choice(
                value=option.value,
                name=_choice_name(option),
                enabled=option.value == default,
            )
            for option in options
        ]
        return inquirer.select(
            message=message,
            choices=choices,
            default=default,
            pointer=">",
            qmark=">",
            amark=">",
            instruction="(use up/down arrows, Enter to select)",
        ).execute()

    for index, option in enumerate(options, start=1):
        selected = " *" if option.value == default else ""
        detail = f" - {option.description}" if option.description else ""
        print(f"  {index}. {option.label}{detail}{selected}")
    while True:
        raw = input(_default_prompt(message, _label_for_value(options, default))).strip()
        if not raw and default is not None:
            return default
        if raw.isdigit():
            index = int(raw)
            if 1 <= index <= len(options):
                return options[index - 1].value
        for option in options:
            if raw == str(option.value) or raw.lower() == option.label.lower():
                return option.value
        warning("Choose a listed item by number or name.")


def status_panel(
    *,
    config_path: str,
    base_url: str,
    model: str,
    model_state: str,
    capabilities: Iterable[str],
    provider: str,
    search_enabled: bool,
    fetch_enabled: bool,
) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="jon.dim", no_wrap=True)
    table.add_column()
    table.add_row("Config", f"[jon.path]{config_path}[/]")
    table.add_row("Ollama", base_url)
    table.add_row("Model", f"[jon.accent]{model}[/]")
    table.add_row("Model status", _state_markup(model_state))
    table.add_row("Capabilities", ", ".join(capabilities) or "unknown")
    table.add_row("Research provider", provider)
    table.add_row(
        "Research tools",
        f"search={_enabled_markup(search_enabled)}, fetch={_enabled_markup(fetch_enabled)}",
    )
    console.print(
        Panel(
            table,
            title="[jon.brand]Jon status[/]",
            border_style="green",
            padding=(1, 2),
        )
    )


def help_panel(*, provider: str, search_enabled: bool, fetch_enabled: bool) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="jon.accent", no_wrap=True)
    table.add_column()
    table.add_row("/help", "Show commands")
    table.add_row("/status", "Show current model and researcher status")
    table.add_row("/configure", "Configure Ollama model and runtime")
    table.add_row("/researcher", "Configure research provider and tools")
    table.add_row("/exit", "Exit")
    footer = (
        f"Researcher: [jon.accent]{provider}[/], "
        f"search={_enabled_markup(search_enabled)}, "
        f"fetch={_enabled_markup(fetch_enabled)}"
    )
    console.print(
        Panel(
            table,
            title="[jon.brand]Commands[/]",
            subtitle=footer,
            border_style="green",
            padding=(1, 2),
        )
    )


def _choice_name(option: SelectOption) -> str:
    if not option.description:
        return option.label
    return f"{option.label}  {option.description}"


def _default_prompt(message: str, default: str) -> str:
    if default:
        return f"{message} [{default}]: "
    return f"{message}: "


def _label_for_value(options: Sequence[SelectOption], value: Any | None) -> str:
    for option in options:
        if option.value == value:
            return option.label
    return str(value or "")


def _enabled_markup(enabled: bool) -> str:
    return "[jon.success]enabled[/]" if enabled else "[jon.warn]disabled[/]"


def _state_markup(state: str) -> str:
    if state == "ready":
        return "[jon.success]ready[/]"
    if "missing" in state:
        return f"[jon.warn]{state}[/]"
    if "unavailable" in state:
        return f"[jon.error]{state}[/]"
    return state


def _compact_json(value: dict[str, Any]) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        encoded = str(value)
    if len(encoded) > 140:
        return encoded[:137] + "..."
    return encoded


def _result_summary(text: str) -> str:
    clean = " ".join(str(text or "").split())
    if not clean:
        return ""
    if len(clean) > 90:
        clean = clean[:87] + "..."
    return f" - {clean}"


def _markdown(text: str) -> Markdown:
    return Markdown(text or " ", style="jon.answer")


def _answer_box(text: str) -> Panel:
    return Panel(
        _markdown(text),
        title="[jon.answer_prefix]jon[/]",
        border_style="white",
        padding=(0, 1),
    )
