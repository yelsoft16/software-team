# software-team Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the software-team Hermes plugin: team.jsonc defines 8 agent roles; the plugin syncs them into advanced-delegation model_map routes, switches the backend to model_map, and injects a compact roster+protocol into the orchestrator's first non-subagent turn.

**Architecture:** One standalone Hermes plugin at `~/.hermes/plugins/software-team/`. A `pre_llm_call` hook (superpowers pattern) injects the roster and triggers an mtime-gated route sync on each session's first call. Sync reuses advanced-delegation's store (`save_routes`, `set_mode`) and core's `atomic_config_write` for `delegation.max_concurrent_children` only. Route ownership is tracked in `~/.hermes/software-team/state.json` so foreign hand-added routes survive syncs. No new Python dependencies.

**Tech Stack:** Python 3 (stdlib only), Hermes plugin API (register/register_skill/register_hook), advanced-delegation store.py, hermes_cli.config, pytest (dev only, via hermes-plugins skill recipe).

**Spec:** `/home/yelsoft/.hermes/plugins/software-team/docs/2026-11-18-software-team-design.md` (authoritative; includes the Opus review resolutions).

## Global Constraints

- `requires_hermes: ">=0.22.5"`; depends on installed plugins superpowers + advanced-delegation (never reimplement their work).
- Route/agent name charset: `^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$`; route name = role name, never a model id.
- Reasoning vocabulary = core `VALID_REASONING_EFFORTS` = (`minimal`, `low`, `medium`, `high`, `xhigh`, `max`, `ultra`); omitted field = provider default.
- team.jsonc contains NO secrets; provider referenced by name only (`api-yelsoft-online`).
- Required agent fields: `name`, `description`, `model`, and `provider` or `base_url`.
- Injection only when `is_first_turn and platform != "subagent"`; size ≤ ~1KB.
- Config writes touch ONLY `delegation.backends.model_map.options`, `delegation.backend`, `delegation.max_concurrent_children`; never `delegation.model`/`provider`/`reasoning_effort`.
- model_map `default` route stays UNSET.
- Invalid agent entries: warn + skip; plugin must never silently die or crash the session.
- Default roster = the 8-agent model table in the spec (provider `api-yelsoft-online`).

## Review Focus

1. Hand-edited team.jsonc with a syntax error, missing `description`, or illegal `reasoning` value → plugin warns, skips that agent, keeps serving the rest (not crash, not full disable).
2. A foreign route added by the user via `hermes delegation config` → survives every sync unchanged.
3. An agent renamed in team.jsonc (e.g. `explore` → `scout`) → old route removed from options AND from state.json, new route added, exactly one route per agent.
4. `enabled: false` on an agent → no route written, no roster entry, agent absent from injection text.
5. Injection text: never returned for `platform == "subagent"`, and ≤ 1024 chars for the full 8-agent roster.

---

### Task 1: Plugin skeleton, manifest, loud skill-tree lookup

**Files:**
- Create: `~/.hermes/plugins/software-team/.hermes-plugin/plugin.yaml`
- Create: `~/.hermes/plugins/software-team/.hermes-plugin/__init__.py`
- Create: `~/.hermes/plugins/software-team/skills/team-protocol/SKILL.md` (placeholder frontmatter + body, real content in Task 7)
- Create: `~/.hermes/plugins/software-team/tests/test_skeleton.py`
- Init git repo at plugin root, branch `feature/build` (local only, no remote).

**Interfaces:**
- Produces: `_skills_dir() -> str` (raises RuntimeError when `skills/team-protocol/SKILL.md` missing); `register(ctx)` registering the team-protocol skill via `ctx.register_skill(name, Path(skill_md), description=...)` (description read from frontmatter by flat line scan) and returning a no-op pre_llm_call hook placeholder that returns `None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_skeleton.py
import yaml, pathlib
PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]

def test_manifest_declares_hook_and_version():
    with open(PLUGIN_DIR / ".hermes-plugin" / "plugin.yaml") as f:
        m = yaml.safe_load(f)
    assert m["name"] == "software-team"
    assert m["provides_hooks"] == ["pre_llm_call"]
    assert m["requires_hermes"] == ">=0.22.5"

def test_skills_dir_raises_when_missing(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("st_init", PLUGIN_DIR / ".hermes-plugin" / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert isinstance(mod._skills_dir(), str)

def test_register_registers_skill(mocker):
    import importlib.util
    spec = importlib.util.spec_from_file_location("st_init", PLUGIN_DIR / ".hermes-plugin" / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ctx = mocker.Mock()
    mod.register(ctx)
    assert ctx.register_skill.called
```

