"""Selection helpers for the Session Picker recent shelf."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor
from sli_ui_toolkit.widgets import Button

from services.io.recent_projects import VIEW_LIST, RecentProjectRecord
from tabs.session_picker.recent.layout import (
    GRID_CARD_H,
    GRID_CARD_W,
    ITEMS_MARGIN,
    ITEMS_MARGIN_RIGHT,
    ITEMS_SPACING,
    LIST_CARD_H,
    row_stride,
)
from ui.theming import resolve_theme_color

# Pastel red for list cards whose project file is missing (cards.py).
_MISSING_LIST_BG = QColor(242, 190, 190)

# Blend accent toward Base — ~half visual punch → soft “постельный” blue.
_SELECTION_PASTEL_MIX = 0.62


def _theme_manager_or_none(theme_manager=None):
    if theme_manager is not None:
        return theme_manager
    try:
        from sli_ui_toolkit.ui.theme_manager import ThemeManager

        return ThemeManager.get_instance()
    except Exception:
        return None


def _raw_accent(theme_manager=None) -> QColor:
    tm = _theme_manager_or_none(theme_manager)
    if tm is None:
        color = QColor("#0078D4")
    else:
        color = QColor(resolve_theme_color(tm, "accent"))
        if not color.isValid():
            color = QColor(resolve_theme_color(tm, "Highlight"))
    if not color.isValid():
        color = QColor("#0078D4")
    color.setAlpha(255)
    return color


def _mix_toward(src: QColor, dst: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, float(t)))
    out = QColor(
        int(round(src.red() * (1.0 - t) + dst.red() * t)),
        int(round(src.green() * (1.0 - t) + dst.green() * t)),
        int(round(src.blue() * (1.0 - t) + dst.blue() * t)),
    )
    out.setAlpha(255)
    return out


def selection_accent_color(theme_manager=None) -> QColor:
    """Soft pastel from app ``accent`` (mixed toward ``Base``)."""
    tm = _theme_manager_or_none(theme_manager)
    accent = _raw_accent(tm)
    if tm is None:
        base = QColor("#ffffff")
    else:
        base = QColor(resolve_theme_color(tm, "Base"))
        if not base.isValid():
            base = QColor(resolve_theme_color(tm, "Window"))
        if not base.isValid():
            base = QColor("#ffffff")
    return _mix_toward(accent, base, _SELECTION_PASTEL_MIX)


def apply_card_selected(
    card: Button,
    selected: bool,
    *,
    accent: QColor | None = None,
) -> None:
    """Highlight with pastel accent fill (not toggle CHECKED chrome).

    Locks background while selected so hover/pressed overlays cannot hide the
    fill until the cursor leaves the card (same pattern as onboarding chips).
    """
    # Clear any leftover CHECKED from earlier selection experiments.
    set_checked = getattr(card, "setRegionChecked", None)
    if callable(set_checked):
        regions = getattr(card, "regions", None)
        region_list = regions() if callable(regions) else getattr(card, "_regions", ())
        for region in region_list or ():
            region_id = getattr(region, "id", None)
            group = getattr(region, "group", None)
            if region_id and group == "card":
                try:
                    set_checked(region_id, False, emit=False)
                except TypeError:
                    set_checked(region_id, False)
                break

    set_override = getattr(card, "set_override_bg_color", None)
    set_locked = getattr(card, "set_bg_locked", None)
    if not callable(set_override):
        return
    if selected:
        fill = QColor(accent) if accent is not None else selection_accent_color()
        if not fill.isValid():
            fill = selection_accent_color()
        fill.setAlpha(255)
        set_override(fill)
        if callable(set_locked):
            set_locked(True)
        return
    # Restore base: missing list cards keep the pastel signal; others default.
    if getattr(card, "_recent_missing", False):
        set_override(QColor(_MISSING_LIST_BG))
    else:
        set_override(None)
    if callable(set_locked):
        set_locked(False)


def card_rect_for_index(
    index: int,
    *,
    view_mode: str,
    columns: int,
    host_width: int,
) -> QRect:
    """Content-host geometry for the card at ``index`` (absolute layout)."""
    card_h = LIST_CARD_H if view_mode == VIEW_LIST else GRID_CARD_H
    stride = row_stride(card_h)
    cols = max(1, int(columns))
    if view_mode == VIEW_LIST:
        row = index
        x = ITEMS_MARGIN
        w = max(1, int(host_width) - ITEMS_MARGIN - ITEMS_MARGIN_RIGHT)
    else:
        row, col = divmod(index, cols)
        x = ITEMS_MARGIN + col * (GRID_CARD_W + ITEMS_SPACING)
        w = GRID_CARD_W
    y = ITEMS_MARGIN + row * stride
    return QRect(x, y, w, card_h)


def paths_intersecting_rect(
    records: list[RecentProjectRecord],
    rect: QRect,
    *,
    view_mode: str,
    columns: int,
    host_width: int,
) -> set[str]:
    """Paths whose card geometry intersects ``rect`` in host coordinates."""
    if rect.isEmpty() or not records:
        return set()
    hit: set[str] = set()
    for index, record in enumerate(records):
        geom = card_rect_for_index(
            index,
            view_mode=view_mode,
            columns=columns,
            host_width=host_width,
        )
        if geom.intersects(rect):
            hit.add(record.path)
    return hit


def ctrl_held(modifiers: Qt.KeyboardModifier) -> bool:
    return bool(modifiers & Qt.KeyboardModifier.ControlModifier) or bool(
        modifiers & Qt.KeyboardModifier.MetaModifier
    )


def preview_selection(
    base: set[str],
    band_paths: set[str],
    *,
    additive: bool,
) -> set[str]:
    if additive:
        return set(base) | set(band_paths)
    return set(band_paths)
