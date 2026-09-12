"""Viewport restore goes through Dispatcher and re-syncs the toolbar.

Regression coverage for session_persistence.py:

* ``restore_viewport_block`` with ``include_file_names_in_saved=True`` must
  dispatch ``SetIncludeFileNamesInSavedAction`` (never bare ``setattr`` on
  the attached viewport — the old ``setattr`` fallbacks routed around the
  no-direct-mutation AST dogma, which scans ``Assign`` but not ``setattr``).
* When the dispatcher is not yet bound the restore must schedule a
  ``QTimer.singleShot`` retry (defer) rather than mutating.
* ``refresh_filename_overlay_toolbar`` must drive the toolbar control to the
  Store value via the existing sync mechanism and never raise.
"""

from __future__ import annotations

import contextlib
import inspect
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.store_viewport import RenderConfig, SessionData, ViewState, ViewportState
from tabs.image_compare import session_persistence
from tabs.image_compare.session_persistence import (
    refresh_filename_overlay_toolbar,
    restore_viewport_block,
    serialize_viewport_block,
)


class _FakeDispatcher:
    """Minimal dispatcher: captures actions, projects via the real reducers."""

    def __init__(self, viewport):
        self.viewport = viewport
        self.actions = []

    def dispatch(self, action, scope="viewport"):
        from tabs.image_compare.state.reducers import (
            ImageRenderConfigReducer,
            ImageSessionReducer,
        )

        self.actions.append(action)
        new_cfg = ImageRenderConfigReducer.reduce(self.viewport.render_config, action)
        if new_cfg is not self.viewport.render_config:
            self.viewport.render_config = new_cfg
        image_state = getattr(self.viewport.session_data, "image_state", None)
        if image_state is not None:
            new_image_state = ImageSessionReducer.reduce(image_state, action)
            if new_image_state is not image_state:
                self.viewport.session_data.image_state = new_image_state


class _FakeDispatchStore:
    def __init__(self, viewport):
        self.viewport = viewport
        self._dispatcher = _FakeDispatcher(viewport)

    def get_dispatcher(self):
        return self._dispatcher

    @contextlib.contextmanager
    def batch_changes(self):
        yield


class _RecordingViewport:
    """Viewport proxy whose ``__setattr__`` records (never silently mutates)."""

    def __init__(self, real):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "writes", [])

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_real"), name)

    def __setattr__(self, name, value):
        object.__getattribute__(self, "writes").append(name)
        setattr(object.__getattribute__(self, "_real"), name, value)


def _source_viewport():
    from tabs.image_compare.state.models import ImageSessionState

    return ViewportState(
        render_config=RenderConfig(
            include_file_names_in_saved=True, font_size_percent=140
        ),
        view_state=ViewState(split_position=0.33),
        session_data=SessionData(
            image_state=ImageSessionState(
                auto_calculate_psnr=True, auto_calculate_ssim=True
            )
        ),
    )


def _fresh_viewport():
    from tabs.image_compare.state.models import ImageSessionState

    return ViewportState(
        session_data=SessionData(image_state=ImageSessionState())
    )


def test_restore_dispatches_include_file_names_without_viewport_setattr():
    blob = serialize_viewport_block(_source_viewport())
    real = _fresh_viewport()
    proxy = _RecordingViewport(real)
    store = _FakeDispatchStore(real)
    # Production reads through the proxy; the fake projects onto the real
    # viewport, so any production-side setattr on the viewport is recorded.
    store.viewport = proxy

    restore_viewport_block(proxy, blob, store)

    kinds = [type(a).__name__ for a in store._dispatcher.actions]
    assert "SetIncludeFileNamesInSavedAction" in kinds
    assert "SetFontSizePercentAction" in kinds
    assert "SetAutoCalculatePsnrAction" in kinds
    assert "SetAutoCalculateSsimAction" in kinds
    assert real.render_config.include_file_names_in_saved is True
    assert real.render_config.font_size_percent == 140
    assert real.session_data.image_state.auto_calculate_psnr is True
    assert real.session_data.image_state.auto_calculate_ssim is True
    # Scoped to the changed paths: the dispatch restores above must not
    # setattr render_config/image_state on the attached viewport. (Other
    # restore sub-paths — view_state Assigns, canvas feature write_snapshot
    # — are separate systems outside this task's scope.)
    forbidden = {"render_config", "image_state"}
    assert not (set(proxy.writes) & forbidden), proxy.writes