- [ ] **Step 2: Run tests, confirm FAIL** (module missing / no manifest)

Run: `cd ~/.hermes/plugins/software-team && REPO=/home/yelsoft/.hermes/hermes-agent SP=$(python3 -c "import sysconfig;print(sysconfig.get_paths()['purelib'])") HERMES_AGENT_REPO=$REPO PYTHONPATH="$SP:$REPO" uv run --quiet --with pytest python -m pytest tests/ -q`
Expected: FAIL (import errors / missing files)

- [ ] **Step 3: Implement manifest + `__init__.py`**

plugin.yaml keys exactly: `name: software-team`, `version: 0.1.0`, `description` (one line), `author: yelsoft`, `provides_hooks: [pre_llm_call]`, `requires_hermes: ">=0.22.5"`. `__init__.py`: `_skills_dir()` mirroring superpowers (candidates: `<plugin>/skills` and `<plugin>/.hermes-plugin/../skills`, raise loudly if neither holds `skills/team-protocol/SKILL.md`); `_strip_frontmatter` + `_frontmatter_value` (flat line scan, no YAML dep); `register(ctx)` registering the skill with a `Path` object (str raises AttributeError and silently disables the plugin).

- [ ] **Step 4: Run tests, confirm PASS**

- [ ] **Step 5: Commit**

```bash
git init && git checkout -b feature/build
git add .hermes-plugin tests skills docs
git commit -m "feat: software-team plugin skeleton with loud skill-tree lookup"
```

---

### Task 2: team.jsonc parsing and agent validation

**Files:**
- Create: `~/.hermes/plugins/software-team/.hermes-plugin/config.py`
- Create: `~/.hermes/plugins/software-team/tests/test_config.py`
- Create: `~/.hermes/plugins/software-team/tests/fixtures/valid.jsonc`, `invalid_reasoning.jsonc`, `missing_description.jsonc`, `broken.jsonc`, `renamed.jsonc`

**Interfaces:**
- Produces (Task 3, 5, 6 consume):
  - `parse_team_config(path: Path) -> dict` — regex comment-strip (`//...` and `/*...*/`, comment-aware) + `json.loads`; raises `TeamConfigError` with the offending line hint.
  - `validate_agents(raw: list[dict], providers: set[str]) -> tuple[list[dict], list[str]]` — returns (valid agents in order, warning strings). Checks: `name` charset regex, `description` non-empty str, `model` non-empty str, `provider` or `base_url` present, `reasoning` (if present) in `hermes_constants.VALID_REASONING_EFFORTS`, `provider` (if present) in `providers`, `enabled` (if present) is bool.
  - `known_providers() -> set[str]` — from `hermes_cli.config.load_config_readonly()`, keys of `config["providers"]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
import pathlib
from st_config import parse_team_config, validate_agents, TeamConfigError

FIX = pathlib.Path(__file__).parent / "fixtures"

def test_parse_strips_comments():
    cfg = parse_team_config(FIX / "valid.jsonc")
    assert "agents" in cfg and len(cfg["agents"]) == 2
    assert cfg["agents"][0]["name"] == "explore"

def test_parse_broken_json_raises():
    try:
        parse_team_config(FIX / "broken.jsonc")
        assert False
    except TeamConfigError:
        pass

def test_validate_rejects_bad_reasoning():
    raw = parse_team_config(FIX / "invalid_reasoning.jsonc")
    valid, warns = validate_agents(raw["agents"], {"api-yelsoft-online"})
    assert not valid
    assert any("reasoning" in w for w in warns)

def test_validate_requires_description():
    raw = parse_team_config(FIX / "missing_description.jsonc")
    valid, warns = validate_agents(raw["agents"], {"api-yelsoft-online"})
    assert not valid

def test_validate_rejects_unknown_provider():
    valid, warns = validate_agents(
        [{"name": "x", "description": "d", "model": "m", "provider": "ghost"}],
        {"api-yelsoft-online"},
    )
    assert not valid and any("provider" in w for w in warns)

def test_validate_drops_disabled_agents():
    valid, warns = validate_agents(
        [
            {"name": "on", "description": "d", "model": "m", "provider": "p"},
            {"name": "off", "description": "d", "model": "m", "provider": "p", "enabled": False},
        ],
        {"p"},
    )
    assert [a["name"] for a in valid] == ["on"]
```

