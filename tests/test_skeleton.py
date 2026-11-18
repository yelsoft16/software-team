import importlib.util
import pathlib
import unittest.mock

import pytest
import yaml

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]


def _load_plugin():
    spec = importlib.util.spec_from_file_location(
        "software_team_init", PLUGIN_DIR / ".hermes-plugin" / "__init__.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_manifest_declares_hook_and_version():
    with open(PLUGIN_DIR / ".hermes-plugin" / "plugin.yaml") as f:
        m = yaml.safe_load(f)
    assert m["name"] == "software-team"
    assert m["version"] == "0.1.0"
    assert m["provides_hooks"] == ["pre_llm_call"]
    assert m["requires_hermes"] == ">=0.22.5"


def test_skills_dir_points_at_skill_tree():
    mod = _load_plugin()
    skills_dir = mod._skills_dir()
    assert isinstance(skills_dir, str)
    assert pathlib.Path(skills_dir, "team-protocol", "SKILL.md").is_file()


def test_skills_dir_raises_when_missing(tmp_path, monkeypatch):
    mod = _load_plugin()
    monkeypatch.setattr(mod, "__file__", str(tmp_path / ".hermes-plugin" / "__init__.py"))
    with pytest.raises(RuntimeError, match="skills"):
        mod._skills_dir()


def test_register_registers_skill_path():
    mod = _load_plugin()
    ctx = unittest.mock.Mock()
    mod.register(ctx)
    ctx.register_skill.assert_called_once()
    name, path = ctx.register_skill.call_args.args
    assert name == "team-protocol"
    # register_skill requires a pathlib.Path; a str raises AttributeError and
    # Hermes silently disables the whole plugin.
    assert isinstance(path, pathlib.Path)
    assert path.name == "SKILL.md"


def test_register_hook_is_noop_placeholder():
    mod = _load_plugin()
    ctx = unittest.mock.Mock()
    mod.register(ctx)
    ctx.register_hook.assert_called_once()
    hook_name, hook = ctx.register_hook.call_args.args
    assert hook_name == "pre_llm_call"
    assert hook() is None
