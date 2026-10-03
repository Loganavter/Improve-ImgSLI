"""Gallery card factory — Button with cover pixmap + text rows.

Thin owner per CODE_PATTERNS.md: construction/wiring + state on Button
itself (``_gallery_*`` attributes). Bodies live in ``ui/card/*`` helpers
as plain functions taking the card/owner; no second class, no ad-hoc
stylesheets — painter pipeline owns visuals. Lazy imports avoid cycles.
"""

from __future__ import annotations

from pathlib import Path as _Path

__path__ = [str(_Path(__file__).with_suffix(""))]  # type: ignore[attr-defined]

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor

from sli_ui_toolkit.widgets import Button, ButtonRegion, CustomSplit

if TYPE_CHECKING:
    from tabs.image_gallery.models import GalleryItem

GALLERY_CARD_W = 250
GALLERY_CARD_H = 170
# Frozen seam with Wave B (gallery DnD): mime type for card drags, defined
# ONCE here. Payload = newline-separated ``file://`` URLs, plus
# ``QMimeData.setUrls()`` with the same files (copy semantics on drop).
GALLERY_PATHS_MIME = "application/x-imgsli-gallery-paths"
# Reference: preview 234×110 r8 at 8,8 inside 250×170 r10 outer, bottom zone 52 (110+52+8+8=170) — balanced vertical
_GALLERY_CONTENT_PADDING: tuple[float, float, float, float] = (8.0, 8.0, 8.0, 8.0)


def _theme_is_dark() -> bool:
    """Darkness for fallback selection — delegates to ``dots._is_dark``."""
    try:
        from tabs.image_gallery.ui.card.dots import _is_dark as _dots_is_dark

        return bool(_dots_is_dark())
    except Exception:
        return True


def _gallery_card_bg() -> QColor:
    """Card surface via theme token with a light/dark-aware fallback chain.

    Chain (frozen seam): ``gallery.card.background`` → ``surface.list`` →
    ``surface.background`` → ``#ffffff`` (light) / dark gray (dark).
    NOTE: the historical dark-only ``QColor(56, 56, 56)`` default (== the
    legacy dark ``gallery.card.background`` value) is kept for the dark
    theme only; the light theme falls back to white.
    """
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        for token in ("gallery.card.background", "surface.list", "surface.background"):
            c = try_resolve_theme_color(ThemeManager.get_instance(), token)
            if c is not None:
                return c if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    if _theme_is_dark():
        return QColor(0x38, 0x38, 0x38)
    return QColor("#ffffff")


def _attach_item(card: Button, item: GalleryItem) -> None:
    """Stash live item reference on the card for in-place updates."""
    card._gallery_item = item  # type: ignore[attr-defined]
    try:
        card.setProperty("gallery_path", str(item.path))
    except Exception:
        pass


def _bind_gallery_card(
    card: Button,
    *,
    on_activate: Callable | None = None,
    on_context_menu: Callable | None = None,
) -> None:
    """Attach click/context handlers to a gallery card.

    ``on_activate`` receives ``(Path, additive bool)`` or just ``(Path,)``.
    ``on_context_menu`` receives ``(Path,)``.
    """
    if on_activate is not None:

        def _on_region(_region_id: str, c=card) -> None:
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