- [ ] **Step 2: Run tests, confirm FAIL**

- [ ] **Step 3: Implement `config.py`**

Comment-strip regex must not eat `//` inside strings (strip only when outside quotes — simple state machine over chars, not one regex). `TeamConfigError(Exception)` with path + reason. Validation follows the store's required-field list (spec, Opus finding H1). `enabled: false` entries are dropped from the returned valid list (they produce no route and no roster entry).

- [ ] **Step 4: Run tests, confirm PASS**

- [ ] **Step 5: Commit** (`feat: team.jsonc JSONC parsing and agent validation`)

---

### Task 3: Route build + ownership-preserving sync via advanced-delegation store

**Files:**
- Create: `~/.hermes/plugins/software-team/.hermes-plugin/sync.py`
- Create: `~/.hermes/plugins/software-team/tests/test_sync.py`

**Interfaces:**
- Consumes: `validate_agents` output (Task 2).
- Produces (Task 5 consumes):
  - `load_store() -> module` — `importlib.util.spec_from_file_location` on `<plugins_dir>/advanced-delegation/store.py` (resolve `plugins_dir = Path(__file__).resolve().parents[2]`); raises RuntimeError if missing.
  - `build_routes(agents: list[dict]) -> list[dict]` — each `{"name": a["name"], "description": a["description"], "provider": a.get("provider"), "base_url": a.get("base_url"), "model": a["model"], "reasoning_effort": a.get("reasoning")}` (omitted keys left out).
  - `sync_routes(agents: list[dict], state_path: Path) -> dict` — summary `{"added": [...], "updated": [...], "removed": [...], "unchanged": bool}`. Logic: read current options via `store.routes(section)`; keep entries whose name NOT in state.json; upsert own entries; if identical to current → no write; else `store.save_routes(merged)` then `store.set_mode("model_map")` (order matters — spec, Opus M1); write state.json = own route names. Guarded by `threading.Lock`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sync.py
import pathlib, json, threading
import st_sync

def test_build_routes_maps_fields():
    routes = st_sync.build_routes([
        {"name": "explore", "description": "scan", "model": "gemini-3.1-flash-lite", "provider": "api-yelsoft-online"},
        {"name": "planner", "description": "plan", "model": "deepseek-v4-pro", "provider": "api-yelsoft-online", "reasoning": "max"},
    ])
    assert routes[0] == {"name": "explore", "description": "scan", "model": "gemini-3.1-flash-lite", "provider": "api-yelsoft-online"}
    assert routes[1]["reasoning_effort"] == "max" and "reasoning" not in routes[1]

def test_sync_preserves_foreign_routes(mocker):
    store = mocker.Mock()
    store.routes.return_value = [{"name": "handmade", "description": "x", "provider": "p", "model": "m"}]
    mocker.patch.object(st_sync, "load_store", return_value=store)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        sp = pathlib.Path(d) / "state.json"
        st_sync.sync_routes([{"name": "explore", "description": "s", "model": "m", "provider": "p"}], sp)
        merged = store.save_routes.call_args[0][0]
        names = [r["name"] for r in merged]
        assert names == ["handmade", "explore"]
        store.set_mode.assert_called_once_with("model_map")
        assert json.loads(sp.read_text()) == ["explore"]

def test_sync_removes_stale_own_route(mocker):
    store = mocker.Mock()
    store.routes.return_value = [
        {"name": "scout", "description": "old", "provider": "p", "model": "m"},
        {"name": "handmade", "description": "x", "provider": "p", "model": "m"},
    ]
    mocker.patch.object(st_sync, "load_store", return_value=store)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        sp = pathlib.Path(d) / "state.json"
        sp.write_text(json.dumps(["scout"]))
        st_sync.sync_routes([{"name": "explore", "description": "s", "model": "m", "provider": "p"}], sp)
        merged = store.save_routes.call_args[0][0]
        assert [r["name"] for r in merged] == ["handmade", "explore"]

