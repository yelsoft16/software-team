"""Memory-maintenance core: state file, interval parsing, reminder line.

A first-turn reminder nudges the user toward memory maintenance when the
MEMORY.md/USER.md files are filling up or the last maintenance is stale.
This module owns the pure logic — state read/write, interval computation and
the Turkish reminder line — so the plugin's first-turn pipeline can stay thin.

Runtime code is stdlib-only (json, datetime, pathlib).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

#: Default maintenance interval when the config block is missing or unusable.
DEFAULT_INTERVAL_DAYS = 7

#: Per-file character budgets (the divisor of the fill percentage).
_FILE_BUDGETS = {"MEMORY.md": 2200, "USER.md": 1375}


def parse_maintenance_block(raw: object) -> tuple[int, str | None]:
    """Parse the config's maintenance block into ``(interval_days, warning)``.

    ``None`` raw or a dict without ``interval_days`` falls back to
    :data:`DEFAULT_INTERVAL_DAYS` with no warning. A non-dict raw, or a value
    that is not an int >= 1 (bools excluded), falls back to the default with a
    warning naming ``interval_days``.
    """
    if raw is None:
        return DEFAULT_INTERVAL_DAYS, None
    if not isinstance(raw, dict):
        return DEFAULT_INTERVAL_DAYS, "maintenance block is not an object; using interval_days=7"
    if "interval_days" not in raw:
        return DEFAULT_INTERVAL_DAYS, None
    value = raw["interval_days"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return (
            DEFAULT_INTERVAL_DAYS,
            f"invalid interval_days {value!r}; using interval_days=7",
        )
    return value, None


def read_state(state_path: Path) -> tuple[str | None, str | None]:
    """Read the state file into ``(last_reminded iso, warning)``.

    A missing file is a clean ``(None, None)``. Corrupt JSON, a non-object
    payload, a missing/non-str/unparseable ``last_reminded`` all return
    ``(None, warning)``. This function never writes.
    """
    try:
        text = state_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        return None, f"cannot read state file: {exc}"
    try:
        data = json.loads(text)
    except ValueError:
        return None, "state file is not valid JSON"
    if not isinstance(data, dict):
        return None, "state file is not a JSON object"
    value = data.get("last_reminded")
    if not isinstance(value, str):
        return None, "state file has no valid last_reminded"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None, "state file last_reminded is not a valid ISO timestamp"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)  # naive → UTC
    return value, None


def compute_days_since(iso: str, now: datetime) -> int:
    """Whole days between the ISO timestamp and *now*, clamped to 0.

    Naive timestamps count as UTC; both sides are normalized to UTC so the
    subtraction is DST-safe. Future timestamps clamp to 0.
    """
    parsed = datetime.fromisoformat(iso)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    now = now.astimezone(timezone.utc)
    return max(0, (now - parsed).days)


def is_due(last_reminded: str | None, interval_days: int, now: datetime) -> bool:
    """True when a reminder is due: never reminded, or stale by the interval."""
    if last_reminded is None:
        return True
    return compute_days_since(last_reminded, now) >= interval_days


def memory_fill_percent(memories_dir: Path) -> int | None:
    """Fullest known memory file's fill percentage, or None if the dir is gone.

    Each file in :data:`_FILE_BUDGETS` contributes ``min(100, round(chars /
    budget * 100))`` (utf-8 with ``errors="replace"``; files that fail to read
    are skipped). Unbudgeted ``*.md`` files are ignored; if none of the known
    files are present the fill is 0.
    """
    if not memories_dir.is_dir():
        return None
    fills: list[int] = []
    for name, budget in _FILE_BUDGETS.items():
        path = memories_dir / name
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fills.append(min(100, round(len(text) / budget * 100)))
    return max(fills) if fills else 0


def build_reminder(days: int | None, fill_percent: int | None) -> str:
    """One-line Turkish reminder; ``days=None`` is the first-run variant.

    The fill clause is dropped when *fill_percent* is None.
    """
    core = "henüz bakım kaydı yok" if days is None else f"son bakım {days} gün önce"
    if fill_percent is not None:
        core += f"; hafıza %{fill_percent} dolu"
    return (
        f"🧹 Hafıza bakımı bekliyor ({core}) — "
        "'bakım yapalım' dersen memory-maintenance skill'iyle başlarım."
    )


def update_last_reminded(state_path: Path, iso: str) -> None:
    """Write *iso* as ``last_reminded``; create the file with O_EXCL semantics.

    The parent directory is created as needed. An existing file is never
    clobbered by the create step (``"x"`` mode, the ensure_user_config pattern);
    FileExistsError falls through to a plain update write.
    """
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"last_reminded": iso}, indent=2) + "\n"
    try:
        with state_path.open("x", encoding="utf-8") as fh:
            fh.write(payload)
    except FileExistsError:
        state_path.write_text(payload, encoding="utf-8")
