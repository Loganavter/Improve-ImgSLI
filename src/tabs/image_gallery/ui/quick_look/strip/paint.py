"""Quick Look series-strip painting + wheel scroll + selection visuals.

Split out of the former ``ui/quick_look/strip.py`` (plan-gallery-split-2026-10-17,
Part C2). Bodies moved verbatim; names/signatures unchanged.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QGraphicsOpacityEffect

from .helpers import _strip_thumb_pitch, _strip_wheel_step


def _strip_lasso_pick(overlay, rect) -> list[str]:
    """Strip item paths whose containers intersect *rect* (viewport coords).

    Pure geometry: maps each thumb container into the scroll viewport (valid
    downward mapping) and keeps the ones the band touches. Series order is
    preserved (container order == series order). Used both by the live
    mid-drag preview and the release-time commit. Never raises.
    """
    try:
        containers = list(getattr(overlay, "_strip_buttons", None) or [])
        items = list(getattr(overlay, "_series_items", None) or [])
    except Exception:
        return []
    try:
        _scroll = getattr(overlay, "_strip_scroll", None)
        _view = _scroll.viewport() if _scroll is not None else None
    except Exception:
        _view = None
    picked: list[str] = []
    try:
        from PySide6.QtCore import QRect as _QR2

        for container, m in zip(containers, items):
            try:
                g = container.geometry()
                if _view is not None:
                    try:
                        _top = container.mapTo(_view, g.topLeft())
                        g = _QR2(_top, g.size())
                    except Exception:
                        pass
            except Exception:
                continue
            try:
                if not g.intersects(rect):
                    continue
            except Exception:
                continue
            try:
                picked.append(str(getattr(m, "path", "") or ""))
            except Exception:
                continue
    except Exception:
        pass
    return [p for p in picked if p]
def _strip_apply_lasso_selection(overlay, rect) -> None:
    """Select strip items whose containers intersect *rect* (viewport coords).

    Quick Look keeps its OWN selection: the picked set lives on the overlay
    (``_strip_selected_paths``) and is never written back to the owner, so a
    strip lasso highlights strip thumbs only and leaves the main grid
    untouched. Refreshes the thumb selection visuals.
    """
    picked = _strip_lasso_pick(overlay, rect)
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg4

        _dbg4(
            "strip lasso picked=%d rect=%s",
            len(picked),
            rect,
        )
    except Exception:
        pass
    try:
        overlay._strip_selected_paths = set(picked)
    except Exception:
        pass
    # Quick Look owns this selection: deliberately NOT written back to the
    # owner (main-grid) state. A strip lasso highlights strip thumbs only —
    # the cards in the tab behind the overlay stay untouched.
    try:
        _strip_refresh_selection(overlay)
    except Exception:
        pass
def _strip_refresh_selection(overlay) -> None:
    """Repaint thumb selection state: lasso-selected or not.

    Region-level CHECKED (``Button.setChecked`` is a no-op without a
    toggle capability) — distinct from the viewing accent border — plus
    the ``strip_selected`` property the overlay painter reads over the
    cover pixmap (same dynamic-state contract as the full rebuild).
    """
    try:
        selected = set(getattr(overlay, "_strip_selected_paths", None) or set())
    except Exception:
        selected = set()
    try:
        from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
        from sli_ui_toolkit.widgets import Button as _B

        for container in list(getattr(overlay, "_strip_buttons", None) or []):
            try:
                thumb = next(
                    (b for b in container.findChildren(_B) if b.objectName().startswith("quicklook_strip_")),
                    None,
                )
                if thumb is None:
                    continue
                path = str(thumb.property("gallery_path") or "")
                was = thumb.blockSignals(True)
                try:
                    thumb.setProperty("strip_selected", path in selected)
                except Exception:
                    pass
                try:
                    thumb._controller.set_state("thumb", ButtonState.CHECKED, path in selected)
                except Exception:
                    pass
                try:
                    thumb.blockSignals(was)
                except Exception:
                    pass
                try:
                    thumb.update()
                except Exception:
                    pass
            except Exception:
                continue
    except Exception:
        pass
def _strip_scroll_wheel(overlay, event) -> bool:
    """Apply one wheel event to the strip horizontal bar. True if consumed."""
    try:
        scroll = getattr(overlay, "_strip_scroll", None)
        if scroll is None:
            return False
        bar = scroll.horizontalScrollBar()
        if bar.maximum() <= bar.minimum():
            return False  # nothing to scroll — let it propagate.
        try:
            pitch = _strip_thumb_pitch(overlay)
        except Exception:
            pitch = 76
        step = _strip_wheel_step(event, pitch)
        if step is None or step == 0:
            return False
        new = max(bar.minimum(), min(bar.maximum(), bar.value() + step))
        if new == bar.value():
            return False  # at the edge — propagate outward.
        bar.setValue(new)
        return True
    except Exception:
        return False
def _strip_selection_overlay(painter, ctx, tm) -> None:  # type: ignore[no-untyped-def]
    """Paint the Quick Look strip's own selection marker over a thumb.

    Region-level CHECKED renders behind the cover pixmap, so over a photo it
    reads as an indistinguishable hover-like wash (never the selection).
    The selected thumb instead gets an explicit, readable marker in the
    widget-scoped overlay pass: a translucent accent tint over the image plus
    a 2px accent border inside the thumb outline. Never raises.
    """
    try:
        widget = getattr(ctx, "widget", None)
        try:
            selected = bool(widget.property("strip_selected")) if widget is not None else False
        except Exception:
            selected = False
        if not selected:
            return
        rect = getattr(ctx, "rect", None)
        if rect is None:
            return
        from PySide6.QtCore import Qt as _QtSel
        from PySide6.QtGui import QBrush as _QBrushSel
        from PySide6.QtGui import QColor as _QColorSel
        from PySide6.QtGui import QPainterPath as _QPathSel
        from PySide6.QtGui import QPen as _QPenSel

        from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _sel_dark
        from tabs.image_gallery.ui.quick_look.helpers import _token_color

        dark = bool(_sel_dark())
        accent = _token_color("accent", "#0078D4" if not dark else "#0096FF")
        if accent is None or not accent.isValid():
            accent = _QColorSel("#0078D4")
        tint = _QColorSel(accent)
        tint.setAlpha(90)
        radii = getattr(ctx, "corner_radii", None) or (0, 0, 0, 0)
        try:
            radius = float(radii[0])
        except Exception:
            radius = 0.0
        painter.save()
        try:
            painter.setRenderHint(painter.RenderHint.Antialiasing, True)
            painter.setPen(_QtSel.PenStyle.NoPen)
            painter.setBrush(_QBrushSel(tint))
            try:
                path = _QPathSel()
                path.addRoundedRect(rect, radius, radius)
                painter.drawPath(path)
            except Exception:
                painter.drawRect(rect)
            pen = _QPenSel(accent)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(_QtSel.BrushStyle.NoBrush)
            try:
                inset = rect.adjusted(1, 1, -1, -1)
                path2 = _QPathSel()
                path2.addRoundedRect(inset, radius, radius)
                painter.drawPath(path2)
            except Exception:
                painter.drawRect(rect)
        finally:
            painter.restore()
    except Exception:
        pass
def _strip_source_outline(painter, ctx, tm) -> None:  # type: ignore[no-untyped-def]
    """Re-paint the source/viewing outline ON TOP of the cover as a solid ring.

    The toolkit's widget-scope ``BorderLayer`` strokes the outline *under*
    the cover pixmap. The pixmap's rounded clip is antialiased, so its
    corner pixels are semi-transparent and let the under-border show
    through unevenly — the outline's inner edge no longer nests with the
    pixmap clip (two independently-antialiased edges on one boundary; see
    docs/dev/rendering/cases/sdf-edge-feather-1px.md and
    docs/dev/qt/precedents.md `painting-antialias-rounded-clips`). Here the
    same band is filled opaquely in the widget-scope overlay pass (after
    every region layer), covering the pixmap's corner pixels and leaving a
    single clean edge. The under-border stays (tests/`borderColor()` rely on
    it) — it is simply no longer visible.

    Geometry mirrors ``BorderLayer``: pen width ``w`` centered on the path
    inset by ``w/2``, so the outer boundary is the widget rect at radius
    ``r + w/2`` and the inner boundary is inset by ``w`` at radius
    ``r - w/2``. Never raises.
    """
    try:
        widget = getattr(ctx, "widget", None)
        if widget is None:
            return
        try:
            color = widget.borderColor()
        except Exception:
            color = None
        if color is None and hasattr(widget, "_border_color_override"):
            color = getattr(widget, "_border_color_override", None)
        if color is None:
            return
        from PySide6.QtCore import Qt as _QtOut
        from PySide6.QtGui import QBrush as _QBrushOut
        from PySide6.QtGui import QColor as _QColorOut
        from PySide6.QtGui import QPainterPath as _QPathOut

        if not isinstance(color, _QColorOut):
            color = _QColorOut(color)
        if not color.isValid():
            return
        try:
            width = float(widget.property("borderWidth") or 1.0)
        except Exception:
            width = 1.0
        width = max(1.0, width)
        rect = getattr(ctx, "rect", None)
        if rect is None:
            return
        radii = getattr(ctx, "corner_radii", None) or (0, 0, 0, 0)
        try:
            radius = float(radii[0])
        except Exception:
            radius = 0.0
        half = width / 2.0
        outer = rect.adjusted(0, 0, 0, 0)
        inner = outer.adjusted(width, width, -width, -width)
        if inner.width() <= 0 or inner.height() <= 0:
            return
        path = _QPathOut()
        path.setFillRule(_QtOut.FillRule.OddEvenFill)
        path.addRoundedRect(outer, radius + half, radius + half)
        path.addRoundedRect(inner, max(0.0, radius - half), max(0.0, radius - half))
        painter.save()
        try:
            painter.setRenderHint(painter.RenderHint.Antialiasing, True)
            painter.setPen(_QtOut.PenStyle.NoPen)
            painter.setBrush(_QBrushOut(color))
            painter.drawPath(path)
        finally:
            painter.restore()
    except Exception:
        pass
def _strip_overlay_painter(painter, ctx, tm) -> None:  # type: ignore[no-untyped-def]
    """Strip thumb overlay: source outline + card hover wash + selection marker.

    Hover wash stays the visual hover only (no IconActionFlyout/capsule on
    strip thumbs); the source/viewing outline is re-painted on top as a
    solid ring (see ``_strip_source_outline``); the selection marker paints
    the strip's OWN selection over the image. Rank pills are real buttons
    now (bottom-center of each thumb), not painted badges.
    """
    try:
        from tabs.image_gallery.ui.card.painters import _gallery_hover_wash

        _gallery_hover_wash(painter, ctx, tm)
    except Exception:
        pass
    try:
        _strip_source_outline(painter, ctx, tm)
    except Exception:
        pass
    try:
        _strip_selection_overlay(painter, ctx, tm)
    except Exception:
        pass
def _refresh_strip_selection(overlay) -> None:
    """In-place selection refresh over the existing strip widgets.

    Updates checked/border/opacity from live item flags; creates no
    widgets, touches no layout. Rank pill text is structural (ranks are in
    the fingerprint), so pills are untouched here — only the viewing
    outline moves. Raises on any structural surprise so the
    caller falls back to the full rebuild (fail-open: performance only,
    never correctness).
    """
    from sli_ui_toolkit.widgets import Button as _RefreshButton

    items = list(overlay._series_items)
    containers = list(overlay._strip_buttons)
    if not containers or len(containers) != len(items):
        raise RuntimeError("strip refresh: container/item count mismatch")
    try:
        from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _rf_is_dark

        dark = bool(_rf_is_dark())
    except Exception:
        dark = True
    try:
        source_path = overlay._source_path
    except Exception:
        source_path = None
    try:
        current_idx = int(getattr(overlay, "_current_idx", 0) or 0)
    except Exception:
        current_idx = 0
    for idx, container in enumerate(containers):
        m = items[idx]
        btn = container.findChild(_RefreshButton, f"quicklook_strip_{idx}")
        if btn is None:
            raise RuntimeError(f"strip refresh: no thumb Button in container {idx}")
        is_viewing = idx == current_idx
        is_source = False
        try:
            if source_path is not None and Path(getattr(m, "path", "")) == Path(source_path):
                is_source = True
        except Exception:
            pass
        rejected = bool(getattr(m, "rejected", False))
        was_blocked = btn.blockSignals(True)
        try:
            try:
                _sel = set(getattr(overlay, "_strip_selected_paths", None) or set())
            except Exception:
                _sel = set()
            try:
                _p = str(getattr(m, "path", "") or "")
            except Exception:
                _p = ""
            try:
                # Local selection marker read by the overlay painter (the
                # region CHECKED background hides behind the cover pixmap).
                btn.setProperty("strip_selected", _p in _sel)
            except Exception:
                pass
            try:
                btn.setChecked(bool(is_viewing) or _p in _sel)
            except Exception:
                pass
            try:
                # Region-level selection visual (setChecked needs toggle).
                from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState as _BS2

                btn._controller.set_state("thumb", _BS2.CHECKED, _p in _sel)
            except Exception:
                pass
            # Border: verified clear path is set_border_color(None) (sets the
            # override to None) + borderWidth back to the fresh unset state.
            try:
                if is_source:
                    from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _ql_is_dark2
                    from tabs.image_gallery.ui.quick_look.helpers import _token_color

                    dark2 = _ql_is_dark2()
                    gold = _token_color("gallery.status.warn", "#b77900" if not dark2 else "#d9a441")
                    if gold is not None:
                        btn.set_border_color(gold)
                        try:
                            btn.setProperty("borderWidth", 2)
                        except Exception:
                            pass
                elif is_viewing:
                    from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _ql_is_dark3
                    from tabs.image_gallery.ui.quick_look.helpers import _token_color

                    dark3 = _ql_is_dark3()
                    accent_c = _token_color("accent", "#0078D4" if not dark3 else "#0096FF")
                    if accent_c is not None:
                        btn.set_border_color(accent_c)
                        try:
                            btn.setProperty("borderWidth", 2)
                        except Exception:
                            pass
                else:
                    btn.set_border_color(None)
                    try:
                        btn.setProperty("borderWidth", None)
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                current_effect = btn.graphicsEffect()
                if rejected:
                    if not isinstance(current_effect, QGraphicsOpacityEffect):
                        eff = QGraphicsOpacityEffect(btn)
                        eff.setOpacity(0.4)
                        btn.setGraphicsEffect(eff)
                    else:
                        current_effect.setOpacity(0.4)
                elif isinstance(current_effect, QGraphicsOpacityEffect):
                    btn.setGraphicsEffect(None)
            except Exception:
                pass
        finally:
            try:
                btn.blockSignals(was_blocked)
            except Exception:
                pass
