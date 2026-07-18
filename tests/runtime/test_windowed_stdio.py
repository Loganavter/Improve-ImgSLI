"""Windowed PyInstaller leaves sys.stderr as None; faulthandler must not crash."""

from __future__ import annotations

import faulthandler
import sys

import pytest

from core.windowed_stdio import enable_faulthandler, ensure_stdio


def test_faulthandler_raises_when_stderr_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stderr", None)
    with pytest.raises(RuntimeError, match="stderr is None"):
        faulthandler.enable()


def test_ensure_stdio_allows_faulthandler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", None)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    ensure_stdio()
    assert sys.stdin is not None
    assert sys.stdout is not None
    assert sys.stderr is not None

    enable_faulthandler()
