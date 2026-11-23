"""Content tests for the team-protocol skill: frontmatter shape + required sections.

The skill is the orchestrator's reference manual for using the injected roster.
These tests pin what the content must carry: catalogue-valid frontmatter (the
description is what the model selects on, and Hermes caps it at 60 chars) and
the core protocol concepts (orchestrator role, the team roles, delegate_task
dispatch, result verification).
"""

import pathlib

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]
SKILL = PLUGIN_DIR / "skills" / "team-protocol" / "SKILL.md"


def test_skill_frontmatter_and_sections():
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\nname: team-protocol\n")
    assert "description:" in text[:200]
    for needle in [
        "Orkestratör",
        "explore",
        "implementer",
        "reviewer",
        "delegate_task",
        "doğrulama",
        "Hafıza döngüsü",
        "hindsight_recall",
        "hindsight_retain",
        "Öğrenimler",
        "steer",
    ]:
        assert needle in text


def test_skill_evidence_discipline_fix_loop_and_qa_row():
    text = SKILL.read_text(encoding="utf-8")
    for needle in [
        "Kanıt disiplini",
        "Önce keşif",
        "Varsayım yasağı",
        "kanıt kaynakları",
        "slop denetimi",
        "| qa |",
    ]:
        assert needle in text


def test_rol_sozlesmeleri_nine_five_block_contracts():
    """One contract per role (each role name exactly once) with the five
    mandated blocks in every contract."""
    ref = PLUGIN_DIR / "skills" / "team-protocol" / "references" / "rol-sozlesmeleri.md"
    assert ref.is_file()
    text = ref.read_text(encoding="utf-8")
    lines = text.splitlines()
    for role in [
        "explore",
        "researcher",
        "consultant",
        "planner",
        "implementer",
        "reviewer",
        "debugger",
        "writer",
        "qa",
    ]:
        assert text.count(role) == 1
        assert sum(1 for line in lines if line.strip() == f"## {role}") == 1
    for block in [
        "**Kısıtlar**",
        "**İş metodu**",
        "**Çıktı biçimi**",
        "**Başarı & başarısızlık koşulları**",
        "**NEVER-ALWAYS**",
    ]:
        assert sum(1 for line in lines if line.strip() == block) == 9


def test_skill_description_fits_catalogue_limit():
    text = SKILL.read_text(encoding="utf-8")
    frontmatter = text.split("---", 2)[1]
    description = next(
        line.split(":", 1)[1].strip().strip("\"'")
        for line in frontmatter.splitlines()
        if line.strip().startswith("description:")
    )
    # Non-empty: the description is the model's selection signal. ≤60 chars:
    # Hermes' catalogue limit (Task 1 review noted it).
    assert 0 < len(description) <= 60
