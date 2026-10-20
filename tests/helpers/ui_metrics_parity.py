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

Pixel mode (the LIVE false green this file also closes)
-------------------------------------------------------
Geometry parity alone is not enough: a surface can re-derive its *numbers* and
still paint the wrong **pixels** (the same cached geometry rounded into a row
whose ink no longer fits, or a label whose "pixmap exists" but whose glyph
bitmap was built for another language/scale). The pixel half of the gate
rasterises the real widget offscreen and asserts on the ink itself:

* ``assert_ink_rows_scale_with_interface_scale`` — the ink-row height (the
  rows of a label that contain glyph pixels) grows by ~the interface-scale
  factor; a constant ink height is named ``UNSCALED``, a factor² ink height
  ``DOUBLE-SCALED``;
* ``assert_ink_fits_its_row`` — the ink bounding box stays strictly inside the
  row box (a label squeezed below its text touches the edge — ``CLIPPED``);
* ``assert_glyph_bitmap_differs_across_language`` — the rendered glyph bitmap
  of a known label has a non-zero pixel diff across en/ru. Presence of a
  pixmap is not content: identical pixels are named ``IDENTICAL`` and fail.

``PixelSurface.__post_init__`` mirrors ``MetricsSurface``: a new pixel surface
cannot ship without a decision on both plan axes.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import pytest
from PySide6.QtCore import QEventLoop, QRect, QTimer
from PySide6.QtGui import QFontDatabase, QFontMetrics, QImage
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

#: Pixel builder: (qapp, monkeypatch) -> (widget, ``PixelProbe``).
PixelBuilder = Callable[[QApplication, Any], "tuple[QWidget, PixelProbe]"]


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


# ---------------------------------------------------------------------------
# Pixel mode — rasterise the real widget and assert on the INK, not the
# geometry numbers. Origin: plan-live-appearance-fixes-2026-10-19, where nine
# geometry tests passed while the owner's chrome was visibly broken.
# ---------------------------------------------------------------------------

#: Per-channel delta above which a pixel counts as ink against the region's
#: modal background. Text antialiasing spans a wide range; 12 separates glyph
#: coverage from a flat face without swallowing it.
INK_TOLERANCE = 12

#: Pixel slack (px) allowed when comparing ink heights against the factor.
#: Font hinting quantises glyph ink at small point sizes (a 9pt label's 10 px
#: ink becomes 18 px at 18pt, not 20) — the gate must accept that rounding
#: while still rejecting "did not scale" (ratio 1.0) and "scaled twice".
_INK_ROUNDING_SLACK = 1.0
_INK_RELATIVE_SLACK = 0.12


@dataclass(frozen=True)
class InkBounds:
    """Bounding box of the ink inside a measured region (region-relative)."""

    left: int
    top: int
    width: int
    height: int
    pixels: int
    region: QRect

    @property
    def right(self) -> int:
        return self.left + self.width - 1

    @property
    def bottom(self) -> int:
        return self.top + self.height - 1

    def __str__(self) -> str:
        return (
            f"{self.width}x{self.height} ink at ({self.left},{self.top}), "
            f"{self.pixels} px, in {self.region.width()}x{self.region.height()}"
        )


def ink_bounds(image: QImage, region: QRect) -> InkBounds | None:
    """Bounding box of pixels that differ from the region's modal colour.

    The modal colour (most frequent pixel in the region) is the row's own
    background, so a selected tab's white face, a button's face and a dialog's
    panel all work without the caller passing a colour. ``None`` means the
    region is empty — a blank render, which is a failure, never a pass.
    """
    assert region.isValid() and not region.isEmpty(), f"empty ink region {region!r}"
    clipped = region.intersected(image.rect())
    assert clipped == region, (
        f"ink region {region!r} is not fully inside the rendered image "
        f"{image.width()}x{image.height()} — the probe would measure dead pixels"
    )
    counts: Counter[tuple[int, int, int]] = Counter()
    for y in range(region.top(), region.bottom() + 1):
        for x in range(region.left(), region.right() + 1):
            counts[image.pixelColor(x, y).getRgb()[:3]] += 1
    background = counts.most_common(1)[0][0]

    min_x = min_y = 10**9
    max_x = max_y = -1
    pixels = 0
    for y in range(region.top(), region.bottom() + 1):
        for x in range(region.left(), region.right() + 1):
            colour = image.pixelColor(x, y).getRgb()[:3]
            if max(abs(colour[i] - background[i]) for i in range(3)) > INK_TOLERANCE:
                pixels += 1
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
    if pixels == 0:
        return None
    return InkBounds(
        left=min_x - region.left(),
        top=min_y - region.top(),
        width=max_x - min_x + 1,
        height=max_y - min_y + 1,
        pixels=pixels,
        region=region,
    )


@dataclass(frozen=True)
class PixelProbe:
    """The pixel probe a surface owns: render, label region, row box, text.

    ``label_region`` must contain ONLY the known label's ink (no icon, border
    or neighbouring text) — the harness measures the ink inside it.
    ``row_region`` is the row/tab/button box the ink must stay inside.
    """

    image: Callable[[], QImage]
    label_region: Callable[[], QRect]
    row_region: Callable[[], QRect]
    label_text: Callable[[], str]


