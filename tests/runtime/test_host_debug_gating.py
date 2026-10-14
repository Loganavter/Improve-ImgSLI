"""Host-UI env-gated debug streams: silent without their flag, loud with it.

Regression guard for the logging-hygiene rule in ``docs/dev/LOGGING.md``:
a noisy subsystem's debug stream must NOT be wired to the global
``debug_mode_enabled`` switch. Each host stream is completely silent unless
its own ``IMGSLI_*_DEBUG`` flag is set (``UI_NAV_DEBUG`` for navigation),
so a persisted ``debug_mode_enabled=true`` cannot turn the log into white
noise.

See ``src/ui/host_debug.py`` and ``src/core/nav_debug.py``.
"""

from __future__ import annotations

import logging

import pytest

import ui.host_debug as host_debug
from core.nav_debug import nav_debug

# (flag, prefix, emit) — one row per gated stream.
_STREAMS = [
    (
        "IMGSLI_TRANSIENT_DEBUG",
        "[transient]",
        lambda: host_debug.transient_debug("resolved %s", "svc"),
    ),
    (
        "IMGSLI_TRANSIENT_DEBUG",
        "[transient-close]",
        lambda: host_debug.transient_close_debug("hide reason=%s", "x"),
    ),
    ("IMGSLI_CTX_MENU_DEBUG", "[ctx-menu]", lambda: host_debug.ctx_menu_debug("open")),
    (
        "IMGSLI_WORKSPACE_DEBUG",
        "[workspace-transition]",
        lambda: host_debug.workspace_transition_debug("cover"),
    ),
    ("IMGSLI_LAYOUT_DEBUG", "[layout-tree]", lambda: host_debug.layout_tree_debug("tree")),
    ("IMGSLI_STARTUP_DEBUG", "[startup]", lambda: host_debug.startup_debug("step")),
    ("IMGSLI_RHI_PRIMER_DEBUG", "[rhi-primer]", lambda: host_debug.rhi_primer_debug("done")),
    (
        "IMGSLI_SCROLL_VALUE_DEBUG",
        "[scroll-value]",
        lambda: host_debug.scroll_value_debug("wheel delta=%s", 1),
    ),
]

_IDS = [row[1] for row in _STREAMS]


def _messages(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records]


@pytest.mark.parametrize("flag,prefix,emit", _STREAMS, ids=_IDS)
def test_stream_silent_without_flag(monkeypatch, caplog, flag, prefix, emit):
    monkeypatch.delenv(flag, raising=False)
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        emit()
    assert not any(prefix in msg for msg in _messages(caplog)), (
        f"{prefix} leaked while {flag} was unset — a noisy stream must not be "
        "wired to the global debug switch"
    )


@pytest.mark.parametrize("flag,prefix,emit", _STREAMS, ids=_IDS)
def test_stream_emits_with_flag(monkeypatch, caplog, flag, prefix, emit):
    monkeypatch.setenv(flag, "1")
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        emit()
    matching = [msg for msg in _messages(caplog) if prefix in msg]
    assert matching, f"{prefix} did not print with {flag}=1"
    # Hybrid emit: explicit flag => WARNING, visible without --debug.
    assert all(record.levelno >= logging.WARNING for record in caplog.records if prefix in record.getMessage())


def test_enabled_predicates_track_env(monkeypatch):
    monkeypatch.delenv("IMGSLI_LAYOUT_DEBUG", raising=False)
    assert host_debug.layout_tree_debug_enabled() is False
    assert host_debug.startup_debug_enabled() is False
    monkeypatch.setenv("IMGSLI_LAYOUT_DEBUG", "yes")
    monkeypatch.setenv("IMGSLI_STARTUP_DEBUG", "on")
    assert host_debug.layout_tree_debug_enabled() is True
    assert host_debug.startup_debug_enabled() is True
    # Falsy spellings stay off (permissive env_flag semantics).
    monkeypatch.setenv("IMGSLI_LAYOUT_DEBUG", "0")
    assert host_debug.layout_tree_debug_enabled() is False


def test_nav_debug_reuses_ui_nav_flag(monkeypatch, caplog):
    monkeypatch.delenv("UI_NAV_DEBUG", raising=False)
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        nav_debug("[nav-card] navigate key=%s", 1)
    assert not any("[nav-card]" in msg for msg in _messages(caplog))

    caplog.clear()
    monkeypatch.setenv("UI_NAV_DEBUG", "1")
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        nav_debug("[nav-card] navigate key=%s", 1)
    assert any("[nav-card]" in msg for msg in _messages(caplog))
