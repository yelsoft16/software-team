"""Ownership-preserving route sync for the software-team plugin.

Routes are persisted through advanced-delegation's store, not this plugin's own config:
the team's agent routes become ``model_map`` options in the active profile's
``config.yaml``, while entries that user hand-edited (or another tool owns) are kept
untouched. Ownership is tracked by a small JSON state file listing the route names
this plugin last wrote, so a later sync can tell its own routes from foreign ones.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
from pathlib import Path
from typing import Any

#: Module name the store is registered under; unique so it never collides with
#: advanced-delegation's own import of its ``store`` module.
_STORE_MODULE_NAME = "_software_team_advanced_delegation_store"

#: One sync at a time: route reads and writes are not atomic together.
_SYNC_LOCK = threading.Lock()


def load_store() -> Any:
    """Load ``advanced-delegation/store.py`` from the shared plugins directory.

    ``plugins_dir`` is resolved from this file's own location (``~/.hermes/plugins``
    for a normal install), so the plugin keeps working no matter where it is checked
    out. Raises RuntimeError when the store file is missing.
    """
    plugins_dir = Path(__file__).resolve().parents[2]
    store_path = plugins_dir / "advanced-delegation" / "store.py"
    if not store_path.is_file():
        raise RuntimeError(f"advanced-delegation store not found at {store_path}")
    module = sys.modules.get(_STORE_MODULE_NAME)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(_STORE_MODULE_NAME, store_path)
    if spec is None or spec.loader is None:  # pragma: no cover - guarded by is_file above
        raise RuntimeError(f"cannot load store from {store_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_STORE_MODULE_NAME] = module  # before exec, so self-imports reuse it
    spec.loader.exec_module(module)
    return module


def build_routes(agents: list[dict]) -> list[dict]:
    """Map validated team agents (Task 2 output) to store route dicts.

    ``provider`` / ``base_url`` / ``reasoning_effort`` are only included when the
    agent actually has them, so downstream route editing never sees empty keys.
    """
    routes = []
    for agent in agents:
        route: dict[str, Any] = {
            "name": agent["name"],
            "description": agent["description"],
            "model": agent["model"],
        }
        if agent.get("provider"):
            route["provider"] = agent["provider"]
        if agent.get("base_url"):
            route["base_url"] = agent["base_url"]
        if agent.get("reasoning"):
            route["reasoning_effort"] = agent["reasoning"]
        routes.append(route)
    return routes


def _route_key(routes: list[dict]) -> tuple:
    """Order-insensitive signature of a route list: no write for pure reordering."""
    return tuple(sorted(tuple(sorted(route.items())) for route in routes))


def _read_state(state_path: Path) -> list[str]:
    if not state_path.is_file():
        return []
    try:
        state = json.loads(state_path.read_text())
    except (OSError, ValueError):
        return []
    return state if isinstance(state, list) else []


def sync_routes(agents: list[dict], state_path: Path) -> dict:
    """Reconcile the store's model_map options with the team's agent routes.

    Foreign routes (never written by this plugin) are preserved as-is and come
    first; this plugin's own stale routes are dropped and its current routes
    upserted. The store is only written when something changed, and the mode is
    only flipped to ``model_map`` after a successful ``save_routes`` (that order
    matters: the mode must never point at options that were not saved). The state
    file records the names this plugin now owns.
    """
    with _SYNC_LOCK:
        store = load_store()
        current = list(store.routes(store.delegation_section()))
        previous = set(_read_state(state_path))
        desired = build_routes(agents)
        desired_by_name = {route["name"]: route for route in desired}
        desired_names = [route["name"] for route in desired]
        desired_set = set(desired_names)
        foreign = [route for route in current
                   if route["name"] not in previous and route["name"] not in desired_set]
        merged = foreign + desired

        current_by_name = {route["name"]: route for route in current}
        summary = {
            "added": [name for name in desired_names if name not in current_by_name],
            "updated": [name for name in desired_names
                        if name in current_by_name and current_by_name[name] != desired_by_name[name]],
            "removed": [route["name"] for route in current
                        if route["name"] in previous and route["name"] not in desired_set],
            "unchanged": _route_key(merged) == _route_key(current),
        }
        if not summary["unchanged"]:
            store.save_routes(merged)
            store.set_mode("model_map")
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(desired_names, indent=2) + "\n")
        return summary