def test_sync_noop_when_unchanged(mocker):
    store = mocker.Mock()
    store.routes.return_value = [{"name": "explore", "description": "s", "provider": "p", "model": "m"}]
    mocker.patch.object(st_sync, "load_store", return_value=store)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        sp = pathlib.Path(d) / "state.json"
        st_sync.sync_routes([{"name": "explore", "description": "s", "model": "m", "provider": "p"}], sp)
        store.save_routes.assert_not_called()
        store.set_mode.assert_not_called()
```

- [ ] **Step 2: Run tests, confirm FAIL**

- [ ] **Step 3: Implement `sync.py`**

`store.save_routes(routes: list[dict])` and `store.set_mode(mode: str)` signatures as used above (verify against advanced-delegation/store.py before finalizing — if signatures differ, adapt the tests to the real API, not the other way round). No-op path compares sorted route tuples of own+preserved set before writing.

- [ ] **Step 4: Run tests, confirm PASS**

- [ ] **Step 5: Commit** (`feat: ownership-preserving model_map route sync`)

---

### Task 4: max_parallel → delegation.max_concurrent_children (single-key write)

**Files:**
- Create: `~/.hermes/plugins/software-team/.hermes-plugin/concurrency.py`
- Create: `~/.hermes/plugins/software-team/tests/test_concurrency.py`

**Interfaces:**
- Consumes: `parse_team_config` (Task 2).
- Produces: `sync_concurrency(max_parallel: int | None) -> bool` — returns True if a write happened. Reads effective config, compares current `delegation.max_concurrent_children`; equal or missing `max_parallel` → no-op. Write via `hermes_cli.config.atomic_config_write` touching ONLY `delegation.max_concurrent_children`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_concurrency.py
import st_concurrency

def test_noop_when_equal(mocker):
    cfg = {"delegation": {"max_concurrent_children": 4}}
    mocker.patch("hermes_cli.config.load_config_readonly", return_value=cfg)
    write = mocker.patch("hermes_cli.config.atomic_config_write")
    assert st_concurrency.sync_concurrency(4) is False
    write.assert_not_called()

def test_writes_only_target_key(mocker, tmp_path):
    from pathlib import Path
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("delegation:\n  max_concurrent_children: 10\n  model: 'keep-me'\n  reasoning_effort: 'high'\n")
    cfg = {"delegation": {"max_concurrent_children": 10, "model": "keep-me", "reasoning_effort": "high"}}
    mocker.patch("hermes_cli.config.load_config_readonly", return_value=cfg)
    mocker.patch("hermes_cli.config.atomic_config_write", side_effect=lambda path, fn: fn(cfg))
    assert st_concurrency.sync_concurrency(4) is True
    assert cfg["delegation"] == {"max_concurrent_children": 4, "model": "keep-me", "reasoning_effort": "high"}
```

- [ ] **Step 2: Run tests, confirm FAIL**

- [ ] **Step 3: Implement `concurrency.py`**

Verify the real `atomic_config_write` signature (callback-based vs dict-based) in `hermes_cli/config.py` before implementing; tests above mock it, adapt the mock shape to the real signature.

- [ ] **Step 4: Run tests, confirm PASS**

- [ ] **Step 5: Commit** (`feat: single-key max_concurrent_children sync`)

---

### Task 5: pre_llm_call hook — roster injection + mtime-gated sync trigger

**Files:**
- Modify: `~/.hermes/plugins/software-team/.hermes-plugin/__init__.py`
- Create: `~/.hermes/plugins/software-team/.hermes-plugin/roster.py`
- Create: `~/.hermes/plugins/software-team/tests/test_hook.py`

