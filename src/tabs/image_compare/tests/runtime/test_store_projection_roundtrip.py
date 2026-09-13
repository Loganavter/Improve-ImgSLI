"""Store->widget projection roundtrip: dispatch must land on every projection.

Behavioral pair of tests/contracts/test_store_projection_symmetry_contracts.py
(static branch symmetry). Uses image_compare as the concrete example of the
shared mechanism (TESTING.md ownership: imports tabs.image_compare, so it
lives here, not in tests/).

Covers the restart desync: Store include_file_names_in_saved=True while the
toolbar button stays unchecked (panel follows the Store, button does not).
SimpleNamespace over MagicMock; no Store mock (a scoped fake viewport is
the Store slice under test).
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_compare.use_cases.chrome_sync import ImageCompareChromeSync


class _CheckControl:
    def __init__(self, checked=False):
        self._checked = bool(checked)

    def isChecked(self):
        return self._checked

    def setChecked(self, checked, emit_signal=True):
        self._checked = bool(checked)

    def setToolTip(self, text):
        pass

    def setVisualIconOverride(self, icon):
        pass

    def setEnabled(self, enabled):
        pass


def _build_sync(*, flag: bool, btn_checked: bool, visible: bool):
    toggled: list[bool] = []
    batches: list[list] = []
    btn = _CheckControl(checked=btn_checked)
    widget = SimpleNamespace(
        toggle_edit_layout_visibility=lambda v: toggled.append(bool(v)),
        window=lambda: SimpleNamespace(ui=SimpleNamespace(workspace_stack=None)),
        isVisible=lambda: visible,
        btn_file_names=btn,
    )
    store = SimpleNamespace(
        viewport=SimpleNamespace(
            render_config=SimpleNamespace(include_file_names_in_saved=flag),
            session_data=SimpleNamespace(
                image_state=SimpleNamespace(image1=None, image2=None)
            ),
        ),
        state_changed=SimpleNamespace(connect=lambda cb: None),
    )

    def _toolbar_presenter(wp):
        tbtn = btn
        tstore = store

        def _sync():
            tbtn.setChecked(
                bool(tstore.viewport.render_config.include_file_names_in_saved),
                emit_signal=False,
            )

        return SimpleNamespace(update_toolbar_states=_sync)

    wp = SimpleNamespace(
        ui_batcher=SimpleNamespace(
            schedule_batch_update=lambda batch: batches.append(list(batch))
        ),
    )
    sync = ImageCompareChromeSync(None, store, resolve_window_presenter=lambda: wp)
    sync.widget = widget
    sync._toolbar_presenter = _toolbar_presenter  # type: ignore[method-assign]
    sync._has_full_res = lambda: False  # type: ignore[method-assign]
    return sync, wp, btn, toggled, batches


def test_visible_domain_syncs_panel_and_button():
    """Dispatch True while visible must move BOTH panel and button."""
    sync, wp, btn, toggled, _batches = _build_sync(
        flag=True, btn_checked=False, visible=True
    )
    sync.handle_store_domain(wp, "viewport")
    assert toggled == [True]
    assert btn.isChecked() is True


def test_hidden_domain_syncs_panel_and_button():
    """Deferred branch must keep the panel/button pair in lockstep too."""
    sync, wp, btn, toggled, _batches = _build_sync(
        flag=False, btn_checked=True, visible=False
    )
    sync.handle_store_domain(wp, "viewport")
    assert toggled == [False]
    assert btn.isChecked() is False


def test_refresh_without_presenter_reports_miss():
    """Post-restore toolbar refresh must not be a silent no-op.

    Regression shape of the restart desync: restore dispatches the Store
    flag, but no presenter is reachable yet, so the button never follows.
    The helper must REPORT the miss (-> bool) instead of returning None.
    """
    from tabs.image_compare.session_persistence import refresh_filename_overlay_toolbar

    store = SimpleNamespace(viewport=SimpleNamespace(), settings=None)
    assert refresh_filename_overlay_toolbar(store) is False
