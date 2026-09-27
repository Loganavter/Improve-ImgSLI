"""Gallery list cards — row Button for list view mode (recent pattern).

List mode reuses the SAME view/pool/selection/marquee and only swaps the
card builders + placement. A list card is one ``Button``: fixed thumb
(contain, whole image fits) + ONE title row (name + badges inline) + ONE
meta row (artifacts + VLM). Row actions (make-best / reject / compare) are
small child Buttons inside the card with hover-only visibility, following
``card/delete_button.py`` wire/sync/pin (fail-open, per-click live
item/owner resolve) and the palette-row capsule idea (one capsule, inner
targets routed by id). Each capsule button has a stable objectName and
calls the same use-case functions as the card context menu.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow, CustomSplit

from tabs.image_gallery.models import GalleryItem

LIST_CARD_H = 64
LIST_THUMB_W = 56

_GALLERY_LIST_PADDING: tuple[float, float, float, float] = (6.0, 6.0, 6.0, 6.0)

_ROW_ACT_BEST = "gallery_row_act_best"
_ROW_ACT_REJECT = "gallery_row_act_reject"
_ROW_ACT_COMPARE = "gallery_row_act_compare"
_ROW_ACT_ATTRS = ("_gallery_row_act_best", "_gallery_row_act_reject", "_gallery_row_act_compare")
_ROW_ACT_SIZE = 24
_ROW_ACT_GAP = 4


def _badges_text(item: GalleryItem) -> str:
    """Inline badges, grid parity: single ``#N`` (crown_rank ?? rank) + ★ + ✕."""
    parts: list[str] = []
    try:
        rank_val = getattr(item, "crown_rank", None)
        if rank_val is None:
            rank_val = getattr(item, "rank", None)
        if rank_val is not None:
            try:
                parts.append(f"#{int(rank_val)}")
            except Exception:
                parts.append(f"#{rank_val}")
    except Exception:
        pass
    try:
        if getattr(item, "is_best", False):
            parts.append("★")
    except Exception:
        pass
    try:
        if getattr(item, "rejected", False):
            parts.append("✕")
    except Exception:
        pass
    return " ".join(parts)


def _artifacts_text(item: GalleryItem) -> str:
    """Plain-words artifact summary: flagged×n / mild×n / OK / …."""
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
            return f"flagged×{flagged}"
        if mild:
            return f"mild×{mild}"
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
    """Compact VLM state: err > tie… > tie-ok / brief > ''."""
    try:
        if getattr(item, "vlm_tie_error", None) or getattr(item, "vlm_brief_error", None):
            return "err"
        if getattr(item, "vlm_tie_pending", False):
            return "tie…"
        if getattr(item, "vlm_tie_result", None) is not None:
            return "tie-ok"
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
    """ONE title row: name + badges inline, normal weight, grid parity size."""
    text = item.name
    badges = _badges_text(item)
    if badges:
        text = f"{text} {badges}"
    return [ButtonRow(text=text, size=12, weight="normal", h_align=Qt.AlignmentFlag.AlignLeft, marquee=True)]


def _list_meta_rows(item: GalleryItem) -> list[ButtonRow]:
    """ONE meta row: artifacts + VLM combined with spaces, right-aligned."""
    parts = [p for p in (_artifacts_text(item), _vlm_text(item)) if p]
    return [ButtonRow(text=" ".join(parts), size=11, h_align=Qt.AlignmentFlag.AlignRight)]


def _thumb_region(item: GalleryItem) -> ButtonRegion:
    """Fixed-width contain thumb (unreadable → '!' like grid covers)."""
    from tabs.image_gallery.ui.card.regions import _item_unreadable

    thumb = getattr(item, "thumbnail", None)
    if thumb is not None and not thumb.isNull():
        return ButtonRegion(id="thumb", pixmap=thumb, image_fill="contain", weight=0.0,
                            group="card", corner_radii=(8, 0, 0, 8), hover_color=QColor(0, 0, 0, 0))
    try:
        unreadable = bool(_item_unreadable(item))
    except Exception:
        unreadable = False
    return ButtonRegion(id="thumb", text="!" if unreadable else "", weight=0.0,
                        group="card", corner_radii=(8, 0, 0, 8), hover_color=QColor(0, 0, 0, 0))


