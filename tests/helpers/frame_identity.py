"""Frame-identity harness: a surface never paints a state it knows is stale.

The class this guards ("the first presented frame is not the settled frame")
has three mechanisms — see `docs/dev/QT_LAYOUT_PITFALLS.md` in the private
docs repo. This helper covers the observable half of any of them: **record
every paint** of a widget across a mutation and require that no paint observed
an intermediate state.

The rule it encodes is deliberately absolute: `paints[0] == paints[-1]`. A
surface that legitimately repaints with the same state (theme, hover) stays
green; a surface that paints the old geometry/font/columns once and then the
new one fails. That "one stale frame" is invisible to settled-state assertions
and to geometry logs, which is exactly why it keeps coming back.

Recording happens **inside the widget's `paintEvent`**, not in an event
filter: a `Paint` filter runs before `settle_on_paint`'s filter (Qt dispatches
filters last-installed-first), so a filter-based recorder would observe the
pre-settle state and report a bug that the paint boundary already fixed.

Usage::

    from tests.helpers.frame_identity import assert_no_stale_paint

    assert_no_stale_paint(
        panel,
        mutate=lambda: window.resize(640, 1000),
        observe=lambda: (panel._items.grid_columns, panel.height()),
        qapp=qapp,
    )
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QApplication, QWidget

Snapshot = tuple


class PaintRecorder:
    """Record ``observe()`` for every paint of *widget* while installed.

    Shadows the widget instance's ``paintEvent``; the original is invoked
    afterwards, so the widget paints exactly as before. Only paints of this
    widget are recorded (not its children) — pass the widget that owns the
    state being asserted (the panel, the strip, the bar).
    """

    def __init__(self, widget: QWidget, observe: Callable[[], Snapshot]) -> None:
        self._widget = widget
        self._observe = observe
        self.paints: list[Snapshot] = []
        self._original = widget.paintEvent  # bound method, called with the event
        widget.paintEvent = self._paint_event  # type: ignore[method-assign]

    def _paint_event(self, event) -> None:
        self.paints.append(self._observe())
        self._original(event)

    def stop(self) -> None:
        try:
            del self._widget.__dict__["paintEvent"]
        except (AttributeError, KeyError):
            self._widget.paintEvent = self._original  # type: ignore[method-assign]


def _drain(qapp: QApplication, turns: int) -> None:
    for _ in range(turns):
        qapp.processEvents()


def assert_no_stale_paint(
    widget: QWidget,
    *,
    mutate: Callable[[], None],
    observe: Callable[[], Snapshot],
    qapp: QApplication | None = None,
    turns: int = 4,
    require_paint: bool = True,
) -> list[Snapshot]:
    """Run *mutate* and assert no paint of *widget* saw an intermediate state.

    *observe* returns the tuple being asserted (the surface's settled inputs:
    geometry, column count, font metrics — whatever the mutation changes).
    Every paint recorded between ``mutate()`` and the drained turns must match
    the final one. Returns the recorded snapshots for a caller's own detail
    assertions.
    """
    app = qapp or QApplication.instance()
    recorder = PaintRecorder(widget, observe)
    try:
        mutate()
        _drain(app, turns)
        paints = list(recorder.paints)
    finally:
        recorder.stop()

    if not paints:
        assert not require_paint, (
            "the mutation produced no paint to inspect; is the widget visible?"
        )
        return paints
    stale = [snapshot for snapshot in paints if snapshot != paints[-1]]
    assert not stale, (
        f"{widget.objectName() or type(widget).__name__} painted an intermediate "
        f"state: {stale} then settled at {paints[-1]}"
    )
    return paints
