"""Compact plain-text roster rendered from validated team agents.

The pre_llm_call hook injects this into the LLM context so the orchestrator knows
which specialist agents exist and how the team protocol drives the work. The spec
pins ≤ 1024 chars for the injected block: ``build_roster`` enforces that budget with
a visible truncation marker (see its docstring).
"""

from __future__ import annotations

_PROTOCOL = (
    "Protocol:",
    "- superpowers skills drive the workflow",
    "- dispatch per role",
    "- agent prompts go into child context",
    "- collect and verify results",
)

#: Hard budget for the injected text: the spec pins ≤ 1024 chars (marker included).
_BUDGET = 1024
_TRUNCATED_MARKER = "⚠ roster truncated"


def build_roster(agents: list[dict]) -> str:
    """Render *agents* as one text block: per agent ``name — description (model@reasoning)``
    followed by the 5-line protocol block. ``reasoning`` is omitted when the agent does
    not pin one.

    The block is capped at :data:`_BUDGET` chars: when a verbose team.jsonc would push
    past it, the static protocol block yields first (the team-protocol skill covers it),
    then trailing agent lines drop, and a visible ``⚠ roster truncated`` marker is
    appended. Truncation always cuts at whole lines, never mid-character.
    """
    lines = ["Software team roster:"]
    for agent in agents:
        reasoning = f"@{agent['reasoning']}" if agent.get("reasoning") else ""
        lines.append(
            f"{agent['name']} — {agent['description']} ({agent['model']}{reasoning})"
        )
    text = "\n".join(lines + list(_PROTOCOL))
    if len(text) > _BUDGET:
        limit = _BUDGET - len(_TRUNCATED_MARKER) - 1  # marker line inside the budget
        while len(lines) > 1 and len("\n".join(lines)) > limit:
            lines.pop()
        text = "\n".join(lines) + "\n" + _TRUNCATED_MARKER
    return text
