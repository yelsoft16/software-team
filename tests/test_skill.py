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
    ]:
        assert needle in text


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
