"""Wave-A drag source: mime/pixmap helpers + card QDrag kickoff (grid_view package, plan C1)."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QObject, QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow, Label, Layer, OverlayScrollArea

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.card import (
    GALLERY_CARD_H,
    GALLERY_CARD_W,
    apply_gallery_selection,
    build_gallery_card,
    gallery_selection_accent,
    update_gallery_card,
)
from tabs.image_gallery.ui.card.activity_pulse import ActivityPulse
from tabs.image_gallery.ui.list.card import (
    LIST_CARD_H,
    _bind_list_row,
    build_gallery_list_card,
    update_gallery_list_card,
)
from ui.widgets.shelf import OpaqueFillHost, apply_opaque_widget_fill

logger = logging.getLogger("ImproveImgSLI")

from .filters import _CardKeyFilter, _CardPressDragFilter

# -- Wave A drag source (QDrag off gallery cards) ---------------------------
#
# Frozen seam with Wave B: mime ``application/x-imgsli-gallery-paths``
# (defined ONCE in ``ui/card.py`` as ``GALLERY_PATHS_MIME``). Payload =
# newline-separated ``file://`` URLs PLUS ``QMimeData.setUrls()`` with the
# same files (copy semantics on drop; files stay on disk — no source
# deletion anywhere). Dragged set: current selection in ``selected_order``
# when the pressed card is inside it, else the single pressed card.


def dragged_paths_for_press(owner, pressed_path: Path) -> list[Path]:
    """Cards a press-drag carries (file-manager rule, mirrors Reject).

    Pressed-inside-selection → whole selection (``selected_order`` first);
    pressed-outside → just the pressed card. Read-only (no selection write).
    """
    try:
        from tabs.image_gallery.ui.card.context_actions import _action_targets

        return list(_action_targets(owner, pressed_path))
    except Exception:
        try:
            return [pressed_path if isinstance(pressed_path, Path) else Path(pressed_path)]
        except Exception:
            return []


def build_gallery_drag_mime(paths: list[Path]) -> QMimeData:
    """Mime for a card drag: ``file://`` URLs + ``setUrls`` (same files)."""
    from tabs.image_gallery.ui.card import GALLERY_PATHS_MIME

    urls = [QUrl.fromLocalFile(str(p)) for p in (paths or [])]
    mime = QMimeData()
    try:
        mime.setData(GALLERY_PATHS_MIME, "\n".join(u.toString() for u in urls).encode("utf-8"))
    except Exception:
        pass
    try:
        mime.setUrls(urls)
    except Exception:
        pass
    return mime


def should_start_gallery_drag(press_pos: QPoint | None, cur_pos: QPoint | None) -> bool:
    """True once the press-move passes ``QApplication.startDragDistance``."""
    try:
        if press_pos is None or cur_pos is None:
            return False
        from PySide6.QtWidgets import QApplication

        return (cur_pos - press_pos).manhattanLength() >= int(QApplication.startDragDistance())
    except Exception:
        return False


def resolve_gallery_drag_pixmap(card, owner, first_path: Path):
    """Preview pixmap for a card drag (preview-only, never written back).

    Pressed card cover pixmap → item thumbnail → disk preview. May be None
    (the QDrag then carries no pixmap); callers check ``isNull`` themselves.
    """
    try:
        region = card.region("cover") if card is not None and hasattr(card, "region") else None
        pix = getattr(region, "pixmap", None)
        if pix is not None and not pix.isNull():
            return pix
    except Exception:
        pass
    try:
        items = getattr(getattr(owner, "state", None), "items", None) or []
        for it in items:
            try:
                if Path(getattr(it, "path")) == Path(first_path):
                    thumb = getattr(it, "thumbnail", None)
                    if thumb is not None and not thumb.isNull():
                        return thumb
                    break
            except Exception:
                continue
    except Exception:
        pass
    try:
        from events.image_carry import preview_pixmap_for_path

        return preview_pixmap_for_path(Path(first_path))
    except Exception:
        return None


#: QDrag preview edge (px): card covers are grid-sized (~200px+) — too big
#: to aim with under the cursor. Shrunk with aspect kept.
GALLERY_DRAG_PREVIEW_EDGE = 112


