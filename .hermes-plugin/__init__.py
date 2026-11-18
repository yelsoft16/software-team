"""software-team plugin: roster-aware orchestration for Hermes.

Register the team-protocol skill and a pre_llm_call hook. On a session's first
turn the hook parses team.jsonc, syncs agent routes + delegation concurrency
into Hermes config, injects a compact roster into the LLM context, and appends
a one-line memory-maintenance reminder when one is due. The whole pipeline is
failure-tolerant: any parse/sync error degrades to a warning line appended to
the roster text, and any maintenance error degrades to a log warning — the hook
never raises.
"""

import importlib.util
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_log = logging.getLogger(__name__)

#: Live user config dir: team.jsonc and state.json live here (Task 6 seeds the
#: template file). HERMES_HOME is the same env var core's hermes home honors.
LIVE_DIR = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "software-team"

#: Last pipeline result, keyed by team.jsonc mtime: while the file's mtime is
#: unchanged, re-runs reuse the cached roster instead of re-parsing/re-syncing.
#: ``data`` is the last parsed team config (for the per-call maintenance check).
#: ``roster is None`` means the pipeline has never run.
_PIPELINE_CACHE: dict = {"mtime": None, "roster": None, "data": None}


def _sibling(name: str):
    """Load a sibling ``.hermes-plugin`` module by file path under a unique name.

    Hermes imports this file as a package (relative imports work), but the test
    suite loads it standalone — a bare ``from . import`` would ImportError there.
    Loading siblings through importlib under a unique module name works in both
    contexts, and the sys.modules cache keeps repeat loads cheap.
    """
    mod_name = f"_software_team_plugin_{name}"
    module = sys.modules.get(mod_name)
    if module is not None:
        return module
    path = Path(__file__).resolve().with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load sibling module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


parse_team_config = _sibling("config").parse_team_config
validate_agents = _sibling("config").validate_agents
known_providers = _sibling("config").known_providers
sync_routes = _sibling("sync").sync_routes
sync_concurrency = _sibling("concurrency").sync_concurrency
build_roster = _sibling("roster").build_roster
maintenance = _sibling("maintenance")
parse_maintenance_block = maintenance.parse_maintenance_block
read_state = maintenance.read_state
is_due = maintenance.is_due
compute_days_since = maintenance.compute_days_since
memory_fill_percent = maintenance.memory_fill_percent
build_reminder = maintenance.build_reminder
update_last_reminded = maintenance.update_last_reminded


def _template_path() -> Path:
    """Locate the shipped ``templates/team.jsonc`` for either install layout.

    - git-clone install: ``templates/`` sits next to ``.hermes-plugin/``.
    - flattened install: ``templates/`` sits next to this module.

    Raises loudly when neither matches: a missing template with no live config
    is a broken install, and the hook surfaces this as a visible warning.
    """
    here = Path(__file__).resolve().parent
    candidates = (here.parent / "templates" / "team.jsonc", here / "templates" / "team.jsonc")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        "software-team plugin: cannot find templates/team.jsonc "
        f"(looked at {candidates}). Reinstall the plugin or restore the template."
    )


