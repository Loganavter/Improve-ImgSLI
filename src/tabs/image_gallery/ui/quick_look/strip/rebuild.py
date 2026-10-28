"""Quick Look series-strip rebuild + scroll follow.

Split out of the former ``ui/quick_look/strip.py`` (plan-gallery-split-2026-10-17,
Part C2). Bodies moved verbatim; names/signatures unchanged.

Audit-Meta: pattern=state-machine size=exempt reason="one strip rebuild lifecycle: full rebuild + the in-place fingerprint-parity selection refresh + scroll follow share one dynamic-state contract (refresh mirrors rebuild so the rebuild path stays byte-identical)"
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsOpacityEffect, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow

from .filters import _StripLassoFilter, _StripRepinFilter, _StripWheelFilter
from .helpers import (
    _repin_strip_rank_buttons,
    _strip_family_add,
    _strip_fingerprint,
    _strip_rank_text_and_style,
    _strip_thumb_pitch,
    open_strip_thumb_menu,
)
from .paint import _refresh_strip_selection, _strip_overlay_painter


def ensure_strip_visible(overlay, idx: int | None = None) -> None:
    """Scroll the strip so the given thumb (default: the current one) is visible.

    Nothing in the app ever scrolled the strip — keyboard/button walks
    left the current thumb out of view with no affordance to find it.
    Called on every populate (both refresh and full-rebuild tails) and by
    the keyboard cursor, which can sit ahead of the shown picture; fail-open
    to no-scroll, never correctness. Never raises.
    """
    try:
        scroll = getattr(overlay, "_strip_scroll", None)
        items = list(getattr(overlay, "_series_items", None) or [])
        buttons = list(getattr(overlay, "_strip_buttons", None) or [])
        if scroll is None or not items or len(buttons) != len(items):
            return
        try:
            idx = int(idx) if idx is not None else int(getattr(overlay, "_current_idx", 0) or 0)
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
    try:
        # Single/ungrouped item: no filmstrip to show — hide the whole row
        # (it would be one lonely thumb) instead of an empty control.
        # Runs here (not at the rebuild tail) so the selection-only fast
        # path keeps it in sync too.
        n_items = len(getattr(overlay, "_series_items", None) or [])
        row = getattr(overlay, "_strip_row", None)
        if row is not None:
            row.setVisible(n_items > 1)
    except Exception:
        pass
    ensure_strip_visible(overlay)
    # The keyboard ring rides the same per-populate sync point: a rebuild whose
    # fingerprint changed (ranks re-stamped, a triage flip, a theme/scale change)
    # replaces every thumb widget, so the focus is re-asserted on the live thumb
    # carrying the snapshotted gallery_path (quick_look/nav_section.py; the
    # snapshot is taken by the top of rebuild_strip).
    try:
        from tabs.image_gallery.ui.quick_look import nav_section as _nav

        _nav.restore_strip_focus(overlay)
    except Exception:
        pass
def rebuild_strip(overlay) -> None:
    # Snapshot the keyboard ring by gallery_path BEFORE any widget churn below:
    # both paths (full rebuild + selection-only refresh) end in
    # ensure_strip_scroll, which restores it (quick_look/nav_section.py).
    # Mirrors grid_view/rebuild.py's _focus_snapshot/_restore_focus pair.
    try:
        from tabs.image_gallery.ui.quick_look import nav_section as _nav

        _nav.snapshot_focus(overlay)
    except Exception:
        pass
    # W6: svg pitch is 76px (thumbs x=816/892/968/1044, 66 wide) — the
    # HBox spacing is pinned here so 4 thumbs span 4*66+3*10=294px and
    # fit the 296px right column with no h-scroll. (The layout itself is
    # built in helpers.py, out of W6 scope; its spacing is overridden.)
    # Quick Look selection is local to the overlay: keep it across walks but
    # drop picks that left the series (a new series must not inherit stale
    # ones). Never seeded from the owner — the grid and the strip no longer
    # share selection.
    try:
        _members = {
            str(getattr(m, "path", "") or "")
            for m in (getattr(overlay, "_series_items", None) or [])
        }
        overlay._strip_selected_paths = {
            p
            for p in (getattr(overlay, "_strip_selected_paths", None) or set())
            if p in _members
        }
    except Exception:
        pass
    # Selection-only fast path: same series/triage/theme/scale as the last
    # full rebuild → update checked/border/opacity in place, no widget
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
        thumb_pm = None
        try:
            from tabs.image_gallery.ui.quick_look.helpers import _thumb_pixmap

            thumb_pm = _thumb_pixmap(m, scaled_px(66), scaled_px(44))
        except Exception:
            thumb_pm = None
        container = QWidget(overlay._strip_host)
        container.setObjectName(f"quicklook_strip_container_{idx}")
        cont_lay = QVBoxLayout(container)
        # Bottom reserve for the rank pill overhang: the pill straddles the
        # thumb's bottom edge (bottom-center, half out = BADGE_HEIGHT//2), so
        # the container must extend at least that far below the thumb or the
        # container rect clips the pill's bottom outline. +2 covers the 1px
        # border and its antialiased edge.
        try:
            from tabs.image_gallery.services.rank_badge import BADGE_HEIGHT as _BADGE_H

            _pill_reserve = scaled_px(_BADGE_H // 2 + 2)
        except Exception:
            _pill_reserve = scaled_px(11)
        cont_lay.setContentsMargins(0, 0, 0, _pill_reserve)
        cont_lay.setSpacing(scaled_px(2))
        cont_lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        # S4: thumbnail goes on a ButtonRegion (Button has no pixmap
        # param); text/click/opacity behavior unchanged.
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
            # overlay_painter: card hover wash (visual
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
        # Rank pill is a real button now (bottom-center of the thumb, in a
        # shared-hover ButtonFamily) — no toolkit badge anywhere on thumbs.
        # Priority: rejected (none) > badge text (computed once upstream).
        try:
            _rank_spec = _strip_rank_text_and_style(m, overlay)
        except Exception:
            _rank_spec = None
        try:
            btn.setProperty("gallery_path", str(getattr(m, "path", "")))
        except Exception:
            pass
        # Context menu: the same ``rightClicked`` signal the grid cards use
        # (ui/card/factory.py ``_bind_gallery_card``) — one proven path, no filter
        # release-time branch. See ``open_strip_thumb_menu``.
        try:
            btn.rightClicked.connect(lambda _b=btn: open_strip_thumb_menu(overlay, _b))
        except Exception:
            pass
        # Quick Look selection is local to the overlay; carry it as a dynamic
        # property so the widget-scoped overlay painter can mark the thumb
        # (the region CHECKED background sits behind the cover pixmap and is
        # barely visible over a photo).
        try:
            _sel = set(getattr(overlay, "_strip_selected_paths", None) or set())
        except Exception:
            _sel = set()
        try:
            _p = str(getattr(m, "path", "") or "")
        except Exception:
            _p = ""
        try:
            btn.setProperty("strip_selected", _p in _sel)
        except Exception:
            pass
        try:
            if is_viewing:
                btn.setChecked(True)
            elif _p in _sel:
                # Region-level: setChecked is a no-op without toggle.
                try:
                    from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState as _BS

                    btn._controller.set_state("thumb", _BS.CHECKED, True)
                except Exception:
                    pass
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
                    # Lasso release on this same thumb: swallow the trailing
                    # click (set by _StripLassoFilter) so a drag-select does
                    # not also walk the preview.
                    if getattr(overlay, "_strip_lasso_ate_click", False):
                        overlay._strip_lasso_ate_click = False
                        return
                except Exception:
                    pass
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
                prev_idx = None
                try:
                    target_idx = None
                    prev_idx = getattr(overlay, "_current_idx", None)
                    for i, mm in enumerate(overlay._series_items):
                        if Path(getattr(mm, "path", "")) == Path(getattr(target, "path", "")):
                            target_idx = i
                            break
                    # Clicking the already-viewing thumb: re-assert strip
                    # visuals only (checked), skip the full repopulate
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
                # A strip click on ANOTHER thumb of the same series is a
                # within-series step: keep the user's wheel-zoom/pan
                # (plan-ql-zoom-persist). The already-viewing thumb returned
                # early above, so a resolvable target that differs from the
                # pre-click index is always the same series, different member.
                # Module function called directly — the class delegator in
                # ``ui/quick_look.py`` takes no flag.
                _preserve = False
                try:
                    _members = list(getattr(overlay, "_series_items", None) or [])
                    _preserve = (
                        target_idx is not None
                        and 0 <= int(target_idx) < len(_members)
                        and int(target_idx) != int(prev_idx)
                    )
                except Exception:
                    _preserve = False
                try:
                    from tabs.image_gallery.ui.quick_look.overlay_parts import (
                        populate as _populate_parts,
                    )

                    _populate_parts._populate(overlay, preserve_view=_preserve)
                except Exception:
                    overlay._populate()
            return _do

        _switch = _make_switch()
        # Card wiring pattern (ui/card/factory.py::_bind_gallery_card): region
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
        # Thumb joins the shared-hover family (rank pills join below).
        _strip_family_add(overlay, btn)
        # Rank badge-button: a real pill bottom-center inside the thumb
        # (edge-touching), walking to the same item. Siblings share one
        # ButtonFamily (shared hover); positioning is layout-external, so
        # _repin_strip_rank_buttons pins it after the rebuild settles.
        if _rank_spec is not None:
            try:
                _rank_text, _rank_bg, _rank_txt = _rank_spec
                from tabs.image_gallery.services.rank_badge import (
                    BADGE_HEIGHT,
                    BADGE_MIN_WIDTH,
                    BADGE_RADIUS,
                )
                from tabs.image_gallery.ui.quick_look.strip.helpers import (
                    _strip_badge_fit,
                )

                # Fit BEFORE creating the row: the font size is part of the
                # row, and a long localized label (ru ``ИСТОЧНИК`` /
                # ``★ ЛУЧШЕЕ``) must pick a smaller face instead of being
                # clipped by the 66px thumb container (live report 2026-10-22).
                _badge_px, _badge_w, _badge_elide = _strip_badge_fit(str(_rank_text))
                rank_btn = Button(
                    rows=[
                        ButtonRow(
                            text=str(_rank_text),
                            size=int(_badge_px),
                            ratio=1.0,
                            color=_rank_txt,
                            elide=bool(_badge_elide),
                        )
                    ],
                    variant="surface",
                    size=(BADGE_MIN_WIDTH, BADGE_HEIGHT),
                    # Design px — Button(corner_radius=...) scales internally;
                    # a scaled_px() here double-scales the pill radius.
                    corner_radius=BADGE_RADIUS,
                    parent=container,
                )
                rank_btn.setObjectName(f"quicklook_rank_{idx}")
                # Size the pill exactly like the grid-card badge (shared
                # geometry): measured text advance + BADGE_H_PAD breathing
                # room, min BADGE_MIN_WIDTH, capped to the thumb. The Button's
                # own sizeHint reserves 24px (12 each side) and lagged the
                # real advance; measuring the label font directly is the same
                # rule the card painter uses (``card/painters.py:117-118``).
                # ``_design_fixed_size`` keeps the DESIGN width for a UiScale
                # re-derive.
                try:
                    if _badge_w > 0:
                        _factor = 1.0
                        try:
                            from sli_ui_toolkit.ui.managers.ui_scale import UiScale as _UiScale

                            _factor = float(_UiScale.get_instance().factor()) or 1.0
                        except Exception:
                            _factor = 1.0
                        _design_w = max(1, int(round(_badge_w / _factor)))
                        rank_btn._design_fixed_size = (_design_w, BADGE_HEIGHT)
                        rank_btn.setFixedSize(int(_badge_w), scaled_px(BADGE_HEIGHT))
                except Exception:
                    pass
                if _rank_bg is not None:
                    try:
                        # White opaque fill (override layer) + the kind color
                        # as a 1px outline — the pill reads as a capsule,
                        # never a gray chip or a translucent wash.
                        from PySide6.QtGui import QColor as _QCO

                        from tabs.image_gallery.ui.quick_look.helpers import _token_color as _pill_token

                        _pill_bg = _pill_token("gallery.pill.background", "#ffffff")
                        if _pill_bg is None:
                            _pill_bg = _QCO("#ffffff")
                        _pill_bg = _QCO(_pill_bg)  # copy: never mutate a manager-owned instance
                        _pill_bg.setAlpha(255)
                        rank_btn.set_override_bg_color(_pill_bg)
                        # Hover must not fall through to the surface hover
                        # token (dark ``#4a4a4a``, opaque): painted over the
                        # white base it left the fixed black ink at ~2:1 —
                        # the #N digits vanished. Pin a light pill hover so
                        # the capsule stays readable on the shared-hover glow.
                        _pill_hover = _pill_token("gallery.pill.background.hover", "#f0f0f0")
                        if _pill_hover is not None:
                            try:
                                rank_btn.set_hover_color(_QCO(_pill_hover))
                            except Exception:
                                pass
                        rank_btn.set_border_color(_rank_bg)
                        try:
                            rank_btn.setProperty("borderWidth", 1)
                        except Exception:
                            pass
                    except Exception:
                        pass
                try:
                    from PySide6.QtCore import Qt as _QtRank

                    rank_btn.setCursor(_QtRank.CursorShape.ArrowCursor)
                    # The pill is a redundant affordance for the same item its
                    # thumb already offers: NoFocus keeps it OUT of the strip
                    # row's cursor targets (quick_look/nav_section.py — a
                    # ToolbarRowsSection focuses every StrongFocus child), so
                    # arrow steps land on the numbered thumb Button, never on
                    # the badge. Verified 2026-10-17: with this line reverted
                    # the row's target list carries ``quicklook_rank_N`` beside
                    # ``quicklook_strip_N`` (the pill is bottom-center, i.e.
                    # right where its thumb sits in the row's step order).
                    rank_btn.setFocusPolicy(_QtRank.FocusPolicy.NoFocus)
                except Exception:
                    pass
                try:
                    rank_btn.regionClicked.connect(lambda _region_id=None, _sw=_switch: _sw())
                except Exception:
                    pass
                try:
                    rank_btn.clicked.connect(_switch)
                except Exception:
                    pass
                try:
                    rank_btn.rightClicked.connect(lambda _b=rank_btn: open_strip_thumb_menu(overlay, _b))
                except Exception:
                    pass
                try:
                    rank_btn.show()
                except Exception:
                    pass
                _strip_family_add(overlay, rank_btn)
            except Exception:
                pass
        cont_lay.addWidget(btn)
        # Shared card context menu (same entries as the grid cards living
        # in the OpaqueFillHost) opens from the thumb's own ``rightClicked``
        # signal — the exact mechanism grid cards use. See
        # ``open_strip_thumb_menu``.
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
        # Rank pills are layout-external: pin from live geometry. Container
        # geometry at the end of a rebuild is still settling (thumbs ride
        # to their final x a pass later), so watch every container's Resize
        # too — not just the host's. One filter object, installed once per
        # widget (re-installs are idempotent).
        try:
            filt = getattr(overlay, "_strip_repin_filter", None)
            if filt is None:
                host0 = getattr(overlay, "_strip_host", None)
                filt = _StripRepinFilter(overlay, host0 if host0 is not None else overlay)
                overlay._strip_repin_filter = filt
            try:
                host = getattr(overlay, "_strip_host", None)
                if host is not None:
                    host.installEventFilter(filt)
            except Exception:
                pass
            for container in list(getattr(overlay, "_strip_buttons", None) or []):
                try:
                    container.installEventFilter(filt)
                except Exception:
                    continue
        except Exception:
            pass
    except Exception:
        pass
    try:
        _repin_strip_rank_buttons(overlay)
    except Exception:
        pass
    try:
        # Marquee-selection lasso: one filter object, installed on the host,
        # the scroll viewport (presses on viewport gaps past the host never
        # reach the host — the working zone must span the full strip width),
        # and every interactive child (thumb button, rank pill, container —
        # presses on children never reach the host). Re-installs on the
        # long-lived host/viewport are guarded; rebuilt children are fresh.
        from sli_ui_toolkit.widgets import Button as _BL

        _host = getattr(overlay, "_strip_host", None)
        _lasso = getattr(overlay, "_strip_lasso_filter", None)
        if _lasso is None and _host is not None:
            _lasso = _StripLassoFilter(overlay, _host)
            overlay._strip_lasso_filter = _lasso
        if _lasso is not None and _host is not None:
            try:
                if not getattr(_host, "_strip_lasso_installed", False):
                    _host.installEventFilter(_lasso)
                    _host._strip_lasso_installed = True  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                _scroll = getattr(overlay, "_strip_scroll", None)
                _viewport = _scroll.viewport() if _scroll is not None else None
                if _viewport is not None and not getattr(_viewport, "_strip_lasso_installed", False):
                    _viewport.installEventFilter(_lasso)
                    _viewport._strip_lasso_installed = True  # type: ignore[attr-defined]
            except Exception:
                pass
            for _container in list(getattr(overlay, "_strip_buttons", None) or []):
                for _w in [_container, *_container.findChildren(_BL)]:
                    try:
                        _w.installEventFilter(_lasso)
                    except Exception:
                        continue
    except Exception:
        pass
    try:
        # Badge pass reads live geometry — repaint after the rebuild.
        overlay.update()
    except Exception:
        pass
