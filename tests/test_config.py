import json

from jon_researcher.config import JonConfig, config_exists, load_config, save_config


def test_config_round_trip(tmp_path) -> None:
    path = tmp_path / "config.json"
    config = JonConfig(
        model="llama3.1:8b",
        base_url="http://localhost:11434",
        timeout=30.0,
        max_tool_rounds=3,
        research_search_enabled=False,
        research_fetch_enabled=True,
    )

    save_config(config, path)

    assert load_config(path) == config


def test_invalid_config_uses_defaults(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"timeout": "bad"}), encoding="utf-8")

    config = load_config(path)

    assert config.model == "gemma4:e2b"
    assert config.timeout == 60.0


def test_jon_home_config_exists_is_isolated(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JON_HOME", str(tmp_path))

    assert not config_exists()

    save_config(JonConfig(), tmp_path / "config.json")

    assert config_exists()