def build_gallery_card(*args, **kwargs) -> Button:  # type: ignore[no-untyped-def]
    """Factory for a gallery card Button.

    Structure: cover pixmap region (image_fill="cover") + text rows,
    split vertically via ``VerticalSplit``. Painter pipeline owns visuals.
    """
    # Lazy imports to avoid cycles (CODE_PATTERNS.md).
    from tabs.image_gallery.ui.card.dots import _dots_for_item
    from tabs.image_gallery.ui.card.hover import _CardHoverFilter
    from tabs.image_gallery.ui.card.painters import _gallery_card_overlay_painter
    from tabs.image_gallery.ui.card.regions import _cover_region, _text_rows
    from tabs.image_gallery.ui.card.visuals import _apply_rejected_visuals, apply_fixed_gallery_card_size

    on_activate = kwargs.pop("on_activate", None)
    on_context_menu = kwargs.pop("on_context_menu", None)
    translate = kwargs.pop("translate", None)
    parent = kwargs.pop("parent", None)
    item = kwargs.pop("item", None)
    owner = kwargs.pop("owner", None)

    actual_parent = parent
    actual_item = item
    actual_translate = translate

    if args:
        if actual_parent is None and len(args) >= 1:
            first = args[0]
            try:
                is_widget = isinstance(first, QWidget)
            except Exception:
                is_widget = False
            has_path = hasattr(first, "path") and hasattr(first, "name")
            if not is_widget and has_path:
                actual_item = first
                args = args[1:]
            else:
                actual_parent = first
                args = args[1:]
        if actual_item is None and len(args) >= 1:
            actual_item = args[0]
            args = args[1:]
        if actual_translate is None and len(args) >= 1:
            cand = args[0]
            if cand is None or callable(cand):
                actual_translate = cand
                args = args[1:]
        if on_activate is None and len(args) >= 1:
            on_activate = args[0]
            args = args[1:]
        if on_context_menu is None and len(args) >= 1:
            on_context_menu = args[0]
            args = args[1:]

    if actual_item is None:
        raise TypeError("build_gallery_card missing required GalleryItem 'item'")
    mode = kwargs.pop("mode", None)
    if mode is None:
        try:
            mode = getattr(actual_item, "mode", None)
        except Exception:
            mode = None
    if mode is None and owner is not None:
        try:
            st = getattr(owner, "state", None)
            mode = getattr(st, "mode", None) if st is not None else getattr(owner, "_mode", None)
        except Exception:
            mode = None
    cover = _cover_region(actual_item)
    text_rows = _text_rows(actual_item, actual_translate, mode=mode)
    # CustomSplit for 8px padding around preview 234×110 r8 at 8,8, text 52 zone at 118 — matches svg 250×170 r10 outer
    # Bg region covers whole outer for card-surface padding and bottom rounding — fixes toolkit group seam
    def _bg_rect(r: QRectF) -> QRectF:
        return QRectF(0, 0, r.width(), r.height())

    def _cover_rect(r: QRectF) -> QRectF:
        return QRectF(8, 8, 234, 110)

    def _text_rect(r: QRectF) -> QRectF:
        return QRectF(0, 118, r.width(), 52)

    card = Button(
        regions=[
            ButtonRegion(
                id="bg",
                group="card",
                corner_radii=(10, 10, 10, 10),
                hover_color=QColor(0, 0, 0, 0),
            ),
            cover,
            ButtonRegion(
                id="text",
                rows=text_rows,
                weight=1.0,
                group="card",
                corner_radii=(0, 0, 10, 10),
                hover_color=QColor(0, 0, 0, 0),
            ),
        ],
        split=CustomSplit(rect_fns=[_bg_rect, _cover_rect, _text_rect]),
        variant="default",
        size=(GALLERY_CARD_W, GALLERY_CARD_H),
        content_padding=_GALLERY_CONTENT_PADDING,
        corner_radius=10,
        overlay_painter=_gallery_card_overlay_painter,
        parent=actual_parent,
        # LMB activation (toggle/quicklook, hundreds of ms) runs after the
        # press ripple finishes. rightClicked (context menu) is unaffected:
        # the toolkit only defers left-click paths.
        defer_click="ripple",
    )
    card._rows_compact = True  # type: ignore[attr-defined]
    # Ensure text rows are centered vertically within text region (not top)
    try:
        card.setProperty("_rows_compact", True)
    except Exception:
        pass
    apply_fixed_gallery_card_size(card)
    _attach_item(card, actual_item)
    try:
        _, _dcols = _dots_for_item(actual_item, mode=mode)
        card._gallery_dot_colors = tuple(_dcols)  # type: ignore[attr-defined]
        card._gallery_mode = mode  # type: ignore[attr-defined]
    except Exception:
        try:
            card._gallery_dot_colors = ()  # type: ignore[attr-defined]
        except Exception:
            pass
    if owner is not None:
        try:
            card._gallery_owner = owner  # type: ignore[attr-defined]
        except Exception:
            pass
    try:
        _apply_rejected_visuals(card, actual_item)
    except Exception:
        pass
    try:
        filt = _CardHoverFilter(card, owner)
        card.installEventFilter(filt)
        card._gallery_hover_filter = filt  # type: ignore[attr-defined]
    except Exception:
        pass
    if on_activate is not None or on_context_menu is not None:
        _bind_gallery_card(card, on_activate=on_activate, on_context_menu=on_context_menu)
    if on_context_menu is None:
        try:
            if hasattr(card, "rightClicked"):

                def _fallback_right(c=card, o=owner):
                    from PySide6.QtGui import QCursor

                    item2 = getattr(c, "_gallery_item", None)
                    p2 = getattr(item2, "path", None) if item2 is not None else None
                    if p2 is None:
                        try:
                            p2 = Path(str(c.property("gallery_path") or ""))
                        except Exception:
                            return
                    try:
                        gp = QCursor.pos()
                    except Exception:
                        gp = None
                    try:
                        _m = getattr(c, "_gallery_mode", None)
                    except Exception:
                        _m = None
                    from tabs.image_gallery.ui.card.context_menu import popup_gallery_card_context_menu

                    popup_gallery_card_context_menu(c, o, Path(p2), global_pos=gp, mode=_m)

                card.rightClicked.connect(_fallback_right)
        except Exception:
            pass
    return card