**Interfaces:**
- Consumes: `validate_agents` (Task 2), `sync_routes` (Task 3), `sync_concurrency` (Task 4), `parse_team_config` (Task 2).
- Produces:
  - `build_roster(agents: list[dict]) -> str` — compact plain text: per agent `name — description (model@reasoning)`, plus 5-line protocol block (superpowers skills drive the workflow; dispatch per role; agent prompts go into child context; collect and verify results).
  - `register(ctx)` now registers the real hook: `def pre_llm_call(session_id=None, user_message=None, conversation_history=None, is_first_turn=None, model=None, platform=None, **kwargs)` → returns `None` when `not is_first_turn or platform == "subagent"`; otherwise runs the mtime-gated pipeline (parse → validate → sync routes + concurrency → build roster), caching by team.jsonc mtime in a module-level dict, and returns `{"context": roster}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hook.py
import importlib.util, pathlib, mocker
PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]

def _load():
    spec = importlib.util.spec_from_file_location("st_init", PLUGIN_DIR / ".hermes-plugin" / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def test_roster_under_1kb():
    mod = _load()
    agents = [
        {"name": n, "description": f"desc {n}", "model": f"m-{n}", "provider": "p", "reasoning": r}
        for n, r in zip(
            ["explore", "researcher", "consultant", "planner", "implementer", "reviewer", "debugger", "writer"],
            [None, "max", "high", "max", "high", "max", "max", "high"],
        )
    ]
    roster = mod.build_roster(agents)
    assert len(roster) <= 1024

def test_hook_skips_subagents_and_later_turns(mocker):
    mod = _load()
    hook = mod._make_hook() if hasattr(mod, "_make_hook") else None
    # fallback: call register and capture hook
    ctx = mocker.Mock()
    ctx.register_hook = mocker.Mock(side_effect=lambda name, fn: setattr(ctx, "hook", fn))
    mod.register(ctx)
    assert ctx.hook(is_first_turn=True, platform="subagent") is None
    assert ctx.hook(is_first_turn=False, platform="cli") is None

def test_hook_injects_roster_on_first_turn(mocker):
    mod = _load()
    mocker.patch.object(mod, "build_roster", return_value="ROSTER")
    mocker.patch.object(mod, "_pipeline", return_value="ROSTER")
    ctx = mocker.Mock()
    ctx.register_hook = mocker.Mock(side_effect=lambda name, fn: setattr(ctx, "hook", fn))
    mod.register(ctx)
    res = ctx.hook(is_first_turn=True, platform="cli")
    assert res == {"context": "ROSTER"}
```

- [ ] **Step 2: Run tests, confirm FAIL**

- [ ] **Step 3: Implement `roster.py` + hook wiring in `__init__.py`**

Keep the pipeline function (`_pipeline`) separate so tests can stub it. Sync failures inside the hook must degrade to a roster-only injection plus a warning line in the roster text (never raise out of the hook).

- [ ] **Step 4: Run tests, confirm PASS**

- [ ] **Step 5: Commit** (`feat: first-turn roster injection with mtime-gated sync`)

---

### Task 6: Template team.jsonc + first-run copy + state init

**Files:**
- Create: `~/.hermes/plugins/software-team/templates/team.jsonc`
- Modify: `~/.hermes/plugins/software-team/.hermes-plugin/__init__.py` (`ensure_user_config()`)
- Create: `~/.hermes/plugins/software-team/tests/test_ensure.py`

**Interfaces:**
- Produces: `ensure_user_config() -> tuple[Path, Path]` — returns (live team.jsonc path, state.json path): `~/.hermes/software-team/team.jsonc` and `~/.hermes/software-team/state.json`. Copies `templates/team.jsonc` if live file absent; initializes state.json to `[]` if absent; never overwrites existing files.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ensure.py
def test_template_has_eight_agents_with_doc_models():
    import pathlib, json
    tpl = pathlib.Path(__file__).resolve().parents[1] / "templates" / "team.jsonc"
    text = tpl.read_text()
    import re
    body = re.sub(r"//[^\n]*", "", text)
    cfg = json.loads(body)
    names = [a["name"] for a in cfg["agents"]]
    assert names == ["explore", "researcher", "consultant", "planner", "implementer", "reviewer", "debugger", "writer"]
    by_name = {a["name"]: a for a in cfg["agents"]}
    assert by_name["explore"]["model"] == "gemini-3.1-flash-lite" and "reasoning" not in by_name["explore"]
    assert by_name["planner"]["model"] == "deepseek-v4-pro" and by_name["planner"]["reasoning"] == "max"
    assert by_name["consultant"]["model"] == "cx/gpt-5.6-sol" and by_name["consultant"]["reasoning"] == "high"
    assert all(a["provider"] == "api-yelsoft-online" for a in cfg["agents"])

