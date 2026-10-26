"""An un-sandboxed test run must not rewrite the user's real settings file.

Measured 2026-10-26: the settings/gallery suites ran against the host XDG (the
sandbox redirected ``XDG_DATA_HOME`` only) and the live
``~/.config/BlinkTable/BlinkTable.conf`` lost its ``[image_gallery_ai]`` group —
the app then asked for an API key that was still in the keyring.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from plugins.settings.manager import _refuse_test_write_to_live_config


def _settings(path: str):
    return SimpleNamespace(fileName=lambda: path)


def test_it_refuses_a_write_outside_the_sandboxed_config_root(monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "probe")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    with pytest.raises(RuntimeError, match="refusing to write the real settings file"):
        _refuse_test_write_to_live_config(
            _settings(os.path.expanduser("~/.config/BlinkTable/BlinkTable.conf"))
        )


def test_it_allows_a_write_inside_the_sandboxed_config_root(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "probe")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _refuse_test_write_to_live_config(_settings(str(tmp_path / "BlinkTable/BlinkTable.conf")))


def test_production_is_untouched(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    _refuse_test_write_to_live_config(_settings("/home/someone/.config/x/y.conf"))
