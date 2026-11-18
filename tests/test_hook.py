"""Tests for the first-turn roster injection hook.

The brief's three tests come first (verbatim intent; the stray ``import mocker`` line
from the brief is dropped — the ``mocker`` fixture is provided by pytest-mock), then
guard tests for the pipeline's failure-degradation contract: the hook must never
raise, sync failures become warning lines in the roster, and re-runs are skipped
while team.jsonc's mtime is unchanged.
"""

import importlib.util
import logging
import os
import pathlib

import pytest

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "st_init", PLUGIN_DIR / ".hermes-plugin" / "__init__.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


VALID_TEAM = """\
{
  // software team
  "agents": [
    {"name": "explore", "description": "explores the codebase", "model": "m-explore", "provider": "p"},
    {"name": "writer", "description": "writes the docs", "model": "m-writer", "provider": "p", "reasoning": "high"}
  ],
  "max_parallel": 4
}
"""


# --- the brief's tests ---------------------------------------------------------------


def test_roster_under_1kb():
    mod = _load()
    agents = [
        {"name": n, "description": f"desc {n}", "model": f"m-{n}", "provider": "p", "reasoning": r}
        for n, r in zip(
            ["explore", "researcher", "consultant", "planner", "implementer", "reviewer", "debugger", "writer"],
            [None, "max", "high", "max", "high", "max", "max", "high"],
        )
    ]
    roster = mod.build_roster(agents)
    assert len(roster) <= 1024


def test_hook_skips_subagents_and_later_turns(mocker):
    mod = _load()
    hook = mod._make_hook() if hasattr(mod, "_make_hook") else None
    # fallback: call register and capture hook
    ctx = mocker.Mock()
    ctx.register_hook = mocker.Mock(side_effect=lambda name, fn: setattr(ctx, "hook", fn))
    mod.register(ctx)
    assert ctx.hook(is_first_turn=True, platform="subagent") is None
    assert ctx.hook(is_first_turn=False, platform="cli") is None


def test_hook_injects_roster_on_first_turn(mocker):
    mod = _load()
    mocker.patch.object(mod, "build_roster", return_value="ROSTER")
    mocker.patch.object(mod, "_pipeline", return_value="ROSTER")
    ctx = mocker.Mock()
    ctx.register_hook = mocker.Mock(side_effect=lambda name, fn: setattr(ctx, "hook", fn))
    mod.register(ctx)
    res = ctx.hook(is_first_turn=True, platform="cli")
    assert res == {"context": "ROSTER"}


# --- guard tests: roster format ------------------------------------------------------


def test_roster_line_format_and_protocol_block():
    mod = _load()
    roster = mod.build_roster([
        {"name": "explore", "description": "d", "model": "m1", "provider": "p"},
        {"name": "writer", "description": "d", "model": "m2", "provider": "p", "reasoning": "high"},
    ])
    assert "explore — d (m1)" in roster
    assert "writer — d (m2@high)" in roster
    assert roster.count("\n") == 1 + 2 + 4  # header + 2 agents + 5-line protocol block


def test_roster_truncates_with_marker_when_over_budget():
    mod = _load()
    agents = [
        {"name": n, "description": "d" * 200, "model": f"m-{n}", "provider": "p", "reasoning": "high"}
        for n in ["explore", "researcher", "consultant", "planner", "implementer", "reviewer", "debugger", "writer"]
    ]
    roster = mod.build_roster(agents)
    assert len(roster) <= 1024
    assert roster.endswith("⚠ roster truncated")
    # truncation drops whole lines, never mid-character: the header and complete
    # leading agent lines survive, nothing partial.
    lines = roster.splitlines()
    assert lines[0] == "Software team roster:"
    assert lines[1].startswith("explore — ")
    assert lines[-1] == "⚠ roster truncated"
    for line in lines[1:-1]:
        assert " — " in line and ")" in line


def test_roster_no_truncation_within_budget():
    mod = _load()
    agents = [
        {"name": n, "description": f"desc {n}", "model": f"m-{n}", "provider": "p", "reasoning": r}
        for n, r in zip(
            ["explore", "researcher", "consultant", "planner", "implementer", "reviewer", "debugger", "writer"],
            [None, "max", "high", "max", "high", "max", "max", "high"],
        )
    ]
    roster = mod.build_roster(agents)
    assert len(roster) <= 1024
    assert "⚠ roster truncated" not in roster
    assert roster.count("\n") == 1 + 8 + 4  # full protocol block survives


def test_live_dir_respects_hermes_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    mod = _load()
    team_path, state_path = mod.ensure_user_config()
    assert team_path == tmp_path / "software-team" / "team.jsonc"
    assert state_path == tmp_path / "software-team" / "state.json"


# --- guard tests: pipeline behavior ---------------------------------------------------


def _pipeline_mod(mocker, tmp_path, *, team_text=None):
    """Load the plugin with ensure_user_config pointed at tmp files."""
    mod = _load()
    team = tmp_path / "team.jsonc"
    state = tmp_path / "state.json"
    if team_text is not None:
        team.write_text(team_text)
    mocker.patch.object(mod, "ensure_user_config", return_value=(team, state))
    mocker.patch.object(mod, "known_providers", return_value={"p"})
    sync_routes = mocker.patch.object(mod, "sync_routes")
    sync_concurrency = mocker.patch.object(mod, "sync_concurrency")
    return mod, team, state, sync_routes, sync_concurrency


