import importlib.util
import pathlib
import unittest.mock

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]
SKILL = PLUGIN_DIR / "skills" / "memory-maintenance" / "SKILL.md"

def test_skill_frontmatter_and_sections():
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\nname: memory-maintenance\n")
    assert "description:" in text[:200]
    for needle in ["hindsight_retain", "backups", "onay", "maintenance.json",
                   "%90", "SOUL.md", "memory aracı", "bakım yapalım"]:
        assert needle in text

def test_skill_description_fits_catalogue_limit():
    frontmatter = SKILL.read_text(encoding="utf-8").split("---", 2)[1]
    description = next(l.split(":", 1)[1].strip().strip("\"'")
                       for l in frontmatter.splitlines()
                       if l.strip().startswith("description:"))
    assert 0 < len(description) <= 60

def test_register_memory_maintenance_skill(mocker):
    spec = importlib.util.spec_from_file_location(
        "st_init", PLUGIN_DIR / ".hermes-plugin" / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ctx = mocker.Mock()
    mod.register(ctx)
    names = [c.args[0] for c in ctx.register_skill.call_args_list]
    assert names == ["team-protocol", "memory-maintenance"]
    path_arg = ctx.register_skill.call_args_list[1].args[1]
    assert isinstance(path_arg, pathlib.Path)   # Path zorunlu — str AttributeError üretir
    assert ctx.register_skill.call_args_list[1].kwargs["description"].strip()
