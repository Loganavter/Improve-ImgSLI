"""List-row card — palette-style row Button (no grid imports).

Own split/regions/routing/overlay live in this package (``ui/list/*``);
item logic comes from ``models``, triage actions from ``use_cases``. No
grid widget/layout code is imported; the only ``ui/card`` reach is the
lazy, pure metric-dot helper (``_metric_dots_for``) so the list dots match
the grid card exactly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonRegion, CustomSplit

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.list.painters import _list_row_overlay_painter
from tabs.image_gallery.ui.list.regions import (
    _list_meta_rows,
    _list_text_rows,
    _thumb_region,
)
from tabs.image_gallery.ui.list.visuals import _apply_list_rejected_visuals

LIST_CARD_H = 64
LIST_THUMB_W = 56  # default when no thumbnail yet (kept for compat)

# Thumb follows the image aspect: w = H * aspect, clamped. Upper cap 21:9
# so panoramas don't eat the row; lower min so portraits stay tappable.
_LIST_THUMB_MIN_W = 32.0
_LIST_THUMB_MAX_ASPECT = 21.0 / 9.0

_LIST_META_MIN_W = 72.0

_GALLERY_LIST_PADDING: tuple[float, float, float, float] = (6.0, 6.0, 6.0, 6.0)

# List rows carry no right-side action chrome: their actions live in the
# right-click card menu (make best / reject / compare / remove), same as the
# grid cards. The row is thumb + title + meta only.
_PLATE_IDS = frozenset({"thumb", "text", "meta"})
LIST_ROW_REGION_IDS = ("thumb", "text", "meta")


def _thumb_width_for(item: GalleryItem) -> float:
    """Design-px thumb width from the live thumbnail aspect (pool-safe)."""
    try:
        thumb = getattr(item, "thumbnail", None)
        if thumb is not None and not thumb.isNull():
            iw, ih = int(thumb.width()), int(thumb.height())
            if iw > 0 and ih > 0:
                w = float(LIST_CARD_H) * (iw / ih)
                return max(_LIST_THUMB_MIN_W, min(w, float(LIST_CARD_H) * _LIST_THUMB_MAX_ASPECT))
    except Exception:
        pass
    return float(LIST_THUMB_W)


def _list_metrics(r: QRectF, thumb_design: float) -> tuple[float, float]:
    """Fixed widths for the row: thumb + meta (title flexes between them)."""
    thumb_w = float(scaled_px(thumb_design))
    meta_w = max(float(scaled_px(_LIST_META_MIN_W)), float(r.width()) * 0.22)
    return thumb_w, meta_w


def _list_text_width(r: QRectF, thumb_design: float) -> float:
    """Flexible title width: whatever is left after thumb + meta."""
    thumb_w, meta_w = _list_metrics(r, thumb_design)
    return max(0.0, float(r.width()) - thumb_w - meta_w)


def _make_rect_fns(state: dict):
    """Per-card split fns closing over the mutable thumb width (pool-safe)."""

    def _thumb_rect(r: QRectF) -> QRectF:
        thumb_w, _ = _list_metrics(r, state["w"])
        return QRectF(0, 0, thumb_w, r.height())

    def _text_rect(r: QRectF) -> QRectF:
        thumb_w, _ = _list_metrics(r, state["w"])
        return QRectF(thumb_w, 0, _list_text_width(r, state["w"]), r.height())

    def _meta_rect(r: QRectF) -> QRectF:
        thumb_w, meta_w = _list_metrics(r, state["w"])
        return QRectF(thumb_w + _list_text_width(r, state["w"]), 0, meta_w, r.height())

    return [_thumb_rect, _text_rect, _meta_rect]


def _bind_list_row(
    card: Button,
    *,
    on_activate: Callable | None = None,
    on_context_menu: Callable | None = None,
) -> None:
    """Route region clicks: the whole row (thumb/text/meta) activates.

    Pool-safe: ``grid_view._rebind_card`` re-runs this after disconnecting,
    so recycled rows never carry a stale closure.
    """
    if on_activate is not None:

        def _on_region(region_id: str, c=card) -> None:
            if region_id not in _PLATE_IDS:
                return
            from PySide6.QtWidgets import QApplication

            try:
                additive = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier)
            except Exception:
                additive = False
            item = getattr(c, "_gallery_item", None)
            path = getattr(item, "path", None) if item is not None else None
            if path is None:
                try:
                    path = Path(str(c.property("gallery_path") or ""))
                except Exception:
                    return
            try:
                on_activate(path, additive)
            except TypeError:
                try:
                    on_activate(path)
                except Exception:
                    pass

        try:
            card.regionClicked.connect(_on_region)
        except Exception:
            pass
        try:
            if hasattr(card, "clicked"):

                def _on_clicked(c=card) -> None:
                    item = getattr(c, "_gallery_item", None)
                    path = getattr(item, "path", None) if item is not None else None
                    if path is None:
                        try:
                            path = Path(str(c.property("gallery_path") or ""))
                        except Exception:
                            return
                    try:
                        on_activate(path, False)
                    except TypeError:
                        try:
                            on_activate(path)
                        except Exception:
                            pass

                card.clicked.connect(_on_clicked)
        except Exception:
            pass
    if on_context_menu is not None:
        try:
            if hasattr(card, "rightClicked"):

                def _on_right(c=card) -> None:
                    item = getattr(c, "_gallery_item", None)
                    path = getattr(item, "path", None) if item is not None else None
                    if path is None:
                        try:
                            path = Path(str(c.property("gallery_path") or ""))
                        except Exception:
                            return
                    try:
                        on_context_menu(path)
                    except Exception:
                        pass

                card.rightClicked.connect(_on_right)
        except Exception:
            pass


def _metric_dots_for(
    item: GalleryItem,
    mode: object,
    domain: object,
    translate=None,
    profile=None,
):
    """Metric-axis dot colors + tooltip infos (grid card parity, lazy import)."""
    try:
        from tabs.image_gallery.ui.card.dots import metric_dots_for_item

        return metric_dots_for_item(
            item, mode=mode, domain=domain, translate=translate, profile=profile
        )
    except Exception:
        return (), ()


def build_gallery_list_card(
    item: GalleryItem,
    parent: QWidget | None = None,
    on_activate: Callable | None = None,
    on_context_menu: Callable | None = None,
    mode: object = None,
    profile: object = None,
    *,
    translate=None,
    domain: object = None,
) -> Button:
    """Factory for a palette-style gallery list row (thumb + title + meta).

    *domain* is the judgment domain (``"ai"`` / ``"algorithms"``) the metric
    dots read; unknown/None degrades to Algorithms inside ``quality_read``.
    *profile* is the ACTIVE metric profile (beats *mode*; ``None`` → mode map).
    """
    state = {"w": _thumb_width_for(item)}
    card = Button(
        regions=[
            _thumb_region(item),
            ButtonRegion(id="text", rows=_list_text_rows(item, translate), weight=1.0, group="card",
                         corner_radii=(0, 0, 0, 0)),
            ButtonRegion(id="meta", rows=_list_meta_rows(item, translate), weight=0.0, group="card",
                         corner_radii=(0, 8, 8, 0)),
        ],
        split=CustomSplit(rect_fns=_make_rect_fns(state)),
        variant="default",
        size=(0, LIST_CARD_H),
        content_padding=_GALLERY_LIST_PADDING,
        # Rounded outer defines the row silhouette on both ends now that the
        # delete chrome (which used to cap the right corner) is gone. 8px is
        # the same radius the thumb region carried; outer and thumb share the
        # left curve, the right cap comes from the outer path.
        corner_radius=8,
        overlay_painter=_list_row_overlay_painter,
        parent=parent,
        defer_click="ripple",
    )
    try:
        # Compact rows: single rows center in the full height. NOTE: this
        # MUST be the Python attribute — build_region_content reads
        # button._rows_compact, a Qt dynamic property alone leaves the
        # non-compact ratio=0.5 layout (content only in the top half).
        card._rows_compact = True  # type: ignore[attr-defined]
        card.setProperty("_rows_compact", True)
        card._gallery_row_state = state  # type: ignore[attr-defined]
        # Attach the tab translator ONCE at build (grid ``_gallery_translate``
        # parity): ``update_gallery_list_card`` defaults to it, so pooled-row
        # rebinds never need ``translate=`` threaded through every call site.
        card._gallery_translate = translate  # type: ignore[attr-defined]
        _dots, _infos = _metric_dots_for(item, mode, domain, translate, profile)
        card._gallery_dot_colors = tuple(_dots)  # type: ignore[attr-defined]
        card._gallery_dot_infos = tuple(_infos)  # type: ignore[attr-defined]
        card._gallery_mode = mode  # type: ignore[attr-defined]
        card._gallery_domain = domain  # type: ignore[attr-defined]
        card._gallery_dot_geometry = None  # type: ignore[attr-defined]
        _attach_list_item(card, item)
        _apply_list_rejected_visuals(card, item)
    except Exception:
        pass
    try:
        from tabs.image_gallery.ui.card.dot_tooltip import ensure_dot_tooltip

        ensure_dot_tooltip(card)
    except Exception:
        pass
    if on_activate is not None or on_context_menu is not None:
        _bind_list_row(card, on_activate=on_activate, on_context_menu=on_context_menu)
    return card


def _attach_list_item(card: Button, item: GalleryItem) -> None:
    """Stash live item reference on the row (card._attach_item parity)."""
    card._gallery_item = item  # type: ignore[attr-defined]
    try:
        card.setProperty("gallery_path", str(item.path))
    except Exception:
        pass


def update_gallery_list_card(
    card: Button,
    item: GalleryItem,
    mode: object = None,
    *,
    translate=None,
    domain: object = None,
    profile: object = None,
) -> None:
    """In-place update of a live list row (update_gallery_card parity)."""
    _tr = translate
    if not callable(_tr):
        # Single source: the translator attached at build time.
        _tr = getattr(card, "_gallery_translate", None)
    _mode = mode
    if _mode is None:
        _mode = getattr(card, "_gallery_mode", None)
    _domain = domain
    if _domain is None:
        _domain = getattr(card, "_gallery_domain", None)
    # Live profile, never the row's own memory (see card.update_gallery_card):
    # a folder without a stored profile must fall back to the mode mapping.
    _profile = profile
    try:
        _dots, _infos = _metric_dots_for(item, _mode, _domain, _tr, _profile)
        card._gallery_dot_colors = tuple(_dots)  # type: ignore[attr-defined]
        card._gallery_dot_infos = tuple(_infos)  # type: ignore[attr-defined]
        card._gallery_mode = _mode  # type: ignore[attr-defined]
        card._gallery_domain = _domain  # type: ignore[attr-defined]
        card._gallery_dot_geometry = None  # type: ignore[attr-defined]
    except Exception:
        pass
    _attach_list_item(card, item)
    try:
        state = getattr(card, "_gallery_row_state", None)
        if isinstance(state, dict):
            state["w"] = _thumb_width_for(item)
    except Exception:
        pass
    thumb = getattr(item, "thumbnail", None)
    if thumb is not None and not thumb.isNull():
        try:
            current = card.region("thumb").pixmap
        except Exception:
            current = None
        if current is not thumb:
            card.update_region("thumb", pixmap=thumb, image_fill="cover")
    else:
        try:
            unreadable = bool(item_unreadable(item))
        except Exception:
            unreadable = False
        card.update_region("thumb", pixmap=None, image_fill="cover")
        try:
            card.update_region("thumb", text="!" if unreadable else "")
        except Exception:
            pass
    try:
        card.update_region("text", rows=_list_text_rows(item, _tr))
        card.update_region("meta", rows=_list_meta_rows(item, _tr))
    except Exception:
        pass
    try:
        parts = [item.name]
        try:
            from tabs.image_gallery.ui.card.visuals import (
                analysis_tooltip_lines,
                vlm_tiebreak_tooltip_line,
            )

            parts.extend(analysis_tooltip_lines(getattr(item, "analysis", None), _tr))
        except Exception:
            pass
        err = getattr(item, "analysis_error", None)
        if err:
            parts.append(str(err))
        vlm_err = getattr(item, "vlm_tie_error", None)
        if vlm_err:
            parts.append(vlm_tiebreak_tooltip_line(_tr, vlm_err))
        card.setToolTip("\n".join(parts))
    except Exception:
        pass
    try:
        _apply_list_rejected_visuals(card, item)
    except Exception:
        pass
