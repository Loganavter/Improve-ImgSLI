"""Gallery list cards — row Button for list view mode (recent pattern).

Recent-projects precedent (session_picker/recent/cards.py build_list_card):
list mode reuses the SAME view/pool/selection/marquee and only swaps the
card builders + placement. A list card is one ``Button`` with horizontal
regions: fixed thumb (cover) + text rows (name/badges) + meta rows
(artifacts/VLM, right-aligned). Sizes come from hints (width free), so rows
hug the widest label instead of a fixed grid cell.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow, CustomSplit

from tabs.image_gallery.models import GalleryItem

LIST_CARD_H = 64
LIST_THUMB_W = 56

_GALLERY_LIST_PADDING: tuple[float, float, float, float] = (6.0, 6.0, 6.0, 6.0)


def _badges_text(item: GalleryItem) -> str:
    parts: list[str] = []
    try:
        if getattr(item, "rejected", False):
            parts.append("✕")
    except Exception:
        pass
    try:
        if getattr(item, "is_best", False):
            parts.append("★")
    except Exception:
        pass
    try:
        rank = getattr(item, "rank", None)
        if rank is not None:
            parts.append(f"R{int(rank)}")
    except Exception:
        pass
    try:
        crown = getattr(item, "crown_rank", None)
        if crown is not None and not getattr(item, "is_best", False):
            parts.append(f"C{int(crown)}")
    except Exception:
        pass
    return " ".join(parts)


def _artifacts_text(item: GalleryItem) -> str:
    """Compact artifact summary: F<n> flagged / M<n> mild / OK / …."""
    try:
        artifacts = getattr(item, "artifacts", None) or {}
        flagged = mild = 0
        for _aid, sev in dict(artifacts).items():
            try:
                s = sev.value.lower() if hasattr(sev, "value") else str(sev).lower()
            except Exception:
                s = "clean"
            if s == "flagged":
                flagged += 1
            elif s == "mild":
                mild += 1
        if flagged:
            return f"F{flagged}"
        if mild:
            return f"M{mild}"
        try:
            from tabs.image_gallery.models import AnalysisStatus

            if getattr(item, "analysis_status", None) == AnalysisStatus.DONE:
                return "OK"
        except Exception:
            pass
        return "…"
    except Exception:
        return "…"


def _vlm_text(item: GalleryItem) -> str:
    """Compact VLM state: err > tie… > tie-done/brief > ''."""
    try:
        if getattr(item, "vlm_tie_error", None) or getattr(item, "vlm_brief_error", None):
            return "err"
        if getattr(item, "vlm_tie_pending", False):
            return "tie…"
        if getattr(item, "vlm_tie_result", None) is not None:
            return "tie✓"
        try:
            status = str(getattr(item, "vlm_brief_status", None) or "none")
        except Exception:
            status = "none"
        if status not in ("none", ""):
            return "brief"
    except Exception:
        pass
    return ""


def _list_text_rows(item: GalleryItem) -> list[ButtonRow]:
    badges = _badges_text(item)
    rows = [
        ButtonRow(
            text=item.name,
            size=13,
            weight="bold",
            h_align=Qt.AlignmentFlag.AlignLeft,
            marquee=True,
        ),
    ]
    if badges:
        rows.append(
            ButtonRow(
                text=badges,
                size=11,
                h_align=Qt.AlignmentFlag.AlignLeft,
            )
        )
    return rows


def _list_meta_rows(item: GalleryItem) -> list[ButtonRow]:
    rows = [
        ButtonRow(
            text=_artifacts_text(item),
            size=11,
            h_align=Qt.AlignmentFlag.AlignRight,
        ),
    ]
    vlm = _vlm_text(item)
    if vlm:
        rows.append(
            ButtonRow(
                text=vlm,
                size=11,
                h_align=Qt.AlignmentFlag.AlignRight,
            )
        )
    return rows


def _thumb_region(item: GalleryItem) -> ButtonRegion:
    """Fixed-width cover thumb (unreadable → '!' like grid covers)."""
    from tabs.image_gallery.ui.card.regions import _item_unreadable

    thumb = getattr(item, "thumbnail", None)
    if thumb is not None and not thumb.isNull():
        return ButtonRegion(
            id="thumb",
            pixmap=thumb,
            image_fill="cover",
            weight=0.0,
            group="card",
            corner_radii=(8, 0, 0, 8),
            hover_color=QColor(0, 0, 0, 0),
        )
    try:
        unreadable = bool(_item_unreadable(item))
    except Exception:
        unreadable = False
    return ButtonRegion(
        id="thumb",
        text="!" if unreadable else "",
        weight=0.0,
        group="card",
        corner_radii=(8, 0, 0, 8),
        hover_color=QColor(0, 0, 0, 0),
    )


def _thumb_rect(r: QRectF) -> QRectF:
    return QRectF(4, 4, scaled_px(LIST_THUMB_W), r.height() - 8)


def _text_rect(r: QRectF) -> QRectF:
    left = 4 + scaled_px(LIST_THUMB_W) + scaled_px(8)
    meta_w = max(scaled_px(72), r.width() * 0.22)
    return QRectF(left, 4, r.width() - left - meta_w - 4, r.height() - 8)


def _meta_rect(r: QRectF) -> QRectF:
    meta_w = max(scaled_px(72), r.width() * 0.22)
    return QRectF(r.width() - meta_w - 4, 4, meta_w, r.height() - 8)


def build_gallery_list_card(
    item: GalleryItem,
    parent: QWidget | None = None,
    on_activate: Callable | None = None,
    on_context_menu: Callable | None = None,
    mode: object = None,
) -> Button:
    """Factory for a gallery list-row Button (recent build_list_card parity)."""
    from tabs.image_gallery.ui.card.hover import _CardHoverFilter
    from tabs.image_gallery.ui.card.visuals import _apply_rejected_visuals

    _ = mode
    card = Button(
        regions=[
            _thumb_region(item),
            ButtonRegion(
                id="text",
                rows=_list_text_rows(item),
                weight=1.0,
                group="card",
                corner_radii=(0, 0, 0, 0),
                hover_color=QColor(0, 0, 0, 0),
            ),
            ButtonRegion(
                id="meta",
                rows=_list_meta_rows(item),
                weight=0.0,
                group="card",
                corner_radii=(0, 8, 8, 0),
                hover_color=QColor(0, 0, 0, 0),
            ),
        ],
        split=CustomSplit(rect_fns=[_thumb_rect, _text_rect, _meta_rect]),
        variant="default",
        size=(0, LIST_CARD_H),
        content_padding=_GALLERY_LIST_PADDING,
        corner_radius=8,
        parent=parent,
        defer_click="ripple",
    )
    try:
        card.setProperty("_rows_compact", True)
    except Exception:
        pass
    _attach_list_item(card, item)
    try:
        _apply_rejected_visuals(card, item)
    except Exception:
        pass
    try:
        filt = _CardHoverFilter(card, None)
        card.installEventFilter(filt)
        card._gallery_hover_filter = filt  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        from tabs.image_gallery.ui.card.delete_button import wire_card_delete_button

        wire_card_delete_button(card, None)
    except Exception:
        pass
    if on_activate is not None or on_context_menu is not None:
        from tabs.image_gallery.ui.card import _bind_gallery_card

        _bind_gallery_card(card, on_activate=on_activate, on_context_menu=on_context_menu)
    return card


def _attach_list_item(card: Button, item: GalleryItem) -> None:
    """Stash live item reference on the row (card._attach_item parity)."""
    card._gallery_item = item  # type: ignore[attr-defined]
    try:
        card.setProperty("gallery_path", str(item.path))
    except Exception:
        pass


def update_gallery_list_card(card: Button, item: GalleryItem, mode: object = None) -> None:
    """In-place update of a live list row (update_gallery_card parity)."""
    from tabs.image_gallery.ui.card.visuals import _apply_rejected_visuals

    _ = mode
    _attach_list_item(card, item)
    thumb = getattr(item, "thumbnail", None)
    if thumb is not None and not thumb.isNull():
        try:
            current = card.region("thumb").pixmap
        except Exception:
            current = None
        if current is not thumb:
            card.update_region("thumb", pixmap=thumb, image_fill="cover")
    else:
        from tabs.image_gallery.ui.card.regions import _item_unreadable

        try:
            unreadable = bool(_item_unreadable(item))
        except Exception:
            unreadable = False
        card.update_region("thumb", pixmap=None, image_fill="cover")
        try:
            card.update_region("thumb", text="!" if unreadable else "")
        except Exception:
            pass
    try:
        card.update_region("text", rows=_list_text_rows(item))
    except Exception:
        pass
    try:
        card.update_region("meta", rows=_list_meta_rows(item))
    except Exception:
        pass
    try:
        from tabs.image_gallery.ui.card.delete_button import sync_card_delete_button

        sync_card_delete_button(card)
    except Exception:
        pass
    try:
        parts = [item.name]
        analysis = getattr(item, "analysis", None)
        if analysis is not None:
            if getattr(analysis, "description", None):
                parts.append(analysis.description)
            if getattr(analysis, "tags", None):
                parts.append(", ".join(analysis.tags))
        err = getattr(item, "analysis_error", None)
        if err:
            parts.append(str(err))
        vlm_err = getattr(item, "vlm_tie_error", None)
        if vlm_err:
            parts.append(f"VLM tie-break: {vlm_err}")
        card.setToolTip("\n".join(parts))
    except Exception:
        pass
    try:
        _apply_rejected_visuals(card, item)
    except Exception:
        pass