def update_gallery_card(card: Button, item: GalleryItem, mode: object = None, owner: object = None) -> None:
    """In-place update of a live gallery card for ``item``.

    *owner* is the explicit triage owner for the mode fallback (threaded
    by callers); the pooled ``_gallery_owner`` attribute is no longer
    consulted (G2 gallery contract). All live callers pass ``mode``
    explicitly, so ``owner=None`` simply skips the fallback (fail-open).
    """
    from tabs.image_gallery.ui.card.dots import _dots_for_item
    from tabs.image_gallery.ui.card.regions import _item_unreadable, _text_rows
    from tabs.image_gallery.ui.card.visuals import _apply_rejected_visuals

    # Pooled cards are rebound to other items; hover/menu state is per-widget
    # and must not survive the rebind (see reset_card_hover_state). Same-path
    # in-place updates (thumbnail arrival) keep the live hover.
    try:
        _old_path = getattr(getattr(card, "_gallery_item", None), "path", None)
    except Exception:
        _old_path = None
    _attach_item(card, item)
    try:
        _new_path = getattr(item, "path", None)
    except Exception:
        _new_path = None
    if _old_path is not None and _new_path is not None and _old_path != _new_path:
        try:
            from tabs.image_gallery.ui.card.hover import reset_card_hover_state

            reset_card_hover_state(card)
        except Exception:
            pass
    _mode = mode
    if _mode is None:
        try:
            _mode = getattr(card, "_gallery_mode", None)
        except Exception:
            _mode = None
    if _mode is None:
        try:
            _mode = getattr(item, "mode", None)
        except Exception:
            _mode = None
    if _mode is None and owner is not None:
        try:
            st = getattr(owner, "state", None)
            _mode = getattr(st, "mode", None) if st is not None else getattr(owner, "_mode", None)
        except Exception:
            pass
    try:
        _, _dcols = _dots_for_item(item, mode=_mode)
        card._gallery_dot_colors = tuple(_dcols)  # type: ignore[attr-defined]
        card._gallery_mode = _mode  # type: ignore[attr-defined]
    except Exception:
        pass
    thumb = getattr(item, "thumbnail", None)
    if thumb is not None and not thumb.isNull():
        # Delivery batches re-run this per item: re-setting the IDENTICAL
        # pixmap still costs a full set_regions (rects + repaint). Skip when
        # the region already shows this exact object.
        try:
            current = card.region("cover").pixmap
        except Exception:
            current = None
        if current is not thumb:
            card.update_region("cover", pixmap=thumb, image_fill="cover")
    else:
        card.update_region("cover", pixmap=None, image_fill="cover")
        try:
            card.update_region("cover", text="!" if _item_unreadable(item) else "")
        except Exception:
            pass
    rows = _text_rows(item, translate=None, mode=_mode)
    card.update_region("text", rows=rows)
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


