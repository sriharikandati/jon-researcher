"""Ollama model discovery helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request


@dataclass(frozen=True, slots=True)
class OllamaModelStatus:
    model: str
    available: bool
    tool_capable: bool
    capabilities: tuple[str, ...] = ()
    error: str = ""


def list_tool_capable_models(base_url: str, *, timeout: float) -> tuple[list[str], str]:
    try:
        installed = list_installed_models(base_url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return [], str(exc)

    tool_capable: list[str] = []
    errors: list[str] = []
    for model in installed:
        status = inspect_model(model, base_url=base_url, timeout=timeout)
        if status.tool_capable:
            tool_capable.append(model)
        elif status.error:
            errors.append(f"{model}: {status.error}")
    return tool_capable, "; ".join(errors)


def list_installed_models(base_url: str, *, timeout: float) -> list[str]:
    payload = _request_json(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
    models = payload.get("models")
    if not isinstance(models, list):
        return []
    names: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or "").strip()
        if name:
            names.append(name)
    return names


def inspect_model(model: str, *, base_url: str, timeout: float) -> OllamaModelStatus:
    try:
        payload = _post_json(
            f"{base_url.rstrip('/')}/api/show",
            {"model": model},
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        return OllamaModelStatus(
            model=model,
            available=False,
            tool_capable=False,
            error=str(exc),
        )
    capabilities = tuple(
        sorted(
            {
                str(item).strip().lower()
                for item in payload.get("capabilities", [])
                if str(item).strip()
            }
        )
    )
    return OllamaModelStatus(
        model=model,
        available=True,
        tool_capable={"completion", "tools"}.issubset(capabilities),
        capabilities=capabilities,
    )


def _request_json(url: str, *, timeout: float) -> dict[str, Any]:
    req = request.Request(url, method="GET")
    return _open_json(req, timeout=timeout)


def _post_json(url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return _open_json(req, timeout=timeout)


def _open_json(req: request.Request, *, timeout: float) -> dict[str, Any]:
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama returned HTTP {exc.code}: {details}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach Ollama: {exc.reason}") from exc
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise RuntimeError("Ollama returned unexpected JSON.")
    return decoded
