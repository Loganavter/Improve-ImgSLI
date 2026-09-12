"""Regression test: ``image_startup_placeholder`` must be dismissed on the
canvas's first real rendered frame.

``ImageCompareWidget._wire_transition_mask_release`` used to only connect
``firstVisualFrameReady`` (which releases the workspace transition mask, a
separate overlay) and never connected ``firstFrameRendered`` to hiding the
placeholder at all — unlike ``multi_compare``'s ``widget.py``, which wires
``canvas.firstFrameRendered`` straight to ``_on_first_frame`` ->
``placeholder.hide()``.

Without that wiring the placeholder stayed shown (and raised) over the
canvas forever, painted at whatever geometry its last ``sync_geometry()``
call (on ``showEvent``) had captured — before layout finished settling
after text-controls-row visibility changes. The gap between that stale,
smaller geometry and the canvas's final, larger size read as "the top of
the canvas shows the theme background, only a bottom strip shows the real
comparison".
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_compare.widget import ImageCompareWidget
from ui.widgets.startup_placeholder import StartupPlaceholder

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])  # type: ignore[assignment]
    assert _APP is not None
    return _APP


class _FakeCanvas(QObject):
    firstFrameRendered = Signal()
    firstVisualFrameReady = Signal()


def test_first_frame_rendered_dismisses_startup_placeholder():
    app = _app()
    parent = QWidget()
    widget = ImageCompareWidget.__new__(ImageCompareWidget)
    QWidget.__init__(widget, parent)
    widget._context = None

    canvas = _FakeCanvas()
    widget.image_label = canvas
    placeholder = StartupPlaceholder(parent, target_widget=None)
    widget.image_startup_placeholder = placeholder

    assert placeholder._dismissed is False

    widget._wire_transition_mask_release()
    canvas.firstFrameRendered.emit()

    assert placeholder._dismissed is True

    placeholder.deleteLater()
    widget.deleteLater()
    parent.deleteLater()
    app.processEvents()


def test_wiring_is_a_noop_without_a_canvas():
    """No ``image_label`` yet (assemble() hasn't run) must not raise."""
    app = _app()
    widget = ImageCompareWidget.__new__(ImageCompareWidget)
    QWidget.__init__(widget)

    widget._wire_transition_mask_release()

    widget.deleteLater()
    app.processEvents()
