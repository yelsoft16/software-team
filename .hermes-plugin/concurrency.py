"""Single-key sync of the team's ``max_parallel`` into core's delegation setting.

Only ``delegation.max_concurrent_children`` is ever written. The raw config document is
read back and handed to core's ``atomic_config_write`` with that one value changed, so
``delegation.model`` / ``provider`` / ``reasoning_effort`` — and every other key — survive
untouched. Handing it the full raw document (rather than a partial ``{"delegation": ...}``)
is also what core requires: its omission guard rejects documents that would drop existing
keys.
"""

from __future__ import annotations

from pathlib import Path

_SECTION = "delegation"
_KEY = "max_concurrent_children"


def sync_concurrency(max_parallel: int | None) -> bool:
    """Write *max_parallel* to ``delegation.max_concurrent_children``; True if written.

    ``None`` (team.jsonc has no ``max_parallel``) and an effective value that already
    matches are no-ops. A non-integer raises ValueError: a malformed team.jsonc value must
    never reach core's config as a string.
    """
    if max_parallel is None:
        return False
    if isinstance(max_parallel, bool) or not isinstance(max_parallel, int):
        raise ValueError(f"max_parallel must be an integer, got {type(max_parallel).__name__}")

    from hermes_cli import config as hermes_config

    config_path: Path = hermes_config.get_config_path()
    effective = hermes_config.load_config_readonly().get(_SECTION)
    if isinstance(effective, dict) and effective.get(_KEY) == max_parallel:
        return False

    document = hermes_config.read_user_config_raw(config_path)
    section = document.get(_SECTION)
    if not isinstance(section, dict):
        section = document[_SECTION] = {}
    section[_KEY] = max_parallel
    hermes_config.atomic_config_write(config_path, document)
    return True