def _create_new(path: Path, data: str) -> bool:
    """Create *path* with *data*, only if it does not exist yet.

    Returns True when this call created the file. ``"x"`` is ``O_CREAT|O_EXCL``:
    creation cannot clobber a file that appeared after the caller's ``exists()``
    check, so "never overwrite" holds under a concurrent first run too. A failed
    write removes its partial file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(data)
    except FileExistsError:
        return False  # another session won the race; its file stays untouched
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return True


def ensure_user_config() -> tuple[Path, Path]:
    """Return the live (team.jsonc, state.json) paths, seeding them on first run.

    team.jsonc is copied from the shipped template and state.json (the route
    ownership list) starts empty. Both are created only when absent: an existing
    file — the user's edits included — is never rewritten.
    """
    team_path = LIVE_DIR / "team.jsonc"
    state_path = LIVE_DIR / "state.json"
    if not team_path.exists():
        if _create_new(team_path, _template_path().read_text(encoding="utf-8")):
            _log.info("software-team: seeded %s from the shipped template", team_path)
    if not state_path.exists():
        _create_new(state_path, "[]\n")
    return team_path, state_path


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


def _warn(warnings: list[str], line: str) -> None:
    """Record a pipeline warning: operator log + roster line (the model sees it too)."""
    _log.warning("software-team: %s", line)
    warnings.append(line)


def _maintenance_paths() -> tuple[Path, Path]:
    """Return ``(state_path, memories_dir)`` for the maintenance check.

    Resolved at call time (LIVE_DIR and HERMES_HOME are read per call), so
    tests can patch this to point at tmp files.
    """
    return (
        LIVE_DIR / "maintenance.json",
        Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "memories",
    )

def _maintenance_reminder(data: dict | None) -> str:
    """One-line memory-maintenance reminder, or ``""`` when not due.

    Fixed order: interval parse (block warning → ``_log.warning``), read_state
    (state warning → ``_log.warning``), ``""`` when not due; days/fill computed
    before the state update, then update_last_reminded(state, now_iso) and
    build_reminder(days, fill). Expected failures surface as warnings; the
    pipeline's try/except is the never-raise net for anything unexpected.
    """
    now = datetime.now(timezone.utc)
    iso = now.isoformat()  # +00:00 soneki
    state_path, memories_dir = _maintenance_paths()
    interval_days, block_warning = parse_maintenance_block(
        data.get("maintenance") if isinstance(data, dict) else None
    )
    if block_warning:
        _log.warning("software-team: %s", block_warning)
    last_reminded, state_warning = read_state(state_path)
    if state_warning:
        _log.warning("software-team: %s", state_warning)
    if not is_due(last_reminded, interval_days, now):
        return ""
    days = compute_days_since(last_reminded, now) if last_reminded is not None else None
    fill = memory_fill_percent(memories_dir)
    update_last_reminded(state_path, iso)
    return build_reminder(days, fill)

def _pipeline() -> str:
    """First-turn pipeline: parse team.jsonc, sync routes + concurrency, build
    roster, then append the memory-maintenance reminder when one is due.

    Roster re-runs are skipped while team.jsonc's mtime is unchanged
    (module-level cache); the maintenance check is time-based and re-evaluated
    on every call. Never raises: a missing/broken team config or any sync
    failure degrades to a warning line appended to the roster text, and a
    maintenance failure degrades to a log warning only.
    """
    team_path, state_path = ensure_user_config()

    mtime = None
    if team_path.is_file():
        try:
            mtime = team_path.stat().st_mtime
        except OSError as exc:  # vanished between is_file and stat
            _log.warning("software-team: cannot stat %s: %s", team_path, exc)
    cache = _PIPELINE_CACHE                     # {"mtime": None, "roster": None, "data": None}
    if cache["roster"] is not None and cache["mtime"] == mtime:
        roster = cache["roster"]
    else:
        warnings: list[str] = []
        agents: list[dict] = []
        data = None
        validated = False
        providers_ok = False

        if not team_path.is_file():
            _warn(warnings, f"team config not found: {team_path}")
        else:
            try:
                data = parse_team_config(team_path)
            except Exception as exc:
                # TeamConfigError (bad JSONC) and OSError (race) both land here:
                # the roster carries the warning, nothing else runs.
                _warn(warnings, f"team config error: {exc}")
            if data is not None:
                try:
                    providers = known_providers()
                    providers_ok = True
                except Exception as exc:
                    _warn(warnings, f"known_providers() failed: {exc}")
                    providers = set()
                try:
                    agents, validate_warnings = validate_agents(data.get("agents", []), providers)
                    validated = True
                except Exception as exc:
                    _warn(warnings, f"agent validation failed: {exc}")
                else:
                    for line in validate_warnings:
                        if line.startswith("info:"):
                            _log.info("software-team: %s", line)
                        else:
                            _warn(warnings, line)

        # Sync routes only when the team config was fully understood: a broken
        # config (or unknowable provider membership) must not wipe the routes a
        # previous good sync wrote.
        if data is not None and validated and providers_ok:
            try:
                sync_routes(agents, state_path)
            except Exception as exc:
                _warn(warnings, f"route sync failed: {exc}")

        # Concurrency is provider-independent: any parsed max_parallel is synced,
        # and a malformed one (ValueError from Task 4) becomes a warning.
        if data is not None:
            try:
                sync_concurrency(data.get("max_parallel"))
            except ValueError as exc:
                _warn(warnings, f"max_parallel not synced: {exc}")
            except Exception as exc:
                _warn(warnings, f"max_parallel sync failed: {exc}")

        try:
            roster = build_roster(agents)
        except Exception as exc:
            roster = ""
            _warn(warnings, f"roster build failed: {exc}")
        if warnings:
            roster = (roster + "\n" if roster else "") + "\n".join(f"⚠ {w}" for w in warnings)

        cache["mtime"], cache["roster"], cache["data"] = mtime, roster, data

    # Bakım zaman temellidir: mtime kapısının DIŞINDA, her çağrıda koşar.
    try:
        reminder = _maintenance_reminder(cache["data"])
    except Exception as exc:                     # asla raise: warn + atla
        _log.warning("software-team: maintenance check failed: %s", exc)
        reminder = ""
    return roster + ("\n" + reminder if reminder else "")


def pre_llm_call(session_id=None, user_message=None, conversation_history=None,
                 is_first_turn=None, model=None, platform=None, **kwargs):
    """First-turn roster injection; ``None`` for subagents and later turns.

    The mtime-gated pipeline's roster goes into the LLM context. Never raises:
    a pipeline crash degrades to a single warning line in the injected text.
    """
    if not is_first_turn or platform == "subagent":
        return None
    try:
        return {"context": _pipeline()}
    except Exception as exc:  # last-resort net: the hook must never raise
        _log.warning("software-team: pipeline failed: %s", exc)
        return {"context": f"⚠ software-team pipeline failed: {exc}"}


def register(ctx):
    skills_dir = _skills_dir()
    skill_md = Path(skills_dir) / "team-protocol" / "SKILL.md"
    description = _frontmatter_value(skill_md.read_text(encoding="utf-8"), "description")

    # register_skill requires a pathlib.Path — a str raises AttributeError and
    # Hermes silently disables the whole plugin.
    ctx.register_skill("team-protocol", skill_md, description=description)
    ctx.register_hook("pre_llm_call", pre_llm_call)
