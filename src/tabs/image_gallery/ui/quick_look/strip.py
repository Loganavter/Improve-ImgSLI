"""Quick look series strip — plain functions taking overlay."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsOpacityEffect, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonRegion, Label


def _strip_overlay_painter(painter, ctx, tm) -> None:  # type: ignore[no-untyped-def]
    """Strip thumb overlay: card hover wash + strip-size badge pill.

    Visual hover only (no IconActionFlyout/capsule on strip thumbs) plus
    the ``_gallery_badge`` pill drawn by the strip-size painter from
    ``ui/card/painters.py``.
    """
    try:
        from tabs.image_gallery.ui.card.painters import _gallery_hover_wash

        _gallery_hover_wash(painter, ctx, tm)
    except Exception:
        pass
    try:
        from tabs.image_gallery.ui.card.painters import _strip_badge_painter

        widget = getattr(ctx, "widget", None)
        if widget is None:
            return
        b_text = getattr(widget, "_gallery_badge", None)
        b_style = getattr(widget, "_gallery_badge_style", None)
        if b_text and b_style is not None:
            rect = getattr(ctx, "rect", None)
            if rect is not None:
                _strip_badge_painter(painter, rect, str(b_text), b_style)
    except Exception:
        pass


def rebuild_strip(overlay) -> None:
    # W6: svg pitch is 76px (thumbs x=816/892/968/1044, 66 wide) — the
    # HBox spacing is pinned here so 4 thumbs span 4*66+3*10=294px and
    # fit the 296px right column with no h-scroll. (The layout itself is
    # built in helpers.py, out of W6 scope; its spacing is overridden.)
    try:
        overlay._strip_layout.setSpacing(scaled_px(10))
    except Exception:
        pass
    for b in list(overlay._strip_buttons):
        try:
            overlay._strip_layout.removeWidget(b)
            b.setParent(None)
            b.deleteLater()
        except Exception:
            pass
    overlay._strip_buttons.clear()
    for cap in list(getattr(overlay, "_strip_caption_labels", [])):
        try:
            overlay._strip_layout.removeWidget(cap)
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
        # Card-style overlay pills (visuals.py contract): btn._gallery_badge
        # + btn._gallery_badge_style, drawn by _strip_badge_painter. The
        # toolkit badge=/setBadge path is used ONLY for the … pending case
        # above. Priority: pending (toolkit) > rejected (none — the dim 0.4
        # opacity effect carries the signal) > SOURCE > ★ BEST > #N.
        try:
            if not pending:
                btn.setBadge(None)
        except Exception:
            pass
        try:
            from PySide6.QtGui import QColor as _QC

            from tabs.image_gallery.ui.card.dots import _accent_color as _strip_accent
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
                _is_best = bool(getattr(m, "is_best", False))
                _rank = getattr(m, "rank", None)
                _crown = getattr(m, "crown_rank", None)
                if _is_best or _rank == 1 or _crown == 1:
                    _acc = _strip_accent()
                    _badge_text = "★ BEST"
                    _badge_style = (True, _acc, _acc, _QC("#ffffff"))
                else:
                    _rv = _crown if _crown is not None else _rank
                    if _rv is not None:
                        try:
                            _badge_text = f"#{int(_rv)}"
                        except Exception:
                            _badge_text = str(_rv)
                        _rank_bg = _strip_token("button.toggle.background.checked", "#555555")
                        _badge_style = (True, _rank_bg, _rank_bg, _QC("#000000"))
            if _badge_text is not None:
                btn._gallery_badge = _badge_text
                btn._gallery_badge_style = _badge_style
            else:
                try:
                    btn._gallery_badge = None
                except Exception:
                    pass
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