@dataclass(frozen=True)
class InkSnapshot:
    """One rasterised state of a surface: image, regions, text and ink bbox."""

    image: QImage
    label_region: QRect
    row_region: QRect
    text: str
    bounds: InkBounds | None
    name: str = ""

    def require_ink(self) -> InkBounds:
        if self.bounds is None:
            raise AssertionError(
                f"{self.name!r}: the label region {self.label_region!r} rendered "
                f"NO ink — a blank/pixmap-held label is not content (text "
                f"{self.text!r}). The rasteriser or the surface paints nothing here."
            )
        return self.bounds


@dataclass(frozen=True)
class PixelSurface:
    """A registered pixel surface: real widget + the ink probe it owns.

    ``axes``/``exemptions`` follow ``MetricsSurface``: both plan axes must be
    asserted or explicitly exempted (an unaccounted axis is a registration
    error). ``modes`` selects LIVE (drive the built widget) or REBUILD (build a
    fresh instance under the lever) per axis.
    """

    name: str
    build: PixelBuilder
    axes: frozenset[str] = frozenset({"scale", "language"})
    modes: Mapping[str, str] = field(default_factory=dict)
    exemptions: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unknown = (set(self.axes) | set(self.modes) | set(self.exemptions)) - KNOWN_AXES
        if unknown:
            raise ValueError(f"{self.name!r}: unknown pixel axis/axes {sorted(unknown)}")
        both = set(self.axes) & set(self.exemptions)
        if both:
            raise ValueError(
                f"{self.name!r}: pixel axis/axes {sorted(both)} are both asserted "
                f"and exempt — keep one decision per axis"
            )
        for axis, mode in self.modes.items():
            if axis not in self.axes:
                raise ValueError(
                    f"{self.name!r}: pixel axis mode for {axis!r} declared but the "
                    f"axis is not in axes (the mode would never run)"
                )
            if mode not in (LIVE, REBUILD):
                raise ValueError(f"{self.name!r}: unknown pixel mode {mode!r} for {axis!r}")
        unaccounted = [a for a in PLAN_AXES if a not in self.axes and a not in self.exemptions]
        if unaccounted:
            raise ValueError(
                f"{self.name!r}: plan axis/axes {unaccounted} neither asserted nor "
                f"exempted — a new pixel surface cannot ship ungated"
            )

    def mode_for(self, axis: str) -> str:
        return self.modes.get(axis, LIVE)


def _snapshot(probe: PixelProbe, name: str) -> InkSnapshot:
    """Rasterise one probe state (call it right before and after a lever)."""
    image = probe.image()
    label_region = probe.label_region()
    return InkSnapshot(
        image=image,
        label_region=label_region,
        row_region=probe.row_region(),
        text=probe.label_text(),
        bounds=ink_bounds(image, label_region),
        name=name,
    )


@contextmanager
def _built(surface: PixelSurface, qapp: QApplication, monkeypatch: Any | None):
    """Build the surface, settle it, and tear the instance down afterwards."""
    widget, probe = surface.build(qapp, monkeypatch)
    try:
        drain_until_stable(qapp, probe.row_region, timeout_ms=1000, stable_frames=2)
        yield probe
    finally:
        widget.close()
        widget.deleteLater()
        qapp.processEvents()


def capture_ink(
    surface: PixelSurface,
    qapp: QApplication | None = None,
    monkeypatch: Any | None = None,
) -> InkSnapshot:
    """Build ``surface`` under the CURRENT metrics and rasterise its label ink."""
    if qapp is None:
        qapp = QApplication.instance()
    assert qapp is not None, "a QApplication is required (use the qapp fixture)"
    with _built(surface, qapp, monkeypatch) as probe:
        return _snapshot(probe, surface.name)


def assert_ink_fits_its_row(snapshot: InkSnapshot) -> None:
    """The ink must sit strictly inside its row box — touching the edge = clipped.

    A label squeezed below its text is invisible to a geometry probe that only
    reads ``sizeHint`` (the row can report the right pitch while the glyphs are
    cut). One pixel of slack on every side proves the text was not truncated.
    """
    bounds = snapshot.require_ink()
    row = snapshot.row_region
    if (
        bounds.left < 1
        or bounds.top < 1
        or bounds.right > row.width() - 2
        or bounds.bottom > row.height() - 2
    ):
        raise AssertionError(
            f"{snapshot.name!r}: CLIPPED — the label ink ({bounds}) touches its "
            f"row box {row.width()}x{row.height()} (text {snapshot.text!r}). "
            f"A row narrower/shorter than its glyphs truncates the label even "
            f"when its geometry re-derives."
        )


