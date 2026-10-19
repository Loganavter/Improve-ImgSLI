"""Runtime parity gate: a registered surface re-derives on a metrics change.

Complements the static contract (``tests/contracts/test_ui_metrics_contracts.py``):
the contract catches the *shape* (a single-axis subscription), this harness
catches the *behaviour* — a real widget built offscreen whose derived geometry
stays stale when a UI metric changes. Origin: the recurring class this plan
closes (a global font/scale change that leaves cached derived state
uninvalidated — tab-bar rects, tab-strip min-height, the CSD menu strip).

The harness drives the production levers — the ``UiScale`` factor, the
``UiFont`` face and the live language entry (``emit_language_changed``) —
through the toolkit/app singletons and asserts the surface's probe actually
moved. ``connect_ui_metrics`` coalesces the source signals through a
zero-timer, so every lever is followed by a real event-loop turn before the
probe is read.

Axis modes
----------
``live`` (default) applies the lever to the already-built widget and requires
its derived geometry to move — the class bug for a long-lived surface (a live
window, flyout, chip).

``rebuild`` applies the lever *before* building a second instance and requires
the rebuilt instance to carry the new metrics. That is the truthful lifecycle
for a surface the host constructs per open (a modal dialog, a settings page
created with the dialog's language, a list row rebuilt per flyout open): those
widgets have no live per-instance subscription to drive, but must not ship
metrics frozen from the first import/build. A surface declares this per axis
via ``axis_modes``; using the wrong mode would either fail a correct modal
dialog or pass a stale one.

Every registered surface must account for the two plan axes (``scale`` and
``language``) either in ``axes`` (asserted) or in ``exemptions`` (explicit
reason, never a silent skip). ``MetricsSurface.__post_init__`` rejects an
unaccounted plan axis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

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

#: The axes the plan (``plan-live-appearance-fixes-2026-10-19``) requires every
#: surface to account for: a live interface-scale change and a language change.
PLAN_AXES: tuple[str, ...] = ("scale", "language")

#: Every axis the harness can drive. ``font`` predates the plan and stays
#: optional for a surface whose probe is not font-derived.
KNOWN_AXES: frozenset[str] = frozenset({"font", "scale", "language"})

#: Axis modes. ``live`` drives the built widget; ``rebuild`` drives the
#: construction of a fresh instance under the new metrics.
LIVE = "live"
REBUILD = "rebuild"

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

    ``axis_modes`` selects ``LIVE`` (default) or ``REBUILD`` per axis;
    ``exemptions`` records every plan axis the surface does not assert, with
    the reason (an unaccounted plan axis is a registration error, not a skip).
    """

    name: str
    build: Builder
    axes: frozenset[str]
    #: When True the probe's numeric values must grow by ~the lever's factor
    #: (not merely change): the harness then also catches DOUBLE scaling
    #: (ratio ~ factor**2) and reports which disease a failure is. Reserved for
    #: surfaces whose probe values are all factor-proportional design px; a
    #: probe mixing window-relative values stays on the plain "moved" check.
    expect_ratio: bool = False
    #: Per-axis driver: ``LIVE`` (default) or ``REBUILD``. A rebuild axis is
    #: applied before construction, so the surface is measured with the host's
    #: per-open lifecycle (modal dialog, page built from the dialog language).
    axis_modes: Mapping[str, str] = field(default_factory=dict)
    #: Plan axis -> reason it is not asserted. Explicit, never a silent skip.
    exemptions: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unknown = (set(self.axes) | set(self.axis_modes) | set(self.exemptions)) - KNOWN_AXES
        if unknown:
            raise ValueError(f"{self.name!r}: unknown metrics axis/axes {sorted(unknown)}")
        both = set(self.axes) & set(self.exemptions)
        if both:
            raise ValueError(
                f"{self.name!r}: axis/axes {sorted(both)} are both asserted and "
                f"exempt — keep one decision per axis"
            )
        for axis, mode in self.axis_modes.items():
            if axis not in self.axes:
                raise ValueError(
                    f"{self.name!r}: axis mode for {axis!r} declared but the axis "
                    f"is not in axes (the mode would never run)"
                )
            if mode not in (LIVE, REBUILD):
                raise ValueError(f"{self.name!r}: unknown mode {mode!r} for {axis!r}")
        unaccounted = [a for a in PLAN_AXES if a not in self.axes and a not in self.exemptions]
        if unaccounted:
            raise ValueError(
                f"{self.name!r}: plan axis/axes {unaccounted} neither asserted nor "
                f"exempted — a new surface cannot ship ungated"
            )

    def mode_for(self, axis: str) -> str:
        return self.axis_modes.get(axis, LIVE)


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


def _language_lever() -> tuple[Callable[[], None], Callable[[], None]]:
    """(apply, restore) — drive the ONE live retranslate entry.

    ``resources.translations.emit_language_changed`` is the same entry the
    Settings-OK path and the in-app control ``set_language`` use
    (``plugins/settings/application_service.py``), so the lever exercises the
    production path rather than a test-only callback. The original language
    pack is restored verbatim (including the "no language active" empty state)
    because the TranslationManager is process-wide.
    """
    import sli_ui_toolkit.i18n as toolkit_i18n
    from resources.translations import emit_language_changed

    manager = toolkit_i18n._manager
    original_lang = manager._current_lang
    original_pack = manager._translations
    target = "ru" if original_lang != "ru" else "en"

    def apply() -> None:
        emit_language_changed(target)

    def restore() -> None:
        if original_lang:
            emit_language_changed(original_lang)
        else:
            # Restore the "no language active" boot state verbatim; emitting
            # would normalize "" to "en" and leak a global language.
            manager._current_lang = original_lang
            manager._translations = original_pack

    return apply, restore


