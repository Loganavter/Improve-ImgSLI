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
    key = (sev or "clean").lower()
    token, dark_fallback = _SEVERITY_TOKEN_FALLBACKS.get(key, _SEVERITY_TOKEN_FALLBACKS["clean"])
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
    """Muted dot for an axis with no score (``gallery.status.neutral``).

    Lower alpha keeps it visually subordinate to measured dots; the tooltip
    still names the axis (``"<label>: —"``) so the gap reads as a gap.
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


def metric_dots_for_item(
    item: GalleryItem,
    mode: object = None,
    domain: object = None,
    translate=None,
    profile=None,
) -> tuple[tuple[object, ...], tuple[tuple[str, int | None], ...]]:
    """Per-metric quality dots: one dot per applicable MEASURED axis.

    Dot count/order = ``rank_fusion.measured_axes_for(mode, profile=profile)``
    (registry report order). ``profile`` is the ACTIVE metric profile (any
    object with ``.axis_ids``); it wins over *mode* when given, so the dots
    show exactly the axes the rank and the AI scorecard use. ``profile=None``
    reproduces the mode mapping. Per-dot value = the CURRENT domain read
    (``quality_read.domain_axis_scores``, 0–100; AI scorecard vs local
    detectors). Color = ``metric_scores.score_band`` mapped onto the existing
    severity tokens; an unscored axis gets the muted neutral dot.

    Returns ``(colors, infos)`` where ``infos`` is the parallel tuple of
    ``(localized_label, score | None)`` used by the hover tooltip.
    """
    try:
        from tabs.image_gallery.services import quality_read as _quality_read
        from tabs.image_gallery.services.metric_scores import score_band
        from tabs.image_gallery.services.rank_fusion import measured_axes_for

        axes = measured_axes_for(mode, profile=profile)
        scores = _quality_read.domain_axis_scores(item, domain=domain)
    except Exception:
        return (), ()
    colors: list[object] = []
    infos: list[tuple[str, int | None]] = []
    for axis_id in axes:
        label = _metric_axis_label(str(axis_id), translate)
        score: int | None = None
        try:
            raw_score = scores.get(axis_id)
            if raw_score is not None:
                score = int(raw_score)
        except Exception:
            score = None
        if score is None:
            colors.append(_neutral_color())
            infos.append((label, None))
            continue
        try:
            band = str(score_band(score)).lower()
        except Exception:
            band = "bad"
        colors.append(_severity_color(_BAND_SEVERITY.get(band, "clean")))
        infos.append((label, score))
    return tuple(colors), tuple(infos)


def dot_tooltip_text(info: tuple[str, int | None]) -> str:
    """Hover text for one dot: ``"<label>: <N>%"`` (``—`` when unscored)."""
    try:
        label, score = info
    except Exception:
        return ""
    if score is None:
        return f"{label}: —"
    try:
        return f"{label}: {int(score)}%"
    except Exception:
        return f"{label}: —"


def _dots_for_item(
    item: GalleryItem,
    mode: object = None,
    domain: object = None,
    translate=None,
    profile=None,
) -> tuple[str, tuple[object, ...]]:
    """Backward-compatible ``(dot_text, colors)`` over ``metric_dots_for_item``.

    ``_DOTS_TEXT`` is kept for old callers/tests but is no longer authoritative:
    the actual dot count comes from the measured-axis set (the active
    *profile* when given, else *mode*).
    """
    colors, _infos = metric_dots_for_item(
        item, mode=mode, domain=domain, translate=translate, profile=profile
    )
    return _DOTS_TEXT, colors
