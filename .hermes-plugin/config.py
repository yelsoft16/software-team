"""team.jsonc parsing and agent validation.

team.jsonc is hand-edited JSONC: comments yes, anything else beyond plain JSON no.
Parsing is comment-strip (a char state machine, so ``//`` inside a string survives) plus
``json.loads``. Validation mirrors advanced-delegation's route requirements, so a bad entry
is reported once at load time instead of exploding during the route write.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from hermes_constants import VALID_REASONING_EFFORTS

# Route-name charset, verbatim from advanced-delegation's store.py.
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class TeamConfigError(Exception):
    """team.jsonc cannot be parsed. The message carries path, line and reason."""


def strip_jsonc_comments(text: str) -> str:
    """Blank out ``//`` and ``/* ... */`` comments, preserving length and newlines.

    Length preservation keeps ``json.JSONDecodeError.lineno`` pointing at the real line.
    A state machine, not a regex: ``"https://x"`` must keep its slashes.
    """
    out = list(text)
    i, n = 0, len(text)
    in_string = in_line = in_block = False
    while i < n:
        ch = text[i]
        if in_line:
            if ch == "\n":
                in_line = False
            else:
                out[i] = " "
        elif in_block:
            if ch == "*" and text.startswith("/", i + 1):
                out[i] = out[i + 1] = " "
                in_block = False
                i += 1
            elif ch != "\n":
                out[i] = " "
        elif in_string:
            if ch == "\\":
                i += 1  # escaped char: the next one cannot close the string
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "/" and text.startswith("//", i):
            out[i] = out[i + 1] = " "
            in_line = True
            i += 1
        elif ch == "/" and text.startswith("/*", i):
            out[i] = out[i + 1] = " "
            in_block = True
            i += 1
        i += 1
    return "".join(out)


def parse_team_config(path: Path) -> dict:
    """Parse a JSONC team file into a dict, or raise :class:`TeamConfigError`."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(strip_jsonc_comments(text))
    except json.JSONDecodeError as exc:
        raise TeamConfigError(f"{path}:{exc.lineno}: invalid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise TeamConfigError(f"{path}: top level must be a JSON object, got {type(data).__name__}")
    if not isinstance(data.get("agents"), list):
        raise TeamConfigError(f'{path}: "agents" must be a list')
    return data


def _problem(entry: dict, providers: set[str]) -> str | None:
    """Return why *entry* cannot become a route, or ``None`` when it is valid."""
    name = entry.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name):
        return f"invalid name {name!r}: must match {NAME_RE.pattern}"
    description = entry.get("description")
    if not isinstance(description, str) or not description.strip():
        return f"agent {name!r}: 'description' must be a non-empty string"
    model = entry.get("model")
    if not isinstance(model, str) or not model.strip():
        return f"agent {name!r}: 'model' must be a non-empty string"
    provider = entry.get("provider")
    base_url = entry.get("base_url")
    if provider is not None and not isinstance(provider, str):
        return f"agent {name!r}: 'provider' must be a string"
    if base_url is not None and not isinstance(base_url, str):
        return f"agent {name!r}: 'base_url' must be a string"
    if not provider and not base_url:
        return f"agent {name!r}: needs 'provider' or 'base_url'"
    reasoning = entry.get("reasoning")
    if reasoning is not None and reasoning not in VALID_REASONING_EFFORTS:
        return (
            f"agent {name!r}: reasoning {reasoning!r} is not one of "
            + ", ".join(VALID_REASONING_EFFORTS)
        )
    if provider and provider not in providers:
        return f"agent {name!r}: provider {provider!r} is not in the Hermes config providers"
    if not isinstance(entry.get("enabled", True), bool):
        return f"agent {name!r}: 'enabled' must be true or false"
    return None


def validate_agents(raw: list[dict], providers: set[str]) -> tuple[list[dict], list[str]]:
    """Split team.jsonc entries into (valid agents in file order, warning strings).

    Bad entries are skipped with a warning. ``enabled: false`` entries are dropped as well
    (no route, no roster) but only with an ``info:``-prefixed warning — they are intentional.
    Duplicate names are skipped: the route name is the store's primary key.
    """
    valid: list[dict] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            warnings.append(f"agents[{index}]: expected an object, got {type(entry).__name__} — skipped")
            continue
        problem = _problem(entry, providers)
        if problem:
            warnings.append(f"{problem} — skipped")
            continue
        name = entry["name"]
        if name in seen:
            warnings.append(f"agent {name!r}: duplicate name — skipped")
            continue
        seen.add(name)
        if entry.get("enabled", True) is False:
            warnings.append(f"info: agent {name!r} is disabled (enabled: false) — skipped")
            continue
        valid.append(entry)
    return valid, warnings


def known_providers() -> set[str]:
    """Provider names declared in the Hermes config; empty set when none are configured."""
    from hermes_cli.config import load_config_readonly

    providers = load_config_readonly().get("providers") or {}
    return set(providers) if isinstance(providers, dict) else set()
