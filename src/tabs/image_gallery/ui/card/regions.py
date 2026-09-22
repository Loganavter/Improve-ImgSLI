"""Region builders for gallery card — cover + text rows."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor as _QColor

from sli_ui_toolkit.widgets import ButtonRegion, ButtonRow

if TYPE_CHECKING:
    from tabs.image_gallery.models import GalleryItem


def _translate_or_default(
    translate: Callable[[str, str], str] | None, key: str, default: str
) -> str:
    if translate is None:
        return default
    try:
        return translate(key, default)
    except Exception:
        return default


def _name_row_color() -> _QColor:
    """Filename row color via theme token (fallback #dfdfdf)."""
    try:
        from tabs.image_gallery.ui.card.dots import _token_color

        return _token_color("gallery.stats.text", "#dfdfdf")
    except Exception:
        return _QColor("#dfdfdf")


def _unreadable_plate_color() -> _QColor:
    """Unreadable '!' plate via theme token (RGB fallback == #303030)."""
    try:
        from tabs.image_gallery.ui.card.dots import _token_color

        c = _token_color("gallery.card.unreadable.plate", "#303030")
        if c is not None:
            return c
    except Exception:
        pass
    return _QColor(48, 48, 48)


def _item_unreadable(item: GalleryItem) -> bool:
    """S2-3: unreadable/corrupt item detection via existing model fields.

    Thumbnail decode failure (``ThumbnailStatus.ERROR``) or an
    ``analysis_error`` that indicates the file could not be read.
    """
    try:
        ts = getattr(item, "thumbnail_status", None)
        if ts is not None and str(getattr(ts, "value", ts)).lower() == "error":
            return True
    except Exception:
        pass
    try:
        err = getattr(item, "analysis_error", None)
        if err:
            low = str(err).lower()
            if any(word in low for word in ("unreadable", "corrupt", "поврежд")):
                return True
    except Exception:
        pass
    return False


def _cover_region(item: GalleryItem) -> ButtonRegion:
    """Cover region: 234×110 r8 — image has r8 all around per svg x52 y200, bottom rounding visible above text zone."""
    thumb = getattr(item, "thumbnail", None)
    if thumb is not None and not thumb.isNull():
        return ButtonRegion(
            id="cover",
            pixmap=thumb,
            image_fill="cover",
            weight=3.0,
            group="card",
            corner_radii=(8, 8, 8, 8),
        )
    if _item_unreadable(item):
        return ButtonRegion(
            id="cover",
            text="!",
            weight=3.0,
            group="card",
            corner_radii=(8, 8, 8, 8),
            override_bg_color=_unreadable_plate_color(),
        )
    return ButtonRegion(
        id="cover",
        weight=3.0,
        group="card",
        corner_radii=(8, 8, 0, 0),
    )


def _text_rows(
    item: GalleryItem,
    translate: Callable[[str, str], str] | None,
    mode: object = None,
) -> list[ButtonRow]:
    # Rejected = strike-through on name row (ButtonRow маркируй per spec).
    try:
        _rejected = bool(getattr(item, "rejected", False))
    except Exception:
        _rejected = False
    rows: list[ButtonRow] = [
        ButtonRow(
            text=item.name,
            size=12,
            weight="normal",
            color=_name_row_color(),
            h_align=Qt.AlignmentFlag.AlignLeft,
            marquee=True,
            strikethrough=_rejected,
        ),
    ]
    # Optional second row: analysis tags or status hint.
    # S2-3: unreadable item — error line in the flagged/danger severity color
    # (mockup: red "unreadable — excluded from triage").
    analysis = getattr(item, "analysis", None)
    err = getattr(item, "analysis_error", None)
    unreadable = _item_unreadable(item)
    err_row: ButtonRow | None = None
    if unreadable:
        try:
            err_text = str(err) if err else _translate_or_default(
                translate, "gallery.card.unreadable", "unreadable — excluded from triage"
            )
        except Exception:
            err_text = str(err) if err else "unreadable — excluded from triage"
        # Lazy import to avoid cycles.
        from tabs.image_gallery.ui.card.dots import _ERROR_LINE_TOKEN_FALLBACK, _token_color

        err_row = ButtonRow(
            text=err_text,
            size=11,
            h_align=Qt.AlignmentFlag.AlignLeft,
            color=_token_color(*_ERROR_LINE_TOKEN_FALLBACK),
            strikethrough=_rejected,
        )
    elif err:
        err_row = ButtonRow(
            text=str(err),
            size=11,
            h_align=Qt.AlignmentFlag.AlignLeft,
            strikethrough=_rejected,
        )
    if analysis is not None and getattr(analysis, "tags", None):
        try:
            tags = ", ".join(analysis.tags[:3])
        except Exception:
            tags = ""
        if tags:
            rows.append(
                ButtonRow(
                    text=tags,
                    size=11,
                    h_align=Qt.AlignmentFlag.AlignLeft,
                    marquee=True,
                    strikethrough=_rejected,
                )
            )
        elif err_row is not None:
            # No tags but still need dots row.
            rows.append(err_row)
    elif err_row is not None:
        rows.append(err_row)
    # Stage 2: three quality dots — single meta-row space-between (real_design.md:2.4)
    # Underlying row is kept empty (height only), per-dot colors drawn by overlay_painter at right
    try:
        from tabs.image_gallery.ui.card.dots import _dots_for_item

        _dot_text, _dot_colors = _dots_for_item(item, mode=mode)
        rows.append(
            ButtonRow(
                text="",
                size=10,
                h_align=Qt.AlignmentFlag.AlignCenter,
                color=None,  # type: ignore[arg-type]
            )
        )
        # stash for overlay already handled outside
        _ = _dot_text
    except Exception:
        pass
    return rows