def _thumb_rect(r: QRectF) -> QRectF:
    return QRectF(4, 4, scaled_px(LIST_THUMB_W), r.height() - 8)


def _text_rect(r: QRectF) -> QRectF:
    left = 4 + scaled_px(LIST_THUMB_W) + scaled_px(8)
    meta_w = max(scaled_px(72), r.width() * 0.22)
    return QRectF(left, 4, r.width() - left - meta_w - 4, r.height() - 8)


def _meta_rect(r: QRectF) -> QRectF:
    meta_w = max(scaled_px(72), r.width() * 0.22)
    return QRectF(r.width() - meta_w - 4, 4, meta_w, r.height() - 8)


def _resolve_capsule_target(card: Button):
    """Live (owner, path) per click — pool-safe (delete_button parity)."""
    item = getattr(card, "_gallery_item", None)
    path = getattr(item, "path", None) if item is not None else None
    if path is None:
        try:
            raw = card.property("gallery_path") or ""
            path = Path(str(raw)) if str(raw) else None
        except Exception:
            path = None
    owner = getattr(card, "_gallery_owner", None)
    if owner is None:
        try:
            win = card.window()
            owner = getattr(win, "_gallery_controller", None) or getattr(win, "_gallery_owner", None)
        except Exception:
            owner = None
    if path is not None and not isinstance(path, Path):
        try:
            path = Path(path)
        except Exception:
            path = None
    return owner, path


def _fire_capsule_action(card: Button, kind: str) -> None:
    """Run one capsule action via the context-menu use-case path (fail-open)."""
    owner, path = _resolve_capsule_target(card)
    if owner is None or path is None:
        return
    try:
        from tabs.image_gallery.use_cases import triage as _triage

        if kind == "best":
            _triage.make_best(owner, path)
        elif kind == "reject":
            _triage.toggle_reject(owner, path)
        elif kind == "compare":
            try:
                if hasattr(owner, "state") and hasattr(owner.state, "selected_paths"):
                    owner.state.selected_paths.add(Path(path))
            except Exception:
                pass
            from tabs.image_gallery.use_cases import carry as _carry

            _carry.carry_selected(owner)
    except Exception:
        pass


def _cursor_over_capsule(card: Button) -> bool:
    """Cursor over the card or a visible capsule button (fail-open False)."""
    try:
        from PySide6.QtGui import QCursor

        import shiboken6

        if not shiboken6.isValid(card):
            return False
        pos = QCursor.pos()
        if bool(card.rect().contains(card.mapFromGlobal(pos))):
            return True
        for attr in _ROW_ACT_ATTRS:
            btn = getattr(card, attr, None)
            if btn is None or not btn.isVisible():
                continue
            try:
                if bool(btn.rect().contains(btn.mapFromGlobal(pos))):
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


class _RowCapsuleFilter(QObject):
    """Hover-only capsule visibility + re-pin (delete_button parity)."""

    def __init__(self, card: Button) -> None:
        super().__init__(card)
        self._card = card

    def _is_capsule_target(self, watched) -> bool:
        try:
            if watched is self._card:
                return True
            return any(watched is getattr(self._card, a, None) for a in _ROW_ACT_ATTRS)
        except Exception:
            return False

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        try:
            t = event.type()
            card = self._card
            if t == QEvent.Type.Enter and self._is_capsule_target(watched):
                card._gallery_row_capsule_hovered = True  # type: ignore[attr-defined]
                sync_row_capsule_buttons(card)
            elif t == QEvent.Type.Leave and self._is_capsule_target(watched):
                if not _cursor_over_capsule(card):
                    card._gallery_row_capsule_hovered = False  # type: ignore[attr-defined]
                    sync_row_capsule_buttons(card)
            elif watched is card and t in (QEvent.Type.Move, QEvent.Type.Resize,
                                           QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.ParentChange):
                sync_row_capsule_buttons(card)
        except Exception:
            pass
        return False


