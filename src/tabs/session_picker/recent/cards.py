"""Grid and list cards for recent project records."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget
from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons import ButtonRow, VerticalSplit
from sli_ui_toolkit.widgets import Button, ButtonRegion, DrawContext

from ui.theming import try_resolve_theme_color

_TOKEN_MISSING_LIST_BG = "recent.missing.list_background"
_TOKEN_MISSING_COVER_BG = "recent.missing.cover_background"
_TOKEN_HOVER_WASH = "recent.card.hover_wash"


def _themed_or_fallback(
    manager: ThemeManager | None, token: str, fallback: QColor | str
) -> QColor:
    """Resolve theme token with hardcoded fallback to preserve visual."""
    try:
        if manager is not None:
            resolved = try_resolve_theme_color(manager, token)
            if resolved is not None and resolved.isValid():
                return QColor(resolved)
    except Exception:
        pass
    return QColor(fallback) if not isinstance(fallback, QColor) else QColor(fallback)


def _missing_list_bg(manager: ThemeManager | None = None) -> QColor:
    tm = manager if manager is not None else _get_theme_manager_or_none()
    return _themed_or_fallback(tm, _TOKEN_MISSING_LIST_BG, "#f2bebe")


def _missing_cover_bg(manager: ThemeManager | None = None) -> QColor:
    tm = manager if manager is not None else _get_theme_manager_or_none()
    return _themed_or_fallback(tm, _TOKEN_MISSING_COVER_BG, "#ffffff")


def _hover_wash_color(tm: ThemeManager | None) -> QColor:
    # Single token with per-theme hex: light #1a000000 (26 alpha black), dark #26ffffff (38 alpha white)
    if tm is None:
        tm = _get_theme_manager_or_none()
    fallback = "#26ffffff" if (tm is not None and _is_dark(tm)) else "#1a000000"
    # Try dark/light specific fallback if token missing
    if tm is None:
        return QColor(fallback)
    resolved = try_resolve_theme_color(tm, _TOKEN_HOVER_WASH)
    if resolved is not None and resolved.isValid():
        return QColor(resolved)
    return QColor(fallback)


def _transparent_color(manager: ThemeManager | None = None) -> QColor:
    # Used for hover_color to keep BackgroundLayer hover off — transparent wash layer does the hover.
    # Tokenize via generic transparent if present, else hardcoded transparent.
    tm = manager if manager is not None else _get_theme_manager_or_none()
    if tm is not None:
        try:
            resolved = try_resolve_theme_color(tm, "transparent")
            if resolved is not None and resolved.isValid():
                c = QColor(resolved)
                c.setAlpha(0)
                return c
        except Exception:
            pass
    return QColor("#00000000")


def _get_theme_manager_or_none() -> ThemeManager | None:
    try:
        return ThemeManager.get_instance()
    except Exception:
        return None


def _is_dark(tm: ThemeManager) -> bool:
    try:
        return bool(tm.is_dark())
    except Exception:
        return False

from services.io.project_preview import peek_project_preview
from services.io.recent_projects import RecentProjectRecord
from tabs.session_picker.icons import Icon as SessionPickerIcon
from tabs.session_picker.icons import get_icon as get_session_picker_icon
from ui.widgets.shelf.layout import (
    GRID_CARD_H,
    GRID_CARD_W,
    GRID_CONTENT_PADDING,
    GRID_ICON_WEIGHT,
    GRID_TEXT_WEIGHT,
    LIST_CARD_H,
    LIST_CONTENT_PADDING,
)
from ui.widgets.shelf.relative_time import format_relative_opened


def _opaque(color: QColor) -> QColor:
    out = QColor(color)
    out.setAlpha(255)
    return out


def _rounded_rect_path(rect: QRectF, radii: tuple[float, float, float, float]) -> QPainterPath:
    """Rounded-rect path with per-corner radii (tl, tr, br, bl)."""
    max_r = min(rect.width(), rect.height()) / 2.0
    tl, tr, br, bl = (max(0.0, min(float(r), max_r)) for r in radii)
    path = QPainterPath()
    path.moveTo(rect.left() + tl, rect.top())
    path.lineTo(rect.right() - tr, rect.top())
    if tr > 0:
        path.arcTo(
            rect.right() - 2 * tr, rect.top(), 2 * tr, 2 * tr, 90.0, -90.0
        )
    path.lineTo(rect.right(), rect.bottom() - br)
    if br > 0:
        path.arcTo(
            rect.right() - 2 * br, rect.bottom() - 2 * br, 2 * br, 2 * br, 0.0, -90.0
        )
    path.lineTo(rect.left() + bl, rect.bottom())
    if bl > 0:
        path.arcTo(
            rect.left(), rect.bottom() - 2 * bl, 2 * bl, 2 * bl, 270.0, -90.0
        )
    path.lineTo(rect.left(), rect.top() + tl)
    if tl > 0:
        path.arcTo(
            rect.left(), rect.top(), 2 * tl, 2 * tl, 180.0, -90.0
        )
    path.closeSubpath()
    return path


def _card_hover_wash(painter: QPainter, ctx: DrawContext, tm: ThemeManager) -> None:
    """``overlay_painter=`` callback: translucent wash over the whole card.

    Runs in the widget-scoped pass, after every region layer, so the wash
    sits over the preview pixmap and the text rows instead of being hidden
    behind them. Regions keep a transparent ``hover_color`` so the stock
    ``BackgroundLayer`` hover (an opaque repaint under the content) stays
    off — this wash is the only hover effect.
    """
    if ctx.effective_bg_locked or ctx.hovered_region_id is None:
        return
    color = _hover_wash_color(tm)
    radii = ctx.corner_radii or (0, 0, 0, 0)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(color))
    painter.drawPath(_rounded_rect_path(ctx.rect, radii))
    painter.restore()


def icon_for_record(record: RecentProjectRecord, context=None):
    if context is not None and record.session_types:
        try:
            icon = context.call_service("get_tab_icon", record.session_types[0])
        except RuntimeError:
            icon = None
        if icon is not None and not icon.isNull():
            return icon
    return get_session_picker_icon(SessionPickerIcon.ADD)


def localize_session_type(session_type: str, tr: Callable[..., str]) -> str:
    fallback = session_type.replace("_", " ").title()
    return tr(f"types.{session_type}", fallback)


def format_session_types(session_types: tuple[str, ...], tr: Callable[..., str]) -> str:
    if not session_types:
        return ""
    return ", ".join(localize_session_type(st, tr) for st in session_types)


def preview_for_record(record: RecentProjectRecord) -> QPixmap | None:
    try:
        return peek_project_preview(record.path)
    except Exception:
        return None


def _attach_record(
    card: Button,
    record: RecentProjectRecord,
    *,
    missing: bool,
) -> None:
    """Keep live record pointers on the card so handlers survive in-place updates."""
    card._recent_record = record
    card._recent_missing = missing
    card.setProperty("recent_path", record.path)


def _cover_region(
    record: RecentProjectRecord,
    *,
    missing: bool,
    context=None,
    corner_radii: tuple[int, int, int, int],
    weight: float,
    icon_size_px: int,
) -> ButtonRegion:
    # Hover is the widget-scoped wash layer, not the opaque BackgroundLayer
    # repaint — transparent hover_color keeps the preview image from being
    # double-shaded under the wash.
    if missing:
        return ButtonRegion(
            id="cover",
            icon=get_session_picker_icon(SessionPickerIcon.MISSING_WARNING),
            icon_size_px=max(36, icon_size_px),
            weight=weight,
            group="card",
            corner_radii=corner_radii,
            override_bg_color=_opaque(_missing_cover_bg()),
            bg_locked=True,
        )
    thumb = preview_for_record(record)
    if thumb is not None and not thumb.isNull():
        return ButtonRegion(
            id="cover",
            pixmap=thumb,
            image_fill="cover",
            weight=weight,
            group="card",
            corner_radii=corner_radii,
            hover_color=_transparent_color(),
        )
    return ButtonRegion(
        id="cover",
        icon=icon_for_record(record, context),
        icon_size_px=icon_size_px,
        weight=weight,
        group="card",
        corner_radii=corner_radii,
        hover_color=_transparent_color(),
    )


def _cover_update_kwargs(region: ButtonRegion) -> dict[str, Any]:
    return {
        "icon": region.icon,
        "pixmap": region.pixmap,
        "image_fill": region.image_fill,
        "icon_size_px": region.icon_size_px,
        "override_bg_color": region.override_bg_color,
        "bg_locked": region.bg_locked,
        "weight": region.weight,
        "corner_radii": region.corner_radii,
        "group": region.group,
    }


def grid_text_rows(
    record: RecentProjectRecord,
    *,
    missing: bool,
    tr: Callable[..., str],
) -> list[ButtonRow]:
    rows = [
        ButtonRow(
            text=record.display_name,
            size=13,
            weight="bold",
            h_align=Qt.AlignmentFlag.AlignLeft,
            marquee=True,
        ),
    ]
    if missing:
        rows.append(
            ButtonRow(
                text=tr("recent.missing", "File missing"),
                size=11,
                h_align=Qt.AlignmentFlag.AlignLeft,
            )
        )
        types = format_session_types(record.session_types, tr)
        if types:
            rows.append(
                ButtonRow(
                    text=types,
                    size=11,
                    h_align=Qt.AlignmentFlag.AlignLeft,
                    marquee=True,
                )
            )
        return rows
    # Keep relative time static. Never marquee a composite "time · type"
    # line — only the session-type row may scroll when it overflows.
    rows.append(
        ButtonRow(
            text=format_relative_opened(record.opened_at, tr),
            size=11,
            h_align=Qt.AlignmentFlag.AlignLeft,
        )
    )
    types = format_session_types(record.session_types, tr)
    if types:
        rows.append(
            ButtonRow(
                text=types,
                size=11,
                h_align=Qt.AlignmentFlag.AlignLeft,
                marquee=True,
            )
        )
    return rows


def list_text_rows(
    record: RecentProjectRecord,
    *,
    missing: bool,
    tr: Callable[..., str],
) -> list[ButtonRow]:
    path_text = tr("recent.missing", "File missing") if missing else record.path
    return [
        ButtonRow(
            text=record.display_name,
            size=13,
            weight="bold",
            h_align=Qt.AlignmentFlag.AlignLeft,
            marquee=True,
        ),
        ButtonRow(
            text=path_text,
            size=11,
            h_align=Qt.AlignmentFlag.AlignLeft,
            marquee=not missing,
        ),
    ]


def list_meta_rows(
    record: RecentProjectRecord,
    *,
    tr: Callable[..., str],
) -> list[ButtonRow]:
    return [
        ButtonRow(
            text=format_relative_opened(record.opened_at, tr),
            size=11,
            h_align=Qt.AlignmentFlag.AlignRight,
        ),
    ]


def apply_fixed_card_size(card: Button, width: int, height: int) -> None:
    card.setFixedSize(scaled_px(width), scaled_px(height))
    card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


def apply_list_card_size(card: Button, height: int) -> None:
    """Fixed height, horizontal stretch to the scroll host width."""
    card.setMinimumWidth(0)
    card.setFixedHeight(scaled_px(height))
    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


def bind_card(
    card: Button,
    *,
    on_activate: Callable[[RecentProjectRecord, bool], None],
    on_context_menu: Callable[[RecentProjectRecord], None],
) -> None:
    # Multi-region cards (cover/text/meta) never hit ``_main``, so ``clicked``
    # stays silent — same pattern as SessionPicker create cards.
    # Handlers read live ``_recent_*`` attrs so in-place updates need no reconnect.
    # Keyboard modifiers are read at click time (Ctrl = toggle selection).
    def _on_region(_region_id, c=card) -> None:
        from PySide6.QtWidgets import QApplication

        from ui.widgets.shelf.selection import ctrl_held

        modifiers = QApplication.keyboardModifiers()
        on_activate(c._recent_record, c._recent_missing, modifiers)  # type: ignore[call-arg]  # panel may accept +modifiers

    # Keep signature flexible: panel may accept (record, missing) or +modifiers.
    card.regionClicked.connect(_on_region)
    if hasattr(card, "clicked"):
        # Keyboard Enter/Space on a focused card activates via the main
        # ``clicked`` signal — multi-region cards only emit ``regionClicked``
        # on mouse clicks, so this is what makes them keyboard-activatable.
        card.clicked.connect(
            lambda c=card: on_activate(
                c._recent_record, c._recent_missing
            )
        )
    if hasattr(card, "rightClicked"):
        card.rightClicked.connect(
            lambda c=card: on_context_menu(c._recent_record)
        )


def update_grid_card(
    card: Button,
    record: RecentProjectRecord,
    *,
    tr: Callable[..., str],
    context=None,
) -> None:
    missing = not Path(record.path).is_file()
    _attach_record(card, record, missing=missing)
    cover = _cover_region(
        record,
        missing=missing,
        context=context,
        corner_radii=(10, 10, 0, 0),
        weight=GRID_ICON_WEIGHT,
        icon_size_px=28,
    )
    card.update_region("cover", **_cover_update_kwargs(cover))
    card.update_region("text", rows=grid_text_rows(record, missing=missing, tr=tr))


def update_list_card(
    card: Button,
    record: RecentProjectRecord,
    *,
    tr: Callable[..., str],
    context=None,
) -> None:
    del context  # list cards have no cover icon
    missing = not Path(record.path).is_file()
    _attach_record(card, record, missing=missing)
    card.update_region("text", rows=list_text_rows(record, missing=missing, tr=tr))
    card.update_region("meta", rows=list_meta_rows(record, tr=tr))
    if missing:
        card.set_override_bg_color(_opaque(_missing_list_bg()))
    else:
        card.set_override_bg_color(None)


def build_grid_card(
    record: RecentProjectRecord,
    *,
    parent: QWidget | None,
    tr: Callable[..., str],
    context=None,
    on_activate: Callable[[RecentProjectRecord, bool], None],
    on_context_menu: Callable[[RecentProjectRecord], None],
) -> Button:
    missing = not Path(record.path).is_file()
    # Cover/preview is grid-only; list cards stay text + meta.
    # Use variant default fill (accent tint) so cards read against the shelf —
    # do not pin override_bg here; opaque scroll/host already stops CSD punch.
    card = Button(
        regions=[
            _cover_region(
                record,
                missing=missing,
                context=context,
                corner_radii=(10, 10, 0, 0),
                weight=GRID_ICON_WEIGHT,
                icon_size_px=28,
            ),
            ButtonRegion(
                id="text",
                rows=grid_text_rows(record, missing=missing, tr=tr),
                weight=GRID_TEXT_WEIGHT,
                group="card",
                corner_radii=(0, 0, 10, 10),
                hover_color=_transparent_color(),
            ),
        ],
        split=VerticalSplit(),
        variant="default",
        size=(GRID_CARD_W, GRID_CARD_H),
        content_padding=GRID_CONTENT_PADDING,
        corner_radius=10,
        overlay_painter=_card_hover_wash,
        parent=parent,
    )
    # Stack title/subtitle by font metrics + gap (ratio mode collides in a
    # short bottom strip once content_padding is applied to every region).
    card._rows_compact = True
    apply_fixed_card_size(card, GRID_CARD_W, GRID_CARD_H)
    _attach_record(card, record, missing=missing)
    bind_card(card, on_activate=on_activate, on_context_menu=on_context_menu)
    return card


def build_list_card(
    record: RecentProjectRecord,
    *,
    parent: QWidget | None,
    tr: Callable[..., str],
    context=None,
    on_activate: Callable[[RecentProjectRecord, bool], None],
    on_context_menu: Callable[[RecentProjectRecord], None],
) -> Button:
    del context
    missing = not Path(record.path).is_file()
    card = Button(
        regions=[
            ButtonRegion(
                id="text",
                rows=list_text_rows(record, missing=missing, tr=tr),
                weight=8.0,
                group="card",
                corner_radii=(8, 0, 0, 8),
                hover_color=_transparent_color(),
            ),
            ButtonRegion(
                id="meta",
                rows=list_meta_rows(record, tr=tr),
                weight=2.0,
                group="card",
                corner_radii=(0, 8, 8, 0),
                hover_color=_transparent_color(),
            ),
        ],
        variant="default",
        size=(0, LIST_CARD_H),
        content_padding=LIST_CONTENT_PADDING,
        corner_radius=8,
        overlay_painter=_card_hover_wash,
        parent=parent,
    )
    card._rows_compact = True
    apply_list_card_size(card, LIST_CARD_H)
    if missing:
        # Missing stays an explicit pastel signal; healthy cards keep default tint.
        card.set_override_bg_color(_opaque(_missing_list_bg()))
    _attach_record(card, record, missing=missing)
    bind_card(card, on_activate=on_activate, on_context_menu=on_context_menu)
    return card