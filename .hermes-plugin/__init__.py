"""software-team plugin: roster-aware orchestration for Hermes.

Task 1 is the skeleton: resolve the skills tree loudly, register the
team-protocol skill, and declare a placeholder pre_llm_call hook.
"""

import os
import re
from pathlib import Path


def _skills_dir() -> str:
    """Locate the plugin's skills/ tree for either supported install layout.

    - git-clone install: `.hermes-plugin/` and `skills/` are siblings, so this
      module resolves `../skills`.
    - flattened install (plugin files copied to the plugin dir root): `skills/`
      sits next to this module.

    Raises loudly when neither matches — a plugin that silently skips its
    skills is how a broken install masquerades as a working one.
    """
    here = os.path.dirname(os.path.realpath(__file__))
    candidates = (
        os.path.realpath(os.path.join(here, "..", "skills")),
        os.path.realpath(os.path.join(here, "skills")),
    )
    for cand in candidates:
        if os.path.isfile(os.path.join(cand, "team-protocol", "SKILL.md")):
            return cand
    raise RuntimeError(
        "software-team plugin: cannot find the skills/ tree "
        f"(looked at {candidates}). Reinstall the plugin or restore "
        "skills/team-protocol/SKILL.md."
    )


def _strip_frontmatter(content: str) -> str:
    match = re.match(r"^---\n[\s\S]*?\n---\n([\s\S]*)$", content)
    return (match.group(1) if match else content).strip()


def _frontmatter_value(content: str, key: str) -> str:
    """Return a flat ``key: value`` scalar from a SKILL.md frontmatter block.

    Hermes reads a skill's description from ``register_skill``'s ``description``
    argument, which defaults to "" — registering only the path leaves the skill
    with a blank description in the catalogue, so the model has nothing to
    select on. Our frontmatter is a flat block of single-line scalars, so a line
    scan covers it without a YAML dependency.
    """
    match = re.match(r"^---\n([\s\S]*?)\n---\n", content)
    if not match:
        return ""
    for line in match.group(1).splitlines():
        name, sep, value = line.partition(":")
        if sep and name.strip() == key:
            return value.strip().strip("\"'")
    return ""


def register(ctx):
    skills_dir = _skills_dir()
    skill_md = Path(skills_dir) / "team-protocol" / "SKILL.md"
    description = _frontmatter_value(skill_md.read_text(encoding="utf-8"), "description")

    # register_skill requires a pathlib.Path — a str raises AttributeError and
    # Hermes silently disables the whole plugin.
    ctx.register_skill("team-protocol", skill_md, description=description)

    # Placeholder: Task 5 rewires this into the roster/route sync hook.
    def pre_llm_call(**kwargs):
        return None

    ctx.register_hook("pre_llm_call", pre_llm_call)