def compose_gallery_drag_pixmap(base, count: int = 1):
    """Shrink a drag source pixmap + count badge for multi-drags.

    Single image → small preview only; N > 1 → blue pill with the white
    count at the preview's top-right corner, half hanging outside
    (circle for a single digit, capsule beyond — file-manager parity). Returns None when *base* is null so callers keep
    the no-pixmap fallback.
    """
    try:
        n = int(count or 0)
    except Exception:
        n = 0
    try:
        if base is None or base.isNull():
            return None
    except Exception:
        return None
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QFont, QPainter, QPixmap

        scaled = base.scaled(
            GALLERY_DRAG_PREVIEW_EDGE,
            GALLERY_DRAG_PREVIEW_EDGE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if n <= 1:
            return scaled
        # White on gallery-accent blue: max contrast for a small readout
        # on any thumbnail underneath (dark pills wash out on dark photos).
        # Single digit → circle; 10+ → capsule (like card pills) so the
        # text fits. Right edge pinned half-outside the preview.
        font = QFont()
        font.setBold(True)
        font.setPixelSize(18)
        badge_h = 30
        if len(str(n)) < 2:
            pill_w = badge_h
        else:
            from PySide6.QtGui import QFontMetrics

            pill_w = QFontMetrics(font).horizontalAdvance(str(n)) + 20
        badge_r = badge_h // 2
        overhang = badge_r
        out = QPixmap(scaled.width() + overhang, scaled.height() + badge_r)
        out.fill(Qt.GlobalColor.transparent)
        painter = QPainter(out)
        try:
            painter.drawPixmap(0, badge_r, scaled)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#0096FF"))
            bx = scaled.width() + overhang - pill_w
            painter.drawRoundedRect(bx, 0, pill_w, badge_h, badge_r, badge_r)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(
                bx, 0, pill_w, badge_h,
                Qt.AlignmentFlag.AlignCenter, str(n),
            )
        finally:
            painter.end()
        return out
    except Exception:
        try:
            return base
        except Exception:
            return None


def _card_drag_path(card) -> Path | None:
    """Path carried by *card* (same resolution as ``_bind_gallery_card``)."""
    try:
        item = getattr(card, "_gallery_item", None)
        path = getattr(item, "path", None) if item is not None else None
        if path is None:
            path = Path(str(card.property("gallery_path") or ""))
        return Path(path) if not isinstance(path, Path) else path
    except Exception:
        return None

def _ensure_card_drag(view, card) -> None:
    """Install the press-drag filter on *card* (idempotent, pool-safe)."""
    self = view
    try:
        if getattr(card, "_gallery_drag_installed", False):
            return
        filt = _CardPressDragFilter(card, self)
        card.installEventFilter(filt)
        card._gallery_drag_installed = True  # type: ignore[attr-defined]
    except Exception:
        pass

def _ensure_card_keys(view, card) -> None:
    """Install the keyboard filter on *card* (idempotent, pool-safe).

    Gives every pooled card the grid navigation + activation policy
    (see ``_CardKeyFilter``). Kept separate from ``_ensure_card_drag``
    so existing drag-installed cards still gain keys after an upgrade.
    """
    self = view
    try:
        if getattr(card, "_gallery_keys_installed", False):
            return
        filt = _CardKeyFilter(card, self)
        card.installEventFilter(filt)
        card._gallery_keys_installed = True  # type: ignore[attr-defined]
    except Exception:
        pass

def note_card_press(view, path: Path, global_pos: QPoint) -> None:
    """Record a card-press origin (no selection write — arming is at drag start)."""
    self = view
    try:
        self._drag_press_path = str(path)
        self._drag_press_pos = global_pos
    except Exception:
        pass

def clear_card_press(view) -> None:
    self = view
    try:
        self._drag_press_path = None
        self._drag_press_pos = None
    except Exception:
        pass

def _drag_owner(view):
    """Triage owner for drag arming (controller, or widget when storeless)."""
    self = view
    try:
        widget = getattr(self, "_gallery_widget", None)
        resolver = getattr(widget, "_owner_for_triage", None)
        if callable(resolver):
            return resolver()
    except Exception:
        pass
    return None

def _gallery_domain(view) -> str:
    """Durable judgment domain for metric dots (``owner._judgment_domain``).

    Shared by every card-update path so a domain switch repaints the dots
    against the same authority the grid card reads; unknown/absent → ``""``
    (``quality_read`` degrades to Algorithms).
    """
    try:
        owner = _drag_owner(view)
        return str(getattr(owner, "_judgment_domain", "") or "")
    except Exception:
        return ""


def build_card_drag(view, card, global_pos: QPoint):  # type: ignore[no-untyped-def]
    """Build the QDrag for the recorded press, or None (no exec here).

    Threshold-gated; press on an unselected card arms single-card
    selection first (dispatch-only via ``selection.commit`` → controller
    ``set_selection``), press on a selected card keeps the group. Ctrl
    toggle routing is untouched (commits on click/release elsewhere).
    """
    self = view
    try:
        press_path = getattr(self, "_drag_press_path", None)
        press_pos = getattr(self, "_drag_press_pos", None)
    except Exception:
        return None
    if press_path is None or press_pos is None or global_pos is None:
        return None
    if not should_start_gallery_drag(press_pos, global_pos):
        return None
    owner = self._drag_owner()
    if owner is None:
        return None
    try:
        pressed = Path(press_path)
    except Exception:
        return None
    dragged = dragged_paths_for_press(owner, pressed)
    if not dragged:
        return None
    try:
        sel = getattr(getattr(owner, "state", None), "selected_paths", None) or set()
        sel_set = {Path(p) if not isinstance(p, Path) else p for p in sel}
    except Exception:
        sel_set = set()
    if pressed not in sel_set:
        # Unselected press → drag exactly the pressed card (arm first).
        dragged = [pressed]
        try:
            from tabs.image_gallery.use_cases import selection as _selection

            _selection.commit(owner, {pressed})
        except Exception:
            pass
    try:
        mime = build_gallery_drag_mime(dragged)
    except Exception:
        return None
    try:
        from tabs.image_gallery.debug import gallery_dnd_debug as _dnd_log

        _dnd_log(
            "card drag start pressed=%s n_dragged=%d dragged=%r",
            Path(press_path).name if press_path else "?",
            len(dragged),
            [Path(p).name for p in list(dragged)[:5]],
        )
    except Exception:
        pass
    try:
        pixmap = resolve_gallery_drag_pixmap(card, owner, dragged[0])
        # Shrink to cursor size + count badge for multi-drags.
        pixmap = compose_gallery_drag_pixmap(pixmap, len(dragged))
    except Exception:
        pixmap = None
    try:
        drag = QDrag(card)
        drag.setMimeData(mime)
        if pixmap is not None and not pixmap.isNull():
            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(0, 0))
        return drag
    except Exception:
        return None

def maybe_start_card_drag(view, card, global_pos: QPoint) -> bool:
    """Threshold → build → ``exec(CopyAction)``. Copy only; files stay."""
    self = view
    try:
        drag = self.build_card_drag(card, global_pos)
    except Exception:
        return False
    if drag is None:
        return False
    try:
        drag.exec(Qt.DropAction.CopyAction)
    except Exception:
        pass
    try:
        self.clear_card_press()
    except Exception:
        pass
    return True
