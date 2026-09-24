"""Quick look helpers — plain functions (no owner state).
Audit-Meta: pattern=thin-owner-target size=exempt reason="ui/quick_look helpers — overlay build + populate helpers sharing one overlay"

Extracted from quick_look.py per CODE_PATTERNS.md thin owner + ui/.
Painter pipeline owns visuals; no QSS styling. Lazy imports for theming.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget


def _is_dark_theme() -> bool:
    try:
        from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _bars_is_dark

        return bool(_bars_is_dark())
    except Exception:
        pass
    return True


class _AccentPillHost(QWidget):
    """Accent-tinted pill backdrop behind the mode chip (explicit paint, no palette)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._bg = self._resolve_bg()
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    @staticmethod
    def _resolve_bg() -> QColor:
        try:
            from sli_ui_toolkit.managers import ThemeManager

            from ui.theming import try_resolve_theme_color

            for token in ("gallery.accent.bar", "accent"):
                c = try_resolve_theme_color(ThemeManager.get_instance(), token)
                if c is not None:
                    # QColor(...) copy: never setAlpha a manager-owned instance in place.
                    col = QColor(c) if isinstance(c, str) else QColor(c)
                    try:
                        if col.alpha() == 255:
                            col.setAlpha(51)
                    except Exception:
                        pass
                    return col
        except Exception:
            pass
        # NOTE: was (0,150,255) at alpha 51 (dark-only rgba) — now accent light/dark chain.
        fallback = QColor("#0078D4" if not _is_dark_theme() else "#0096FF")
        try:
            fallback.setAlpha(51)
        except Exception:
            pass
        return fallback

    def _on_theme_changed(self) -> None:
        try:
            self._bg = self._resolve_bg()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        self._on_theme_changed()

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            from sli_ui_toolkit.managers import scaled_px

            p = QPainter(self)
            try:
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(self._bg)
                p.drawRoundedRect(self.rect(), scaled_px(8), scaled_px(8))
            finally:
                p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass


# S4 v2 LIGHT (svg:31): 1040x620 card plate — card fill + 1px border + rx 12.
QUICK_LOOK_CARD_RADIUS_PX = 12

# W11: nav chevron glyph size (pt rows). The mockup chevron path spans
# ~18px in the 36px circle (svg prev/next); the text ‹ › at 18pt rendered
# small, so the rows size up to 24 — circles stay 36px, ring untouched.
QUICK_LOOK_NAV_GLYPH_PT = 24