def test_ensure_copies_and_never_overwrites(mocker, tmp_path):
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location(
        "st_init", pathlib.Path(__file__).resolve().parents[1] / ".hermes-plugin" / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mocker.patch.object(mod, "LIVE_DIR", tmp_path)
    p1, p2 = mod.ensure_user_config()
    assert p1.exists() and p2.exists()
    p1.write_text("USER EDIT")
    p1b, _ = mod.ensure_user_config()
    assert p1b.read_text() == "USER EDIT"
```

- [ ] **Step 2: Run tests, confirm FAIL**

- [ ] **Step 3: Implement template + `ensure_user_config()`**

Template content: JSONC with the 8-agent table from the spec's model mapping (exact model ids, reasoning values; explore has NO reasoning field), `max_parallel: 4`, top comment explaining the file (Turkish, short) and the reasoning vocabulary. `LIVE_DIR` = `Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "software-team"` — keep as module constant so tests can patch.

- [ ] **Step 4: Run tests, confirm PASS**

- [ ] **Step 5: Commit** (`feat: default team template with first-run copy`)

---

### Task 7: team-protocol SKILL.md content + README

**Files:**
- Modify: `~/.hermes/plugins/software-team/skills/team-protocol/SKILL.md` (real content)
- Create: `~/.hermes/plugins/software-team/README.md`
- Create: `~/.hermes/plugins/software-team/tests/test_skill.py`

**Interfaces:** none (content task).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_skill.py
def test_skill_frontmatter_and_sections():
    import pathlib
    p = pathlib.Path(__file__).resolve().parents[1] / "skills" / "team-protocol" / "SKILL.md"
    text = p.read_text()
    assert text.startswith("---\nname: team-protocol\n")
    assert "description:" in text[:200]
    for needle in ["Orkestratör", "explore", "implementer", "reviewer", "delegate_task", "doğrulama"]:
        assert needle in text
```

- [ ] **Step 2: Run tests, confirm FAIL** (placeholder lacks sections)

- [ ] **Step 3: Write the skill content**

Turkish, ~80-120 lines: role→work mapping table (which superpowers workflow phase uses which role), dispatch rules (fresh child context built by orchestrator; include the role's prompt from team.jsonc in the child's goal/context; never assume the child shares your context), result collection + verification (superpowers:verification-before-completion), fallback rules (unrouted tasks stay with the orchestrator). README: install/usage/team.jsonc reference, Turkish.

- [ ] **Step 4: Run tests, confirm PASS**

- [ ] **Step 5: Commit** (`docs: team protocol skill and README`)

---

### Task 8: Live verification — plugin loads, syncs routes, injects roster

**Files:** none new (verification task; only docs/tests touched if fixes are needed).

- [ ] **Step 1: Prove the plugin loads in the real install**

Run: `hermes plugins list`
Expected: `software-team` listed with status enabled, no load errors.

- [ ] **Step 2: Prove the sync established the routes and backend**

Run: `hermes delegation config --show`
Expected: mode `Model routes (model_map)`; options contain exactly the 8 agent route names with provider `api-yelsoft-online`; `max_concurrent_children: 4`; `default` route absent.

- [ ] **Step 3: Prove a foreign route survives a resync**

Run: `hermes delegation config` (add one test route manually, e.g. `manual-test`), then start a new session (or trigger the hook), then `hermes delegation config --show`.
Expected: `manual-test` still present alongside the 8 team routes. Remove `manual-test` afterwards.

- [ ] **Step 4: Prove injection is live and subagents are clean**

Start a new Hermes session (or a fresh first turn) and confirm the roster text appears in the first-turn context; then spawn one delegate_task child and confirm its context contains no roster (child transcript first turn).

- [ ] **Step 5: Commit any fixes + final commit**

```bash
git add -A && git commit -m "chore: live verification fixes"
```

---

## Self-review notes (run after writing, fix inline)

- Spec coverage: all builder-leftover bullets map to Tasks 1-8 (layout→1, config lifecycle→6, JSONC+validation→2, sync semantics+ownership+race→3, concurrency→4, injection format/budget→5, skill content→7, live proof→8). Review Focus items 1-5 pinned in Tasks 2, 3, 3, 6/5, 5 respectively.
- Type consistency: `validate_agents` returns `(valid, warns)` everywhere; `sync_routes(agents, state_path)` signature consistent across Tasks 3 and 5; `build_roster(agents)` consistent.
- Proportion: plan is shorter than the spec+reviews it implements; bodies left to implementers except where the design pins them (model table, field lists, ordering).
