"""Video editor dialog geometry derived from export/settings content.

Every value here is authored in DESIGN px and resolved through ``scaled_px``
at use time — never at import. The module-level ``*_PX`` constants are the
design values; ``video_editor_geometry_policy()`` is built per call so its
height floor follows a live ``UiScale`` change instead of freezing at the
factor of the first import.

Fit-to-screen
-------------
The dialog's *content*, not just its window, has a vertical floor: the
preview/settings row on top, toolbar + timeline below. That floor used to be
fixed, which a 720p screen cannot show once the CSD title band and the
UiScale factor are added (measured offscreen: 730 px of content minimum at
factor 1.0, 873 px at 1.25, against 680 available on 1280x720). A final
``setMinimumSize`` cannot fix that — Qt raises the window back to the layout
minimum after ``show()`` — so :func:`compute_video_editor_fit` budgets the
measured full-density minimum against the target screen and
:func:`apply_video_editor_fit` shrinks the panes accordingly. Spacious screens
get the unchanged design values. The window-side half of the idiom is
``GeometryApplyPolicy.fit_screen`` (shared_toolkit layout_sizing); this module
owns the content half and the policy flag follows the plan.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtWidgets import QApplication

from tabs.host_helpers import (
    GeometryApplyPolicy,
    apply_dialog_geometry,
)
from tabs.image_compare.plugins.video_editor.geometry_helpers import (
    clamp,
    tab_widget_intrinsic_width,
    widget_width_hint,
)
from sli_ui_toolkit.managers import scaled_px

MIN_VIDEO_EDITOR_PREVIEW_WIDTH_PX = 240
MIN_VIDEO_EDITOR_PREVIEW_HEIGHT_PX = 135
MIN_VIDEO_EDITOR_SETTINGS_WIDTH_PX = 350
MAX_VIDEO_EDITOR_SETTINGS_WIDTH_PX = 650
VIDEO_EDITOR_TOP_MARGIN_PX = 20
VIDEO_EDITOR_TOP_HORIZONTAL_SPACING_PX = 10
# ``content_layout`` around TopTabHost in ``build_settings_panel`` (12 + 12).
VIDEO_EDITOR_TABS_CONTENT_H_MARGINS_PX = 24
MIN_VIDEO_EDITOR_DIALOG_HEIGHT_PX = 600

# Dialog/panes design px — single source for ``dialog/shell.py`` and
# ``dialog/sections.py`` (they used to spell these out inline).
VIDEO_EDITOR_INITIAL_WIDTH_PX = 1200
VIDEO_EDITOR_INITIAL_HEIGHT_PX = 850
VIDEO_EDITOR_TOOLBAR_HEIGHT_PX = 50
MIN_VIDEO_EDITOR_TIMELINE_HEIGHT_PX = 210
MIN_VIDEO_EDITOR_BOTTOM_CONTAINER_HEIGHT_PX = 250

# Settings panel top block (resolution / fps / preview-quality rows) and the
# compact density a short screen may switch it to.
VIDEO_EDITOR_SETTINGS_STATIC_SPACING_PX = 14
VIDEO_EDITOR_SETTINGS_STATIC_MARGINS_PX = (12, 12, 12, 10)
VIDEO_EDITOR_SETTINGS_STATIC_ROW_COUNT = 3
VIDEO_EDITOR_SETTINGS_STATIC_COMPACT_SPACING_PX = 6
VIDEO_EDITOR_SETTINGS_STATIC_COMPACT_MARGINS_PX = (8, 6, 8, 6)

# Fit floor: below this the timeline stops being usable, so the fit stops
# there and the window keeps a content minimum taller than the screen rather
# than collapsing the timeline. The preview keeps its design minimum — the
# settings panel is the taller pane, so ``max(preview, panel)`` never lets a
# preview shrink buy vertical room.
MIN_VIDEO_EDITOR_FIT_TIMELINE_HEIGHT_PX = 60

# Decoration constant, NOT design px: the CSD-wrapped window grows by this band
# on EACH side of the size passed to ``resize`` (measured offscreen: 1200x850
# -> 1216x866 at factor 1.0 and 1.25 alike). Subtracted from the screen budget
# so the shown window fits ``availableGeometry()``.
VIDEO_EDITOR_CSD_BAND_PX = 8

_FIT_BASELINE_ATTR = "_video_editor_fit_baseline"
_FIT_APPLIED_ATTR = "_video_editor_fit_applied"


def settings_static_compact_saving_px() -> int:
    """Design-px height the compact settings density saves on the top block."""
    gaps = max(0, VIDEO_EDITOR_SETTINGS_STATIC_ROW_COUNT - 1)
    saving = (
        VIDEO_EDITOR_SETTINGS_STATIC_SPACING_PX
        - VIDEO_EDITOR_SETTINGS_STATIC_COMPACT_SPACING_PX
    ) * gaps
    full_top, full_bottom = (
        VIDEO_EDITOR_SETTINGS_STATIC_MARGINS_PX[1],
        VIDEO_EDITOR_SETTINGS_STATIC_MARGINS_PX[3],
    )
    compact_top, compact_bottom = (
        VIDEO_EDITOR_SETTINGS_STATIC_COMPACT_MARGINS_PX[1],
        VIDEO_EDITOR_SETTINGS_STATIC_COMPACT_MARGINS_PX[3],
    )
    return saving + (full_top + full_bottom) - (compact_top + compact_bottom)


@dataclass(frozen=True)
class VideoEditorFit:
    """How the dialog's vertical budget is divided on one screen.

    ``shrink`` False ⇒ the full-density layout fits (every field is the design
    value, applying the plan is a no-op). ``fits_screen`` False ⇒ even the fit
    floors do not fit; the plan is still applied, best effort.
    """

    available_width: int | None = None
    available_height: int | None = None
    shrink: bool = False
    fits_screen: bool = True
    compact_settings: bool = False
    preview_min_height: int = 0
    settings_min_height: int | None = None
    timeline_min_height: int = 0
    bottom_min_height: int = 0
    splitter_min_height: int = 0
    dialog_min_height: int = 0
    initial_width: int = 0
    initial_height: int = 0

    @property
    def screen_constrained(self) -> bool:
        """True when the screen forced this plan (the policy's ``fit_screen``)."""
        return self.shrink


@dataclass(frozen=True)
class _Budget:
    """Measured full-density vertical parts (px at the live UiScale factor)."""

    chrome_height: int  # decorated-window band around the layout (CSD)
    top_height: int  # preview/settings row
    bottom_height: int  # toolbar + timeline pane
    handle: int  # splitter grip
    settings_height: int

    def merged(self, other: "_Budget") -> "_Budget":
        """Per-field maximum — keeps the full-density baseline stable."""
        return _Budget(
            chrome_height=max(self.chrome_height, other.chrome_height),
            top_height=max(self.top_height, other.top_height),
            bottom_height=max(self.bottom_height, other.bottom_height),
            handle=max(self.handle, other.handle),
            settings_height=max(self.settings_height, other.settings_height),
        )

    @property
    def required_height(self) -> int:
        return self.chrome_height + self.top_height + self.handle + self.bottom_height


def available_screen_size(dialog=None) -> tuple[int, int] | None:
    """``availableGeometry()`` of ``dialog``'s screen as ``(width, height)``.

    Mirrors the ``shared_toolkit.ui.layout_sizing`` rule (``window().screen()``,
    primary as fallback) because a tab may not import the platform package
    (``tests/contracts/test_tabs_isolation.py``).
    """
    screen = None
    window = getattr(dialog, "window", None)
    window = window() if callable(window) else None
    if window is not None and hasattr(window, "screen"):
        screen = window.screen()
    if screen is None:
        screen = QApplication.primaryScreen()
    if screen is None:
        return None
    available = screen.availableGeometry()
    return max(1, int(available.width())), max(1, int(available.height()))


def _measure_budget(dialog) -> _Budget | None:
    """Measure the full-density vertical parts, ``None`` for a pane-less stub."""
    splitter = getattr(dialog, "vertical_splitter", None)
    top = getattr(dialog, "top_container", None)
    bottom = getattr(dialog, "bottom_container", None)
    panel = getattr(dialog, "settings_panel", None)
    if splitter is None or top is None or bottom is None or panel is None:
        return None

    try:
        dialog.ensurePolished()
    except Exception:
        return None
    layout = dialog.layout() if hasattr(dialog, "layout") else None
    margins = layout.contentsMargins() if layout is not None else None
    chrome = int(margins.top()) + int(margins.bottom()) if margins is not None else 0
    top.ensurePolished()
    bottom.ensurePolished()
    panel.ensurePolished()
    return _Budget(
        chrome_height=max(0, chrome),
        top_height=int(top.minimumSizeHint().height()),
        bottom_height=int(bottom.minimumHeight()),
        handle=int(splitter.handleWidth()),
        settings_height=int(panel.minimumSizeHint().height()),
    )


def _baseline_budget(dialog) -> _Budget | None:
    """Full-density measurements, captured once and never revised downward.

    A later pass runs on a layout a previous fit may have shrunk, so live hints
    describe the SHRUNK panes and cannot tell a small screen from a small
    window. The baseline grows to the largest values seen (the first pass can
    run before the window decoration adds its band) and is then stable.
    """
    live = _measure_budget(dialog)
    if live is None:
        return None
    cached = getattr(dialog, _FIT_BASELINE_ATTR, None)
    budget = live if cached is None else cached.merged(live)
    try:
        setattr(dialog, _FIT_BASELINE_ATTR, budget)
    except Exception:
        pass
    return budget


def compute_video_editor_fit(
    dialog=None,
    available: tuple[int, int] | None = None,
) -> VideoEditorFit:
    """Budget the dialog against the screen it will open on.

    ``available`` overrides the resolved screen (tests). Without a screen (no
    ``QApplication``) or without the editor panes to measure, the plan is the
    plain design-scale one (``shrink=False``).
    """
    full = VideoEditorFit(
        preview_min_height=scaled_px(MIN_VIDEO_EDITOR_PREVIEW_HEIGHT_PX),
        timeline_min_height=scaled_px(MIN_VIDEO_EDITOR_TIMELINE_HEIGHT_PX),
        bottom_min_height=scaled_px(MIN_VIDEO_EDITOR_BOTTOM_CONTAINER_HEIGHT_PX),
        dialog_min_height=scaled_px(MIN_VIDEO_EDITOR_DIALOG_HEIGHT_PX),
        initial_width=scaled_px(VIDEO_EDITOR_INITIAL_WIDTH_PX),
        initial_height=scaled_px(VIDEO_EDITOR_INITIAL_HEIGHT_PX),
    )
    screen = available if available is not None else available_screen_size(dialog)
    if not screen:
        return full

    avail_w, avail_h = max(1, int(screen[0])), max(1, int(screen[1]))
    band = 2 * VIDEO_EDITOR_CSD_BAND_PX
    screen_fields = {
        "available_width": avail_w,
        "available_height": avail_h,
        # Opening size, capped so the decorated window fits the screen.
        "initial_width": min(full.initial_width, max(1, avail_w - band)),
        "initial_height": min(full.initial_height, max(1, avail_h - band)),
    }

    budget = _baseline_budget(dialog) if dialog is not None else None
    if budget is None or budget.required_height <= avail_h:
        # Nothing to fit (or nothing measurable): design values, unchanged.
        return replace(full, **screen_fields)

    if budget.settings_height > 0:
        compact_saving = scaled_px(settings_static_compact_saving_px())
        top_after = max(0, budget.top_height - compact_saving)
        settings_after = max(0, budget.settings_height - compact_saving)
    else:
        compact_saving = 0
        top_after = budget.top_height
        settings_after = 0

    toolbar = scaled_px(VIDEO_EDITOR_TOOLBAR_HEIGHT_PX)
    timeline_floor = scaled_px(MIN_VIDEO_EDITOR_FIT_TIMELINE_HEIGHT_PX)
    bottom_floor = toolbar + timeline_floor
    # Room left for the bottom pane once chrome + top + grip + toolbar are paid
    # for; never above the design minimum and never below the floor.
    allowed_bottom = avail_h - (
        budget.chrome_height + top_after + budget.handle + toolbar
    )
    bottom_min = clamp(
        allowed_bottom,
        minimum=min(bottom_floor, budget.bottom_height),
        maximum=budget.bottom_height,
    )
    timeline_min = max(timeline_floor, bottom_min - toolbar)

    fitted = replace(
        budget,
        top_height=top_after,
        bottom_height=bottom_min,
        settings_height=settings_after,
    )
    return replace(
        full,
        **screen_fields,
        shrink=True,
        fits_screen=fitted.required_height <= avail_h,
        compact_settings=compact_saving > 0,
        settings_min_height=settings_after if budget.settings_height > 0 else None,
        timeline_min_height=timeline_min,
        bottom_min_height=bottom_min,
        splitter_min_height=top_after + budget.handle + bottom_min,
        dialog_min_height=min(full.dialog_min_height, avail_h),
    )


def apply_settings_static_density(layout, *, compact: bool) -> None:
    """Set the settings top block to the full or compact density."""
    if layout is None:
        return
    spacing = VIDEO_EDITOR_SETTINGS_STATIC_SPACING_PX
    if compact:
        spacing = VIDEO_EDITOR_SETTINGS_STATIC_COMPACT_SPACING_PX
    left, top, right, bottom = (
        VIDEO_EDITOR_SETTINGS_STATIC_COMPACT_MARGINS_PX
        if compact
        else VIDEO_EDITOR_SETTINGS_STATIC_MARGINS_PX
    )
    layout.setSpacing(scaled_px(spacing))
    layout.setContentsMargins(
        scaled_px(left), scaled_px(top), scaled_px(right), scaled_px(bottom)
    )


def apply_video_editor_fit(
    dialog,
    fit: VideoEditorFit | None = None,
) -> VideoEditorFit:
    """Apply ``fit`` to the dialog's panes (content floors + density).

    Idempotent: a full-scale plan restores the design minimums if an earlier
    pass shrank them. No resize happens here — the opening size is
    :func:`apply_initial_size`, which must run after the minimum is applied.
    """
    fit = fit if fit is not None else compute_video_editor_fit(dialog)
    if dialog is None:
        return fit

    static_layout = getattr(dialog, "settings_static_layout", None)
    apply_settings_static_density(static_layout, compact=fit.compact_settings)

    preview = getattr(dialog, "preview_label", None)
    panel = getattr(dialog, "settings_panel", None)
    scroll_area = getattr(dialog, "scroll_area", None)
    bottom = getattr(dialog, "bottom_container", None)
    splitter = getattr(dialog, "vertical_splitter", None)
    applied = bool(getattr(dialog, _FIT_APPLIED_ATTR, False))

    if fit.shrink:
        if preview is not None and fit.preview_min_height > 0:
            preview.setMinimumHeight(fit.preview_min_height)
        if panel is not None and fit.settings_min_height is not None:
            panel.setMinimumHeight(fit.settings_min_height)
        if scroll_area is not None and fit.timeline_min_height > 0:
            scroll_area.setMinimumHeight(fit.timeline_min_height)
        if bottom is not None and fit.bottom_min_height > 0:
            bottom.setMinimumHeight(fit.bottom_min_height)
        if splitter is not None and fit.splitter_min_height > 0:
            splitter.setMinimumHeight(fit.splitter_min_height)
    elif applied:
        # Screen got roomier (or the plan no longer shrinks): restore the
        # design floors so the dialog behaves exactly as before.
        if preview is not None:
            preview.setMinimumHeight(scaled_px(MIN_VIDEO_EDITOR_PREVIEW_HEIGHT_PX))
        if panel is not None:
            panel.setMinimumHeight(0)
        if scroll_area is not None:
            scroll_area.setMinimumHeight(scaled_px(MIN_VIDEO_EDITOR_TIMELINE_HEIGHT_PX))
        if bottom is not None:
            bottom.setMinimumHeight(
                scaled_px(MIN_VIDEO_EDITOR_BOTTOM_CONTAINER_HEIGHT_PX)
            )
        if splitter is not None:
            splitter.setMinimumHeight(0)

    try:
        setattr(dialog, _FIT_APPLIED_ATTR, bool(fit.shrink))
    except Exception:
        pass

    layout = dialog.layout() if hasattr(dialog, "layout") else None
    if layout is not None:
        layout.invalidate()
    return fit


def apply_initial_size(dialog, fit: VideoEditorFit | None = None) -> VideoEditorFit:
    """Resize a hidden dialog to the plan's opening size (visible: no-op).

    Runs AFTER the minimum is applied: the CSD wrapper re-applies its outer
    band on a geometry round trip, and a resize issued while a stale, larger
    minimum is still in place lands one band too tall.
    """
    fit = fit if fit is not None else compute_video_editor_fit(dialog)
    if dialog is None or fit.initial_width <= 0 or fit.initial_height <= 0:
        return fit
    if hasattr(dialog, "isVisible") and dialog.isVisible():
        return fit
    dialog.resize(fit.initial_width, fit.initial_height)
    return fit


def video_editor_geometry_policy(
    fit: VideoEditorFit | None = None,
) -> GeometryApplyPolicy:
    """Apply policy for the top-row geometry pass, built per call.

    ``minimum_floor`` resolves its design-px height through ``scaled_px`` here
    rather than being frozen into a module-level policy at import. The floor is
    the fit plan's (screen-capped) height; ``fit_screen`` follows the plan — the
    plan bounds the CONTENT, the policy flag only bounds the window, and a
    dialog stub with no panes to fit keeps the design floor.
    """
    if fit is None:
        fit = compute_video_editor_fit()
    floor_height = fit.dialog_min_height or scaled_px(MIN_VIDEO_EDITOR_DIALOG_HEIGHT_PX)
    return GeometryApplyPolicy(
        resize_when_hidden=False,
        update_minimum=True,
        minimum_floor=(0, floor_height),
        width_bounds=None,
        center_on_parent=False,
        fit_screen=fit.screen_constrained,
    )


def _tabs_required_panel_width(dialog) -> int:
    """Tab strip width plus the horizontal margins of its parent layout."""
    tabs = getattr(dialog, "tabs", None)
    width = tab_widget_intrinsic_width(tabs)
    if tabs is None:
        return width

    parent = tabs.parentWidget() if hasattr(tabs, "parentWidget") else None
    layout = parent.layout() if parent is not None else None
    if layout is not None:
        margins = layout.contentsMargins()
        width += int(margins.left()) + int(margins.right())
    else:
        width += scaled_px(VIDEO_EDITOR_TABS_CONTENT_H_MARGINS_PX)
    return width


def compute_settings_panel_width(dialog) -> int:
    minimum = scaled_px(MIN_VIDEO_EDITOR_SETTINGS_WIDTH_PX)
    maximum = scaled_px(MAX_VIDEO_EDITOR_SETTINGS_WIDTH_PX)
    static_width = widget_width_hint(getattr(dialog, "settings_static_container", None))
    tabs_width = _tabs_required_panel_width(dialog)
    export_width = widget_width_hint(getattr(dialog, "btn_export", None))

    optimal = max(minimum, static_width, tabs_width, export_width)
    return clamp(optimal, minimum=minimum, maximum=maximum)


def _pane_row_min_width(
    *,
    left_min: int,
    spacing: int,
    right_min: int,
    outer_margins: int = 0,
) -> int:
    """Minimum width of a left|right pane row: outer + left + spacing + right.

    Kept local on purpose: the shared ``HorizontalPaneMinimum`` is a
    platform-internal layout primitive and is deliberately NOT re-exported
    through ``tabs.host_helpers`` (the tab-isolation seam). A tab that needs
    this trivial sum owns it.
    """
    return outer_margins + left_min + spacing + right_min


def compute_minimum_dialog_width(settings_width: int) -> int:
    return _pane_row_min_width(
        left_min=scaled_px(MIN_VIDEO_EDITOR_PREVIEW_WIDTH_PX),
        spacing=scaled_px(VIDEO_EDITOR_TOP_HORIZONTAL_SPACING_PX),
        right_min=settings_width,
        outer_margins=scaled_px(VIDEO_EDITOR_TOP_MARGIN_PX),
    )


def apply_top_row_geometry(dialog) -> int:
    # Width first: its measurement must happen on the layout the dialog was
    # built with — a layout activation from the fit pass resizes children to
    # their minimums and would shrink the measured panel width.
    settings_width = compute_settings_panel_width(dialog)
    dialog.settings_panel.setMinimumWidth(scaled_px(MIN_VIDEO_EDITOR_SETTINGS_WIDTH_PX))
    dialog.settings_panel.setFixedWidth(settings_width)

    fit = compute_video_editor_fit(dialog)
    apply_video_editor_fit(dialog, fit)

    min_dialog_width = compute_minimum_dialog_width(settings_width)
    apply_dialog_geometry(
        dialog,
        min_dialog_width,
        fit.dialog_min_height,
        policy=video_editor_geometry_policy(fit),
    )
    apply_initial_size(dialog, fit)
    return settings_width