# Re-exports via PEP 562 for backward compat (tests import via card).
_LAZY_REEXPORTS: dict[str, tuple[str, str]] = {
    "_ACCENT_TOKEN_FALLBACK": ("tabs.image_gallery.ui.card.dots", "_ACCENT_TOKEN_FALLBACK"),
    "_DOTS_ROW_GAP": ("tabs.image_gallery.ui.card.dots", "_DOTS_ROW_GAP"),
    "_DOTS_TEXT": ("tabs.image_gallery.ui.card.dots", "_DOTS_TEXT"),
    "_ERROR_LINE_TOKEN_FALLBACK": ("tabs.image_gallery.ui.card.dots", "_ERROR_LINE_TOKEN_FALLBACK"),
    "_SEVERITY_TOKEN_FALLBACKS": ("tabs.image_gallery.ui.card.dots", "_SEVERITY_TOKEN_FALLBACKS"),
    "_dots_for_item": ("tabs.image_gallery.ui.card.dots", "_dots_for_item"),
    "_accent_color": ("tabs.image_gallery.ui.card.dots", "_accent_color"),
    "_error_line_color": ("tabs.image_gallery.ui.card.dots", "_error_line_color"),
    "_is_dark": ("tabs.image_gallery.ui.card.dots", "_is_dark"),
    "_severity_color": ("tabs.image_gallery.ui.card.dots", "_severity_color"),
    "_token_color": ("tabs.image_gallery.ui.card.dots", "_token_color"),
    "_CardHoverFilter": ("tabs.image_gallery.ui.card.hover", "_CardHoverFilter"),
    "_hide_card_hover_underline": ("tabs.image_gallery.ui.card.hover", "_hide_card_hover_underline"),
    "_show_card_hover_underline": ("tabs.image_gallery.ui.card.hover", "_show_card_hover_underline"),
    "_dots_overlay_painter": ("tabs.image_gallery.ui.card.painters", "_dots_overlay_painter"),
    "_gallery_card_overlay_painter": ("tabs.image_gallery.ui.card.painters", "_gallery_card_overlay_painter"),
    "_left_badge_painter": ("tabs.image_gallery.ui.card.painters", "_left_badge_painter"),
    "_cover_region": ("tabs.image_gallery.ui.card.regions", "_cover_region"),
    "_item_unreadable": ("tabs.image_gallery.ui.card.regions", "_item_unreadable"),
    "_text_rows": ("tabs.image_gallery.ui.card.regions", "_text_rows"),
    "_translate_or_default": ("tabs.image_gallery.ui.card.regions", "_translate_or_default"),
    "_apply_rejected_visuals": ("tabs.image_gallery.ui.card.visuals", "_apply_rejected_visuals"),
    "apply_fixed_gallery_card_size": ("tabs.image_gallery.ui.card.visuals", "apply_fixed_gallery_card_size"),
    "apply_gallery_selection": ("tabs.image_gallery.ui.card.visuals", "apply_gallery_selection"),
    "gallery_selection_accent": ("tabs.image_gallery.ui.card.visuals", "gallery_selection_accent"),
    "popup_gallery_card_context_menu": ("tabs.image_gallery.ui.card.context_menu", "popup_gallery_card_context_menu"),
}


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    if name in _LAZY_REEXPORTS:
        mod, attr = _LAZY_REEXPORTS[name]
        import importlib

        return getattr(importlib.import_module(mod), attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():  # type: ignore[no-untyped-def]
    return sorted(list(globals().keys()) + list(_LAZY_REEXPORTS.keys()))
