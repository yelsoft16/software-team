import pathlib
import re

import pytest

from st_config import TeamConfigError, known_providers, parse_team_config, validate_agents

FIX = pathlib.Path(__file__).parent / "fixtures"


def test_parse_strips_comments():
    cfg = parse_team_config(FIX / "valid.jsonc")
    assert "agents" in cfg and len(cfg["agents"]) == 2
    assert cfg["agents"][0]["name"] == "explore"


def test_parse_broken_json_raises():
    try:
        parse_team_config(FIX / "broken.jsonc")
        assert False
    except TeamConfigError:
        pass


def test_validate_rejects_bad_reasoning():
    raw = parse_team_config(FIX / "invalid_reasoning.jsonc")
    valid, warns = validate_agents(raw["agents"], {"api-yelsoft-online"})
    assert not valid
    assert any("reasoning" in w for w in warns)


def test_validate_requires_description():
    raw = parse_team_config(FIX / "missing_description.jsonc")
    valid, warns = validate_agents(raw["agents"], {"api-yelsoft-online"})
    assert not valid


def test_validate_rejects_unknown_provider():
    valid, warns = validate_agents(
        [{"name": "x", "description": "d", "model": "m", "provider": "ghost"}],
        {"api-yelsoft-online"},
    )
    assert not valid and any("provider" in w for w in warns)


def test_validate_drops_disabled_agents():
    valid, warns = validate_agents(
        [
            {"name": "on", "description": "d", "model": "m", "provider": "p"},
            {"name": "off", "description": "d", "model": "m", "provider": "p", "enabled": False},
        ],
        {"p"},
    )
    assert [a["name"] for a in valid] == ["on"]


# --- guards the brief's tests do not cover -------------------------------------------


def test_parse_keeps_slashes_inside_strings():
    """``https://`` in a value must survive the comment stripper."""
    cfg = parse_team_config(FIX / "valid.jsonc")
    assert cfg["agents"][0]["prompt"].endswith("// this is a string, not a comment")


def test_parse_error_carries_path_and_line_hint():
    with pytest.raises(TeamConfigError) as exc:
        parse_team_config(FIX / "broken.jsonc")
    msg = str(exc.value)
    assert "broken.jsonc" in msg
    assert re.search(r":\d+:", msg), msg


def test_parse_renamed_fixture_is_valid():
    cfg = parse_team_config(FIX / "renamed.jsonc")
    assert [a["name"] for a in cfg["agents"]] == ["scout", "auditor"]
    valid, warns = validate_agents(cfg["agents"], {"api-yelsoft-online"})
    assert [a["name"] for a in valid] == ["scout", "auditor"] and not warns


def test_parse_requires_object_root_and_agents_list(tmp_path):
    path = tmp_path / "team.jsonc"
    path.write_text("[1, 2]")
    with pytest.raises(TeamConfigError, match="object"):
        parse_team_config(path)
    path.write_text('{"agents": {"explore": {}}}')
    with pytest.raises(TeamConfigError, match="agents"):
        parse_team_config(path)


def test_validate_rejects_bad_name_charset():
    valid, warns = validate_agents(
        [{"name": "bad name!", "description": "d", "model": "m", "provider": "p"}], {"p"}
    )
    assert not valid and any("name" in w for w in warns)


def test_validate_rejects_non_bool_enabled():
    valid, warns = validate_agents(
        [{"name": "x", "description": "d", "model": "m", "provider": "p", "enabled": "false"}],
        {"p"},
    )
    assert not valid and any("enabled" in w for w in warns)


def test_validate_rejects_duplicate_names():
    agent = {"name": "dup", "description": "d", "model": "m", "provider": "p"}
    valid, warns = validate_agents([agent, dict(agent)], {"p"})
    assert len(valid) == 1 and any("duplicate" in w for w in warns)


def test_validate_skips_non_dict_entries():
    valid, warns = validate_agents(["oops", {"name": "ok", "description": "d", "model": "m", "provider": "p"}], {"p"})
    assert [a["name"] for a in valid] == ["ok"] and warns


def test_known_providers_reads_config(monkeypatch):
    import hermes_cli.config

    monkeypatch.setattr(hermes_cli.config, "load_config_readonly", lambda: {"providers": {"a": {}, "b": {}}})
    assert known_providers() == {"a", "b"}


def test_known_providers_missing_key_returns_empty_set(monkeypatch):
    import hermes_cli.config

    monkeypatch.setattr(hermes_cli.config, "load_config_readonly", lambda: {})
    assert known_providers() == set()