def sync_row_capsule_buttons(card: Button) -> None:
    """Reposition + hover-gate the row action capsule (fail-open)."""
    try:
        import shiboken6

        btns = []
        for attr in _ROW_ACT_ATTRS:
            btn = getattr(card, attr, None)
            if btn is None or not shiboken6.isValid(btn):
                return
            btns.append(btn)
        size = int(scaled_px(_ROW_ACT_SIZE))
        hovered = bool(getattr(card, "_gallery_row_capsule_hovered", False))
        w, h = int(card.width()), int(card.height())
        total = len(btns) * size + (len(btns) - 1) * _ROW_ACT_GAP
        x, y = max(0, w - total - 8), max(0, (h - size) // 2)
        for i, btn in enumerate(btns):
            btn.move(x + i * (size + _ROW_ACT_GAP), y)
            if hovered:
                if not btn.isVisible():
                    btn.show()
                btn.raise_()
            elif btn.isVisible():
                btn.hide()
    except Exception:
        pass


def wire_row_capsule_buttons(card: Button, owner) -> None:
    """Attach the hover-only ★/✕/⇄ capsule to *card* (in-rect children)."""
    _ = owner
    try:
        size = int(scaled_px(_ROW_ACT_SIZE))
    except Exception:
        size = _ROW_ACT_SIZE
    specs = (
        (_ROW_ACT_BEST, "★", "Make best", "best", "_gallery_row_act_best"),
        (_ROW_ACT_REJECT, "✕", "Reject", "reject", "_gallery_row_act_reject"),
        (_ROW_ACT_COMPARE, "⇄", "Compare", "compare", "_gallery_row_act_compare"),
    )
    for object_name, text, tip, kind, attr in specs:
        try:
            if getattr(card, attr, None) is not None:
                continue
            btn = Button(text=text, variant="ghost", parent=card)
            btn.setObjectName(object_name)
            btn.setFixedSize(size, size)
            btn.setToolTip(tip)
            btn.hide()
        except Exception:
            continue

        def _slot(_checked=False, c=card, k=kind) -> None:
            _fire_capsule_action(c, k)

        try:
            btn.clicked.connect(_slot)
            setattr(card, attr, btn)
            card.destroyed.connect(btn.deleteLater)
        except Exception:
            pass
    try:
        card._gallery_row_capsule_hovered = False  # type: ignore[attr-defined]
        filt = _RowCapsuleFilter(card)
        card._gallery_row_capsule_filter = filt  # type: ignore[attr-defined]
        card.installEventFilter(filt)
        for attr in _ROW_ACT_ATTRS:
            btn = getattr(card, attr, None)
            if btn is not None:
                btn.installEventFilter(filt)
    except Exception:
        pass
    sync_row_capsule_buttons(card)


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
            ButtonRegion(id="text", rows=_list_text_rows(item), weight=1.0, group="card",
                         corner_radii=(0, 0, 0, 0), hover_color=QColor(0, 0, 0, 0)),
            ButtonRegion(id="meta", rows=_list_meta_rows(item), weight=0.0, group="card",
                         corner_radii=(0, 8, 8, 0), hover_color=QColor(0, 0, 0, 0)),
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
        _attach_list_item(card, item)
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
        wire_row_capsule_buttons(card, None)
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
            card.update_region("thumb", pixmap=thumb, image_fill="contain")
    else:
        from tabs.image_gallery.ui.card.regions import _item_unreadable

        try:
            unreadable = bool(_item_unreadable(item))
        except Exception:
            unreadable = False
        card.update_region("thumb", pixmap=None, image_fill="contain")
        try:
            card.update_region("thumb", text="!" if unreadable else "")
        except Exception:
            pass
    try:
        card.update_region("text", rows=_list_text_rows(item))
        card.update_region("meta", rows=_list_meta_rows(item))
    except Exception:
        pass
    try:
        from tabs.image_gallery.ui.card.delete_button import sync_card_delete_button

        sync_card_delete_button(card)
        sync_row_capsule_buttons(card)
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
