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
