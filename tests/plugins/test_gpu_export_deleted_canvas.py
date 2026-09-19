"""GPU export survives canvas deletion (shiboken race, no traceback spam)."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from plugins.export.services import gpu_export_proxy as proxy_mod
from plugins.export.services.gpu_export_proxy import (
    GpuExportProxy,
    _CanvasGoneError,
    _widget_alive,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _proxy(qapp):
    p = GpuExportProxy()
    qapp.processEvents()
    return p


def test_ensure_widget_drops_deleted_cache_and_recreates(qapp, monkeypatch):
    from unittest.mock import MagicMock

    p = _proxy(qapp)
    dead, fresh = SimpleNamespace(name="dead"), MagicMock(name="fresh")
    monkeypatch.setattr(proxy_mod.sip, "isValid", lambda w: w is fresh)
    monkeypatch.setattr(proxy_mod, "create_canvas_widget", lambda: fresh)
    monkeypatch.setattr(proxy_mod, "configure_offscreen_widget", lambda w: None)
    monkeypatch.setattr(proxy_mod, "show_offscreen_widget", lambda w: None)
    p._widget = dead
    try:
        assert p._ensure_widget() is fresh
        assert p._widget is fresh
    finally:
        p.shutdown()


def test_ensure_widget_dead_cache_no_provider_skips(qapp, monkeypatch):
    p = _proxy(qapp)
    monkeypatch.setattr(proxy_mod.sip, "isValid", lambda w: False)
    monkeypatch.setattr(proxy_mod, "create_canvas_widget", lambda: None)
    p._widget = SimpleNamespace(name="dead")
    try:
        assert p._ensure_widget() is None
        assert p._widget is None
    finally:
        p.shutdown()


def test_render_plan_frame_dead_widget_never_touches_rhi(qapp, monkeypatch):
    p = _proxy(qapp)
    monkeypatch.setattr(proxy_mod.sip, "isValid", lambda w: False)
    dead = SimpleNamespace(name="dead")  # no .rhi attr: AttributeError if reached
    plan = SimpleNamespace(canvas_w=64, canvas_h=64)
    try:
        with pytest.raises(_CanvasGoneError):
            p._render_plan_frame(dead, plan, SimpleNamespace(), {}, store=None)
    finally:
        p.shutdown()


def test_render_on_main_thread_routes_quiet_abort(qapp, monkeypatch, caplog):
    p = _proxy(qapp)
    sentinel = SimpleNamespace(name="canvas")
    monkeypatch.setattr(proxy_mod, "_widget_alive", lambda w: True)
    monkeypatch.setattr(proxy_mod.GpuExportProxy, "_ensure_widget", lambda self: sentinel)
    boom = _CanvasGoneError("canvas widget deleted during export grab: gone")

    def _raise(self, widget, plan, diff_image, timings, store=None):
        raise boom

    monkeypatch.setattr(proxy_mod.GpuExportProxy, "_render_plan_frame", _raise)
    box: dict = {}
    payload = {"mode": "render_plan", "plan": SimpleNamespace(), "result_box": box}
    try:
        with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
            p._render_on_main_thread(payload)
    finally:
        p.shutdown()
    assert box["error"] is boom
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_widget_alive_fail_open(monkeypatch):
    # NOTE: real shiboken6.isValid duck-types unknown objects as valid —
    # the probe only ever sees real QObjects in production.
    monkeypatch.setattr(proxy_mod.sip, "isValid", lambda w: False)
    assert _widget_alive(None) is False
    assert _widget_alive(SimpleNamespace()) is False
    monkeypatch.setattr(
        proxy_mod.sip, "isValid", lambda w: (_ for _ in ()).throw(RuntimeError("gone"))
    )
    assert _widget_alive(SimpleNamespace()) is False
