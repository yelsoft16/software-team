"""Expose ``.hermes-plugin/config.py`` to tests as the top-level module ``st_config``.

The plugin ships the file as ``config.py`` (loaded by Hermes from the plugin dir), while the
task brief's tests import it as ``st_config``. Loading it through importlib under that name
avoids putting ``.hermes-plugin`` on ``sys.path``, where a bare ``config`` module could
shadow an unrelated top-level module.
"""

import importlib.util
import pathlib
import sys

_CONFIG_PATH = pathlib.Path(__file__).resolve().parents[1] / ".hermes-plugin" / "config.py"
_spec = importlib.util.spec_from_file_location("st_config", _CONFIG_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover - only if the file vanished
    raise ImportError(f"cannot load {_CONFIG_PATH}")
_module = importlib.util.module_from_spec(_spec)
sys.modules["st_config"] = _module  # before exec: dataclasses/pickle look the module up
_spec.loader.exec_module(_module)