def test_pipeline_syncs_once_and_reuses_cache_when_mtime_unchanged(mocker, tmp_path):
    mod, team, _, sync_routes, sync_concurrency = _pipeline_mod(
        mocker, tmp_path, team_text=VALID_TEAM
    )
    first = mod._pipeline()
    assert "explore" in first and "writer" in first
    sync_routes.assert_called_once()
    sync_concurrency.assert_called_once_with(4)  # T4-M4: team.jsonc's max_parallel, exactly
    # same mtime -> cached roster, no re-parse / re-sync
    second = mod._pipeline()
    assert second == first
    sync_routes.assert_called_once()
    sync_concurrency.assert_called_once()
    # mtime bump -> pipeline re-runs
    stat = team.stat()
    os.utime(team, (stat.st_atime, stat.st_mtime + 5))
    mod._pipeline()
    assert sync_routes.call_count == 2
    assert sync_concurrency.call_count == 2


def test_pipeline_missing_team_file_yields_warning_and_no_sync(mocker, tmp_path):
    mod, _, _, sync_routes, sync_concurrency = _pipeline_mod(mocker, tmp_path)
    roster = mod._pipeline()
    assert "⚠" in roster and "not found" in roster
    sync_routes.assert_not_called()
    sync_concurrency.assert_not_called()


def test_pipeline_parse_failure_degrades_to_warning_roster(mocker, tmp_path):
    mod, _, _, sync_routes, sync_concurrency = _pipeline_mod(
        mocker, tmp_path, team_text="{ not json"
    )
    roster = mod._pipeline()
    assert "⚠" in roster and "team.jsonc" in roster
    # roster-only injection: no sync on a broken team config (must not wipe routes)
    sync_routes.assert_not_called()
    sync_concurrency.assert_not_called()


def test_pipeline_route_sync_failure_appends_warning_and_continues(mocker, tmp_path):
    mod, _, _, sync_routes, sync_concurrency = _pipeline_mod(
        mocker, tmp_path, team_text=VALID_TEAM
    )
    sync_routes.side_effect = RuntimeError("store boom")
    roster = mod._pipeline()
    assert "explore" in roster  # roster still injected
    assert "route sync failed: store boom" in roster
    sync_concurrency.assert_called_once_with(4)


def test_pipeline_invalid_max_parallel_warns_and_continues(mocker, tmp_path):
    mod, _, _, sync_routes, sync_concurrency = _pipeline_mod(
        mocker, tmp_path, team_text=VALID_TEAM.replace('"max_parallel": 4', '"max_parallel": "4"')
    )
    sync_concurrency.side_effect = ValueError("max_parallel must be an integer")
    roster = mod._pipeline()
    assert "explore" in roster
    assert "max_parallel" in roster and "⚠" in roster
    sync_routes.assert_called_once()


def test_pipeline_known_providers_failure_warns_and_skips_route_sync(mocker, tmp_path):
    mod, _, _, sync_routes, sync_concurrency = _pipeline_mod(
        mocker, tmp_path, team_text=VALID_TEAM
    )
    mocker.patch.object(
        mod, "known_providers", side_effect=ImportError("no hermes_cli")
    )
    roster = mod._pipeline()
    assert "known_providers()" in roster
    # provider membership is unknowable: sync would drop every provider route (data loss)
    sync_routes.assert_not_called()
    # concurrency is provider-independent: still synced from team.jsonc
    sync_concurrency.assert_called_once_with(4)


def test_pipeline_routes_info_lines_to_log_not_roster(mocker, tmp_path, caplog):
    team_text = """\
{
  "agents": [
    {"name": "valid", "description": "ok", "model": "m", "provider": "p"},
    {"name": "bad name!", "description": "ok", "model": "m", "provider": "p"},
    {"name": "off", "description": "ok", "model": "m", "provider": "p", "enabled": false}
  ],
  "max_parallel": 2
}
"""
    mod, _, _, sync_routes, _ = _pipeline_mod(mocker, tmp_path, team_text=team_text)
    with caplog.at_level(logging.INFO):
        roster = mod._pipeline()
    # non-info validation warnings land in the roster ...
    assert "invalid name" in roster
    # ... info: lines (intentional disables) go to the info channel, not the roster
    assert "disabled" not in roster
    assert any("disabled" in rec.message and rec.levelno == logging.INFO for rec in caplog.records)
    assert any("invalid name" in rec.message and rec.levelno == logging.WARNING for rec in caplog.records)
    # only the valid agent is synced
    synced = sync_routes.call_args.args[0]
    assert [agent["name"] for agent in synced] == ["valid"]


def test_hook_survives_pipeline_crash(mocker):
    mod = _load()
    mocker.patch.object(mod, "_pipeline", side_effect=RuntimeError("boom"))
    ctx = mocker.Mock()
    ctx.register_hook = mocker.Mock(side_effect=lambda name, fn: setattr(ctx, "hook", fn))
    mod.register(ctx)
    res = ctx.hook(is_first_turn=True, platform="cli")
    assert isinstance(res, dict) and "boom" in res["context"]
