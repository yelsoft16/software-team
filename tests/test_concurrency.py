"""Tests for the single-key ``delegation.max_concurrent_children`` sync.

Core's writer is dict-based — ``atomic_config_write(config_path, data)`` — not the callback
shape sketched in the plan, so these mocks capture the document it is handed.
"""

import pytest

import st_concurrency

BASE = """\
delegation:
  max_concurrent_children: 10
  model: 'keep-me'  # keep
  provider: 'p'
  reasoning_effort: 'high'
providers:
  x: {}
"""


def test_noop_when_equal(mocker):
    cfg = {"delegation": {"max_concurrent_children": 4}}
    mocker.patch("hermes_cli.config.load_config_readonly", return_value=cfg)
    write = mocker.patch("hermes_cli.config.atomic_config_write")
    assert st_concurrency.sync_concurrency(4) is False
    write.assert_not_called()


def test_noop_when_missing_max_parallel(mocker):
    load = mocker.patch("hermes_cli.config.load_config_readonly")
    write = mocker.patch("hermes_cli.config.atomic_config_write")
    assert st_concurrency.sync_concurrency(None) is False
    load.assert_not_called()
    write.assert_not_called()


def test_writes_only_target_key(mocker, tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(BASE)
    cfg = {
        "delegation": {
            "max_concurrent_children": 10,
            "model": "keep-me",
            "provider": "p",
            "reasoning_effort": "high",
        },
        "providers": {"x": {}},
    }
    mocker.patch("hermes_cli.config.get_config_path", return_value=cfg_file)
    mocker.patch("hermes_cli.config.load_config_readonly", return_value=cfg)
    write = mocker.patch("hermes_cli.config.atomic_config_write")
    assert st_concurrency.sync_concurrency(4) is True
    path, data = write.call_args.args
    assert path == cfg_file
    assert data["delegation"] == {
        "max_concurrent_children": 4,
        "model": "keep-me",
        "provider": "p",
        "reasoning_effort": "high",
    }
    assert data["providers"] == {"x": {}}


# --- guards the brief's tests do not cover -------------------------------------------


def test_real_write_keeps_siblings_comments_and_is_idempotent(tmp_path, monkeypatch):
    """End-to-end against a tmp config: only the one key changes, then a re-sync is a no-op."""
    hc = pytest.importorskip("hermes_cli.config")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(BASE)
    monkeypatch.setattr(hc, "get_config_path", lambda: cfg_file)
    monkeypatch.setattr(hc, "load_config_readonly", lambda: hc.read_user_config_raw(cfg_file))

    assert st_concurrency.sync_concurrency(4) is True
    text = cfg_file.read_text()
    assert "max_concurrent_children: 4" in text
    assert "# keep" in text
    assert hc.read_user_config_raw(cfg_file) == {
        "delegation": {
            "max_concurrent_children": 4,
            "model": "keep-me",
            "provider": "p",
            "reasoning_effort": "high",
        },
        "providers": {"x": {}},
    }
    assert st_concurrency.sync_concurrency(4) is False


def test_adds_key_without_dropping_other_delegation_keys(tmp_path, monkeypatch):
    hc = pytest.importorskip("hermes_cli.config")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("delegation:\n  model: 'keep-me'\n")
    monkeypatch.setattr(hc, "get_config_path", lambda: cfg_file)
    monkeypatch.setattr(hc, "load_config_readonly", lambda: hc.read_user_config_raw(cfg_file))

    assert st_concurrency.sync_concurrency(4) is True
    assert hc.read_user_config_raw(cfg_file) == {
        "delegation": {"model": "keep-me", "max_concurrent_children": 4}
    }


def test_creates_delegation_section_when_absent(tmp_path, monkeypatch):
    hc = pytest.importorskip("hermes_cli.config")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("providers:\n  x: {}\n")
    monkeypatch.setattr(hc, "get_config_path", lambda: cfg_file)
    monkeypatch.setattr(hc, "load_config_readonly", lambda: hc.read_user_config_raw(cfg_file))

    assert st_concurrency.sync_concurrency(4) is True
    assert hc.read_user_config_raw(cfg_file) == {
        "providers": {"x": {}},
        "delegation": {"max_concurrent_children": 4},
    }


def test_rejects_non_integer_max_parallel():
    with pytest.raises(ValueError, match="max_parallel"):
        st_concurrency.sync_concurrency("4")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="max_parallel"):
        st_concurrency.sync_concurrency(True)  # bool is not a count
