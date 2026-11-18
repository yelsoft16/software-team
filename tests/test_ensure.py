"""Tests for the shipped team template and the first-run seeding (Task 6).

The brief's two tests come first (intent verbatim; pytest-mock's ``mocker`` is
replaced by ``unittest.mock`` so this file needs no extra dependency), followed
by guards the brief does not cover: the template must pass the plugin's own
validation, render inside the 1KB roster budget, document the file-order rule,
and an existing state.json must survive a second run.
"""

import importlib.util
import json
import pathlib
import re
import unittest.mock

import pytest

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = PLUGIN_DIR / "templates" / "team.jsonc"

AGENT_ORDER = [
    "explore", "researcher", "consultant", "planner",
    "implementer", "reviewer", "debugger", "writer",
]


def _load():
    spec = importlib.util.spec_from_file_location(
        "st_init", PLUGIN_DIR / ".hermes-plugin" / "__init__.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _template_config():
    """Parse the template the way the brief's test does: strip // comments, json.loads."""
    return json.loads(re.sub(r"//[^\n]*", "", TEMPLATE.read_text(encoding="utf-8")))


# --- the brief's tests ---------------------------------------------------------------


def test_template_has_eight_agents_with_doc_models():
    text = TEMPLATE.read_text(encoding="utf-8")
    body = re.sub(r"//[^\n]*", "", text)
    cfg = json.loads(body)
    names = [a["name"] for a in cfg["agents"]]
    assert names == AGENT_ORDER
    by_name = {a["name"]: a for a in cfg["agents"]}
    assert by_name["explore"]["model"] == "gemini-3.1-flash-lite" and "reasoning" not in by_name["explore"]
    assert by_name["planner"]["model"] == "deepseek-v4-pro" and by_name["planner"]["reasoning"] == "max"
    assert by_name["consultant"]["model"] == "cx/gpt-5.6-sol" and by_name["consultant"]["reasoning"] == "high"
    assert all(a["provider"] == "api-yelsoft-online" for a in cfg["agents"])


def test_ensure_copies_and_never_overwrites(tmp_path):
    mod = _load()
    with unittest.mock.patch.object(mod, "LIVE_DIR", tmp_path):
        p1, p2 = mod.ensure_user_config()
        assert p1.exists() and p2.exists()
        p1.write_text("USER EDIT")
        p1b, _ = mod.ensure_user_config()
        assert p1b.read_text() == "USER EDIT"


# --- guards: template content --------------------------------------------------------


def test_template_matches_spec_model_table_and_max_parallel():
    cfg = _template_config()
    by_name = {a["name"]: a for a in cfg["agents"]}
    expected = {
        "explore": ("gemini-3.1-flash-lite", None),
        "researcher": ("deepseek-v4.1-flash", "max"),
        "consultant": ("cx/gpt-5.6-sol", "high"),
        "planner": ("deepseek-v4-pro", "max"),
        "implementer": ("mimo-v2.6-pro", "high"),
        "reviewer": ("glm-5.3-flash", "max"),
        "debugger": ("deepseek-v4-pro", "max"),
        "writer": ("mimo-v2.6-flash", "high"),
    }
    assert set(by_name) == set(expected)
    for name, (model, reasoning) in expected.items():
        assert by_name[name]["model"] == model
        if reasoning is None:
            assert "reasoning" not in by_name[name]
        else:
            assert by_name[name]["reasoning"] == reasoning
    assert cfg["max_parallel"] == 4
    for agent in cfg["agents"]:
        assert agent["prompt"].strip(), f"{agent['name']} needs a prompt"


def test_template_passes_plugin_validation():
    import st_config

    raw = st_config.parse_team_config(TEMPLATE)["agents"]
    agents, warnings = st_config.validate_agents(raw, {"api-yelsoft-online"})
    assert warnings == []
    assert [a["name"] for a in agents] == AGENT_ORDER


def test_template_roster_fits_budget_without_truncation():
    """T5 binding: the shipped descriptions must not push the roster past 1KB."""
    import st_config

    mod = _load()
    raw = st_config.parse_team_config(TEMPLATE)["agents"]
    agents, _ = st_config.validate_agents(raw, {"api-yelsoft-online"})
    roster = mod.build_roster(agents)
    assert len(roster) <= 1024
    assert "⚠ roster truncated" not in roster


def test_template_comment_documents_file_order_and_reasoning():
    head = TEMPLATE.read_text(encoding="utf-8").split("\n{", 1)[0]
    assert head.lstrip().startswith("//")
    low = head.lower()
    assert "dosya sırası" in low  # agents render in file order; top = most important
    for level in ("minimal", "low", "medium", "high", "xhigh", "max", "ultra"):
        assert level in low


def test_template_carries_no_endpoint_or_key():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "api.yelsoft.online" not in text
    assert "key_env" not in text
    assert "sk-" not in text


# --- guards: first-run seeding -------------------------------------------------------


def test_ensure_copies_template_byte_for_byte_and_seeds_empty_state(tmp_path):
    mod = _load()
    with unittest.mock.patch.object(mod, "LIVE_DIR", tmp_path):
        team, state = mod.ensure_user_config()
    assert team.read_text(encoding="utf-8") == TEMPLATE.read_text(encoding="utf-8")
    assert json.loads(state.read_text(encoding="utf-8")) == []


def test_existing_state_file_is_never_overwritten(tmp_path):
    mod = _load()
    (tmp_path / "state.json").write_text('["mine"]')
    with unittest.mock.patch.object(mod, "LIVE_DIR", tmp_path):
        _, state = mod.ensure_user_config()
    assert state.read_text() == '["mine"]'


def test_ensure_creates_missing_parent_dirs(tmp_path):
    mod = _load()
    live = tmp_path / "nested" / "software-team"
    with unittest.mock.patch.object(mod, "LIVE_DIR", live):
        team, state = mod.ensure_user_config()
    assert team.parent == live and team.is_file() and state.is_file()


def test_missing_template_raises_only_when_seeding_is_needed(tmp_path):
    mod = _load()
    with unittest.mock.patch.object(mod, "LIVE_DIR", tmp_path), unittest.mock.patch.object(
        mod, "_template_path", side_effect=RuntimeError("no template")
    ):
        with pytest.raises(RuntimeError, match="no template"):
            mod.ensure_user_config()
    # A live file already exists -> nothing to copy, a missing template is harmless.
    (tmp_path / "team.jsonc").write_text("{}")
    with unittest.mock.patch.object(mod, "LIVE_DIR", tmp_path), unittest.mock.patch.object(
        mod, "_template_path", side_effect=RuntimeError("no template")
    ):
        team, state = mod.ensure_user_config()
    assert team.read_text() == "{}" and state.is_file()
