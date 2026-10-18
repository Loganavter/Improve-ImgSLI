"""Runtime parity gate: a registered surface re-derives on a metrics change.

Complements the static contract (``tests/contracts/test_ui_metrics_contracts.py``):
the contract catches the *shape* (a single-axis subscription), this harness
catches the *behaviour* — a real widget built offscreen whose derived geometry
stays stale when a UI metric changes. Origin: the recurring class this plan
closes (a global font/scale change that leaves cached derived state
uninvalidated — tab-bar rects, tab-strip min-height, the CSD menu strip).

The harness drives the two production levers — the ``UiScale`` factor and the
``UiFont`` face — through the toolkit singletons and asserts the surface's
geometry probe actually moved. ``connect_ui_metrics`` coalesces the source
signals through a zero-timer, so every lever is followed by a real event-loop
turn before the probe is read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QFontDatabase, QFontMetrics
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.managers import UiFont, UiScale
from tests.helpers.drain_until_stable import drain_until_stable

#: The probe string used to pick a font face with *measurably* different
#: metrics — a face with identical advances would prove nothing.
_PROBE_TEXT = "File"

#: Scale lever target — far enough from 1.0 that rounded px geometry moves.
_SCALE_TARGET = 1.25

#: Builder: (qapp, monkeypatch) -> (widget, probe). monkeypatch may be None
#: for surfaces that need no module patching.
Builder = Callable[[QApplication, Any], "tuple[QWidget, Callable[[], Any]]"]


@dataclass(frozen=True)
class MetricsSurface:
    """A registered surface: build a widget, probe its derived geometry.

    ``build(qapp, monkeypatch)`` returns ``(widget, probe)`` where ``probe()``
    snapshots the derived-geometry values the widget's own metrics handler
    owns. ``axes`` declares which UI metrics the surface derives from — the
    harness asserts the probe moves under exactly those levers (a scale-only
    surface is not expected to move under the font lever, and asserting
    otherwise would test nothing but rounding coincidence).
    """

    name: str
    build: Builder
    axes: frozenset[str]


def _flush_metrics_channel(qapp: QApplication) -> None:
    """Run real event-loop turns until the coalesced ``UiMetrics.changed`` fires.

    ``connect_ui_metrics`` emits through a zero-timer after the source
    notification; a plain ``processEvents`` drain is not guaranteed to run
    it (under a full-suite event backlog the flush lands several turns late).
    A spy slot is connected to the channel and the loop spins until that
    emission arrives — bounded, then gives up (the probe assert then fails
    with a clear message rather than hanging). Listening to the public
    ``changed`` signal keeps this independent of the channel's private
    pending-axes bookkeeping (an earlier revision read ``metrics._pending``,
    which the toolkit renamed — the whole gate then failed on the attribute
    error, not on the surfaces).
    """
    import time

    from sli_ui_toolkit.ui.managers.ui_metrics import UiMetrics

    metrics = UiMetrics.get_instance()
    fired: list[Any] = []
    connection = metrics.changed.connect(lambda axes: fired.append(axes))
    deadline = time.monotonic() + 1.0
    try:
        while not fired and time.monotonic() <= deadline:
            loop = QEventLoop()
            QTimer.singleShot(2, loop.quit)
            loop.exec()
            qapp.processEvents()
    finally:
        try:
            metrics.changed.disconnect(connection)
        except (RuntimeError, TypeError):
            pass


def _scale_lever() -> tuple[Callable[[], None], Callable[[], None]]:
    """(apply, restore) — move the UiScale factor off its current value."""
    ui_scale = UiScale.get_instance()
    original = ui_scale.factor()
    target = _SCALE_TARGET if original != _SCALE_TARGET else 1.5

    def apply() -> None:
        ui_scale.set_factor(target)

    def restore() -> None:
        ui_scale.set_factor(original)

    return apply, restore


def _font_lever() -> tuple[Callable[[], None], Callable[[], None]]:
    """(apply, restore) — pin a UI face with measurably different metrics.

    The alternate face is chosen by *measuring* (first family, in sorted order,
    whose advance for ``_PROBE_TEXT`` differs from the current face's), so the
    lever cannot silently degrade to a no-op on a similar-metrics system.
    """
    ui_font = UiFont.get_instance()
    current = ui_font.family()
    base_advance = QFontMetrics(ui_font.resolve()).horizontalAdvance(_PROBE_TEXT)
    alternate: str | None = None
    for family in sorted(QFontDatabase.families()):
        if family == current:
            continue
        metrics = QFontMetrics(ui_font.resolve(family=family))
        if metrics.horizontalAdvance(_PROBE_TEXT) != base_advance:
            alternate = family
            break
    if alternate is None:
        pytest.skip(
            "no alternate font family with different metrics is available; "
            "the font lever cannot move font-derived geometry here"
        )

    # Capture the original override BEFORE the first apply can change it.
    original_override = ui_font._family_override

    def apply() -> None:
        ui_font.set_family(alternate)

    def restore() -> None:
        ui_font.set_family(original_override)

    return apply, restore


def assert_reflows_on_metrics_change(
    surface: MetricsSurface,
    qapp: QApplication | None = None,
    monkeypatch: Any | None = None,
) -> None:
    """Assert ``surface``'s derived geometry re-derives under each declared axis.

    Builds the real widget offscreen, settles it, then per declared axis:
    snapshot the probe, apply the lever, drain the coalesced channel, assert
    the probe moved, restore. The probe must move under EACH declared axis —
    a stale handler leaves it at the pre-lever value (the class bug).
    """
    if qapp is None:
        qapp = QApplication.instance()
    assert qapp is not None, "a QApplication is required (use the qapp fixture)"

    widget, probe = surface.build(qapp, monkeypatch)
    assert widget is not None
    try:
        for axis in ("font", "scale"):
            if axis not in surface.axes:
                continue
            apply, restore = (
                _font_lever() if axis == "font" else _scale_lever()
            )
            try:
                before = drain_until_stable(
                    qapp, probe, timeout_ms=1000, stable_frames=2
                )
                apply()
                _flush_metrics_channel(qapp)
                after = drain_until_stable(
                    qapp, probe, timeout_ms=1000, stable_frames=2
                )
            finally:
                restore()
                _flush_metrics_channel(qapp)
            assert after != before, (
                f"{surface.name!r}: derived geometry did not re-derive on a "
                f"{axis} change — probe stayed at {before!r}. The widget is "
                f"subscribed to a single metrics axis (or its handler no "
                f"longer re-derives); wire it through connect_ui_metrics / "
                f"MetricsContainer."
            )
    finally:
        # Drop the Python reference; the conftest teardown destroys top-levels
        # (connect_ui_metrics connections die with the widget's destroyed).
        del widget, probe