def test_missing_dispatcher_defers_instead_of_mutating(monkeypatch):
    blob = serialize_viewport_block(_source_viewport())
    # Scope to the changed paths: feature_settings/magnifier restores go
    # through the canvas property system (a separate, out-of-scope writer
    # that mutates regardless of dispatcher and varies with which features
    # other test modules have registered). The render_config/image_state
    # dispatch-or-defer paths under test see only their own keys.
    data = {
        "render_config": blob.get("render_config"),
        "image_state": blob.get("image_state"),
    }
    viewport = _fresh_viewport()
    scheduled = []

    class _FakeTimer:
        @staticmethod
        def singleShot(msec, fn):
            scheduled.append((msec, fn))

    monkeypatch.setattr(session_persistence, "QTimer", _FakeTimer)
    store = SimpleNamespace(
        viewport=viewport, get_dispatcher=lambda: None,
    )

    restore_viewport_block(viewport, data, store)

    assert scheduled, "expected a QTimer.singleShot retry, not a mutation"
    assert viewport.render_config.include_file_names_in_saved is False
    assert viewport.render_config.font_size_percent == 120
    assert viewport.session_data.image_state.auto_calculate_psnr is False
    assert viewport.session_data.image_state.auto_calculate_ssim is False


class _MockCheckControl:
    def __init__(self, checked=False):
        self._checked = checked
        self.calls = []

    def isChecked(self):
        return self._checked

    def setChecked(self, checked, emit_signal=True):
        self.calls.append((bool(checked), emit_signal))
        self._checked = bool(checked)

    def setToolTip(self, text):
        self.calls.append(("tooltip", text))


def _toolbar_presenter(flag, checked):
    control = _MockCheckControl(checked=checked)
    store = SimpleNamespace(
        viewport=SimpleNamespace(
            render_config=SimpleNamespace(include_file_names_in_saved=flag),
            view_state=SimpleNamespace(movement_speed_per_sec=2.0),
        ),
        settings=SimpleNamespace(current_language="en"),
    )
    presenter = SimpleNamespace(
        store=store,
        widget=SimpleNamespace(btn_file_names=control),
    )
    return presenter, control


def test_refresh_toolbar_drives_control_to_store_value():
    presenter, control = _toolbar_presenter(True, False)
    refresh_filename_overlay_toolbar(presenter.store, presenter)
    assert control.isChecked() is True
    assert any(
        isinstance(c, tuple) and c == (True, False) for c in control.calls
    ), control.calls

    presenter, control = _toolbar_presenter(False, True)
    refresh_filename_overlay_toolbar(presenter.store, presenter)
    assert control.isChecked() is False


def test_refresh_toolbar_never_raises_on_partial_inputs():
    refresh_filename_overlay_toolbar(None)
    refresh_filename_overlay_toolbar(None, None)
    refresh_filename_overlay_toolbar(SimpleNamespace(), None)
    refresh_filename_overlay_toolbar(SimpleNamespace(viewport=None), None)
    refresh_filename_overlay_toolbar(
        SimpleNamespace(viewport=SimpleNamespace()), SimpleNamespace()
    )
    refresh_filename_overlay_toolbar(
        SimpleNamespace(viewport=SimpleNamespace()),
        SimpleNamespace(store=None, widget=None),
    )


def test_refresh_toolbar_signature():
    params = inspect.signature(refresh_filename_overlay_toolbar).parameters
    assert list(params) == ["store", "presenter"]
    assert params["presenter"].default is None
