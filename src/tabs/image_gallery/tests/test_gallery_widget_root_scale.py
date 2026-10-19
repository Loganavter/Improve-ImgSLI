"""Gallery page root chrome follows the UI scale (live, not just at build).

The page root carried the raw ``setContentsMargins(24, 12, 24, 40)`` literal
(real_design.md §2.7) while its sibling ``setSpacing`` already resolved
``scaled_px(12)``: the margins stayed at design px after every interface-scale
change. They now resolve through ``view_prefs.apply_root_design_metrics`` at
use time and re-resolve on the unified metrics channel
(plan ``plan-live-appearance-fixes-2026-10-19``).

Builds the real widget offscreen at factor 1.0 and 1.5; a value that does not
grow by the factor is STALE (the pre-fix bug), ``factor**2`` would be DOUBLE.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import UiScale, scaled_px
from tabs.image_gallery.widget import ImageGalleryWidget

#: Design px of the page root chrome (real_design.md §2.7).
_ROOT_MARGIN = (24, 12, 24, 40)
_ROOT_SPACING = 12


def _drain_metrics_channel() -> None:
    """Run real event-loop turns until the coalesced metrics zero-timer has fired.

    A factor change queues ``UiMetrics.changed`` on a zero-timer; if this test
    ends first, the emission lands in the NEXT test's event loop and re-renders
    unrelated surfaces. Drain at teardown.
    """
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    for _ in range(6):
        loop = QEventLoop()
        QTimer.singleShot(2, loop.quit)
        loop.exec()
        app.processEvents()


@pytest.fixture(autouse=True)
def _restore_ui_scale():
    yield
    UiScale.get_instance().set_factor(1.0)
    _drain_metrics_channel()


def _margins(widget: QWidget) -> tuple[int, int, int, int, int]:
    layout = widget.layout()
    assert layout is not None
    m = layout.contentsMargins()
    return (m.left(), m.top(), m.right(), m.bottom(), layout.spacing())


def test_root_margins_resolve_design_px_at_factor_1_0(qapp) -> None:
    UiScale.get_instance().set_factor(1.0)
    widget = ImageGalleryWidget(context=None)
    try:
        assert _margins(widget) == (*_ROOT_MARGIN, _ROOT_SPACING)
    finally:
        widget.deleteLater()


def test_root_margins_follow_the_scale_at_build(qapp) -> None:
    UiScale.get_instance().set_factor(1.5)
    widget = ImageGalleryWidget(context=None)
    try:
        expected = (
            *(scaled_px(v) for v in _ROOT_MARGIN),
            scaled_px(_ROOT_SPACING),
        )
        assert expected == (36, 18, 36, 60, 18), f"UiScale 1.5 sanity: {expected}"
        assert _margins(widget) == expected, (
            f"gallery root chrome at factor 1.5 is {_margins(widget)}, expected "
            f"{expected} (design {_ROOT_MARGIN} x factor)"
        )
    finally:
        widget.deleteLater()


def _spin_until_changed(qapp, probe, *, timeout_ms: int = 1000):
    """Run real event-loop turns until ``probe()`` moves.

    The metrics bus coalesces through a zero-timer, so a plain stability drain
    (``drain_until_stable``) can legitimately read the pre-change value and
    return: wait for the *change*, not for stability.
    """
    import time

    from PySide6.QtCore import QEventLoop, QTimer

    before = probe()
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() <= deadline:
        loop = QEventLoop()
        QTimer.singleShot(2, loop.quit)
        loop.exec()
        qapp.processEvents()
        current = probe()
        if current != before:
            return current
    return probe()


def test_root_margins_re_resolve_on_a_live_scale_change(qapp) -> None:
    UiScale.get_instance().set_factor(1.0)
    widget = ImageGalleryWidget(context=None)
    try:
        before = _margins(widget)
        UiScale.get_instance().set_factor(1.5)
        after = _spin_until_changed(qapp, lambda: _margins(widget))
        expected = (*(scaled_px(v) for v in _ROOT_MARGIN), scaled_px(_ROOT_SPACING))
        assert after == expected, (
            f"gallery root chrome did not re-resolve on a live scale change: "
            f"{before} -> {after}, expected {expected}"
        )
    finally:
        widget.deleteLater()


def test_root_metrics_owner_is_the_view_prefs_module() -> None:
    """The page is a documented thin owner — the chrome body must live in
    ``ui/widget_parts/view_prefs`` (CODE_PATTERNS), not on the widget."""
    from tabs.image_gallery.ui.widget_parts import view_prefs

    assert view_prefs.ROOT_MARGIN_PX == _ROOT_MARGIN
    assert view_prefs.ROOT_SPACING_PX == _ROOT_SPACING
    assert callable(view_prefs.apply_root_design_metrics)
    assert callable(view_prefs.on_root_metrics_changed)


def test_no_raw_root_literal_in_the_widget() -> None:
    """Falsification guard: the old raw literal must not come back."""
    import inspect

    source = inspect.getsource(ImageGalleryWidget.__init__)
    assert "setContentsMargins(24, 12, 24, 40)" not in source
    assert "_apply_root_design_metrics()" in source
