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
    store.route_default.return_value = "handmade"
    mocker.patch.object(st_sync, "load_store", return_value=store)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        sp = pathlib.Path(d) / "state.json"
        st_sync.sync_routes([{"name": "explore", "description": "s", "model": "m", "provider": "p"}], sp)
        merged = store.save_routes.call_args[0][0]
        names = [r["name"] for r in merged]
        assert names == ["handmade", "explore"]
        assert store.save_routes.call_args[0][1] == "handmade"  # user-set default passed through, never wiped
        store.set_mode.assert_called_once_with("model_map")
        assert json.loads(sp.read_text()) == ["explore"]


def test_sync_removes_stale_own_route(mocker):
    store = mocker.Mock()
    store.routes.return_value = [
        {"name": "scout", "description": "old", "provider": "p", "model": "m"},
        {"name": "handmade", "description": "x", "provider": "p", "model": "m"},
    ]
    store.route_default.return_value = ""  # absent default stays unset (never written)
    mocker.patch.object(st_sync, "load_store", return_value=store)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        sp = pathlib.Path(d) / "state.json"
        sp.write_text(json.dumps(["scout"]))
        st_sync.sync_routes([{"name": "explore", "description": "s", "model": "m", "provider": "p"}], sp)
        merged = store.save_routes.call_args[0][0]
        assert [r["name"] for r in merged] == ["handmade", "explore"]
        assert store.save_routes.call_args[0][1] == ""


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


def test_sync_skips_nameless_foreign_entry(mocker):
    store = mocker.Mock()
    store.routes.return_value = [
        {"description": "corrupted, no name", "model": "m"},
        {"name": "handmade", "description": "x", "provider": "p", "model": "m"},
    ]
    store.route_default.return_value = ""
    mocker.patch.object(st_sync, "load_store", return_value=store)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        sp = pathlib.Path(d) / "state.json"
        summary = st_sync.sync_routes(
            [{"name": "explore", "description": "s", "model": "m", "provider": "p"}], sp)
        merged = store.save_routes.call_args[0][0]
        # Nameless entry left untouched (never owned, never deleted)…
        assert merged[0] == {"description": "corrupted, no name", "model": "m"}
        # …other foreign routes preserved, desired routes appended.
        assert [r.get("name") for r in merged] == [None, "handmade", "explore"]
        assert summary["skipped_nameless"] == 1
        assert summary["warning"]


def test_route_key_handles_unorderable_values():
    # dict vs list at the same sorted position: pre-fix, tuple comparison
    # short-circuits into `dict < list` and raises TypeError.
    routes = [
        {"name": "handmade", "description": "x", "model": "m", "extra": {"k": "v"}},
        {"name": "typed", "description": "x", "model": "m", "extra": ["a"]},
    ]
    key = st_sync._route_key(routes)
    assert key == st_sync._route_key(list(reversed(routes)))  # order-insensitive


def test_sync_foreign_route_with_list_value_does_not_raise(mocker):
    store = mocker.Mock()
    store.routes.return_value = [
        {"name": "handmade", "description": "x", "model": "m", "tags": ["a", "b"]},
        {"name": "typed", "description": "x", "model": "m", "meta": {"k": "v"}},
    ]
    store.route_default.return_value = ""
    mocker.patch.object(st_sync, "load_store", return_value=store)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        sp = pathlib.Path(d) / "state.json"
        st_sync.sync_routes([{"name": "explore", "description": "s", "model": "m", "provider": "p"}], sp)
        merged = store.save_routes.call_args[0][0]
        assert [r["name"] for r in merged] == ["handmade", "typed", "explore"]
        assert merged[0]["tags"] == ["a", "b"] and merged[1]["meta"] == {"k": "v"}
    # Serialization-based key stays order-insensitive with nested values.
    routes = store.routes.return_value
    assert st_sync._route_key(routes) == st_sync._route_key(list(reversed(routes)))


def test_sync_saves_9th_qa_route_with_model_and_reasoning(mocker):
    # pin: the 9-agent team (qa as 9th) flows through route sync with its
    # model and reasoning resolved — qa = mimo-v2.6-flash @ high (owner decision).
    store = mocker.Mock()
    store.routes.return_value = []
    store.route_default.return_value = ""
    mocker.patch.object(st_sync, "load_store", return_value=store)
    agents = [
        {"name": n, "description": f"desc {n}", "model": f"m-{n}", "provider": "p", "reasoning": r}
        for n, r in zip(
            ["explore", "researcher", "consultant", "planner", "implementer", "reviewer", "debugger", "writer"],
            [None, "max", "high", "max", "high", "max", "max", "high"],
        )
    ]
    agents.append({"name": "qa", "description": "QA icrasisi", "model": "mimo-v2.6-flash",
                   "provider": "p", "reasoning": "high"})
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        sp = pathlib.Path(d) / "state.json"
        summary = st_sync.sync_routes(agents, sp)
        merged = store.save_routes.call_args[0][0]
        assert [r["name"] for r in merged] == [a["name"] for a in agents]
        assert "qa" in summary["added"]
        qa = next(r for r in merged if r["name"] == "qa")
        assert qa["model"] == "mimo-v2.6-flash"
        assert qa["reasoning_effort"] == "high" and "reasoning" not in qa
        assert json.loads(sp.read_text()) == [a["name"] for a in agents]
        store.set_mode.assert_called_once_with("model_map")


def test_sync_saves_routes_before_setting_mode(mocker):
    store = mocker.Mock()
    store.routes.return_value = []
    store.route_default.return_value = ""
    calls = mocker.Mock()
    calls.attach_mock(store.save_routes, "save_routes")
    calls.attach_mock(store.set_mode, "set_mode")
    mocker.patch.object(st_sync, "load_store", return_value=store)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        sp = pathlib.Path(d) / "state.json"
        st_sync.sync_routes([{"name": "explore", "description": "s", "model": "m", "provider": "p"}], sp)
    assert [call[0] for call in calls.mock_calls] == ["save_routes", "set_mode"]
