"""Persistent configuration for Jon."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "gemma4:e2b"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_TOOL_ROUNDS = 5
DEFAULT_RESEARCH_PROVIDER = "duckduckgo"
APP_CONFIG_DIR = ".local/share/jon-researcher"
LEGACY_CONFIG_DIR = ".jon-researcher"


@dataclass(frozen=True, slots=True)
class JonConfig:
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout: float = DEFAULT_TIMEOUT
    max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS
    research_search_enabled: bool = True
    research_fetch_enabled: bool = True
    research_provider: str = DEFAULT_RESEARCH_PROVIDER
    research_api_keys: dict[str, str] = field(default_factory=dict)

    @property
    def research_enabled(self) -> bool:
        return self.research_search_enabled or self.research_fetch_enabled


def config_path() -> Path:
    raw_home = os.environ.get("JON_HOME")
    if raw_home:
        return Path(raw_home).expanduser() / "config.json"
    return Path.home() / APP_CONFIG_DIR / "config.json"


def legacy_config_path() -> Path:
    return Path.home() / LEGACY_CONFIG_DIR / "config.json"


def config_exists(path: Path | None = None) -> bool:
    if path is not None:
        return path.exists()
    if os.environ.get("JON_HOME"):
        return config_path().exists()
    return config_path().exists() or legacy_config_path().exists()


def load_config(path: Path | None = None) -> JonConfig:
    selected_path = path or _load_path()
    if not selected_path.exists():
        return _with_env_overrides(JonConfig())
    try:
        payload = json.loads(selected_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _with_env_overrides(JonConfig())
    if not isinstance(payload, dict):
        return _with_env_overrides(JonConfig())

    config = JonConfig(
        model=str(payload.get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        base_url=str(payload.get("base_url") or DEFAULT_BASE_URL).strip()
        or DEFAULT_BASE_URL,
        timeout=_float_value(payload.get("timeout"), DEFAULT_TIMEOUT),
        max_tool_rounds=max(
            0, _int_value(payload.get("max_tool_rounds"), DEFAULT_MAX_TOOL_ROUNDS)
        ),
        research_search_enabled=bool(payload.get("research_search_enabled", True)),
        research_fetch_enabled=bool(payload.get("research_fetch_enabled", True)),
        research_provider=str(
            payload.get("research_provider") or DEFAULT_RESEARCH_PROVIDER
        )
        .strip()
        .lower()
        or DEFAULT_RESEARCH_PROVIDER,
        research_api_keys=_api_keys(payload.get("research_api_keys")),
    )
    return _with_env_overrides(config)


def save_config(config: JonConfig, path: Path | None = None) -> Path:
    selected_path = path or config_path()
    selected_path.parent.mkdir(parents=True, exist_ok=True)
    selected_path.write_text(
        json.dumps(asdict(config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return selected_path


def _load_path() -> Path:
    selected_path = config_path()
    if selected_path.exists():
        return selected_path
    legacy_path = legacy_config_path()
    if legacy_path.exists() and not os.environ.get("JON_HOME"):
        return legacy_path
    return selected_path


def update_config(config: JonConfig, **updates: Any) -> JonConfig:
    return replace(config, **updates)


def _with_env_overrides(config: JonConfig) -> JonConfig:
    updates: dict[str, Any] = {}
    if os.environ.get("JON_MODEL"):
        updates["model"] = os.environ["JON_MODEL"].strip() or config.model
    if os.environ.get("JON_OLLAMA_BASE_URL"):
        updates["base_url"] = (
            os.environ["JON_OLLAMA_BASE_URL"].strip() or config.base_url
        )
    if os.environ.get("JON_TIMEOUT"):
        updates["timeout"] = _float_value(os.environ["JON_TIMEOUT"], config.timeout)
    if os.environ.get("JON_MAX_TOOL_ROUNDS"):
        updates["max_tool_rounds"] = max(
            0, _int_value(os.environ["JON_MAX_TOOL_ROUNDS"], config.max_tool_rounds)
        )
    if os.environ.get("JON_RESEARCH_PROVIDER"):
        updates["research_provider"] = (
            os.environ["JON_RESEARCH_PROVIDER"].strip().lower()
            or config.research_provider
        )
    if not updates:
        return config
    return replace(config, **updates)


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _api_keys(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    keys: dict[str, str] = {}
    for raw_name, raw_key in value.items():
        name = str(raw_name or "").strip().lower()
        api_key = str(raw_key or "").strip()
        if name and api_key:
            keys[name] = api_key
    return keys
