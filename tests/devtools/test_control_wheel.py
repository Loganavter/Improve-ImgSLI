"""``ui_wheel`` — phase-aware wheel delivery over the control surface.

The MCP surface could click, press, hover and focus an element, but had no way
to send a **wheel** event — so a scroll defect could only be reproduced with an
external ``xdotool`` and a physical wheel. That gap hid a real one (2026-10-22):
high-resolution wheels and smooth-scroll compositors mark *every* event
``ScrollBegin``, and the toolkit's glide re-based its target on each one, so the
viewport crawled (~2.5 px per event instead of 60 per notch). Reproducing it
needs a *phase*, which is exactly what this verb adds.

Pinned here (red against a naive implementation that always sends
``NoScrollPhase`` or ignores ``phase``):

* a plain ``phase=none`` stream and a ``phase=begin`` stream move the same
  scroll area by the same amount (the asymmetry was the defect);
* ``phase=begin`` events are actually delivered as ``ScrollBegin`` (the
  receiving widget records the phases it saw);
* an unknown phase is the control surface's own ``MethodError``, never a
  silently ignored call;
* count is clamped to at least one event.

Runs offscreen — no Xvfb.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, Qt
from PySide6.QtWidgets import QApplication, QScrollArea, QVBoxLayout, QWidget

from core.control.elements import interaction
from core.control.elements.inventory import Element
from core.control.handlers import MethodError


class _PhaseRecorder(QScrollArea):
    """A scroll area that records the scroll phases its viewport receives."""

    _want = frozenset({QEvent.Type.Wheel})

    def __init__(self) -> None:
        super().__init__()
        self.phases: list[Qt.ScrollPhase] = []
        host = QWidget()
        host.setFixedHeight(6000)
        QVBoxLayout(host)
        self.setWidget(host)
        self.setWidgetResizable(False)
        self.resize(400, 300)
        self.show()

    def viewportEvent(self, event) -> bool:  # noqa: N802
        if event.type() in self._want:
            self.phases.append(event.phase())
        return super().viewportEvent(event)


def _element(area: QWidget) -> Element:
    return Element(
        id="test/scroll",
        widget=area,
        role="scroll",
        label="scroll",
        rect=QRect(0, 0, 400, 300),
        window="Test",
        surface="test",
        action_id=None,
        owner_tab=None,
        enabled=True,
        visible=True,
    )


def _run(phase: str, *, count: int = 10) -> tuple[int, list[Qt.ScrollPhase]]:
    area = _PhaseRecorder()
    try:
        # The scroll range lands on the first layout pass; without it a wheel
        # event is delivered (phases recorded) but there is nothing to scroll.
        for _ in range(3):
            QApplication.processEvents()
        interaction.wheel_element(_element(area), delta=-120, phase=phase, count=count)
        QApplication.processEvents()
        # A plain QScrollArea applies the wheel synchronously; give a toolkit
        # glide (if the widget were one) its ticks too.
        for _ in range(40):
            QApplication.processEvents()
        value = area.verticalScrollBar().value()
        phases = list(area.phases)
        return value, phases
    finally:
        area.close()
        area.deleteLater()
        QApplication.processEvents()


def test_begin_stream_and_plain_stream_move_equally(qapp) -> None:
    """A ScrollBegin-marked stream must not lose progress vs a plain one."""
    plain, _ = _run("none")
    begin, _ = _run("begin")
    assert plain > 0 and begin > 0
    assert begin == plain, (
        f"phase=begin moved {begin}px while phase=none moved {plain}px — "
        "the high-resolution stream is losing progress"
    )


def test_begin_events_are_delivered_as_scroll_begin(qapp) -> None:
    _, phases = _run("begin", count=3)
    assert phases, "no wheel event reached the widget"
    assert set(phases) == {Qt.ScrollPhase.ScrollBegin}, phases


def test_plain_phase_is_no_scroll_phase(qapp) -> None:
    _, phases = _run("none", count=3)
    assert set(phases) == {Qt.ScrollPhase.NoScrollPhase}, phases


def test_unknown_phase_is_a_named_refusal(qapp) -> None:
    area = _PhaseRecorder()
    try:
        try:
            interaction.wheel_element(_element(area), phase="spin")
        except MethodError as exc:
            assert "phase" in str(exc)
        else:  # pragma: no cover - the assertion below is the test
            raise AssertionError("an unknown wheel phase was accepted")
    finally:
        area.close()
        area.deleteLater()
        QApplication.processEvents()


def test_wheel_over_a_child_scrolls_the_owning_area(qapp) -> None:
    """A wheel aimed at a child inside a scroll area scrolls that area.

    This is the live case: the gallery inventory exposes cards, not the scroll
    viewport, and a toolkit card (a Button) can return from ``wheelEvent``
    without scrolling. The verb walks up to the owning ``QAbstractScrollArea``
    instead of silently doing nothing.
    """
    area = _PhaseRecorder()
    try:
        for _ in range(3):
            QApplication.processEvents()
        child = area.widget()
        assert child is not None
        element = _element(child)
        element.rect = child.rect()
        interaction.wheel_element(element, delta=-120, phase="begin", count=10)
        for _ in range(20):
            QApplication.processEvents()
        assert area.verticalScrollBar().value() > 0, (
            "a wheel over a child of the scroll area did not scroll it"
        )
    finally:
        area.close()
        area.deleteLater()
        QApplication.processEvents()


def test_count_never_sends_zero_events(qapp) -> None:
    _, phases = _run("none", count=0)
    assert len(phases) >= 1, "count=0 sent no event at all"