def _lever(axis: str) -> tuple[Callable[[], None], Callable[[], None]]:
    if axis == "font":
        return _font_lever()
    if axis == "scale":
        return _scale_lever()
    if axis == "language":
        return _language_lever()
    raise ValueError(f"unknown metrics axis {axis!r}")


def _numeric_total(value: Any) -> float | None:
    """Sum the ints/floats found in a probe value (None when there are none).

    Probes return ints, tuples of ints/QSize, or nested tuples — the harness
    only needs a monotone scalar to compare before/after, and the RATIO of two
    such sums is exactly what a factor-proportional surface must produce.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, bytes)):
        # Text probes (labels) carry no geometry; iterating a string would
        # recurse over characters forever.
        return None
    if isinstance(value, (int, float)):
        return float(value)
    total = 0.0
    found = False
    for item in value:
        part = _numeric_total(item)
        if part is not None:
            total += part
            found = True
    return total if found else None


def assert_scaled_ratio(
    before: Any,
    after: Any,
    factor: float,
    name: str,
    axis: str,
) -> None:
    """Assert the probe grew by ~*factor*, and name the disease when it did not.

    Three distinguishable failures, each with its own message:

    * ``ratio ~ 1.0``  — the value never re-derived (the class this harness
      exists for: a cached/baked design px, or a handler that re-runs on the
      wrong axis);
    * ``ratio ~ factor**2`` — DOUBLE scaling (a scale-resolved value fed back
      through the resolver — the second disease, previously invisible to a
      "did it move?" assertion);
    * anything in between — a PARTIAL re-derivation (some of the probe's
      values follow the lever, some do not), which is the shape a half-fixed
      surface has.
    """
    total_before = _numeric_total(before)
    total_after = _numeric_total(after)
    if not total_before or total_after is None:
        raise AssertionError(
            f"{name!r}: probe is not numeric ({before!r}) — a ratio surface "
            f"must expose ints/sizes"
        )
    ratio = total_after / total_before
    # A mixed probe (widths that include font-derived text plus design-px
    # paddings) rounds to a few percent off the factor; the two diseases sit
    # far outside this band (1.0 and factor**2), so the gate stays sharp.
    tolerance = max(0.09, abs(factor - 1.0) * 0.35)
    if abs(ratio - factor) <= tolerance:
        return
    if abs(ratio - 1.0) <= tolerance:
        disease = (
            "STALE: the value did not re-derive on a "
            f"{axis} change (cached/baked design px, or a handler on the "
            "wrong axis)"
        )
    elif abs(ratio - factor ** 2) <= max(tolerance, factor ** 2 * 0.1):
        disease = (
            "DOUBLE-SCALED: a scale-resolved value was fed back through the "
            f"resolver (expected ~{factor:.2f}, got ~{factor ** 2:.2f})"
        )
    else:
        disease = "PARTIALLY re-derived (only some of the probe's values follow the lever)"
    raise AssertionError(
        f"{name!r}: expected the probe to grow by ~{factor:.2f} on a {axis} "
        f"change, got {ratio:.3f} ({total_before:.1f} -> {total_after:.1f}) — {disease}"
    )


def _assert_moved(name: str, before: Any, after: Any, axis: str) -> None:
    assert after != before, (
        f"{name!r}: derived geometry did not re-derive on a "
        f"{axis} change — probe stayed at {before!r}. The widget is "
        f"subscribed to a single metrics axis (or its handler no "
        f"longer re-derives); wire it through connect_ui_metrics / "
        f"MetricsContainer."
    )


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

    ``REBUILD`` axes apply the lever before constructing a second instance and
    settle that instance's probe; the baseline probe is compared against it.
    """
    if qapp is None:
        qapp = QApplication.instance()
    assert qapp is not None, "a QApplication is required (use the qapp fixture)"

    widget, probe = surface.build(qapp, monkeypatch)
    rebuilt: QWidget | None = None
    try:
        for axis in ("font", "scale", "language"):
            if axis not in surface.axes:
                continue
            apply, restore = _lever(axis)
            try:
                before = drain_until_stable(
                    qapp, probe, timeout_ms=1000, stable_frames=2
                )
                factor_before = UiScale.get_instance().factor() if axis == "scale" else None
                apply()
                factor_after = UiScale.get_instance().factor() if axis == "scale" else None
                if surface.mode_for(axis) == REBUILD:
                    rebuilt, rebuilt_probe = surface.build(qapp, monkeypatch)
                    after = drain_until_stable(
                        qapp, rebuilt_probe, timeout_ms=1000, stable_frames=2
                    )
                else:
                    _flush_metrics_channel(qapp)
                    after = drain_until_stable(
                        qapp, probe, timeout_ms=1000, stable_frames=2
                    )
            finally:
                restore()
                if rebuilt is not None:
                    rebuilt.deleteLater()
                    rebuilt = None
                if axis in ("font", "scale"):
                    # Drain the restore lever too: a queued coalesced emission
                    # must not land in the next test's event loop.
                    _flush_metrics_channel(qapp)
            if surface.expect_ratio and axis == "scale" and factor_before:
                assert_scaled_ratio(
                    before,
                    after,
                    float(factor_after or 0.0) / factor_before,
                    surface.name,
                    axis,
                )
                continue
            _assert_moved(surface.name, before, after, axis)
    finally:
        # Drop the Python reference; the conftest teardown destroys top-levels
        # (connect_ui_metrics connections die with the widget's destroyed).
        del widget, probe
