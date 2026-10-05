"""Quick look series strip — plain functions taking overlay.

Audit-Meta: pattern=thin-owner-target size=exempt reason="one strip concern: full rebuild + in-place selection refresh share one dynamic-state contract (refresh mirrors rebuild so the rebuild path stays byte-identical)"
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QEvent
from PySide6.QtWidgets import QGraphicsOpacityEffect, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonFamily, ButtonRegion, ButtonRow


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


class _StripLassoFilter(QObject):
    """Rubber-band multi-select (marquee selection) on the strip.

    Left-press + drag past the drag threshold opens a QRubberBand over
    the host; on release every thumb container intersecting the rect
    joins the selection (owner ``selected_paths``/``selected_order`` in
    series order — the Group action's ≥2-targets input). A release that
    never passed the threshold is an ordinary click: the filter returns
    False without touching anything and the thumb's own switch path runs.

    When the press started on a thumb and a lasso DID show, the trailing
    release would still fire the thumb click (same widget press+release)
    and walk the preview — that click is swallowed via
    ``overlay._strip_lasso_ate_click`` (checked first in ``_make_switch``).

    Installed on the host, the scroll viewport (full strip width —
    viewport gaps past the host edge must start a lasso too) and every
    thumb container, thumb button and rank pill (presses on children
    never reach the host filter); positions map to host coordinates.

    Two guards keep coordinates honest. First, dedup: one physical event
    reaches this filter once per ancestor (receiver, then each parent it
    propagates to) with IDENTICAL raw type/buttons/pos, and a second
    mapping would use the wrong widget's coordinates — repeats are
    skipped so exactly the first delivery (watched == receiver, correct
    coords) takes effect. Second, plain containers (host/viewport/thumb
    container) swallow handled Left press/move/release so nothing
    propagates further; buttons/pills are never swallowed (clicks,
    ripple, hover stay intact — and buttons accept presses/releases
    themselves, so those never propagate anyway). Never raises.
    """

    def __init__(self, overlay, host):
        super().__init__(host)
        self._overlay = overlay
        self._host = host
        self._origin = None
        self._band = None
        # Dedup key of the last processed press/move/release: one physical
        # event reaches this filter once per ancestor (receiver, then each
        # parent it propagates to) with IDENTICAL type/buttons/pos, and the
        # second mapping would use the wrong widget's coordinates. Skip
        # repeats so exactly one handling (the first, with watched ==
        # receiver and correct coords) takes effect.
        self._seen = None

    def _to_host(self, widget, pos):
        try:
            if widget is None or widget is self._host:
                return pos
            return widget.mapTo(self._host, pos)
        except Exception:
            return pos

    def _threshold(self) -> int:
        try:
            from PySide6.QtWidgets import QApplication as _QA

            return max(4, int(_QA.startDragDistance()))
        except Exception:
            return 8

    def _hide_band(self):
        band, self._band = self._band, None
        if band is not None:
            try:
                band.hide()
            except Exception:
                pass

    def eventFilter(self, watched, event):  # noqa: N802
        # Return policy (kills double-delivery: a press handled on the host
        # must never ALSO be processed on the viewport — propagated events
        # keep the original receiver's coordinates, so the second mapping
        # produces garbage rects):
        # - plain containers (host/viewport/thumb container): swallow
        #   handled Left press/move/release (nothing else needs them; no
        #   grab is set, so later moves hit-test fresh with watched ==
        #   receiver and every mapping stays correct);
        # - buttons/pills: never swallow (clicks, ripple, hover stay
        #   intact; buttons accept presses/releases themselves, so nothing
        #   propagates further anyway).
        try:
            from PySide6.QtCore import QPoint as _QP
            from PySide6.QtCore import QRect as _QR

            try:
                from sli_ui_toolkit.widgets import Button as _BL

                _is_button = isinstance(watched, _BL)
            except Exception:
                _is_button = False
            t = event.type()
            if t == QEvent.Type.MouseButtonPress:
                try:
                    if event.button() == Qt.MouseButton.LeftButton:
                        try:
                            _pos = event.position().toPoint()
                            _key = (t, event.button(), _pos.x(), _pos.y())
                        except Exception:
                            self._origin = None
                            return False
                        if _key == self._seen:
                            return False
                        self._seen = _key
                        self._hide_band()
                        self._origin = self._to_host(watched, _pos)
                        try:
                            from tabs.image_gallery.debug import gallery_debug as _dbg

                            _dbg(
                                "strip lasso press on=%s pos=%s",
                                type(watched).__name__,
                                self._origin,
                            )
                        except Exception:
                            pass
                        if not _is_button:
                            return True
                except Exception:
                    self._origin = None
            elif t == QEvent.Type.MouseMove:
                if self._origin is not None:
                    try:
                        if not (event.buttons() & Qt.MouseButton.LeftButton):
                            self._origin = None
                            self._hide_band()
                        else:
                            _raw = event.position().toPoint()
                            _mkey = (t, event.buttons(), _raw.x(), _raw.y())
                            if _mkey == self._seen:
                                return False
                            self._seen = _mkey
                            cur = self._to_host(watched, _raw)
                            dx = cur.x() - self._origin.x()
                            dy = cur.y() - self._origin.y()
                            if self._band is None and (abs(dx) + abs(dy)) >= self._threshold():
                                from PySide6.QtWidgets import QRubberBand as _QRB

                                self._band = _QRB(_QRB.Shape.Rectangle, self._host)
                                try:
                                    self._band.show()
                                except Exception:
                                    pass
                                try:
                                    from tabs.image_gallery.debug import gallery_debug as _dbg2

                                    _dbg2("strip lasso band shown origin=%s", self._origin)
                                except Exception:
                                    pass
                            if self._band is not None:
                                self._band.setGeometry(_QR(_QP(self._origin), _QP(cur)).normalized())
                                if not _is_button:
                                    return True
                    except Exception:
                        pass
            elif t == QEvent.Type.MouseButtonRelease:
                try:
                    if event.button() == Qt.MouseButton.LeftButton and self._origin is not None:
                        _rpos = event.position().toPoint()
                        _rkey = (t, event.button(), _rpos.x(), _rpos.y())
                        if _rkey == self._seen:
                            return False
                        self._seen = _rkey
                        _had_band = self._band is not None and self._band.isVisible()
                        if _had_band:
                            rect = self._band.geometry().normalized()
                            try:
                                from tabs.image_gallery.debug import gallery_debug as _dbg3

                                _dbg3("strip lasso release rect=%s", rect)
                            except Exception:
                                pass
                            if rect.width() >= 4 or rect.height() >= 4:
                                try:
                                    self._overlay._strip_lasso_ate_click = True
                                except Exception:
                                    pass
                                try:
                                    _strip_apply_lasso_selection(self._overlay, rect)
                                except Exception:
                                    pass
                        self._origin = None
                        self._hide_band()
                        if _had_band and not _is_button:
                            return True
                except Exception:
                    pass
        except Exception:
            pass
        return False


def _strip_apply_lasso_selection(overlay, rect) -> None:
    """Select strip items whose containers intersect *rect* (host coords).

    Series order is preserved (container order == series order). Writes
    the owner selection (``set_selection`` wholesale when available, else
    direct ``state`` writes — same fallback idiom as the triage UI) and
    refreshes thumb checked visuals.
    """
    try:
        containers = list(getattr(overlay, "_strip_buttons", None) or [])
        items = list(getattr(overlay, "_series_items", None) or [])
    except Exception:
        return
    picked: list[str] = []
    try:
        for container, m in zip(containers, items):
            try:
                g = container.geometry()
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
    picked = [p for p in picked if p]
    try:
        overlay._strip_selected_paths = set(picked)
    except Exception:
        pass
    owner = getattr(overlay, "_owner", None)
    try:
        setter = getattr(owner, "set_selection", None)
        if callable(setter):
            try:
                setter(list(picked))
            except Exception:
                pass
    except Exception:
        pass
    try:
        st = getattr(owner, "state", None)
        if st is not None:
            if hasattr(st, "selected_paths"):
                try:
                    st.selected_paths = set(picked)
                except Exception:
                    pass
            if hasattr(st, "selected_order"):
                try:
                    st.selected_order = list(picked)
                except Exception:
                    pass
    except Exception:
        pass
    try:
        _strip_refresh_selection(overlay)
    except Exception:
        pass


def _strip_refresh_selection(overlay) -> None:
    """Repaint thumb selection state: lasso-selected or not.

    Region-level CHECKED (``Button.setChecked`` is a no-op without a
    toggle capability) — distinct from the viewing accent border.
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


def _strip_rank_text_and_style(m, is_source: bool):
    """Rank pill content for one series member (badge-button input).

    Priority (mirrors the old badge order): pending "…" > rejected None >
    SOURCE > #N. Returns ``(text, outline, text_color, width_px)`` — the
    pill fills white with ``outline`` as its 1px border — or None when no
    pill is shown. Never raises.
    """
    try:
        from PySide6.QtGui import QColor as _QC

        from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _strip_dark
        from tabs.image_gallery.ui.quick_look.helpers import _token_color as _strip_token

        _strip_is_dark = _strip_dark()
        _ink = _QC("#000000")
        if bool(getattr(m, "vlm_tie_pending", False)):
            bg = _strip_token("surface.button", "#8a8a8a" if not _strip_is_dark else "#5a5a5a")
            if bg is None:
                bg = _QC(90, 90, 90)
            return ("…", bg, _ink, scaled_px(24))
        if bool(getattr(m, "rejected", False)):
            return None  # no pill — dim effect carries the signal
        if is_source:
            _gold = _strip_token("gallery.status.warn", "#b77900" if not _strip_is_dark else "#d9a441")
            return ("SOURCE", _gold, _ink, scaled_px(58))
        _rank = getattr(m, "rank", None)
        _crown = getattr(m, "crown_rank", None)
        _rv = _crown if _crown is not None else _rank
        if _rv is None and bool(getattr(m, "is_best", False)):
            _rv = 1
        if _rv is None:
            return None
        # Synced with grid cards (ui/card/visuals.py): no BEST pill —
        # the leader shows its #N rank like every ranked item.
        try:
            _text = f"#{int(_rv)}"
        except Exception:
            _text = str(_rv)
        _rank_bg = _strip_token("button.toggle.background.checked", "#555555")
        return (_text, _rank_bg, _ink, scaled_px(34))
    except Exception:
        return None


def _strip_family(overlay):
    """Shared-hover family for strip thumbs + rank pills (created once).

    One family for both: hovering a thumb lights its pill (and siblings),
    hovering a pill lights the thumbs — the strip reads as one control.
    """
    try:
        fam = getattr(overlay, "_strip_family", None)
        if fam is None:
            fam = ButtonFamily(overlay)
            try:
                fam.setSharedHover(True)
            except Exception:
                pass
            overlay._strip_family = fam
        return fam
    except Exception:
        return None


def _strip_family_add(overlay, button) -> None:
    """Link a strip button into the shared-hover family. Never raises."""
    try:
        fam = _strip_family(overlay)
        if fam is not None and button is not None:
            fam.addButton(button)
    except Exception:
        pass


def _repin_strip_rank_buttons(overlay) -> None:
    """Pin each rank pill centered on its thumb's bottom edge (half out).

    Rank buttons are layout-external children of the thumb container — the
    container reserves the overhang below the thumb — so container resizes
    never move them: re-pin after rebuilds and host resizes. Never raises.
    """
    try:
        containers = list(getattr(overlay, "_strip_buttons", None) or [])
    except Exception:
        return
    for idx, container in enumerate(containers):
        try:
            thumb = container.findChild(Button, f"quicklook_strip_{idx}")
            pill = container.findChild(Button, f"quicklook_rank_{idx}")
            if thumb is None or pill is None:
                continue
            tg = thumb.geometry()
            # Fresh pills report 0 live width until shown — but the pill
            # size is fixed at build, so pin from the minimum (valid
            # immediately), hint as the last resort.
            try:
                pw = int(pill.minimumWidth()) or int(pill.sizeHint().width())
            except Exception:
                pw = 0
            try:
                ph = int(pill.minimumHeight()) or int(pill.sizeHint().height())
            except Exception:
                ph = 0
            if pw <= 0 or ph <= 0:
                continue
            pill.move(
                tg.x() + max(0, (tg.width() - pw) // 2),
                tg.y() + max(0, tg.height() - ph // 2),
            )
        except Exception:
            continue


class _StripRepinFilter(QObject):
    """Host-resize filter: re-pin rank pills when the strip settles.

    Installed once per overlay (parented to the host); layout settling
    after a rebuild is async, so the end-of-rebuild repin alone can pin
    from stale geometry. Never raises.
    """

    def __init__(self, overlay, parent=None):
        super().__init__(parent)
        self._overlay = overlay

    def eventFilter(self, watched, event):  # noqa: N802
        try:
            if event.type() == QEvent.Type.Resize:
                _repin_strip_rank_buttons(self._overlay)
        except Exception:
            pass
        return False


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


def _strip_overlay_painter(painter, ctx, tm) -> None:  # type: ignore[no-untyped-def]
    """Strip thumb overlay: card hover wash only.

    Visual hover only (no IconActionFlyout/capsule on strip thumbs).
    Rank pills are real buttons now (bottom-center of each thumb), not
    painted badges.
    """
    try:
        from tabs.image_gallery.ui.card.painters import _gallery_hover_wash

        _gallery_hover_wash(painter, ctx, tm)
    except Exception:
        pass


def _strip_rank_key(m) -> tuple:
    """Rank identity for one series member (rank-pill input).

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
        pending = bool(getattr(m, "vlm_tie_pending", False))
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


def _strip_seed_selection_from_owner(overlay) -> None:
    """Mirror the grid selection into the strip's picked set.

    Cards selected in the gallery grid (owner ``state.selected_paths``)
    must read as selected on the QL strip thumbs — otherwise the strip
    shows an unselected row on top of selected cards (inverted UX). The
    owner is the source of truth: replace (not union), restricted to
    series members. Owners without a ``selected_paths`` state (bare
    test doubles) leave the overlay set untouched.
    """
    try:
        owner = getattr(overlay, "_owner", None)
        st = getattr(owner, "state", None)
        if st is None or not hasattr(st, "selected_paths"):
            return
        try:
            names = set(str(p) for p in (getattr(st, "selected_paths", None) or set()))
        except Exception:
            return
        try:
            members = set(
                str(getattr(m, "path", "") or "")
                for m in (getattr(overlay, "_series_items", None) or [])
            )
        except Exception:
            members = set()
        try:
            overlay._strip_selected_paths = {p for p in names if not members or p in members}
        except Exception:
            pass
    except Exception:
        pass


def rebuild_strip(overlay) -> None:
    # W6: svg pitch is 76px (thumbs x=816/892/968/1044, 66 wide) — the
    # HBox spacing is pinned here so 4 thumbs span 4*66+3*10=294px and
    # fit the 296px right column with no h-scroll. (The layout itself is
    # built in helpers.py, out of W6 scope; its spacing is overridden.)
    # Selection-only fast path: same series/triage/theme/scale as the last
    # full rebuild → update checked/border/opacity in place, no widget
    # churn. Any mismatch (or first build) falls through to today's rebuild.
    try:
        _strip_seed_selection_from_owner(overlay)
    except Exception:
        pass
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
        # Bottom reserve for the rank pill overhang: the pill straddles
        # the thumb's bottom edge (half out), so the container extends
        # past the thumb instead of clipping it.
        cont_lay.setContentsMargins(0, 0, 0, scaled_px(8))
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
        # Priority: pending "…" > rejected (none) > SOURCE > #N.
        try:
            _rank_spec = _strip_rank_text_and_style(m, is_source)
        except Exception:
            _rank_spec = None
        try:
            btn.setProperty("gallery_path", str(getattr(m, "path", "")))
        except Exception:
            pass
        try:
            if is_viewing:
                btn.setChecked(True)
            else:
                try:
                    _sel = set(getattr(overlay, "_strip_selected_paths", None) or set())
                except Exception:
                    _sel = set()
                if str(getattr(m, "path", "") or "") in _sel:
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
                try:
                    target_idx = None
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
        # Thumb joins the shared-hover family (rank pills join below).
        _strip_family_add(overlay, btn)
        # Rank badge-button: a real pill bottom-center inside the thumb
        # (edge-touching), walking to the same item. Siblings share one
        # ButtonFamily (shared hover); positioning is layout-external, so
        # _repin_strip_rank_buttons pins it after the rebuild settles.
        if _rank_spec is not None:
            try:
                _rank_text, _rank_bg, _rank_txt, _rank_w = _rank_spec
                rank_btn = Button(
                    rows=[ButtonRow(text=str(_rank_text), size=11, ratio=1.0, color=_rank_txt)],
                    variant="surface",
                    size=(int(_rank_w), scaled_px(16)),
                    corner_radius=scaled_px(8),
                    parent=container,
                )
                rank_btn.setObjectName(f"quicklook_rank_{idx}")
                if _rank_bg is not None:
                    try:
                        # White opaque fill (override layer) + the kind color
                        # as a 1px outline — the pill reads as a capsule,
                        # never a gray chip or a translucent wash.
                        from PySide6.QtGui import QColor as _QCO

                        _white = _QCO("#ffffff")
                        _white.setAlpha(255)
                        rank_btn.set_override_bg_color(_white)
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
                    rank_btn.show()
                except Exception:
                    pass
                _strip_family_add(overlay, rank_btn)
            except Exception:
                pass
        cont_lay.addWidget(btn)
        # Shared card context menu (same idiom as the grid cards living
        # in the OpaqueFillHost): popup_gallery_card_context_menu for the
        # thumb's own item. No filename captions — the rank pill already
        # carries the state and the row stays a uniform height.
        def _make_strip_menu(item=m, anchor=btn):
            def _show_menu():
                try:
                    from PySide6.QtGui import QCursor as _QCursor

                    _gp = _QCursor.pos()
                except Exception:
                    _gp = None
                try:
                    from tabs.image_gallery.ui.card.context_menu import popup_gallery_card_context_menu

                    _owner = getattr(overlay, "_owner", None)
                    popup_gallery_card_context_menu(
                        anchor, _owner, Path(str(getattr(item, "path", "") or "")), global_pos=_gp
                    )
                except Exception:
                    pass
            return _show_menu

        _show_menu = _make_strip_menu()
        # Card wiring pattern (ui/card.py): rightClicked opens the shared
        # menu; bind eagerly — same late-closure hazard as _switch above.
        try:
            btn.rightClicked.connect(_show_menu)
        except Exception:
            pass
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
