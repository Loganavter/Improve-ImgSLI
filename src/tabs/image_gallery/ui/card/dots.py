"""Dots helpers — severity tokens & per-dot colors (painter pipeline only)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tabs.image_gallery.models import GalleryItem

# S2-12: colors via ThemeManager tokens per THEMING.md; fallback hex kept for offscreen tests
_SEVERITY_TOKEN_FALLBACKS: dict[str, tuple[str, str]] = {
    "clean": ("gallery.status.ok", "#3fbf5f"),
    "mild": ("gallery.status.warn", "#e8b64c"),
    "flagged": ("gallery.status.danger", "#D93025"),
}
# Light-theme counterparts of the dark fallbacks above (themes.json light section).
_SEVERITY_FALLBACKS_LIGHT: dict[str, str] = {
    "clean": "#2e7d32",
    "mild": "#b77900",
    "flagged": "#c0392b",
}
_ERROR_LINE_TOKEN_FALLBACK = ("gallery.status.danger", "#D93025")
_ERROR_LINE_FALLBACK_LIGHT = "#c0392b"
_ACCENT_TOKEN_FALLBACK = ("gallery.accent.bar", "#0096FF")
_ACCENT_FALLBACK_LIGHT = "#0078D4"

_DOTS_TEXT = "● ● ●"
_DOTS_ROW_GAP = 2  # RowsContent.row_gap default (compact layout)
#: Dot diameter / center pitch for the metric-axis dots row (grid + list).
#: DESIGN px — resolve through :func:`dot_diameter` / :func:`dot_pitch` at USE
#: time so the painted dots follow UiScale (a raw literal kept them at the 1.0
#: px on a scaled card — owner report 2026-10-19).
DOT_DIAMETER = 8
DOT_PITCH = 14


def dot_diameter() -> float:
    """Metric-dot diameter in DEVICE px at the live UiScale factor."""
    from sli_ui_toolkit.managers import scaled_px

    return float(scaled_px(DOT_DIAMETER))


def dot_pitch() -> float:
    """Metric-dot center pitch in DEVICE px at the live UiScale factor."""
    from sli_ui_toolkit.managers import scaled_px

    return float(scaled_px(DOT_PITCH))


#: ``metric_scores.score_band`` → the existing severity token trio. ``mid`` is
#: the current band id (``warn`` kept for forward/backward compatibility).
_BAND_SEVERITY: dict[str, str] = {
    "good": "clean",
    "mid": "mild",
    "warn": "mild",
    "bad": "flagged",
}


def _is_dark() -> bool:
    """Current theme darkness for fallback selection (Rule A).

    Keyed ONLY on ``ThemeManager.is_dark()``: a bare manager defaults to
    ``_current_theme='light'`` (``is_dark()`` False), and an
    empty/unregistered palette does NOT imply dark. Callers
    (``stats_strip``, ``grid_view``, ``hover``) delegate here, so every
    ``_fallback_for(light, dark)`` pair resolves light under a bare manager —
    same as the ``_is_dark_theme`` chains in ``toolbar``/``quick_look``.
    """
    try:
        from sli_ui_toolkit.managers import ThemeManager

        return bool(ThemeManager.get_instance().is_dark())
    except Exception:
        # Manager unreachable (no Qt host at all) — mirror the bare-manager
        # default, which is the light theme.
        return False


def _token_color(token: str, fallback_hex: str):
    """Resolve a ThemeManager palette token; fall back when absent."""
    from PySide6.QtGui import QColor

    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        resolved = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if resolved is not None:
            # resolved may be QColor or hex string — normalize to QColor
            return QColor(resolved) if isinstance(resolved, str) else resolved
    except Exception:
        pass
    return QColor(fallback_hex)


def _severity_color(sev: str):
    """Paint a severity token; a non-severity (unmeasured/unknown) paints neutral.

    ``UNMEASURED``/``"unknown"`` are NOT failures and NOT "clean": both take the
    muted neutral chip so a dot never claims a measured-good state. There is no
    ``clean`` default here — an unrecognized token is a non-measurement.
    """
    key = str(sev or "").strip().lower()
    pair = _SEVERITY_TOKEN_FALLBACKS.get(key)
    if pair is None:
        return _neutral_color()
    token, dark_fallback = pair
    fallback = dark_fallback if _is_dark() else _SEVERITY_FALLBACKS_LIGHT.get(key, dark_fallback)
    return _token_color(token, fallback)


def _error_line_color():
    """Rejected/error line: ``gallery.status.danger`` → light/dark fallback."""
    token, dark_fallback = _ERROR_LINE_TOKEN_FALLBACK
    fallback = dark_fallback if _is_dark() else _ERROR_LINE_FALLBACK_LIGHT
    return _token_color(token, fallback)


def _accent_color():
    """Badge/underline accent with the frozen chain + light/dark fallback.

    ``gallery.accent.bar`` → ``accent`` → ``#0078D4`` (light) / ``#0096FF`` (dark).
    Used for hover underline, the provenance pill and selection chrome — NOT for
    metric dots since 2026-10-27 (a dot's colour codes its score band; the
    instrument is a tooltip fact only).
    """
    from PySide6.QtGui import QColor

    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        mgr = ThemeManager.get_instance()
        for tok in ("gallery.accent.bar", "accent"):
            resolved = try_resolve_theme_color(mgr, tok)
            if resolved is not None:
                return QColor(resolved) if isinstance(resolved, str) else resolved
    except Exception:
        pass
    return QColor(_ACCENT_TOKEN_FALLBACK[1] if _is_dark() else _ACCENT_FALLBACK_LIGHT)


def _neutral_color():
    """Muted dot for the PENDING affordance (``gallery.status.neutral``).

    Painted once per ASKED axis while no axis of the set carries a score ("still
    measuring"); as soon as one does, ``metric_dots_for_item`` drops every gap
    record, so this colour stops being used for that card. Lower alpha keeps the
    placeholder visually subordinate to measured dots.
    """
    color = _token_color("gallery.status.neutral", "#8a8a8a")
    try:
        color.setAlpha(120)
    except Exception:
        pass
    return color


def _metric_axis_label(axis_id: str, translate=None) -> str:
    """Localized ``image_gallery.metric.<axis>`` → registry label → id."""
    default = axis_id
    try:
        from tabs.image_gallery.services.metric_scores import spec_for

        spec = spec_for(axis_id)
        if spec is not None and spec.label:
            default = spec.label
    except Exception:
        pass
    if callable(translate):
        try:
            return str(translate(f"image_gallery.metric.{axis_id}", default))
        except Exception:
            pass
    return default


def layout_dots(
    n: int,
    x_right: float,
    y_center: float,
    avail_width: float,
) -> list[tuple[float, float]]:
    """Right-aligned wrapped dot block — the ONE placement authority.

    Pure geometry (no widgets): too many dots to fit *avail_width* at the live
    ``dot_pitch()`` (design ``DOT_PITCH`` × UiScale) WRAP into multiple rows
    instead of shrinking the pitch. ``cols`` is the
    floor of ``avail_width / DOT_PITCH`` (at least 1), rows fill top-to-bottom,
    every row is right-aligned to the SAME ``x_right`` (a partially filled last
    row sits flush right), and the whole block is vertically centered on
    ``y_center`` (the filename line) with ``DOT_PITCH`` between row centers.

    Returns a list of ``(x_center, y_center)`` parallel to the dot index, so
    index ``i``'s center is at ``result[i]``. Shared by the grid card
    (``ui/card/painters.py``) and the list row (``ui/list/painters.py``) so both
    surfaces wrap identically.
    """
    try:
        count = int(n)
    except Exception:
        return []
    if count <= 0:
        return []
    try:
        x_right = float(x_right)
        y_top_center = float(y_center)
        avail = float(avail_width)
    except Exception:
        return []
    # DEVICE px at the live factor — the callers' avail/right edge are device px.
    pitch = dot_pitch()
    try:
        cols = max(1, int(avail // pitch))
    except Exception:
        cols = 1
    rows = -(-count // cols)  # ceil(count / cols) without floats
    row_step = pitch
    first_y = y_top_center - (rows - 1) * row_step / 2.0
    centers: list[tuple[float, float]] = []
    for index in range(count):
        row = index // cols
        col = index % cols
        # Dots in THIS row (the last row may be partial); all flush right.
        in_row = min(cols, count - row * cols)
        x = x_right - (in_row - 1 - col) * pitch
        y = first_y + row * row_step
        centers.append((float(x), float(y)))
    return centers


def _is_measured(record) -> bool:  # type: ignore[no-untyped-def]
    """Does this ``AxisValue`` carry a measurement (not a ``status="gap"``)?"""
    try:
        if str(getattr(record, "status", "") or "") == "gap":
            return False
        return getattr(record, "value", None) is not None
    except Exception:
        return False


def _is_analyzing(item) -> bool:
    """Is this item's analysis actually in flight right now (the pill's truth)?

    The placeholder dot set is an AFFORDANCE for work in progress, so it must
    appear only while ``ActivityPulse`` shows that work (the same
    ``activity_of`` source as the "Analyzing" pill). A finished card with no
    measured axes paints nothing.
    """
    try:
        from tabs.image_gallery.services.activity import ACTIVE_PHASES, activity_of

        got = activity_of(item)
        return bool(got) and str(got[0]) in ACTIVE_PHASES
    except Exception:
        return False


def metric_dots_for_item(
    item: GalleryItem,
    mode: object = None,
    domain: object = None,
    translate=None,
    profile=None,
) -> tuple[tuple[object, ...], tuple[tuple[str, int | None], ...]]:
    """Per-metric quality dots: the MEASURED axes of the ACTIVE axis set.

    Dot axis set = ``profile_judged.scorecard_axis_ids(mode, profile=profile)``
    — the registry report order followed by the axes the judge NAMED for this
    series (P7-C). ``profile`` is the ACTIVE metric profile; it wins over *mode*
    when given, so the dots show exactly the axes the rows, the rank and the AI
    scorecard use. ``profile=None`` reproduces the mode mapping (registry only).
    Per-dot value = the per-axis ``AxisValue`` from ``analysis.read.read_axes``
    (0–100; AI scorecard vs local detectors), so the number carries its own
    producer and provenance. Color = ``metric_scores.score_band`` mapped onto
    the existing severity tokens for EVERY measured dot, whatever measured it:
    the colour codes the SCORE, so one number is one colour across instruments.

    (Superseded 2026-10-27: the P7-C "accent = the judge's instrument" marker is
    cancelled — every MEASURED judge dot painted ``_accent_color()``, so a
    90/60/20 scorecard read as three identical blue dots and the card could only
    be understood by hovering. The instrument still reaches the user through the
    TEXT: ``judged_axis_label`` keeps ``name · measured by the judge`` in the
    tooltip. ``_accent_color`` stays for hover/selection chrome.)

    TWO PHASES, this one decision (owner, 2026-10-22) — a gap is not a dot once
    anything exists to dot about:

    * **pending** — no axis in the asked set carries a value (every record is a
      ``status="gap"``): paint the WHOLE asked set in the muted neutral
      (``_neutral_color``), the "still measuring" affordance. Camera therefore
      shows its 8 grey dots exactly as before.
    * **measured** — at least one record is measured: paint ONLY the measured
      axes, in asked-set order. Gaps are suppressed (no grey placeholder, no
      reserved space), so a partially measured card counts its real metrics and
      each landing axis adds one dot; the count never returns to the
      placeholder set.

    Grid card and list row both read this function's ``(colors, infos)``
    (``ui/card.py`` / ``ui/list/card.py``), so the rule has exactly one
    implementation — the painters only place what they are handed.

    Returns ``(colors, infos)`` where ``infos`` is the parallel tuple of
    ``(localized_label, score | None)`` used by the hover tooltip.

    Since P7-C the axis set is BOTH halves (``scorecard_axis_ids``: the registry
    axes plus the names the judge invented), read through the one read path so a
    judge dot carries the same measured/gap record as a registry dot. A judge
    dot is never blended into the registry indicator unlabeled: an invented name
    has no registry label, so its tooltip carries ``name · measured by the
    judge``. A registry axis keeps its registry label (the P5/P7-A parity) even
    when this context has no local producer for it. Both halves are COLOURED by
    their band (see above) — the instrument is a text fact, not a colour.
    """
    try:
        from tabs.image_gallery.analysis.read import read_axes
        from tabs.image_gallery.services.metric_scores import score_band
        from tabs.image_gallery.services.profile_judged import scorecard_axis_ids
        from tabs.image_gallery.ui.quick_look.metrics.judged import (
            is_judged_axis,
            judged_axis_label,
        )

        axes = scorecard_axis_ids(mode, profile=profile)
        records = read_axes(item, domain=domain, axes=axes, profile=profile)
    except Exception:
        return (), ()
    measured = tuple(record for record in records if _is_measured(record))
    if measured:
        # Measured phase: the gaps have no dot at all — a placeholder would
        # re-claim the count the affordance just handed over (owner 2026-10-22).
        records = measured
    elif not _is_analyzing(item):
        # Nothing measured AND nothing running: the analysis set is a LIE here
        # (owner: the 8 dots stayed after "Analyzing" disappeared, so they read
        # as eight pending criteria that never finish). An idle card with no
        # measured axis paints no dots at all.
        return (), ()
    colors: list[object] = []
    infos: list[tuple[str, int | None]] = []
    for record in records:
        axis_id = record.axis
        # A judge-INVENTED name has no registry label, so its label carries the
        # name and the provenance; a registry axis keeps its registry label
        # (P5/P7-A parity), even when the judge is the only instrument able to
        # measure it in this context. Provenance lives in the TEXT only — the
        # colour below is the score's, never the instrument's (owner 2026-10-27).
        if is_judged_axis(axis_id, profile=profile):
            label = judged_axis_label(str(axis_id), profile=profile, translate=translate)
        else:
            label = _metric_axis_label(str(axis_id), translate)
        score: int | None = int(record.value) if record.status == "ok" else None
        if score is None:
            colors.append(_neutral_color())
            infos.append((label, None))
            continue
        try:
            band = str(score_band(score)).lower()
        except Exception:
            band = "bad"
        colors.append(_severity_color(_BAND_SEVERITY.get(band, "unmeasured")))
        infos.append((label, score))
    return tuple(colors), tuple(infos)


#: Tooltip value for a dot that carries no measurement. Localized rows use
#: ``image_gallery.quick_look.not_measured``; the dot tooltip is built from the
#: geometry's ``(label, score)`` pair (no overlay/translator reaches it), so it
#: says the same fact in the shared English wording.
_UNMEASURED_TOOLTIP = "not measured"


def dot_tooltip_text(info: tuple[str, int | None]) -> str:
    """Hover text for one dot: ``"<label>: <N>%"`` or ``"<label>: not measured"``.

    An absent score is stated as a non-measurement — never a ``0%`` and never a
    silent dash that reads as "zero" (read-boundary contract).
    """
    try:
        label, score = info
    except Exception:
        return ""
    if score is None:
        return f"{label}: {_UNMEASURED_TOOLTIP}"
    try:
        return f"{label}: {int(score)}%"
    except Exception:
        return f"{label}: {_UNMEASURED_TOOLTIP}"


def _dots_for_item(
    item: GalleryItem,
    mode: object = None,
    domain: object = None,
    translate=None,
    profile=None,
) -> tuple[str, tuple[object, ...]]:
    """Backward-compatible ``(dot_text, colors)`` over ``metric_dots_for_item``.

    ``_DOTS_TEXT`` is kept for old callers/tests but is no longer authoritative:
    the actual dot count comes from the measured-axis set of the active
    *profile* (else *mode*), or from the whole asked set while nothing in it is
    measured yet (the pending affordance — see ``metric_dots_for_item``).
    """
    colors, _infos = metric_dots_for_item(
        item, mode=mode, domain=domain, translate=translate, profile=profile
    )
    return _DOTS_TEXT, colors