def assert_ink_scales_with_factor(
    before: InkSnapshot,
    after: InkSnapshot,
    factor: float,
) -> None:
    """The ink-row height must grow by ~*factor*; name the disease otherwise."""
    before_ink = before.require_ink()
    after_ink = after.require_ink()
    expected = before_ink.height * factor
    delta = abs(after_ink.height - expected)
    slack = max(_INK_ROUNDING_SLACK, _INK_RELATIVE_SLACK * expected)
    if delta <= slack:
        return
    ratio = after_ink.height / before_ink.height
    if abs(ratio - 1.0) <= _INK_RELATIVE_SLACK:
        disease = (
            "UNSCALED: the ink height did not follow the interface scale "
            "(a baked/fixed pixel font or a row pinned to design px)"
        )
    elif abs(ratio - factor**2) <= max(_INK_RELATIVE_SLACK * factor**2, 0.15):
        disease = (
            "DOUBLE-SCALED: the ink height grew by ~the squared factor "
            f"(expected ~{factor:.2f}x, got ~{factor**2:.2f}x)"
        )
    else:
        disease = (
            "PARTIALLY scaled (only some of the row's ink follows the scale — "
            "mixed fixed/scaled px in the label or row)"
        )
    raise AssertionError(
        f"{before.name!r}: expected the ink-row height of {before.text!r} to "
        f"grow by ~{factor:.2f}x ({before_ink.height} px -> ~{expected:.1f} px), "
        f"got {after_ink.height} px ({ratio:.2f}x) — {disease}"
    )


def assert_ink_rows_scale_with_interface_scale(
    surface: PixelSurface,
    qapp: QApplication | None = None,
    monkeypatch: Any | None = None,
    *,
    factor: float = 2.0,
) -> None:
    """Drive the scale lever and assert the surface's ink height follows it.

    LIVE surfaces are driven in place (the long-lived chrome the owner
    reported); REBUILD surfaces are constructed fresh under the new factor
    (modal dialogs, per-open pages). Both also assert the row containment in
    both states — a label that scales but no longer fits is still broken.
    """
    if qapp is None:
        qapp = QApplication.instance()
    assert qapp is not None, "a QApplication is required (use the qapp fixture)"
    assert "scale" in surface.axes, f"{surface.name!r}: scale axis not asserted"

    ui_scale = UiScale.get_instance()
    original = ui_scale.factor()
    target = factor if original != factor else 1.5
    with _built(surface, qapp, monkeypatch) as probe:
        before = _snapshot(probe, surface.name)
        try:
            ui_scale.set_factor(target)
            if surface.mode_for("scale") == REBUILD:
                after = capture_ink(surface, qapp, monkeypatch)
            else:
                _flush_metrics_channel(qapp)
                drain_until_stable(qapp, probe.row_region, timeout_ms=1000, stable_frames=2)
                after = _snapshot(probe, surface.name)
        finally:
            ui_scale.set_factor(original)
            _flush_metrics_channel(qapp)

    assert_ink_fits_its_row(before)
    assert_ink_fits_its_row(after)
    assert_ink_scales_with_factor(before, after, target / original)


def assert_glyph_bitmap_differs_across_language(
    surface: PixelSurface,
    qapp: QApplication | None = None,
    monkeypatch: Any | None = None,
) -> None:
    """A known label's glyph bitmap must have a non-zero pixel diff across en/ru."""
    if qapp is None:
        qapp = QApplication.instance()
    assert qapp is not None, "a QApplication is required (use the qapp fixture)"
    assert "language" in surface.axes, f"{surface.name!r}: language axis not asserted"

    apply, restore = _language_lever()
    before = capture_ink(surface, qapp, monkeypatch)
    try:
        apply()
        after = capture_ink(surface, qapp, monkeypatch)
    finally:
        restore()
        _flush_metrics_channel(qapp)

    assert before.text != after.text, (
        f"{surface.name!r}: IDENTICAL labels {before.text!r} in both languages — "
        f"the surface did not retranslate/build in the new language, so the "
        f"pixel diff below would prove nothing"
    )
    before.require_ink()
    after.require_ink()
    diff = _glyph_pixel_diff(before, after)
    assert diff > 0, (
        f"{surface.name!r}: IDENTICAL glyph bitmap — the label text changed "
        f"({before.text!r} -> {after.text!r}) but the rasterised label region is "
        f"pixel-identical; the rendered content never followed the language "
        f"(a held pixmap/cache is not content)."
    )


def _glyph_pixel_diff(before: InkSnapshot, after: InkSnapshot) -> int:
    """Count differing pixels between the two label crops (padded to a union)."""
    left = before.image.copy(before.label_region)
    right = after.image.copy(after.label_region)
    width = max(left.width(), right.width())
    height = max(left.height(), right.height())

    def _padded(source: QImage) -> QImage:
        canvas = QImage(width, height, QImage.Format.Format_RGB32)
        canvas.fill(0)
        for y in range(source.height()):
            for x in range(source.width()):
                canvas.setPixelColor(x, y, source.pixelColor(x, y))
        return canvas

    a = _padded(left)
    b = _padded(right)
    diff = 0
    for y in range(height):
        for x in range(width):
            ca = a.pixelColor(x, y).getRgb()[:3]
            cb = b.pixelColor(x, y).getRgb()[:3]
            if max(abs(ca[i] - cb[i]) for i in range(3)) > INK_TOLERANCE:
                diff += 1
    return diff
