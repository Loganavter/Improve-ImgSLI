"""Quick look series strip — plain functions taking overlay.

Audit-Meta: pattern=thin-owner-target size=exempt reason="one strip concern: full rebuild + in-place selection refresh share one dynamic-state contract (refresh mirrors rebuild so the rebuild path stays byte-identical)"
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QEvent
from PySide6.QtWidgets import QGraphicsOpacityEffect, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonRegion, Label


def _strip_thumb_pitch(overlay) -> int:
    """One-thumb scroll pitch in px (live geometry, no size assumptions).

    Container width + layout spacing; falls back to the W6 66+10 budget
    when nothing is built yet. Never raises.
    """
    try:
        buttons = list(getattr(overlay, "_strip_buttons", None) or [])
        if buttons:
            try:
                w = int(buttons[0].width())
            except Exception:
                w = 0
            try:
                s = int(overlay._strip_layout.spacing())
            except Exception:
                s = 0
            if w > 0:
                return max(1, w + max(0, s))
    except Exception:
        pass
    try:
        return max(1, int(scaled_px(66)) + int(scaled_px(10)))
    except Exception:
        return 76


def _strip_wheel_step(event, pitch: int = 76) -> int | None:
    """Horizontal scroll px from a wheel event over the strip (pure).

    Prefers angleDelta.x; falls back to angleDelta.y (a plain vertical
    wheel over a horizontal filmstrip scrolls it — filmstrip convention);
    high-resolution pixel deltas map 1:1. One 120-unit notch moves exactly
    one thumb pitch (deliberately NOT lines*singleStep, which jumps three
    thumbs per notch). Sign follows Qt convention (positive delta scrolls
    toward the start). None when the event carries no scrollable delta.
    Never raises.
    """
    try:
        step = max(1, int(pitch))
    except Exception:
        step = 76
    try:
        try:
            pd = event.pixelDelta()
            if pd is not None and (int(pd.x()) or int(pd.y())):
                dx = int(pd.x())
                return -dx if dx else -int(pd.y())
        except Exception:
            pass
        try:
            ad = event.angleDelta()
            if ad is None:
                return None
            raw = int(ad.x()) or int(ad.y())
        except Exception:
            return None
        if not raw:
            return None
        return -int(round(raw / 120.0 * step))
    except Exception:
        return None


class _StripWheelFilter(QObject):
    """Viewport wheel filter: plain wheel over the strip scrolls it.

    The toolkit OverlayScrollArea glides only the vertical bar, which the
    strip never overflows — without this filter a wheel over the strip
    does nothing (the native bars are AlwaysOff). Consumes the event only
    when the strip actually moved (at an edge it returns False so the
    wheel propagates to the outer vertical column scroll). Installed once
    per overlay; parented to the viewport. Never raises.
    """

    def __init__(self, overlay, parent=None):
        super().__init__(parent)
        self._overlay = overlay

    def eventFilter(self, watched, event):  # noqa: N802
        try:
            if event.type() == QEvent.Type.Wheel and _strip_scroll_wheel(
                self._overlay, event
            ):
                return True
        except Exception:
            pass
        return False


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


def ensure_strip_visible(overlay) -> None:
    """Scroll the strip so the current thumb is visible (walk follow).

    Nothing in the app ever scrolled the strip — keyboard/button walks
    left the current thumb out of view with no affordance to find it.
    Called on every populate (both refresh and full-rebuild tails);
    fail-open to no-scroll, never correctness. Never raises.
    """
    try:
        scroll = getattr(overlay, "_strip_scroll", None)
        items = list(getattr(overlay, "_series_items", None) or [])
        buttons = list(getattr(overlay, "_strip_buttons", None) or [])
        if scroll is None or not items or len(buttons) != len(items):
            return
        try:
            idx = int(getattr(overlay, "_current_idx", 0) or 0)
        except Exception:
            return
        if not 0 <= idx < len(buttons):
            return
        try:
            pitch = _strip_thumb_pitch(overlay)
        except Exception:
            pitch = 76
        scroll.ensureWidgetVisible(buttons[idx], max(1, pitch), 0)
    except Exception:
        pass


def _apply_strip_badge(btn, badge_text, badge_style) -> None:
    """Apply a strip pill via the toolkit Button badge API.

    ``badge_style`` is the ``(filled, bg, border, text)`` tuple used across
    gallery pills. ``None`` text clears the badge. Toolkit-painted, so it
    scrolls/repaints with the button itself — no overlay pass needed.
    """
    try:
        if badge_text is None:
            try:
                btn.setBadge(None)
            except Exception:
                pass
            return
        try:
            btn.setBadge(str(badge_text))
        except Exception:
            return
        try:
            filled, bg, border, txt = badge_style
            btn.setBadgeStyle(
                filled=bool(filled),
                bordered=border is not None,
                background_color=bg,
                border_color=border,
                text_color=txt,
            )
        except Exception:
            pass
    except Exception:
        pass


def ensure_strip_scroll(overlay) -> None:
    """Install the wheel filter once, then follow the current thumb."""
    try:
        if not bool(getattr(overlay, "_strip_wheel_installed", False)):
            try:
                scroll = getattr(overlay, "_strip_scroll", None)
                viewport = scroll.viewport() if scroll is not None else None
                if viewport is not None:
                    filt = _StripWheelFilter(overlay, viewport)
                    viewport.installEventFilter(filt)
                    overlay._strip_wheel_filter = filt
                    overlay._strip_wheel_installed = True
            except Exception:
                pass
    except Exception:
        pass
    ensure_strip_visible(overlay)


def _strip_overlay_painter(painter, ctx, tm) -> None:  # type: ignore[no-untyped-def]
    """Strip thumb overlay: card hover wash only.

    Visual hover only (no IconActionFlyout/capsule on strip thumbs).
    Thumb pills (rank/SOURCE/pending) render via the toolkit Button badge
    API (``btn.setBadge``), which paints with the button itself.
    """
    try:
        from tabs.image_gallery.ui.card.painters import _gallery_hover_wash

        _gallery_hover_wash(painter, ctx, tm)
    except Exception:
        pass


def _strip_rank_key(m) -> tuple:
    """Rank identity for one series member (badge input).

    Mirrors the badge priority in ``rebuild_strip``: crown_rank wins over
    rank, which wins over the is_best fallback.
    """
    try:
        c = getattr(m, "crown_rank", None)
        if c is not None:
            return ("crown", str(c))
        r = getattr(m, "rank", None)
        if r is not None:
            return ("rank", str(r))
    except Exception:
        pass
    try:
        if bool(getattr(m, "is_best", False)):
            return ("best", True)
    except Exception:
        pass
    return ("none", False)


def _strip_fingerprint(overlay) -> tuple:
    """Structural identity of the strip (everything a FULL rebuild consumes).

    Per-walk dynamic state (checked + border on old/new idx) is deliberately
    EXCLUDED — a walk changes only that, which the in-place refresh covers.
    Anything else (triage flags, ranks, theme, scale, series/source change)
    mismatches and falls back to today's full rebuild.
    """
    try:
        items = list(getattr(overlay, "_series_items", None) or [])
    except Exception:
        return ()
    try:
        paths = tuple(str(getattr(m, "path", "") or "") for m in items)
        rejected = tuple(bool(getattr(m, "rejected", False)) for m in items)
        pending = tuple(bool(getattr(m, "vlm_tie_pending", False)) for m in items)
        ranks = tuple(_strip_rank_key(m) for m in items)
        source = str(getattr(overlay, "_source_path", None) or "")
        try:
            from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _fp_is_dark

            dark = bool(_fp_is_dark())
        except Exception:
            dark = True
        try:
            sp = int(scaled_px(66))
        except Exception:
            sp = 66
        return (paths, rejected, pending, ranks, source, dark, sp)
    except Exception:
        return ()


def _refresh_strip_selection(overlay) -> None:
    """In-place selection refresh over the existing strip widgets.

    Updates checked/border/badge/opacity from live item flags; creates no
    widgets, touches no layout. Raises on any structural surprise so the
    caller falls back to the full rebuild (fail-open: performance only,
    never correctness). Captions are untouched: they only exist for
    tie-break pending items, and pending flags are part of the fingerprint
    (unchanged on this path by construction).
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
        btn = container.findChild(_RefreshButton)
        if btn is None:
            raise RuntimeError(f"strip refresh: no Button in container {idx}")
        is_viewing = idx == current_idx
        is_source = False
        try:
            if source_path is not None and Path(getattr(m, "path", "")) == Path(source_path):
                is_source = True
        except Exception:
            pass
        rejected = bool(getattr(m, "rejected", False))
        pending = bool(getattr(m, "vlm_tie_pending", False))
        was_blocked = btn.blockSignals(True)
        try:
            # Toolkit badge: pending … only (mirrors rebuild_strip).
            try:
                if pending:
                    btn.setBadge("…")
                    try:
                        from tabs.image_gallery.ui.quick_look.helpers import _token_color, _token_rgba_qcolor

                        from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _ql_is_dark

                        dark = _ql_is_dark()
                        bg = _token_color("surface.button", "#8a8a8a" if not dark else "#5a5a5a")
                        from PySide6.QtGui import QColor as _QC

                        try:
                            from sli_ui_toolkit.managers import ThemeManager

                            from ui.theming import try_resolve_theme_color

                            _txt = try_resolve_theme_color(ThemeManager.get_instance(), "button.primary.text")
                            txt_col = _txt if isinstance(_txt, _QC) else _QC(_txt) if isinstance(_txt, str) else None
                            if _txt is None or txt_col is None:
                                txt_col = _QC("#000000" if not dark else "#ffffff")
                        except Exception:
                            txt_col = _QC("#000000" if not dark else "#ffffff")
                        if bg is None:
                            bg = _QC(90, 90, 90)
                        btn.setBadgeStyle(filled=True, background_color=bg, text_color=txt_col)
                    except Exception:
                        pass
                else:
                    btn.setBadge(None)
            except Exception:
                pass
            # Overlay pill badge (mirrors rebuild_strip priority).
            try:
                from PySide6.QtGui import QColor as _QC

                from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _strip_dark
                from tabs.image_gallery.ui.quick_look.helpers import _token_color as _strip_token

                _strip_is_dark = _strip_dark()
                _badge_text = None
                _badge_style = None
                if pending:
                    pass  # toolkit … badge above; no overlay pill
                elif rejected:
                    pass  # no badge — dim effect below carries the signal
                elif is_source:
                    _gold = _strip_token("gallery.status.warn", "#b77900" if not _strip_is_dark else "#d9a441")
                    _badge_text = "SOURCE"
                    _badge_style = (True, _gold, _gold, _QC("#000000"))
                else:
                    _rank = getattr(m, "rank", None)
                    _crown = getattr(m, "crown_rank", None)
                    _rv = _crown if _crown is not None else _rank
                    if _rv is None and bool(getattr(m, "is_best", False)):
                        _rv = 1
                    if _rv is not None:
                        try:
                            _badge_text = f"#{int(_rv)}"
                        except Exception:
                            _badge_text = str(_rv)
                        _rank_bg = _strip_token("button.toggle.background.checked", "#555555")
                        _badge_style = (True, _rank_bg, _rank_bg, _QC("#000000"))
                # Pending keeps the toolkit "…" badge above: do not clear it.
                if not pending:
                    _apply_strip_badge(btn, _badge_text, _badge_style)
            except Exception:
                pass
            try:
                btn.setChecked(bool(is_viewing))
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


