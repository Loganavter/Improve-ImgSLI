"""Grid and list cards for recent project records."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget
from sli_ui_toolkit.ui.widgets.buttons import ButtonRow, VerticalSplit
from sli_ui_toolkit.widgets import Button, ButtonRegion

from services.io.project_preview import peek_project_preview
from services.io.recent_projects import RecentProjectRecord
from tabs.session_picker.icons import Icon as SessionPickerIcon
from tabs.session_picker.icons import get_icon as get_session_picker_icon
from tabs.session_picker.recent.layout import (
    GRID_CARD_H,
    GRID_CARD_W,
    GRID_CONTENT_PADDING,
    GRID_ICON_WEIGHT,
    GRID_TEXT_WEIGHT,
    LIST_CARD_H,
    LIST_CONTENT_PADDING,
)
from tabs.session_picker.recent.relative_time import format_relative_opened

# Pastel red for list cards whose project file is missing.
_MISSING_LIST_BG = QColor(242, 190, 190)
_MISSING_COVER_BG = QColor(255, 255, 255)


def _opaque(color: QColor) -> QColor:
    out = QColor(color)
    out.setAlpha(255)
    return out


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
    if missing:
        return ButtonRegion(
            id="cover",
            icon=get_session_picker_icon(SessionPickerIcon.MISSING_WARNING),
            icon_size_px=max(36, icon_size_px),
            weight=weight,
            group="card",
            corner_radii=corner_radii,
            override_bg_color=_opaque(_MISSING_COVER_BG),
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
        )
    return ButtonRegion(
        id="cover",
        icon=icon_for_record(record, context),
        icon_size_px=icon_size_px,
        weight=weight,
        group="card",
        corner_radii=corner_radii,
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
    card.setFixedSize(width, height)
    card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


def apply_list_card_size(card: Button, height: int) -> None:
    """Fixed height, horizontal stretch to the scroll host width."""
    card.setMinimumWidth(0)
    card.setFixedHeight(height)
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

        from tabs.session_picker.recent.selection import ctrl_held

        modifiers = QApplication.keyboardModifiers()
        on_activate(c._recent_record, c._recent_missing, modifiers)

    # Keep signature flexible: panel may accept (record, missing) or +modifiers.
    card.regionClicked.connect(_on_region)
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
        card.set_override_bg_color(_opaque(_MISSING_LIST_BG))
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
            ),
        ],
        split=VerticalSplit(),
        variant="default",
        size=(GRID_CARD_W, GRID_CARD_H),
        content_padding=GRID_CONTENT_PADDING,
        corner_radius=10,
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
            ),
            ButtonRegion(
                id="meta",
                rows=list_meta_rows(record, tr=tr),
                weight=2.0,
                group="card",
                corner_radii=(0, 8, 8, 0),
            ),
        ],
        variant="default",
        size=(0, LIST_CARD_H),
        content_padding=LIST_CONTENT_PADDING,
        corner_radius=8,
        parent=parent,
    )
    card._rows_compact = True
    apply_list_card_size(card, LIST_CARD_H)
    if missing:
        # Missing stays an explicit pastel signal; healthy cards keep default tint.
        card.set_override_bg_color(_opaque(_MISSING_LIST_BG))
    _attach_record(card, record, missing=missing)
    bind_card(card, on_activate=on_activate, on_context_menu=on_context_menu)
    return card
