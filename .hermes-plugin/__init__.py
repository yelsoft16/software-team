"""software-team plugin: roster-aware orchestration for Hermes.

Register the team-protocol skill and a pre_llm_call hook. On a session's first
turn the hook parses team.jsonc, syncs agent routes + delegation concurrency
into Hermes config, and injects a compact roster into the LLM context. The
whole pipeline is failure-tolerant: any parse/sync error degrades to a warning
line appended to the roster text — the hook never raises.
"""

import importlib.util
import logging
import os
import re
import sys
from pathlib import Path

_log = logging.getLogger(__name__)

#: Live user config dir: team.jsonc and state.json live here (Task 6 seeds the
#: template file). HERMES_HOME is the same env var core's hermes home honors.
LIVE_DIR = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "software-team"

#: Last pipeline result, keyed by team.jsonc mtime: while the file's mtime is
#: unchanged, re-runs reuse the cached roster instead of re-parsing/re-syncing.
#: ``roster is None`` means the pipeline has never run.
_PIPELINE_CACHE: dict = {"mtime": None, "roster": None}


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


def ensure_user_config() -> tuple[Path, Path]:
    """Return the live (team.jsonc, state.json) paths.

    Task 6 replaces this body with template-copy logic; until then the paths
    point at the live files directly.
    """
    return LIVE_DIR / "team.jsonc", LIVE_DIR / "state.json"


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


def _pipeline() -> str:
    """First-turn pipeline: parse team.jsonc, sync routes + concurrency, build roster.

    Re-runs are skipped while team.jsonc's mtime is unchanged (module-level
    cache). Never raises: a missing/broken team config or any sync failure
    degrades to a warning line appended to the roster text.
    """
    team_path, state_path = ensure_user_config()

    mtime = None
    if team_path.is_file():
        try:
            mtime = team_path.stat().st_mtime
        except OSError as exc:  # vanished between is_file and stat
            _log.warning("software-team: cannot stat %s: %s", team_path, exc)
    cache = _PIPELINE_CACHE
    if cache["roster"] is not None and cache["mtime"] == mtime:
        return cache["roster"]

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

    cache["mtime"] = mtime
    cache["roster"] = roster
    return roster


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