def rebuild_strip(overlay) -> None:
    # W6: svg pitch is 76px (thumbs x=816/892/968/1044, 66 wide) — the
    # HBox spacing is pinned here so 4 thumbs span 4*66+3*10=294px and
    # fit the 296px right column with no h-scroll. (The layout itself is
    # built in helpers.py, out of W6 scope; its spacing is overridden.)
    # Selection-only fast path: same series/triage/theme/scale as the last
    # full rebuild → update checked/border/badge/opacity in place, no widget
    # churn. Any mismatch (or first build) falls through to today's rebuild.
    try:
        _fp_now = _strip_fingerprint(overlay)
    except Exception:
        _fp_now = ()
    if _fp_now:
        try:
            _fp_stored = getattr(overlay, "_strip_fingerprint", None)
            _buttons = getattr(overlay, "_strip_buttons", None) or []
            _n_items = len(getattr(overlay, "_series_items", None) or [])
            if _fp_stored == _fp_now and _n_items and len(_buttons) == _n_items:
                _refresh_strip_selection(overlay)
                ensure_strip_scroll(overlay)
                try:
                    # Badge pass reads live attrs — repaint after in-place refresh.
                    overlay.update()
                except Exception:
                    pass
                return
        except Exception:
            pass
    # Full rebuild: drop the stored fingerprint first so a mid-rebuild
    # failure can never leave a stale match behind (fail-open).
    try:
        overlay._strip_fingerprint = None
    except Exception:
        pass
    try:
        overlay._strip_layout.setSpacing(scaled_px(10))
    except Exception:
        pass
    for b in list(overlay._strip_buttons):
        try:
            overlay._strip_layout.removeWidget(b)
            # Hide before orphaning: a visible widget reparented to None
            # maps a stillborn toplevel + stale activation token (global
            # busy cursor on Wayland — see grid_view._clear_series_headers).
            b.hide()
            b.setParent(None)
            b.deleteLater()
        except Exception:
            pass
    overlay._strip_buttons.clear()
    for cap in list(getattr(overlay, "_strip_caption_labels", [])):
        try:
            overlay._strip_layout.removeWidget(cap)
            cap.hide()
            cap.setParent(None)
            cap.deleteLater()
        except Exception:
            pass
    overlay._strip_caption_labels.clear()
    try:
        while overlay._strip_layout.count():
            it = overlay._strip_layout.takeAt(0)
            w = it.widget() if it is not None else None
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
    except Exception:
        pass
    for idx, m in enumerate(overlay._series_items):
        is_viewing = idx == overlay._current_idx
        is_source = False
        try:
            if overlay._source_path is not None and Path(getattr(m, "path", "")) == Path(overlay._source_path):
                is_source = True
        except Exception:
            pass
        rejected = bool(getattr(m, "rejected", False))
        pending = bool(getattr(m, "vlm_tie_pending", False))
        thumb_pm = None
        try:
            from tabs.image_gallery.ui.quick_look.helpers import _thumb_pixmap

            thumb_pm = _thumb_pixmap(m, scaled_px(66), scaled_px(44))
        except Exception:
            thumb_pm = None
        container = QWidget(overlay._strip_host)
        container.setObjectName(f"quicklook_strip_container_{idx}")
        cont_lay = QVBoxLayout(container)
        cont_lay.setContentsMargins(0, 0, 0, 0)
        cont_lay.setSpacing(scaled_px(2))
        cont_lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        # S4: thumbnail goes on a ButtonRegion (Button has no pixmap
        # param); text/badge/click/opacity behavior unchanged.
        regions = None
        if thumb_pm is not None and not thumb_pm.isNull():
            try:
                regions = [
                    ButtonRegion(
                        id="thumb",
                        pixmap=thumb_pm,
                        image_fill="cover",
                        group="card",
                        # Like the tab cards (cover r8) and clean-review
                        # thumbs (top r10): the painter clips the cover to
                        # these radii (PixmapContent rounded path).
                        corner_radii=(6, 6, 6, 6),
                    )
                ]
            except Exception:
                regions = None
        if regions is not None:
            # W6: 66px thumbs per svg (x=816/892/968/1044 w=66 h=44).
            # Series switch re-populates the overlay (~300ms) — let the
            # ripple finish first (same defer_click as the bar buttons).
            # overlay_painter: card hover wash + strip badge pill (visual
            # hover only, no flyout/capsule on strip thumbs).
            btn = Button(text="", variant="surface", size=(66, 44), parent=container, regions=regions, defer_click="ripple", overlay_painter=_strip_overlay_painter)
        else:
            btn = Button(text="", variant="surface", size=(66, 44), parent=container, defer_click="ripple", overlay_painter=_strip_overlay_painter)
        btn.setObjectName(f"quicklook_strip_{idx}")
        # D1: explicit arrow — strip thumbs are rebuilt per populate and
        # would otherwise inherit a stale plate resize cursor.
        try:
            from PySide6.QtCore import Qt as _Qt

            btn.setCursor(_Qt.CursorShape.ArrowCursor)
        except Exception:
            pass
        try:
            if pending:
                btn.setBadge("…")
                try:
                    from tabs.image_gallery.ui.quick_look.helpers import _token_color, _token_rgba_qcolor

                    from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _ql_is_dark

                    dark = _ql_is_dark()
                    bg = _token_color("surface.button", "#8a8a8a" if not dark else "#5a5a5a")
                    # badge text via theme token with light/dark-aware fallback
                    from PySide6.QtGui import QColor as _QC

                    try:
                        from sli_ui_toolkit.managers import ThemeManager

                        from ui.theming import try_resolve_theme_color

                        _txt = try_resolve_theme_color(ThemeManager.get_instance(), "button.primary.text")
                        txt_col = _txt if isinstance(_txt, _QC) else _QC(_txt) if isinstance(_txt, str) else None
                        if _txt is None or txt_col is None:
                            txt_col = _QC("#000000" if not dark else "#ffffff")
                    except Exception:
                        txt_col = _QC("#000000" if not dark else "#ffffff")
                    if bg is None:
                        bg = _QC(90, 90, 90)
                    btn.setBadgeStyle(filled=True, background_color=bg, text_color=txt_col)
                except Exception:
                    pass
        except Exception:
            pass
        # Thumb pills render via the toolkit Button badge API
        # (``_apply_strip_badge`` above): rank/SOURCE text with the same
        # priority. The toolkit badge path below is used ONLY for the …
        # pending case. Priority: pending (toolkit) > rejected (none — the
        # dim 0.4 opacity effect carries the signal) > SOURCE > ★ BEST > #N.
        try:
            if not pending:
                btn.setBadge(None)
        except Exception:
            pass
        try:
            from PySide6.QtGui import QColor as _QC

            from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _strip_dark
            from tabs.image_gallery.ui.quick_look.helpers import _token_color as _strip_token

            _strip_is_dark = _strip_dark()
            _badge_text = None
            _badge_style = None
            if pending:
                pass  # toolkit … badge above; no overlay pill
            elif rejected:
                pass  # no badge — dim effect below carries the signal
            elif is_source:
                _gold = _strip_token("gallery.status.warn", "#b77900" if not _strip_is_dark else "#d9a441")
                _badge_text = "SOURCE"
                _badge_style = (True, _gold, _gold, _QC("#000000"))
            else:
                # Synced with grid cards (ui/card/visuals.py): no BEST pill —
                # the leader shows its #N rank like every ranked item.
                _rank = getattr(m, "rank", None)
                _crown = getattr(m, "crown_rank", None)
                _rv = _crown if _crown is not None else _rank
                if _rv is None and bool(getattr(m, "is_best", False)):
                    _rv = 1
                if _rv is not None:
                    try:
                        _badge_text = f"#{int(_rv)}"
                    except Exception:
                        _badge_text = str(_rv)
                    _rank_bg = _strip_token("button.toggle.background.checked", "#555555")
                    _badge_style = (True, _rank_bg, _rank_bg, _QC("#000000"))
            # Pending keeps the toolkit "…" badge above: do not clear it.
            if not pending:
                _apply_strip_badge(btn, _badge_text, _badge_style)
        except Exception:
            pass
        try:
            btn.setProperty("gallery_path", str(getattr(m, "path", "")))
        except Exception:
            pass
        try:
            if is_viewing:
                btn.setChecked(True)
        except Exception:
            pass
        try:
            btn.setEnabled(True)
        except Exception:
            pass
        try:
            if is_source:
                from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _ql_is_dark2
                from tabs.image_gallery.ui.quick_look.helpers import _token_color

                # NOTE: was #e8b64c (dark-only) — now gallery.status.warn light/dark chain.
                dark2 = _ql_is_dark2()
                gold = _token_color("gallery.status.warn", "#b77900" if not dark2 else "#d9a441")
                if gold is not None:
                    btn.set_border_color(gold)
                    # BorderLayer honors color only with an explicit width —
                    # without it the source/viewing outline is invisible.
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

        def _make_switch(target=m):
            def _do():
                try:
                    from tabs.image_gallery.debug import gallery_debug as _dbg

                    _dbg(
                        "strip switch click path=%s current=%s idx=%s",
                        getattr(target, "path", "?"),
                        getattr(getattr(overlay, "_current_item", None), "path", "?"),
                        getattr(overlay, "_current_idx", "?"),
                    )
                except Exception:
                    pass
                try:
                    target_idx = None
                    for i, mm in enumerate(overlay._series_items):
                        if Path(getattr(mm, "path", "")) == Path(getattr(target, "path", "")):
                            target_idx = i
                            break
                    # Clicking the already-viewing thumb: re-assert strip
                    # visuals only (badges/checked), skip the full repopulate
                    # (preview+metrics+artifacts rebuild looks like a blink
                    # with zero content change). Path equality is the item
                    # identity here (objects are re-resolved across layers).
                    cur = getattr(overlay, "_current_item", None)
                    same_path = (
                        cur is not None
                        and str(getattr(cur, "path", None) or "")
                        == str(getattr(target, "path", "") or "")
                    )
                    if (
                        target_idx is not None
                        and target_idx == getattr(overlay, "_current_idx", None)
                        and same_path
                    ):
                        try:
                            overlay._rebuild_strip()
                        except Exception:
                            pass
                        return
                except Exception:
                    pass
                overlay._current_item = target
                try:
                    for i, mm in enumerate(overlay._series_items):
                        if Path(getattr(mm, "path", "")) == Path(getattr(target, "path", "")):
                            overlay._current_idx = i
                            break
                except Exception:
                    pass
                overlay._populate()
            return _do

        _switch = _make_switch()
        # Card wiring pattern (ui/card.py::_bind_gallery_card): region
        # clicks emit regionClicked while clicked fires ONLY for region
        # _main. The strip thumb region id is "thumb", so clicked alone
        # never switched — connect both; exactly one fires per click.
        # NOTE: bind _switch EAGERLY (default arg): a bare closure over
        # the loop variable would resolve to the LAST button's switch
        # at emit time (every thumb led to the last series member).
        try:
            btn.regionClicked.connect(lambda _region_id=None, _sw=_switch: _sw())
        except Exception:
            pass
        try:
            btn.clicked.connect(_switch)
        except Exception:
            pass
        cont_lay.addWidget(btn)
        caption_text = ""
        if pending:
            caption_text = "tie-break pending"
        elif is_viewing and len(overlay._series_items) > 1:
            caption_text = ""
        if caption_text:
            try:
                from tabs.image_gallery.ui.quick_look.helpers import _make_label as _strip_label
            except Exception:
                _strip_label = Label  # type: ignore
            if _strip_label is Label:
                cap = Label(caption_text, pixel_size=11, parent=container)
            else:
                cap = _strip_label(caption_text, parent=container, pixel_size=11, pt=11.5)
            cap.setObjectName(f"quicklook_strip_cap_{idx}")
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cont_lay.addWidget(cap)
            overlay._strip_caption_labels.append(cap)
        overlay._strip_buttons.append(container)
        overlay._strip_layout.addWidget(container)
        # First build is shown later via an ancestor show(); on every later
        # rebuild (walk) the host is already visible yet new children stay
        # hidden (no implicit show) — excluded from layout hints, host
        # collapses to 0 and the strip "disappears". Show explicitly.
        try:
            container.show()
        except Exception:
            pass
    # Fixed-content host inside a non-resizable scroller: size it to its
    # contents explicitly (the area never stretches it). The area observes
    # the host (Resize/LayoutRequest) and re-syncs ranges itself.
    # activate() first: on rebuild the layout can report a stale 0 hint
    # (measured live: 2 fresh 44px containers, host hint 0 → adjustSize
    # collapses the strip to 0 and it "disappears" on every walk).
    try:
        overlay._strip_layout.activate()
    except Exception:
        pass
    try:
        overlay._strip_host.adjustSize()
    except Exception:
        pass
    try:
        overlay._strip_fingerprint = _fp_now or _strip_fingerprint(overlay)
    except Exception:
        pass
    ensure_strip_scroll(overlay)
    try:
        # Badge pass reads live geometry — repaint after the rebuild.
        overlay.update()
    except Exception:
        pass
