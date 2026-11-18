"""Compact plain-text roster rendered from validated team agents.

The pre_llm_call hook injects this into the LLM context so the orchestrator knows
which specialist agents exist and how the team protocol drives the work. Budget is
structural, not enforced here: the spec pins ≤ 1024 chars for the full 8-agent roster
plus the protocol block, so descriptions in team.jsonc must stay short (they do in the
template; Task 6 owns that file).
"""

from __future__ import annotations

_PROTOCOL = (
    "Protocol:",
    "- superpowers skills drive the workflow",
    "- dispatch per role",
    "- agent prompts go into child context",
    "- collect and verify results",
)


def build_roster(agents: list[dict]) -> str:
    """Render *agents* as one text block: per agent ``name — description (model@reasoning)``
    followed by the 5-line protocol block. ``reasoning`` is omitted when the agent does
    not pin one.
    """
    lines = ["Software team roster:"]
    for agent in agents:
        reasoning = f"@{agent['reasoning']}" if agent.get("reasoning") else ""
        lines.append(
            f"{agent['name']} — {agent['description']} ({agent['model']}{reasoning})"
        )
    lines.extend(_PROTOCOL)
    return "\n".join(lines)
