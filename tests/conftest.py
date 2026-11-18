"""Expose ``.hermes-plugin/*.py`` to tests as top-level modules ``st_*``.

The plugin ships the files as ``config.py`` / ``sync.py`` / ``concurrency.py`` (loaded by
Hermes from the plugin dir), while the task briefs' tests import them as ``st_config`` /
``st_sync`` / ``st_concurrency``. Loading them through importlib under those names avoids
putting ``.hermes-plugin`` on ``sys.path``, where a bare ``config`` module could shadow an
unrelated top-level module.
"""

import importlib.util
import pathlib
import sys

_PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1] / ".hermes-plugin"


def _load(module_name: str, filename: str) -> None:
    path = _PLUGIN_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - only if the file vanished
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # before exec: dataclasses/pickle look the module up
    spec.loader.exec_module(module)


for _name, _filename in (
    ("st_config", "config.py"),
    ("st_sync", "sync.py"),
    ("st_concurrency", "concurrency.py"),
):
    _load(_name, _filename)
del _name, _filename