class _CardPlate(QWidget):
    """Quick look card plate — ``gallery.card.background`` fill + border, rx 12.

    Painter pipeline owns visuals (explicit paintEvent, theme-subscribed);
    no QSS, no palette. Token chains mirror the grid-card seam
    (``ui/card.py::_gallery_card_bg``, ``ui/card/visuals.py``).
    All QColor() calls take resolved variables — never literals
    (contracts/test_no_hardcoded_qcolor.py baseline).
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._bg = self._resolve_bg()
        self._border = self._resolve_border()
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    @staticmethod
    def _resolve_bg():
        try:
            from sli_ui_toolkit.managers import ThemeManager

            from ui.theming import try_resolve_theme_color

            mgr = ThemeManager.get_instance()
            for token in ("gallery.card.background", "surface.list", "surface.background"):
                c = try_resolve_theme_color(mgr, token)
                if c is not None:
                    return c if isinstance(c, QColor) else QColor(c)
        except Exception:
            pass
        return _token_color(
            "gallery.card.background", "#ffffff" if not _is_dark_theme() else "#383838"
        )

    @staticmethod
    def _resolve_border():
        try:
            from sli_ui_toolkit.managers import ThemeManager

            from ui.theming import try_resolve_theme_color

            mgr = ThemeManager.get_instance()
            for token in ("gallery.card.border", "flyout.border"):
                try:
                    c = try_resolve_theme_color(mgr, token)
                except Exception:
                    c = None
                if c is not None:
                    return c if isinstance(c, QColor) else QColor(c)
        except Exception:
            pass
        return _token_color(
            "gallery.card.border", "#e2e4e8" if not _is_dark_theme() else "#4a4a4a"
        )

    def _on_theme_changed(self) -> None:
        try:
            self._bg = self._resolve_bg()
        except Exception:
            pass
        try:
            self._border = self._resolve_border()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        self._on_theme_changed()

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            from PySide6.QtCore import QRectF
            from PySide6.QtGui import QPen

            from sli_ui_toolkit.managers import scaled_px

            p = QPainter(self)
            try:
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                r = QRectF(self.rect())
                rx = scaled_px(QUICK_LOOK_CARD_RADIUS_PX)
                p.setPen(Qt.PenStyle.NoPen)
                try:
                    bg = self._bg
                except Exception:
                    bg = self._resolve_bg()
                p.setBrush(bg)
                p.drawRoundedRect(r, rx, rx)
                try:
                    border = self._border
                except Exception:
                    border = self._resolve_border()
                try:
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.setPen(QPen(border, 1))
                    p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), rx, rx)
                except Exception:
                    pass
            finally:
                p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass


def _load_preview_pixmap(path: Path, target_w: int = 640, target_h: int = 456) -> QPixmap | None:
    try:
        pm = QPixmap(str(path))
        if pm.isNull():
            return None
        w = pm.width()
        h = pm.height()
        if w <= 0 or h <= 0:
            return pm
        return pm.scaled(target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    except Exception:
        return None


def _thumb_pixmap(item, size: int = 66) -> QPixmap | None:
    try:
        thumb = getattr(item, "thumbnail", None)
        if thumb is not None and not thumb.isNull():
            return thumb.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        pm = QPixmap(str(getattr(item, "path", "")))
        if pm is not None and not pm.isNull():
            return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    except Exception:
        pass
    return None


def _theme_color(token: str, fallback: str) -> object:
    """Resolve ThemeManager token with fallback hex via ui.theming wrapper (contract-safe)."""
    try:
        from ui.theming import resolve_theme_color

        from sli_ui_toolkit.managers import ThemeManager

        return resolve_theme_color(ThemeManager.get_instance(), token)
    except Exception:
        try:
            from PySide6.QtGui import QColor

            return QColor(fallback)
        except Exception:
            return None


def _token_color(token: str, fallback: str) -> QColor | None:
    """Resolve a ThemeManager token, falling back to *fallback* hex when absent.

    Goes through the sanctioned ``ui.theming.try_resolve_theme_color`` wrapper
    (contract: manual theming glue lives only in theme infra).
    """
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        c = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if c is not None:
            return QColor(c) if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    try:
        return QColor(fallback)
    except Exception:
        return None


def _token_rgba_qcolor(token: str, fallback_rgba: tuple[int, int, int, int]) -> QColor | None:
    """Resolve token via ``try_resolve_theme_color`` with rgba fallback."""
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        c = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if c is not None:
            return c if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    try:
        return QColor(*fallback_rgba)
    except Exception:
        return None


def _set_colored_text(btn, text: str, color: QColor | None) -> None:
    """Painter-pipeline text color via ButtonRow color (no QSS, no palette)."""
    try:
        from sli_ui_toolkit.widgets import ButtonRow

        btn.setRows([ButtonRow(text=text, size=None, ratio=1.0, color=color)])
    except Exception:
        try:
            btn.setText(text)
        except Exception:
            pass


# S4 v2 LIGHT mockup-pt sizing (W4 item 1): every quick-look Label renders at
# the mockup's own number as *points* via the UiFont point path
# (``UiFont.resolve(point_size=...)`` — scaled exactly once, no UiScale or
# settings changes). ``Label`` itself accepts only ``pixel_size`` (its
# ``_apply_style`` re-runs on font/scale changes using the pixel value), so
# the point font is applied *after* construction and re-asserted after
# Label's own pixel-based restyle. Theme flips only recolor
# (``Label._on_theme_changed``), so they never clobber the point font.
_POINT_PT_BY_PIXEL = {13: 13, 12: 12, 11: 11.5, 10: 10, 9: 9}


def _apply_point_size(label, pt: int | float, **font_kwargs) -> None:
    """Apply a mockup-pt font to a Label via the UiFont point path.

    Extra ``font_kwargs`` (e.g. ``bold=True``) forward to
    ``UiFont.resolve`` so overrides set via the Label constructor survive.
    """
    try:
        from sli_ui_toolkit.managers import UiFont, UiScale

        ui_font = UiFont.get_instance()
        label.setFont(ui_font.resolve(point_size=float(pt), **font_kwargs))
    except Exception:
        try:
            f = label.font()
            f.setPointSizeF(float(pt))
            if font_kwargs.get("bold") is not None:
                f.setBold(bool(font_kwargs["bold"]))
            label.setFont(f)
        except Exception:
            return
    # Re-assert after Label's own pixel-based _apply_style (wired at Label
    # construction, so it always runs first): font_changed and scale_changed
    # would otherwise revert the point font to the pixel value.
    try:
        import weakref as _wr

        from sli_ui_toolkit.managers import UiFont as _UiFont2, UiScale as _UiScale2

        _ui_font = _UiFont2.get_instance()
        _pt = float(pt)
        _fkw = dict(font_kwargs)
        _ref = _wr.ref(label)
        _conns: list = []

        def _reassert() -> None:
            tgt = _ref()
            if tgt is None:
                for _sig, _slot in list(_conns):
                    try:
                        _sig.disconnect(_slot)
                    except Exception:
                        pass
                _conns.clear()
                return
            try:
                tgt.setFont(_UiFont2.get_instance().resolve(point_size=_pt, **_fkw))
            except Exception:
                pass

        try:
            _conns.append((_ui_font.font_changed, _ui_font.font_changed.connect(_reassert)))
            _scale = _UiScale2.get_instance()
            _conns.append((_scale.scale_changed, _scale.scale_changed.connect(_reassert)))
        except Exception:
            pass
    except Exception:
        pass


def _make_label(text: str = "", parent=None, pixel_size: int = 10, pt=None, **kwargs):
    """Create a toolkit Label with mockup-pt sizing (W4 item 1).

    ``pixel_size`` is kept as the Label fallback; the rendered size is the
    mockup number as points (``pt`` override or ``_POINT_PT_BY_PIXEL``).
    """
    from sli_ui_toolkit.widgets import Label

    lbl = Label(text, pixel_size=pixel_size, parent=parent, **kwargs)
    try:
        _resolve_kw = {k: kwargs[k] for k in ("bold", "italic") if kwargs.get(k) is not None}
        _apply_point_size(lbl, float(pt) if pt is not None else _POINT_PT_BY_PIXEL.get(pixel_size, pixel_size), **_resolve_kw)
    except Exception:
        pass
    if kwargs.get("elide"):
        # W7: elide paints truncated text but does NOT shrink
        # QLabel.sizeHint (full-text hint forces the 296px column into
        # h-scroll; minimum_width alone only sets minimumSize). Ignored
        # lets the layout reserve the minimum instead of the hint.
        try:
            lbl.setSizePolicy(QSizePolicy.Policy.Ignored, lbl.sizePolicy().verticalPolicy())
        except Exception:
            pass
    return lbl


class _RuleWidget(QWidget):
    """1px horizontal rule — file-local painted divider (W4 item 3).

    The toolkit ``Divider`` is a button-region dataclass, not a widget
    (``TypeError`` on ``parent=``), and there is no toolkit divider widget
    (``DividerLayer`` is a painter layer, not a ``QWidget``). So the three
    quick-look section rules live here: explicit paintEvent with the
    ``separator.color`` token, theme-subscribed. No QSS.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        from sli_ui_toolkit.managers import scaled_px

        self.setFixedHeight(scaled_px(9))
        try:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        except Exception:
            pass
        self._color = self._resolve_color()
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    @staticmethod
    def _resolve_color():
        try:
            from sli_ui_toolkit.managers import ThemeManager

            from ui.theming import try_resolve_theme_color

            c = try_resolve_theme_color(ThemeManager.get_instance(), "separator.color")
            if c is not None:
                return c if isinstance(c, QColor) else QColor(c)
        except Exception:
            pass
        return _token_color("separator.color", "#e5e5e5")

    def _on_theme_changed(self) -> None:
        try:
            self._color = self._resolve_color()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        self._on_theme_changed()

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            p = QPainter(self)
            try:
                r = self.rect()
                p.fillRect(0, r.height() // 2, r.width(), 1, self._color)
            finally:
                p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass


def reposition_nav_buttons(overlay) -> None:
    """Pin prev/next circles half-outside the card edges (W4 item 6, W10).

    W10: the circles are overlay children (siblings above the card plate),
    positioned in OVERLAY coords — each center sits on the card's left/right
    edge, vertically centered on the preview band. W4..W9 parented them to
    the card plate, whose parent-rect clipping erased the outside half
    (offscreen overlay grab: outside-half pixel was pure veil). Called from
    ``resizeEvent`` and after ``_populate`` (best effort before first show).
    """
    try:
        content = getattr(overlay, "_content", None)
        host = getattr(overlay, "_preview_host", None)
        prev = getattr(overlay, "_prev_btn", None)
        nxt = getattr(overlay, "_next_btn", None)
        if content is None or host is None or prev is None or nxt is None:
            return
        try:
            card = content.geometry()
        except Exception:
            return
        try:
            host_pos = host.mapTo(overlay, QPoint(0, 0))
        except Exception:
            return
        cy = host_pos.y() + host.height() // 2
        for btn, left_edge in ((prev, True), (nxt, False)):
            try:
                bw = btn.width() or btn.sizeHint().width()
                bh = btn.height() or btn.sizeHint().height()
            except Exception:
                continue
            x = card.x() - bw // 2 if left_edge else card.x() + card.width() - bw // 2
            btn.move(x, cy - bh // 2)
            try:
                btn.raise_()
            except Exception:
                pass
    except Exception:
        pass


def reposition_grip(overlay) -> None:
    """Pin the drag-resize grip to the card's bottom-right corner (W8).

    Absolute child of the card plate (same idiom as
    ``reposition_nav_buttons`` / ``reposition_source_inset``). Runs from the
    overlay's ``_content`` Resize filter, ``resizeEvent``, and the grip's
    own drag handler.

    W-B: ends with the card re-layout (preview-with-aspect rescale + footer
    reflow). This function is the one resize entry point that lives in this
    module AND is already invoked on every resize path by ``quick_look.py``
    (``_content`` Resize filter + overlay ``resizeEvent``, both out of W-B
    scope), so the re-layout rides all resizes with no new hooks and no
    out-of-scope edits.
    """
    try:
        content = getattr(overlay, "_content", None)
        grip = getattr(overlay, "_resize_grip", None)
        if content is None or grip is None:
            return
        grip.move(
            max(0, content.width() - grip.width()),
            max(0, content.height() - grip.height()),
        )
        try:
            grip.raise_()
        except Exception:
            pass
    except Exception:
        pass
    try:
        _relayout_on_card_resize(overlay)
    except Exception:
        pass


def clamp_card_size(overlay, want_w: int, want_h: int) -> tuple[int, int]:
    """Clamp a wanted card size to the session-only resize bounds (W8/W9).

    Floor: the S4 mockup 1040×620 card. Ceiling: the overlay (parent/window)
    minus the 16px margin on each side. Shared by the corner grip drag and
    the full-border drag so both handles agree exactly.
    """
    try:
        from sli_ui_toolkit.managers import scaled_px

        margin = scaled_px(16)
        try:
            bound_w = max(0, overlay.width() - margin * 2)
            bound_h = max(0, overlay.height() - margin * 2)
        except Exception:
            bound_w, bound_h = 0, 0
        new_w = max(scaled_px(1040), int(want_w))
        new_h = max(scaled_px(620), int(want_h))
        if bound_w > 0:
            new_w = min(new_w, bound_w)
        if bound_h > 0:
            new_h = min(new_h, bound_h)
        return new_w, new_h
    except Exception:
        return int(want_w), int(want_h)


# W9: full-border resize — an 8px hit strip along the WHOLE card border
# (4 edges + 4 corners, 8 drag directions). Zones are hit-tested from the
# overlay's _content eventFilter (quick_look.py) and reuse the W8 clamp +
# reposition idiom. No QSS: hover affordance is cursor-only, and the
# painted _ResizeGrip stays as the SE corner's visual affordance.
RESIZE_BORDER_PX = 8


def resize_zone_at(content, pos) -> str | None:
    """Hit-test a _content-local point against the 8px border strip (W9).

    Returns one of ``left`` / ``right`` / ``top`` / ``bottom`` /
    ``top_left`` / ``top_right`` / ``bottom_left`` / ``bottom_right``,
    or None when the point is outside the strip (interior).
    """
    try:
        from sli_ui_toolkit.managers import scaled_px

        strip = scaled_px(RESIZE_BORDER_PX)
        w = content.width()
        h = content.height()
        x = pos.x()
        y = pos.y()
        left = x < strip
        right = x >= w - strip
        top = y < strip
        bottom = y >= h - strip
        if top and left:
            return "top_left"
        if top and right:
            return "top_right"
        if bottom and left:
            return "bottom_left"
        if bottom and right:
            return "bottom_right"
        if left:
            return "left"
        if right:
            return "right"
        if top:
            return "top"
        if bottom:
            return "bottom"
        return None
    except Exception:
        return None


def resize_cursor_for(zone: str | None):
    """Hover/drag cursor for a resize zone (W9). None → default arrow."""
    try:
        from PySide6.QtCore import Qt

        mapping = {
            "left": Qt.CursorShape.SizeHorCursor,
            "right": Qt.CursorShape.SizeHorCursor,
            "top": Qt.CursorShape.SizeVerCursor,
            "bottom": Qt.CursorShape.SizeVerCursor,
            "top_left": Qt.CursorShape.SizeFDiagCursor,
            "bottom_right": Qt.CursorShape.SizeFDiagCursor,
            "top_right": Qt.CursorShape.SizeBDiagCursor,
            "bottom_left": Qt.CursorShape.SizeBDiagCursor,
        }
        return mapping.get(zone if zone is not None else "")
    except Exception:
        return None


def _distribute_column_floors(overlay) -> None:
    """Pin left/right minimums from the LIVE card width (65/35 split).

    QBoxLayout hands all undistributed extra space to a single side, so
    stretch factors alone cannot hold mockup proportions AND share growth:
    the column ended stranded at ~496px after shrink-back (clipped preview).
    Instead the floors consume the width exactly — left (preview priority)
    takes 65% of the extra, right 35% — leaving no remainder to misdeal.
    Floors derive from the card width only (never from grown children), so
    nothing ratchets: shrink restores 640/296.
    """
    try:
        from sli_ui_toolkit.managers import scaled_px

        content = getattr(overlay, "_content", None)
        host = getattr(overlay, "_preview_host", None)
        if content is None or host is None:
            return
        left = host.parentWidget()
        scroll = content.findChild(QWidget, "quicklook_right_scroll")
        if left is None or scroll is None:
            return
        outer = content.layout()
        mid = left.parentWidget().layout()
        try:
            om = outer.contentsMargins()
            mm = mid.contentsMargins()
            avail = (
                content.width()
                - om.left() - om.right()
                - mm.left() - mm.right()
                - mid.spacing()
            )
        except Exception:
            avail = content.width() - scaled_px(40)
        base_l, base_r = scaled_px(640), scaled_px(296)
        extra = max(0, int(avail) - base_l - base_r)
        left_extra = int(round(extra * 0.65))
        left.setMinimumWidth(base_l + left_extra)
        scroll.setMinimumWidth(base_r + (extra - left_extra))
    except Exception:
        pass


def relayout_report_rows(overlay) -> None:
    """Lay metric + artifact rows flat in the right column, uniformly spaced.

    Rows (tracked in ``overlay._metric_rows`` / ``overlay._artifact_rows``)
    become direct ``right_lay`` children with stretch 0, in visual order,
    with one stretch-1 spacer between every consecutive pair — metrics rows,
    then artifact rows, inserted right before the series divider. Rows pin
    at sizeHint; ALL surplus splits evenly among the N equal spacers at
    every height (gap = surplus/N, collapsing to the 4px spacing floor
    when short). The series/strip/brief blocks below stay pinned after the
    last row. Called after every metrics/artifacts rebuild (either order);
    never raises.
    """
    try:
        lay = getattr(overlay, "_right_lay", None)
        host = getattr(overlay, "_report_host", None)
        anchor = getattr(overlay, "_div_series", None)
        if lay is None or host is None or anchor is None:
            return
        rows = list(getattr(overlay, "_metric_rows", [])) + list(getattr(overlay, "_artifact_rows", []))
        # Detach previous pass: tracked rows plus any spacers this function
        # inserted (this layout owns no other spacers, so sweep them all).
        for row in rows:
            try:
                lay.removeWidget(row)
            except Exception:
                pass
        for i in range(lay.count() - 1, -1, -1):
            try:
                it = lay.itemAt(i)
            except Exception:
                continue
            if it is not None and it.widget() is None and it.spacerItem() is not None:
                try:
                    lay.removeItem(it)
                except Exception:
                    pass
        try:
            idx = lay.indexOf(anchor)
        except Exception:
            idx = -1
        if idx < 0:
            return
        for n, row in enumerate(rows):
            try:
                if row.parent() is not host:
                    row.setParent(host)
            except Exception:
                pass
            try:
                lay.insertWidget(idx, row, 0)
            except Exception:
                continue
            idx += 1
            if n < len(rows) - 1:
                try:
                    lay.insertStretch(idx, 1)
                except Exception:
                    pass
                idx += 1
    except Exception:
        pass


def _repin_after_card_resize(overlay) -> None:
    """Re-run the absolute-child pin hooks after a card resize step.

    W-B: the card re-layout (preview-with-aspect rescale + footer reflow)
    rides along via ``reposition_grip`` (called below), so the drag paths
    (grip / border / ring) and the overlay Resize paths all re-layout
    through this one entry.
    """
    try:
        overlay._reposition_source_inset()
    except Exception:
        pass
    try:
        reposition_grip(overlay)
    except Exception:
        pass


def _rescale_preview_to_host(overlay) -> None:
    """Rescale the stashed full preview pixmap to the live label size (W-B).

    Export-window idiom: the preview pane stretches with the card while the
    image inside keeps its aspect (``KeepAspectRatio`` letterbox, never a
    stretch). ``populate_preview`` stashes the unscaled source in
    ``overlay._preview_full``; this re-derives the shown pixmap from it on
    every card resize. No-op when nothing populatable is stashed (fake
    paths, null pixmaps) or the label has no size yet.
    """
    try:
        full = getattr(overlay, "_preview_full", None)
        label = getattr(overlay, "_preview_label", None)
        if full is None or label is None:
            return
        try:
            if full.isNull():
                return
        except Exception:
            return
        try:
            from sli_ui_toolkit.managers import scaled_px

            target_w = label.width()
            target_h = label.height()
            if target_w <= 0 or target_h <= 0:
                target_w, target_h = scaled_px(640), scaled_px(456)
        except Exception:
            return
        try:
            from PySide6.QtCore import Qt

            scaled = full.scaled(
                target_w,
                target_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        except Exception:
            return
        try:
            if scaled is not None and not scaled.isNull():
                label.setPixmap(scaled)
        except Exception:
            pass
    except Exception:
        pass


def _reflow_footer(overlay) -> None:
    """Reflow the bottom action bar after a card resize (W-B).

    Export-window idiom: action buttons keep their natural widths on the
    left, the hint stays pinned right via the bar stretch. The layout does
    the reflow itself; this hook guarantees its invariants (hint is the
    last bar item, bar geometry is refreshed) so a resize can never strand
    the hint mid-bar. Never hides or closes anything.
    """
    try:
        bar = None
        try:
            content = getattr(overlay, "_content", None)
            if content is not None:
                bar = content.findChild(QWidget, "quicklook_bottom_bar")
        except Exception:
            bar = None
        if bar is None:
            return
        hint = getattr(overlay, "_hint_label", None)
        try:
            lay = bar.layout()
        except Exception:
            lay = None
        if lay is not None and hint is not None:
            try:
                if lay.count() > 0 and lay.itemAt(lay.count() - 1).widget() is not hint:
                    lay.removeWidget(hint)
                    lay.addWidget(hint)
            except Exception:
                pass
        try:
            bar.updateGeometry()
        except Exception:
            pass
    except Exception:
        pass


def _relayout_on_card_resize(overlay) -> None:
    """Card re-layout entry for every resize step (W-B).

    Preview stretches with aspect, footer reflows. Called from
    ``reposition_grip`` (the in-scope hook every resize path already runs);
    also reachable directly. No close paths, no size-policy changes (W8
    min-only stays: minimum 1040×620, no maximum).
    """
    _distribute_column_floors(overlay)
    _rescale_preview_to_host(overlay)
    _reflow_footer(overlay)


# W11: nav arrows (overlay children sitting in the ring zone) must NEVER
# start a drag. A press/drag starting inside either arrow rect walks the
# series and consumes the event — the arrow rects are excluded from ring +
# plate drag hit-testing at the handler level (the pure zone functions
# ``resize_zone_at`` / ``ring_zone_at`` stay arrow-agnostic so their unit
# geometry is unchanged). This covers the fall-through production case:
# enabled buttons consume presses as widgets, but DISABLED buttons (single
# item) let presses through to the overlay/plate handlers, where the outer
# half of the circle sits inside the ring band. Hover over an arrow shows
# the plain arrow cursor, never a resize cursor.


def nav_button_at(overlay, overlay_pos):
    """Overlay-local hit-test against the prev/next circles (W11).

    Returns the hit button or None. Geometry is overlay-local (W10: the
    circles are overlay children), so plate callers must map content-local
    points via ``content.mapTo(overlay, local)`` first.
    """
    try:
        for btn in (getattr(overlay, "_prev_btn", None), getattr(overlay, "_next_btn", None)):
            try:
                if btn is not None and btn.geometry().contains(overlay_pos):
                    return btn
            except Exception:
                continue
    except Exception:
        pass
    return None


def _walk_for_nav_button(overlay, btn) -> None:
    """Walk the series for a nav-arrow press (W11). Prev → −1, next → +1."""
    try:
        overlay._walk(-1 if btn is getattr(overlay, "_prev_btn", None) else 1)
    except Exception:
        pass


def handle_border_press(overlay, event) -> bool:
    """Start a full-border drag on left-press inside the strip (W9).

    W11: presses inside either nav-arrow rect walk the series and are
    consumed (never a drag). Returns True when the press was consumed
    (caller must accept it).
    """
    try:
        from PySide6.QtCore import Qt

        if event.button() != Qt.MouseButton.LeftButton:
            return False
        content = getattr(overlay, "_content", None)
        if content is None:
            return False
        try:
            local = event.position().toPoint()
        except Exception:
            return False
        try:
            nav_hit = nav_button_at(overlay, content.mapTo(overlay, local))
        except Exception:
            nav_hit = None
        if nav_hit is not None:
            _walk_for_nav_button(overlay, nav_hit)
            try:
                event.accept()
            except Exception:
                pass
            return True
        zone = resize_zone_at(content, local)
        if zone is None:
            return False
        try:
            start_global = event.globalPosition().toPoint()
        except Exception:
            return False
        overlay._border_drag = (zone, start_global, content.geometry())
        cursor = resize_cursor_for(zone)
        if cursor is not None:
            try:
                content.setCursor(cursor)
            except Exception:
                pass
        try:
            event.accept()
        except Exception:
            pass
        return True
    except Exception:
        return False


def handle_border_move(overlay, event) -> bool:
    """Hover cursors + live border drag (W9). True when consumed."""
    try:
        from PySide6.QtCore import Qt

        content = getattr(overlay, "_content", None)
        if content is None:
            return False
        drag = getattr(overlay, "_border_drag", None)
        if drag is not None:
            try:
                cur = event.globalPosition().toPoint()
            except Exception:
                return False
            zone, start_global, start_geom = drag
            dx = cur.x() - start_global.x()
            dy = cur.y() - start_global.y()
            want_w = start_geom.width()
            want_h = start_geom.height()
            if "left" in zone:
                want_w = start_geom.width() - dx
            elif "right" in zone:
                want_w = start_geom.width() + dx
            if "top" in zone:
                want_h = start_geom.height() - dy
            elif "bottom" in zone:
                want_h = start_geom.height() + dy
            new_w, new_h = clamp_card_size(overlay, want_w, want_h)
            try:
                # Anchor the opposite edge: left/top drags move the card
                # so the edge under the cursor tracks it (right/bottom
                # drags keep the W8 top-left anchor).
                new_x = start_geom.x() + (start_geom.width() - new_w) if "left" in zone else start_geom.x()
                new_y = start_geom.y() + (start_geom.height() - new_h) if "top" in zone else start_geom.y()
                if new_x != start_geom.x() or new_y != start_geom.y():
                    content.move(new_x, new_y)
                content.resize(new_w, new_h)
            except Exception:
                pass
            _repin_after_card_resize(overlay)
            try:
                event.accept()
            except Exception:
                pass
            return True
        # Hover (no buttons): cursor-only affordance, never consumed.
        try:
            buttons = event.buttons()
        except Exception:
            buttons = Qt.MouseButton.NoButton
        if buttons != Qt.MouseButton.NoButton:
            return False
        try:
            local = event.position().toPoint()
        except Exception:
            return False
        # W11: arrow rects never show a resize cursor (plain arrow instead).
        try:
            if nav_button_at(overlay, content.mapTo(overlay, local)) is not None:
                try:
                    content.unsetCursor()
                except Exception:
                    pass
                return False
        except Exception:
            pass
        cursor = resize_cursor_for(resize_zone_at(content, local))
        try:
            if cursor is not None:
                content.setCursor(cursor)
            else:
                content.unsetCursor()
        except Exception:
            pass
        return False
    except Exception:
        return False


def handle_border_release(overlay, event) -> bool:
    """End a full-border drag (W9). True when a drag was active."""
    try:
        drag = getattr(overlay, "_border_drag", None)
        if drag is None:
            return False
        overlay._border_drag = None
        _repin_after_card_resize(overlay)
        try:
            content = getattr(overlay, "_content", None)
            if content is not None:
                content.unsetCursor()
        except Exception:
            pass
        try:
            event.accept()
        except Exception:
            pass
        return True
    except Exception:
        return False


def ring_zone_at(overlay, pos) -> str | None:
    """Hit-test an OVERLAY-local point against the 8px ring OUTSIDE the card.

    W10: the W9 strip lives on the card plate (inner edge only) — the 8px
    band on the veil around the card grabbed nothing. This mirrors
    ``resize_zone_at`` for that outer band: returns the same 8 zone names
    when ``pos`` is outside the card but within ``RESIZE_BORDER_PX`` of it,
    else None (interior, card children, and open veil all return None —
    a plain veil click must never start a drag, W6).
    """
    try:
        from sli_ui_toolkit.managers import scaled_px

        content = getattr(overlay, "_content", None)
        if content is None:
            return None
        try:
            card = content.geometry()
        except Exception:
            return None
        try:
            x = pos.x()
            y = pos.y()
        except Exception:
            return None
        # Interior (including the card border itself) belongs to the W9
        # plate filter, never to the ring.
        try:
            if card.contains(pos):
                return None
        except Exception:
            pass
        strip = scaled_px(RESIZE_BORDER_PX)
        left = card.x() - strip <= x < card.x()
        right = card.x() + card.width() <= x < card.x() + card.width() + strip
        top = card.y() - strip <= y < card.y()
        bottom = card.y() + card.height() <= y < card.y() + card.height() + strip
        # Ring bands only run alongside the card (corners are strip×strip
        # squares); anything beyond is open veil.
        v_span = card.y() - strip <= y < card.y() + card.height() + strip
        h_span = card.x() - strip <= x < card.x() + card.width() + strip
        if (left or right) and not v_span:
            return None
        if (top or bottom) and not h_span:
            return None
        if top and left:
            return "top_left"
        if top and right:
            return "top_right"
        if bottom and left:
            return "bottom_left"
        if bottom and right:
            return "bottom_right"
        if left:
            return "left"
        if right:
            return "right"
        if top:
            return "top"
        if bottom:
            return "bottom"
        return None
    except Exception:
        return None


def handle_ring_press(overlay, event) -> bool:
    """Start a border drag from the OUTER ring (W10). True when consumed.

    Shares the ``_border_drag`` tuple + ``clamp_card_size`` + cursor idiom
    with the W9 plate handlers, so inner and outer drags agree exactly.
    Plain veil clicks (``ring_zone_at`` None) return False — W6 holds.
    W11: presses inside either nav-arrow rect walk the series and are
    consumed (arrows never start a drag).
    """
    try:
        from PySide6.QtCore import Qt

        if event.button() != Qt.MouseButton.LeftButton:
            return False
        content = getattr(overlay, "_content", None)
        if content is None:
            return False
        try:
            local = event.position().toPoint()
        except Exception:
            return False
        nav_hit = nav_button_at(overlay, local)
        if nav_hit is not None:
            _walk_for_nav_button(overlay, nav_hit)
            try:
                event.accept()
            except Exception:
                pass
            return True
        zone = ring_zone_at(overlay, local)
        if zone is None:
            return False
        try:
            start_global = event.globalPosition().toPoint()
        except Exception:
            return False
        overlay._border_drag = (zone, start_global, content.geometry())
        cursor = resize_cursor_for(zone)
        if cursor is not None:
            try:
                overlay.setCursor(cursor)
            except Exception:
                pass
        try:
            event.accept()
        except Exception:
            pass
        return True
    except Exception:
        return False


def handle_ring_hover(overlay, event) -> bool:
    """Hover cursors over the outer ring (W10). Never consumed.

    Overlay-level moves carry overlay-local positions, so the W9 plate
    hover (content-local) cannot serve here. Cursor-only affordance, no QSS.
    """
    try:
        from PySide6.QtCore import Qt

        if getattr(overlay, "_border_drag", None) is not None:
            return False
        try:
            buttons = event.buttons()
        except Exception:
            buttons = Qt.MouseButton.NoButton
        if buttons != Qt.MouseButton.NoButton:
            return False
        try:
            local = event.position().toPoint()
        except Exception:
            return False
        # W11: arrow rects never show a resize cursor (plain arrow instead).
        try:
            if nav_button_at(overlay, local) is not None:
                try:
                    overlay.unsetCursor()
                except Exception:
                    pass
                return False
        except Exception:
            pass
        cursor = resize_cursor_for(ring_zone_at(overlay, local))
        try:
            if cursor is not None:
                overlay.setCursor(cursor)
            else:
                overlay.unsetCursor()
        except Exception:
            pass
        return False
    except Exception:
        return False


def handle_ring_release(overlay, event) -> bool:
    """End an outer-ring drag (W10). True when a drag was active."""
    try:
        if getattr(overlay, "_border_drag", None) is None:
            return False
        overlay._border_drag = None
        _repin_after_card_resize(overlay)
        try:
            overlay.unsetCursor()
        except Exception:
            pass
        try:
            content = getattr(overlay, "_content", None)
            if content is not None:
                content.unsetCursor()
        except Exception:
            pass
        try:
            event.accept()
        except Exception:
            pass
        return True
    except Exception:
        return False


class _ResizeGrip(QWidget):
    """Bottom-right drag handle for the resizable quick look card (W8).

    Painter-painted (three diagonal grip lines in the ``separator.color``
    token, theme-subscribed) — no QSS, no palette. Dragging resizes the
    card plate in place (top-left anchored): minimum 1040×620, clamped to
    the overlay size minus margin; session-only, nothing persisted. After
    every step the existing reposition hooks (nav circles, source inset)
    re-run via ``overlay._reposition_source_inset()`` plus
    ``reposition_grip``.
    """

    GRIP_PX = 20

    def __init__(self, overlay, parent=None) -> None:
        super().__init__(parent)
        self._overlay_ref = overlay
        from sli_ui_toolkit.managers import scaled_px

        self.setFixedSize(scaled_px(self.GRIP_PX), scaled_px(self.GRIP_PX))
        self.setObjectName("quicklook_resize_grip")
        try:
            from PySide6.QtCore import Qt

            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        except Exception:
            pass
        self._color = self._resolve_color()
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass
        self._drag_start = None
        self._drag_size = None

    @staticmethod
    def _resolve_color():
        try:
            from sli_ui_toolkit.managers import ThemeManager

            from ui.theming import try_resolve_theme_color

            c = try_resolve_theme_color(ThemeManager.get_instance(), "separator.color")
            if c is not None:
                return c if isinstance(c, QColor) else QColor(c)
        except Exception:
            pass
        return _token_color("separator.color", "#e5e5e5")

    def _on_theme_changed(self) -> None:
        try:
            self._color = self._resolve_color()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        self._on_theme_changed()

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            from PySide6.QtGui import QPen

            from sli_ui_toolkit.managers import scaled_px

            p = QPainter(self)
            try:
                color = self._color
                if color is None:
                    # Contract-safe re-resolve (token helper, never a
                    # bare literal — test_no_hardcoded_qcolor ratchet).
                    color = _token_color("separator.color", "#e5e5e5")
                pen = QPen(color if color is not None else QColor(0, 0, 0, 0))
                pen.setWidthF(max(1.0, scaled_px(1)))
                p.setPen(pen)
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                w = self.width()
                h = self.height()
                step = scaled_px(4)
                for i in range(3):
                    off = step * (i + 1)
                    p.drawLine(w - off, h, w, h - off)
            finally:
                p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass

    def mousePressEvent(self, event) -> None:  # noqa: N802
        try:
            from PySide6.QtCore import Qt

            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_start = event.globalPosition().toPoint()
                content = getattr(self._overlay_ref, "_content", None)
                if content is not None:
                    self._drag_size = content.size()
                event.accept()
                return
        except Exception:
            pass
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        try:
            if self._drag_start is not None and self._drag_size is not None:
                overlay = self._overlay_ref
                content = getattr(overlay, "_content", None)
                if content is not None:
                    delta = event.globalPosition().toPoint() - self._drag_start
                    want_w = self._drag_size.width() + delta.x()
                    want_h = self._drag_size.height() + delta.y()
                    # W9: shared session-only clamp (floor 1040×620, ceiling
                    # overlay minus 16px margin) — same as the border drag.
                    new_w, new_h = clamp_card_size(overlay, want_w, want_h)
                    content.resize(new_w, new_h)
                    # The _content Resize filter re-runs nav/inset/grip
                    # hooks; belt-and-braces for paths that compress events.
                    _repin_after_card_resize(overlay)
                event.accept()
                return
        except Exception:
            pass
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_start = None
        self._drag_size = None
        super().mouseReleaseEvent(event)


def _source_dimensions(src_item, src_path) -> tuple[int, int] | None:
    """Source image dimensions: metrics width/height first, QPixmap fallback."""
    metrics = getattr(src_item, "metrics", None) if src_item is not None else None
    if isinstance(metrics, dict):
        try:
            w = metrics.get("width")
            h = metrics.get("height")
            if w and h:
                return int(w), int(h)
        except Exception:
            pass
    try:
        if src_path is not None:
            pm = QPixmap(str(src_path))
            if not pm.isNull():
                return pm.width(), pm.height()
    except Exception:
        pass
    return None


# -- UI construction helpers (thin owner delegation) -------------------------

def build_overlay_ui(overlay) -> None:
    """Construct QuickLookOverlay layout (thin owner delegator).

    Reads/writes overlay attributes directly per CODE_PATTERNS plain function.
    No QSS, painter pipeline only, lazy imports for theming.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QFrame, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

    from sli_ui_toolkit.managers import scaled_px
    from sli_ui_toolkit.widgets import Button, ButtonRow

    try:
        from tabs.image_gallery.ui.quick_look.source_inset import _InsetCaptionStrip, _SourceInsetHost
    except Exception:
        from PySide6.QtWidgets import QWidget as _W

        _SourceInsetHost = _W  # type: ignore
        _InsetCaptionStrip = _W  # type: ignore

    overlay._content = _CardPlate(overlay)
    overlay._content.setObjectName("QuickLookContent")
    # W9: the whole border is a resize strip — hover cursors need
    # button-free MouseMove delivery on the plate (no QSS involved).
    try:
        overlay._content.setMouseTracking(True)
    except Exception:
        pass
    overlay._border_drag = None
    # S4 mockup panel is 1040x620 — minimum (floor), not a suggestion.
    # W8: NO maximum — the user drag-resizes via the corner grip handle.
    overlay._content.setMinimumSize(scaled_px(1040), scaled_px(620))
    outer = QVBoxLayout(overlay._content)
    outer.setContentsMargins(scaled_px(16), scaled_px(12), scaled_px(16), scaled_px(12))
    # W5: the 620-tall card must fit without scrollbars (S4 mockup: none) —
    # the W4 pt fonts cost ~95px of row height vs the mockup's px lines,
    # so the column/mode chrome gaps densify instead of scrolling. Budget:
    # content min-height must stay under the mid-row viewport (~505px);
    # every spacing below is sized against that budget (see W5 DONE note).
    outer.setSpacing(scaled_px(4))
    chip_row = QHBoxLayout()
    chip_row.setContentsMargins(0, 0, 0, 0)
    chip_row.setSpacing(scaled_px(8))
    # NOTE: bold goes through the _make_label constructor (never setBold
    # after): setBold re-runs Label's pixel-based _apply_style and would
    # revert the mockup-pt font.
    overlay._mode_chip = _make_label("FIDELITY MODE", parent=overlay._content, pixel_size=10, pt=10, color_token="accent", bold=True)
    overlay._mode_chip.setObjectName("quicklook_mode_chip")
    # S4 mockup: accent-tinted pill behind the chip (fill accent @ 0.2).
    # Painted host (explicit paintEvent, theme-subscribed) — no QSS, no palette.
    try:
        pill = _AccentPillHost(overlay._content)
        pill.setObjectName("quicklook_mode_chip_pill")
        pill_lay = QHBoxLayout(pill)
        pill_lay.setContentsMargins(scaled_px(10), scaled_px(2), scaled_px(10), scaled_px(2))
        pill_lay.setSpacing(0)
        overlay._mode_chip.setParent(pill)
        pill_lay.addWidget(overlay._mode_chip)
        overlay._mode_chip_pill = pill
        chip_row.addWidget(pill)
        # Reparenting resets the explicit font — re-assert the pt size after.
        _apply_point_size(overlay._mode_chip, 10, bold=True)
    except Exception:
        try:
            chip_row.addWidget(overlay._mode_chip)
        except Exception:
            pass
    chip_row.addStretch(1)
    overlay._close_btn = Button(text="✕", variant="surface", size=(28, 28), parent=overlay._content)
    overlay._close_btn.setObjectName("quicklook_close")
    overlay._close_btn.clicked.connect(overlay.hide)
    chip_row.addWidget(overlay._close_btn)
    outer.addLayout(chip_row)
    mid = QHBoxLayout()
    mid.setContentsMargins(0, 0, 0, 0)
    mid.setSpacing(scaled_px(16))
    left = QWidget(overlay._content)
    left.setObjectName("QuickLookLeft")
    # Expanding (not Preferred): a Preferred pane caps at its sizeHint, so it
    # would never take layout growth (sticky 640/496 split). Expanding shares
    # extra space by stretch; minimums still floor the shrink-back.
    left.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    left_lay = QVBoxLayout(left)
    left_lay.setContentsMargins(0, 0, 0, 0)
    left_lay.setSpacing(scaled_px(8))
    preview_row = QHBoxLayout()
    preview_row.setContentsMargins(0, 0, 0, 0)
    preview_row.setSpacing(scaled_px(6))
    preview_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
    # S4 v2 (svg:67-70): 36px circular prev/next overlapping the card edge
    # half-outside (W4 item 6) — W10: overlay children (siblings above the
    # card plate), positioned by reposition_nav_buttons in overlay coords,
    # NOT layout items and NOT card children (the plate clips children to
    # its rect, which erased the outside half). Glyph via rows (rows-only buttons take setFixedSize
    # so 36x36 actually lands); round shape via corner_radius (design px,
    # scaled internally); no QSS anywhere on this path.
    # W9: mockup paint — #f1f2f4 disc, #d7dade ring, #23262b chevron.
    # Fill goes through set_override_bg_color (exact base layer), NOT
    # set_background_color: the derived-palette path early-returns on
    # DISABLED with border=None, so a single-item card rendered a flat
    # #e0e0e0 disc with no ring. The override path keeps the explicit
    # border in every state. Glyph ratio=1.0 (ButtonRow defaults to 0.5,
    # which parked the chevron in the top half — dark rows y 8..13 of 36).
    _nav_glyph = _token_color("gallery.nav.glyph", "#23262b")
    _nav_fill = _token_color("gallery.nav.fill", "#f1f2f4")
    _nav_border = _token_color("gallery.nav.border", "#d7dade")
    # W11: glyph rows size up to QUICK_LOOK_NAV_GLYPH_PT (ratio=1.0 keeps
    # them centered, ring intact in both states) — 36px circles unchanged.
    overlay._prev_btn = Button(rows=[ButtonRow(text="‹", size=QUICK_LOOK_NAV_GLYPH_PT, ratio=1.0, color=_nav_glyph)], variant="surface", size=(36, 36), corner_radius=18, parent=overlay)
    overlay._prev_btn.setObjectName("quicklook_prev")
    try:
        if _nav_fill is not None:
            overlay._prev_btn.set_override_bg_color(_nav_fill)
        if _nav_border is not None:
            overlay._prev_btn.set_border_color(_nav_border)
    except Exception:
        pass
    overlay._prev_btn.clicked.connect(lambda: overlay._walk(-1))
    preview_host = QWidget(left)
    preview_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    preview_host.setObjectName("QuickLookPreviewHost")
    overlay._preview_host = preview_host
    preview_host_lay = QVBoxLayout(preview_host)
    preview_host_lay.setContentsMargins(0, 0, 0, 0)
    preview_host_lay.setSpacing(scaled_px(6))
    overlay._preview_label = QLabel(preview_host)
    overlay._preview_label.setObjectName("quicklook_preview")
    overlay._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    overlay._preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    # Mockup preview is 640x456 (svg): the label floor holds the min-card
    # proportions (640 preview + 296 column) so grow->shrink settles back
    # instead of splitting the leftover 1:1 (which stranded ~496px on the
    # scroll and clipped the preview). The pixmap itself stays aspect-kept
    # (W-B reflow); this floor is layout geometry only.
    overlay._preview_label.setMinimumSize(scaled_px(640), scaled_px(456))
    try:
        overlay._preview_label.setScaledContents(False)
    except Exception:
        pass
    preview_host_lay.addWidget(overlay._preview_label, 1)
    overlay._source_inset_host = _SourceInsetHost(overlay._preview_label)
    overlay._source_inset_host.setObjectName("quicklook_source_inset_host")
    src_lay = QVBoxLayout(overlay._source_inset_host)
    src_lay.setContentsMargins(scaled_px(2), scaled_px(2), scaled_px(2), scaled_px(2))
    src_lay.setSpacing(scaled_px(2))
    # W4 item 5: caption is an amber-on-dark strip overlaid at the inset
    # bottom (svg:53-64), elided to the strip width — not a VBox label.
    # The attribute name stays _source_inset_label (tests + populate read it).
    try:
        overlay._source_inset_caption = _InsetCaptionStrip(overlay._source_inset_host)
        overlay._source_inset_label = overlay._source_inset_caption.label
    except Exception:
        overlay._source_inset_label = _make_label("SOURCE", parent=overlay._source_inset_host, pixel_size=9, pt=9)
        overlay._source_inset_label.setObjectName("quicklook_source_inset_title")
    overlay._source_inset_pix = QLabel(overlay._source_inset_host)
    overlay._source_inset_pix.setObjectName("quicklook_source_inset_pix")
    overlay._source_inset_pix.setFixedSize(scaled_px(150), scaled_px(84))
    overlay._source_inset_pix.setAlignment(Qt.AlignmentFlag.AlignCenter)
    overlay._source_inset_pix.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    # Background fill is painted by _SourceInsetHost itself (theme-subscribed
    # paintEvent) — no palette here.
    src_lay.addWidget(overlay._source_inset_pix)
    overlay._source_inset_host.raise_()
    overlay._source_inset_host.hide()
    overlay._crop_host = QWidget(preview_host)
    overlay._crop_host.setObjectName("quicklook_crop_host")
    crop_lay = QVBoxLayout(overlay._crop_host)
    crop_lay.setContentsMargins(0, 0, 0, 0)
    crop_lay.setSpacing(scaled_px(2))
    overlay._crop_title = _make_label("SHARPNESS CROP", parent=overlay._crop_host, pixel_size=9, pt=9)
    overlay._crop_title.setObjectName("quicklook_crop_title")
    crop_lay.addWidget(overlay._crop_title)
    overlay._crop_pix = QLabel(overlay._crop_host)
    overlay._crop_pix.setObjectName("quicklook_crop_pix")
    overlay._crop_pix.setFixedSize(scaled_px(150), scaled_px(84))
    overlay._crop_pix.setAlignment(Qt.AlignmentFlag.AlignCenter)
    overlay._crop_pix.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    crop_lay.addWidget(overlay._crop_pix)
    preview_host_lay.addWidget(overlay._crop_host)
    fname_row = QHBoxLayout()
    fname_row.setContentsMargins(0, 0, 0, 0)
    fname_row.setSpacing(scaled_px(8))
    overlay._filename_label = _make_label("", parent=preview_host, pixel_size=12, pt=12, bold=True)
    overlay._filename_label.setObjectName("quicklook_filename")
    fname_row.addWidget(overlay._filename_label)
    overlay._meta_label = _make_label("", parent=preview_host, pixel_size=11, pt=11.5)
    overlay._meta_label.setObjectName("quicklook_meta")
    fname_row.addWidget(overlay._meta_label)
    fname_row.addStretch(1)
    preview_host_lay.addLayout(fname_row)
    preview_row.addWidget(preview_host, 1)
    overlay._next_btn = Button(rows=[ButtonRow(text="›", size=QUICK_LOOK_NAV_GLYPH_PT, ratio=1.0, color=_nav_glyph)], variant="surface", size=(36, 36), corner_radius=18, parent=overlay)
    overlay._next_btn.setObjectName("quicklook_next")
    try:
        if _nav_fill is not None:
            overlay._next_btn.set_override_bg_color(_nav_fill)
        if _nav_border is not None:
            overlay._next_btn.set_border_color(_nav_border)
    except Exception:
        pass
    overlay._next_btn.clicked.connect(lambda: overlay._walk(1))
    left_lay.addLayout(preview_row, 1)
    # W4 item 4: the Esc hint lives at the right end of the bottom button
    # bar (built below), not in the left column. Nothing added here.
    mid.addWidget(left, 1)
    right_scroll = QScrollArea(overlay._content)
    right_scroll.setObjectName("quicklook_right_scroll")
    # W13: the mockup's right column is min 296px (svg x=816 w=296) and
    # STRETCHES with the card — a minimum, never a fixed width. The
    # value/sub labels still elide (they take the free row width via
    # stretch), so a wider column never summons scrollbars; the column
    # never drops below 296.
    right_scroll.setMinimumWidth(scaled_px(296))
    try:
        right_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    except Exception:
        pass
    # W4 item 2: frameless — the scroll frame drew a bogus box around the
    # right column. No QSS (stock Qt widget, frame shape only).
    try:
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
    except Exception:
        pass
    right_scroll.setWidgetResizable(True)
    # W7: widths are bounded by construction (296px column, elided text,
    # fixed thumbs) — a full-text sizeHint must never summon a scrollbar.
    # Horizontal is AlwaysOff; vertical stays AsNeeded.
    right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    right_host = QWidget(right_scroll)
    right_host.setObjectName("quicklook_right_host")
    # W13: the host expands with the scroll viewport (the scroll area is
    # widget-resizable, so the host tracks the stretched column width).
    try:
        right_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    except Exception:
        pass
    right_lay = QVBoxLayout(right_host)
    right_lay.setContentsMargins(0, 0, 0, 0)
    # W5: 10→4 (see outer spacing note — the 296px column must fit the
    # 620 card with metrics + 2 artifact rows + series + brief, no scroll).
    right_lay.setSpacing(scaled_px(4))
    right_lay.setAlignment(Qt.AlignmentFlag.AlignTop)
    overlay._report_title = _make_label("Fidelity report", parent=right_host, pixel_size=13, pt=13, bold=True)
    overlay._report_title.setObjectName("quicklook_report_title")
    right_lay.addWidget(overlay._report_title)
    overlay._report_sub = _make_label("", parent=right_host, pixel_size=10, pt=10, elide=True, minimum_width=40)
    overlay._report_sub.setObjectName("quicklook_report_sub")
    right_lay.addWidget(overlay._report_sub)
    # FLAT report section: metric + artifact rows are direct right_lay
    # children (stretch 0) with one uniform stretch-1 spacer between every
    # consecutive pair — rows pin at sizeHint, ALL surplus splits evenly
    # among the spacers at every height (gap = surplus/N, floor = spacing
    # when short). Nested host layouts can NOT do this: QBoxLayout deals
    # absolute space by stretch, so a host's share gets eaten by its fixed
    # rows and starves its inner gaps while boundary spacers balloon.
    # Rows are parented to right_host (visible ancestor) and tracked in
    # overlay._metric_rows / overlay._artifact_rows; relayout_report_rows()
    # owns row/spacer placement after every rebuild.
    overlay._report_host = right_host
    overlay._right_lay = right_lay
    # S4 mockup divider before the series context block (svg:462) — a
    # file-local 1px painted rule (W4 item 3); the toolkit Divider is a
    # button-region dataclass, not a widget.
    overlay._div_series = _RuleWidget(right_host)
    overlay._div_series.setObjectName("quicklook_div_series")
    right_lay.addWidget(overlay._div_series)
    # W7: the hub stem can be a long filename ("Series 1 · <stem>":
    # probe measured 315px) — elide to the column like the sublines.
    overlay._series_header = _make_label("Series", parent=right_host, pixel_size=11, pt=13, bold=True, elide=True, minimum_width=40)
    overlay._series_header.setObjectName("quicklook_series_header")
    right_lay.addWidget(overlay._series_header)
    overlay._series_sub = _make_label("", parent=right_host, pixel_size=10, pt=11.5, elide=True, minimum_width=40)
    overlay._series_sub.setObjectName("quicklook_series_sub")
    right_lay.addWidget(overlay._series_sub)
    overlay._strip_host = QWidget(right_host)
    overlay._strip_host.setObjectName("quicklook_strip_host")
    overlay._strip_layout = QHBoxLayout(overlay._strip_host)
    overlay._strip_layout.setContentsMargins(0, 0, 0, 0)
    overlay._strip_layout.setSpacing(scaled_px(6))
    overlay._strip_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
    right_lay.addWidget(overlay._strip_host)
    # S4 mockup divider before the compare-brief teaser (svg:600) — painted
    # rule, see _div_series.
    overlay._div_brief = _RuleWidget(right_host)
    overlay._div_brief.setObjectName("quicklook_div_brief")
    right_lay.addWidget(overlay._div_brief)
    overlay._brief_label = _make_label("", parent=right_host, pixel_size=11, pt=11.5)
    overlay._brief_label.setObjectName("quicklook_brief")
    overlay._brief_label.setWordWrap(True)
    # W7: a word-wrap label reports the UNWRAPPED width as its sizeHint
    # (~346px live) — it must wrap to the column, never widen it.
    try:
        overlay._brief_label.setSizePolicy(QSizePolicy.Policy.Ignored, overlay._brief_label.sizePolicy().verticalPolicy())
    except Exception:
        pass
    # W7: QLabel.minimumSizeHint for wrapped text is the height at the
    # LONGEST-WORD width (2 phantom lines here) — the layout reserves it
    # and the 620px card gains a 4px v-scroll. The label always lays out
    # at the column width, so pin the minimum width to the column floor:
    # minimumSizeHint becomes the height AT that width (honest, grows
    # with real line count) and the column minimum stays 296. W13: the
    # 296 floor is unchanged for wider (stretched) columns — the label
    # fills them via its Ignored horizontal policy.
    try:
        overlay._brief_label.setMinimumWidth(scaled_px(296))
    except Exception:
        pass
    right_lay.addWidget(overlay._brief_label)
    right_scroll.setWidget(right_host)
    # W13: the right column takes resize space too (stretch 1) — the
    # preview keeps priority with its own stretch 1 plus the larger
    # expanding preview pane. W8 min-only stays (minimum 1040×620, no
    # maximum); the column floor is the 296px minimum above.
    mid.addWidget(right_scroll, 1)
    outer.addLayout(mid, 1)
    # S4 mockup divider above the bottom action bar (svg:648) — painted
    # rule, see _div_series.
    overlay._div_bar = _RuleWidget(overlay._content)
    overlay._div_bar.setObjectName("quicklook_div_bar")
    outer.addWidget(overlay._div_bar)
    # bottom bar
    bar = QWidget(overlay._content)
    bar.setObjectName("quicklook_bottom_bar")
    bar_lay = QHBoxLayout(bar)
    bar_lay.setContentsMargins(0, scaled_px(4), 0, 0)
    bar_lay.setSpacing(scaled_px(8))
    dark_bottom = _is_dark_theme()
    # NOTE: old fallbacks were dark-only (#0096FF, #D93025, #e8b64c) — now light/dark chains.
    accent = _token_color("accent", "#0078D4" if not dark_bottom else "#0096FF")
    danger = _token_color("gallery.status.danger", "#c0392b" if not dark_bottom else "#d64545")
    warning = _token_color("gallery.status.warn", "#b77900" if not dark_bottom else "#d9a441")
    overlay._compare_btn = Button(text="Compare →", variant="surface", parent=bar)
    overlay._compare_btn.setObjectName("quicklook_compare")
    try:
        if accent is not None:
            overlay._compare_btn.set_background_color(accent)
            _set_colored_text(overlay._compare_btn, "Compare →", accent)
    except Exception:
        pass
    overlay._compare_btn.clicked.connect(overlay._on_compare)
    bar_lay.addWidget(overlay._compare_btn)
    overlay._multi_btn = Button(text="Add to Multi Compare", variant="surface", parent=bar)
    overlay._multi_btn.setObjectName("quicklook_multi")
    overlay._multi_btn.clicked.connect(overlay._on_multi)
    bar_lay.addWidget(overlay._multi_btn)
    overlay._reject_btn = Button(text="✕ Reject", variant="surface", parent=bar)
    overlay._reject_btn.setObjectName("quicklook_reject")
    overlay._reject_text_color = danger
    try:
        if danger is not None:
            overlay._reject_btn.set_border_color(danger)
            _set_colored_text(overlay._reject_btn, "✕ Reject", danger)
    except Exception:
        pass
    overlay._reject_btn.clicked.connect(overlay._on_reject)
    bar_lay.addWidget(overlay._reject_btn)
    overlay._set_source_btn = Button(text="Set as source", variant="surface", parent=bar)
    overlay._set_source_btn.setObjectName("quicklook_set_source")
    try:
        if warning is not None:
            overlay._set_source_btn.set_border_color(warning)
            _set_colored_text(overlay._set_source_btn, "Set as source", warning)
    except Exception:
        pass
    overlay._set_source_btn.clicked.connect(overlay._on_set_source)
    bar_lay.addWidget(overlay._set_source_btn)
    bar_lay.addStretch(1)
    # W4 item 4: the hint sits at the right end of the button bar row
    # (svg:198, right-aligned), out of the left column.
    # W11 pinned policy: Esc no longer closes (X is the only close path).
    overlay._hint_label = _make_label("X closes · ←→ walk series", parent=bar, pixel_size=10, pt=10)
    overlay._hint_label.setObjectName("quicklook_hint")
    bar_lay.addWidget(overlay._hint_label)
    outer.addWidget(bar)
    overlay.add_widget(overlay._content, slot=None)
    # W8: bottom-right drag handle — painter-painted, absolute child of the
    # card plate, pinned by reposition_grip (Resize filter / resizeEvent).
    overlay._resize_grip = _ResizeGrip(overlay, overlay._content)
    reposition_grip(overlay)
    try:
        overlay._resize_grip.raise_()
    except Exception:
        pass
    overlay._strip_buttons: list = []
    overlay._metric_rows: list = []
    overlay._artifact_rows: list = []
    overlay._strip_caption_labels: list = []


# -- populate helpers -------------------------------------------------------

def populate_preview(overlay, item) -> None:
    # W-B: stash the unscaled source in ``overlay._preview_full`` so
    # ``_rescale_preview_to_host`` can re-derive the shown pixmap at the
    # live label size on every card resize (preview stretches with aspect,
    # export-window idiom). The initial shown pixmap keeps the old size.
    try:
        from sli_ui_toolkit.managers import scaled_px
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap
        try:
            overlay._preview_full = None
        except Exception:
            pass
        try:
            full = QPixmap(str(getattr(item, "path", "")))
            if full is not None and not full.isNull():
                try:
                    overlay._preview_full = full
                except Exception:
                    pass
        except Exception:
            pass
        if getattr(overlay, "_preview_full", None) is None:
            try:
                thumb = getattr(item, "thumbnail", None)
                if thumb is not None and not thumb.isNull():
                    overlay._preview_full = thumb
            except Exception:
                pass
        pm = _load_preview_pixmap(Path(getattr(item, "path", "")), scaled_px(640), scaled_px(456))
        if pm is not None and not pm.isNull():
            overlay._preview_label.setPixmap(pm)
        else:
            thumb = getattr(item, "thumbnail", None)
            if thumb is not None and not thumb.isNull():
                overlay._preview_label.setPixmap(thumb.scaled(scaled_px(320), scaled_px(260), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                overlay._preview_label.setText("No preview")
                overlay._preview_label.setPixmap(QPixmap())
        # Settle the initial pixmap at the live label size when populated
        # after layout (keeps the old 640×456 pixels pre-layout).
        try:
            _rescale_preview_to_host(overlay)
        except Exception:
            pass
    except Exception:
        pass


def populate_source_inset(overlay, item, is_fidelity: bool) -> None:
    try:
        overlay._source_inset_host.setVisible(bool(is_fidelity))
        if is_fidelity:
            from tabs.image_gallery.ui.quick_look.source_inset import reposition_source_inset
            reposition_source_inset(overlay)
    except Exception:
        pass
    if not is_fidelity:
        return
    try:
        from sli_ui_toolkit.managers import scaled_px
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap
        src = overlay._source_path
        src_item = None
        owner = overlay._owner
        try:
            items = list(getattr(getattr(owner, "state", None), "items", []) or []) if owner is not None else []
            if src is not None:
                for it2 in items:
                    if Path(getattr(it2, "path", "")) == Path(src):
                        src_item = it2
                        break
        except Exception:
            pass
        pix = None
        if src_item is not None:
            pix = _thumb_pixmap(src_item, scaled_px(150))
        elif src is not None:
            try:
                pm2 = QPixmap(str(src))
                if not pm2.isNull():
                    pix = pm2.scaled(scaled_px(150), scaled_px(84), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            except Exception:
                pass
        if pix is not None and not pix.isNull():
            overlay._source_inset_pix.setPixmap(pix)
        else:
            overlay._source_inset_pix.setText("—")
        src_name = Path(src).name if src is not None else "source"
        caption = f"SOURCE · {src_name}"
        dims = _source_dimensions(src_item, src)
        if dims is not None:
            caption += f" · {dims[0]}×{dims[1]}"
        overlay._source_inset_label.setText(caption)
    except Exception:
        pass


def populate_crop(overlay, item, is_fidelity: bool = False) -> None:
    """Sharpness-crop inset — non-fidelity modes only.

    S4 v2 LIGHT is fidelity mode and draws no ``SHARPNESS CROP`` inset
    (camera/batch modes keep it). Hidden in fidelity, shown otherwise.
    """
    try:
        overlay._crop_host.setVisible(not bool(is_fidelity))
    except Exception:
        pass
    if is_fidelity:
        return
    try:
        from sli_ui_toolkit.managers import scaled_px
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap
        pm_full = QPixmap(str(getattr(item, "path", "")))
        if not pm_full.isNull():
            w = pm_full.width()
            h = pm_full.height()
            cw = max(1, w // 3)
            ch = max(1, h // 3)
            x = max(0, (w - cw) // 2)
            y = max(0, (h - ch) // 2)
            crop = pm_full.copy(x, y, cw, ch)
            crop_scaled = crop.scaled(scaled_px(150), scaled_px(84), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            overlay._crop_pix.setPixmap(crop_scaled)
        else:
            thumb = getattr(item, "thumbnail", None)
            if thumb is not None and not thumb.isNull():
                overlay._crop_pix.setPixmap(thumb.scaled(scaled_px(150), scaled_px(84), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
            else:
                overlay._crop_pix.setText("—")
    except Exception:
        pass


def populate_filename_meta(overlay, item, is_fidelity: bool) -> None:
    try:
        overlay._filename_label.setText(str(getattr(item, "name", Path(getattr(item, "path", "")).name)))
    except Exception:
        pass
    try:
        from PySide6.QtGui import QPixmap
        # S4 mockup meta order: dims · format · size (+ upscale suffix).
        dims_txt: str | None = None
        fmt_txt: str | None = None
        size_txt: str | None = None
        upscale_n = None
        p = Path(getattr(item, "path", ""))
        try:
            if p.is_file():
                sz = p.stat().st_size
                if sz < 1024:
                    size_txt = f"{sz} B"
                elif sz < 1024 * 1024:
                    size_txt = f"{sz/1024:.1f} KB"
                else:
                    size_txt = f"{sz/1024/1024:.1f} MB"
                fmt_txt = p.suffix.lstrip(".").upper() or "IMG"
            pm_meta = QPixmap(str(p))
            if not pm_meta.isNull():
                dims_txt = f"{pm_meta.width()} × {pm_meta.height()}"
        except Exception:
            pass
        metrics = getattr(item, "metrics", None) or {}
        if isinstance(metrics, dict) and metrics.get("upscale_factor"):
            try:
                upscale_n = int(metrics.get("upscale_factor"))
            except Exception:
                upscale_n = None
        meta_parts = [t for t in (dims_txt, fmt_txt, size_txt) if t]
        if is_fidelity and overlay._source_path is not None:
            if upscale_n is not None and upscale_n > 1:
                meta_parts.append(f"upscale ×{upscale_n} from source")
            elif upscale_n == 1:
                # W4 item 7: explicit same-size text when truly ×1.
                # W5: factor 1 also covers item-smaller-than-source (the
                # max(1, ...) clamp) — only claim "same size" when the
                # item is not genuinely smaller; else say so honestly.
                # Falls back to the old text whenever either side's dims
                # are unknown (never a fabricated comparison).
                if _item_smaller_than_source(overlay, dims_txt):
                    meta_parts.append("smaller than source")
                else:
                    meta_parts.append("same size as source")
            else:
                meta_parts.append("upscale from source")
        elif upscale_n is not None and upscale_n > 1:
            meta_parts.append(f"upscale ×{upscale_n}")
        overlay._meta_label.setText(" · ".join(meta_parts))
    except Exception:
        pass


def _item_smaller_than_source(overlay, dims_txt: str | None) -> bool:
    """True only when the item's long side is known-smaller than the source's.

    Compares the already-formatted item dims (``"W × H"``) against
    ``_source_dimensions`` (metrics first, QPixmap fallback). False on any
    unknown side — callers keep the neutral text instead of guessing.
    """
    try:
        if not dims_txt or "×" not in dims_txt:
            return False
        iw, ih = (int(p.strip()) for p in dims_txt.split("×"))
        src = getattr(overlay, "_source_path", None)
        src_item = None
        try:
            owner = getattr(overlay, "_owner", None)
            items = list(getattr(getattr(owner, "state", None), "items", []) or [])
            if src is not None:
                for it2 in items:
                    if Path(getattr(it2, "path", "")) == Path(src):
                        src_item = it2
                        break
        except Exception:
            pass
        sdims = _source_dimensions(src_item, src)
        if sdims is None:
            return False
        return max(iw, ih) < max(sdims[0], sdims[1])
    except Exception:
        return False


def populate_report_header(overlay, is_fidelity: bool, mode_str: str) -> None:
    try:
        if is_fidelity:
            overlay._report_title.setText("Fidelity report")
            src_name = Path(overlay._source_path).name if overlay._source_path is not None else "source"
            overlay._report_sub.setText(f"vs SOURCE {src_name} · shared/analysis engine")
        else:
            if "CAMERA" in mode_str:
                overlay._report_title.setText("Camera report")
                overlay._report_sub.setText("sharpness / exposure profile · local metrics")
            else:
                overlay._report_title.setText("Batch report")
                overlay._report_sub.setText("distance to centroid · artifact flags")
    except Exception:
        pass


def populate_series_header(overlay) -> None:
    """S4 mockup series context: ``Series 1 · <hub>`` + fidelity subline."""
    try:
        items = list(overlay._series_items or [])
        n = len(items)
        cur = getattr(overlay, "_current_item", None)
        # 1-based cluster index among the owner's series (display only —
        # triage ownership stays in use_cases/wave A, never duplicated here).
        idx = 1
        try:
            owner = getattr(overlay, "_owner", None)
            series_raw = getattr(getattr(owner, "state", None), "series", None)
            if series_raw:
                clusters: list[list] = []
                for entry in list(series_raw):
                    if hasattr(entry, "members"):
                        clusters.append(list(getattr(entry, "members") or []))
                    elif isinstance(entry, (list, tuple)):
                        clusters.append(list(entry))
                if clusters and cur is not None:
                    try:
                        cur_path = Path(getattr(cur, "path", ""))
                        for i, cl in enumerate(clusters):
                            if any(Path(getattr(m, "path", "")) == cur_path for m in cl):
                                idx = i + 1
                                break
                    except Exception:
                        pass
        except Exception:
            pass
        # Hub label: source stem when a source is set, else the first member
        # stem of the viewing cluster (a real member, never invented).
        hub = ""
        try:
            src = getattr(overlay, "_source_path", None)
            if src is not None:
                hub = Path(src).stem
            elif items:
                hub = Path(getattr(items[0], "path", "")).stem
        except Exception:
            pass
        if n > 1:
            overlay._series_header.setText(f"Series {idx} · {hub}" if hub else f"Series {idx}")
        else:
            overlay._series_header.setText("Single")
        rejected_cnt = sum(1 for m in items if bool(getattr(m, "rejected", False)))
        pending = sum(1 for m in items if bool(getattr(m, "vlm_tie_pending", False)))
        if n > 1:
            try:
                is_fidelity = bool(getattr(overlay, "_source_path", None) is not None)
            except Exception:
                is_fidelity = False
            if is_fidelity:
                sub = f"{n} upscales of one source · rank by fidelity · {rejected_cnt} rejected"
            else:
                sub = f"rank by fidelity · {rejected_cnt} rejected"
            if pending:
                sub += f" · {pending} tie-break pending"
            overlay._series_sub.setText(sub)
        else:
            overlay._series_sub.setText("ungrouped")
    except Exception:
        pass


def local_brief_fallback(item, series_items) -> str:
    """Deterministic ``vs #N`` brief from local metrics when VLM is absent.

    Same shape as the mockup teaser (``vs #2: …``) but every number comes
    from ``item.metrics`` — no invented detail, no region claims. Returns ""
    when there is nothing comparative to say (caller hides the label).
    """
    try:
        mates = [m for m in (series_items or []) if m is not item]
        if not mates:
            return ""

        def _rank_of(m, default):
            r = getattr(m, "rank", None) or getattr(m, "crown_rank", None)
            try:
                return int(r) if r is not None else default
            except Exception:
                return default

        viewing_rank = _rank_of(item, 0)
        other = None
        other_rank = None
        for m in mates:
            r = getattr(m, "rank", None) or getattr(m, "crown_rank", None)
            try:
                r = int(r) if r is not None else None
            except Exception:
                r = None
            if r is not None and r > viewing_rank and (other_rank is None or r < other_rank):
                other, other_rank = m, r
        if other is None:
            # No worse-ranked mate: fall back to the best-ranked other.
            best = None
            for m in mates:
                r = getattr(m, "rank", None) or getattr(m, "crown_rank", None)
                try:
                    r = int(r) if r is not None else None
                except Exception:
                    r = None
                if r is not None and (best is None or r < best[0]):
                    best = (r, m)
            if best is not None:
                other_rank, other = best
            else:
                other, other_rank = mates[0], _rank_of(mates[0], 2)

        def _f(metrics, *keys):
            for k in keys:
                v = metrics.get(k)
                if v is not None:
                    try:
                        return float(v)
                    except Exception:
                        continue
            return None

        ma = getattr(item, "metrics", None) or {}
        mb = getattr(other, "metrics", None) or {}
        if not isinstance(ma, dict):
            ma = {}
        if not isinstance(mb, dict):
            mb = {}
        ssim_a, ssim_b = _f(ma, "ssim"), _f(mb, "ssim")
        hf_a = _f(ma, "hf_ratio", "detail_gain")
        hf_b = _f(mb, "hf_ratio", "detail_gain")
        if ssim_a is None and ssim_b is None and hf_a is None and hf_b is None:
            return ""
        clauses: list[str] = []
        if ssim_a is not None and ssim_b is not None:
            clauses.append(f"SSIM {ssim_a:.2f} vs {ssim_b:.2f}")
        elif ssim_a is not None:
            clauses.append(f"SSIM {ssim_a:.2f}")
        if hf_a is not None and hf_b is not None:
            clauses.append(f"detail {int(hf_a * 100):+d}% vs {int(hf_b * 100):+d}%")
        elif hf_a is not None:
            clauses.append(f"detail {int(hf_a * 100):+d}%")
        # Banding note for the *other* item only, severity-only (no regions).
        banding = None
        try:
            raw = getattr(other, "artifacts", None)
            if isinstance(raw, dict):
                from tabs.image_gallery.models import Artifact as _Artifact

                sev = raw.get(_Artifact.BANDING, raw.get("banding"))
                banding = (sev.value if hasattr(sev, "value") else sev)
            if banding is None and isinstance(mb, dict):
                artm = mb.get("artifacts")
                if isinstance(artm, dict):
                    banding = artm.get("banding", artm.get("BANDING"))
                    banding = banding.value if hasattr(banding, "value") else banding
        except Exception:
            banding = None
        try:
            banding = str(banding).lower() if banding is not None else None
        except Exception:
            banding = None
        tail = ""
        if banding in ("mild", "flagged"):
            tail = f"#{other_rank} shows banding" + (" (flagged)" if banding == "flagged" else "")
        head = " · ".join(clauses)
        text = f"vs #{other_rank}: {head}" if head else f"vs #{other_rank}"
        if tail:
            text += f"; {tail}"
        return text
    except Exception:
        return ""


def populate_brief(overlay, item) -> None:
    try:
        brief = ""
        vlm_brief = getattr(item, "vlm_brief", None)
        status = getattr(item, "vlm_brief_status", "none")
        if vlm_brief is not None:
            try:
                summary = getattr(vlm_brief, "summary", "") or ""
                diffs = getattr(vlm_brief, "differences", ()) or ()
                if summary:
                    brief = summary
                    if diffs:
                        brief += " — " + "; ".join(list(diffs)[:2])
                else:
                    brief = "; ".join(list(diffs)[:2]) if diffs else ""
                if status == "pending":
                    brief = "AI brief…"
            except Exception:
                brief = ""
            if not brief and status == "pending":
                brief = "AI brief…"
        if not brief:
            # Deterministic local fallback (no VLM): vs-#N from metrics.
            try:
                brief = local_brief_fallback(item, getattr(overlay, "_series_items", []))
            except Exception:
                brief = ""
        if brief:
            overlay._brief_label.setText(brief)
            overlay._brief_label.setVisible(True)
        else:
            overlay._brief_label.setText("")
            overlay._brief_label.setVisible(False)
    except Exception:
        try:
            overlay._brief_label.setVisible(False)
        except Exception:
            pass

