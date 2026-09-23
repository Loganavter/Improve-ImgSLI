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
    """Pin prev/next circles half-outside the card edges (W4 item 6).

    Absolute children of the card plate (like ``reposition_source_inset``):
    each circle's center sits on the card's left/right edge, vertically
    centered on the preview band. Called from ``resizeEvent`` and after
    ``_populate`` (best effort before first show).
    """
    try:
        content = getattr(overlay, "_content", None)
        host = getattr(overlay, "_preview_host", None)
        prev = getattr(overlay, "_prev_btn", None)
        nxt = getattr(overlay, "_next_btn", None)
        if content is None or host is None or prev is None or nxt is None:
            return
        host_pos = host.mapTo(content, QPoint(0, 0))
        cy = host_pos.y() + host.height() // 2
        cw = content.width()
        for btn, left_edge in ((prev, True), (nxt, False)):
            try:
                bw = btn.width() or btn.sizeHint().width()
                bh = btn.height() or btn.sizeHint().height()
            except Exception:
                continue
            x = -bw // 2 if left_edge else cw - bw // 2
            btn.move(x, cy - bh // 2)
            try:
                btn.raise_()
            except Exception:
                pass
    except Exception:
        pass


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
    # S4 mockup panel is 1040x620 — floor, not a suggestion.
    overlay._content.setMinimumSize(scaled_px(1040), scaled_px(620))
    try:
        overlay._content.setMaximumSize(scaled_px(1040), scaled_px(620))
    except Exception:
        pass
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
    left_lay = QVBoxLayout(left)
    left_lay.setContentsMargins(0, 0, 0, 0)
    left_lay.setSpacing(scaled_px(8))
    preview_row = QHBoxLayout()
    preview_row.setContentsMargins(0, 0, 0, 0)
    preview_row.setSpacing(scaled_px(6))
    preview_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
    # S4 v2 (svg:67-70): 36px circular prev/next overlapping the card edge
    # half-outside (W4 item 6) — absolute children of the card plate,
    # positioned by reposition_nav_buttons (like reposition_source_inset),
    # NOT layout items. Glyph via rows (rows-only buttons take setFixedSize
    # so 36x36 actually lands); round shape via corner_radius (design px,
    # scaled internally); no QSS anywhere on this path.
    # Glyph color is a fixed dark token (mockup #23262b); the border is set
    # explicitly so it survives the disabled state (W4 item 6).
    _nav_glyph = _token_color("gallery.nav.glyph", "#23262b")
    _nav_border = _token_color("gallery.card.border", "#e2e4e8")
    overlay._prev_btn = Button(rows=[ButtonRow(text="‹", size=18, color=_nav_glyph)], variant="surface", size=(36, 36), corner_radius=18, parent=overlay._content)
    overlay._prev_btn.setObjectName("quicklook_prev")
    try:
        if _nav_border is not None:
            overlay._prev_btn.set_border_color(_nav_border)
    except Exception:
        pass
    overlay._prev_btn.clicked.connect(lambda: overlay._walk(-1))
    preview_host = QWidget(left)
    preview_host.setObjectName("QuickLookPreviewHost")
    overlay._preview_host = preview_host
    preview_host_lay = QVBoxLayout(preview_host)
    preview_host_lay.setContentsMargins(0, 0, 0, 0)
    preview_host_lay.setSpacing(scaled_px(6))
    overlay._preview_label = QLabel(preview_host)
    overlay._preview_label.setObjectName("quicklook_preview")
    overlay._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    overlay._preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    overlay._preview_label.setMinimumSize(scaled_px(320), scaled_px(260))
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
    overlay._next_btn = Button(rows=[ButtonRow(text="›", size=18, color=_nav_glyph)], variant="surface", size=(36, 36), corner_radius=18, parent=overlay._content)
    overlay._next_btn.setObjectName("quicklook_next")
    try:
        if _nav_border is not None:
            overlay._next_btn.set_border_color(_nav_border)
    except Exception:
        pass
    overlay._next_btn.clicked.connect(lambda: overlay._walk(1))
    left_lay.addLayout(preview_row, 1)
    # W4 item 4: the Esc hint lives at the right end of the bottom button
    # bar (built below), not in the left column. Nothing added here.
    mid.addWidget(left, 2)
    right_scroll = QScrollArea(overlay._content)
    right_scroll.setObjectName("quicklook_right_scroll")
    # W5: the mockup's right column is a fixed 296px (svg x=816 w=296) —
    # the value/sub labels elide to it instead of stretching it into
    # h-scrollbars. mid-stretch still gives the left preview the rest.
    right_scroll.setFixedWidth(scaled_px(296))
    # W4 item 2: frameless — the scroll frame drew a bogus box around the
    # right column. No QSS (stock Qt widget, frame shape only).
    try:
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
    except Exception:
        pass
    right_scroll.setWidgetResizable(True)
    right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    right_host = QWidget(right_scroll)
    right_host.setObjectName("quicklook_right_host")
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
    overlay._metrics_host = QWidget(right_host)
    overlay._metrics_host.setObjectName("quicklook_metrics_host")
    overlay._metrics_layout = QVBoxLayout(overlay._metrics_host)
    overlay._metrics_layout.setContentsMargins(0, 0, 0, 0)
    overlay._metrics_layout.setSpacing(scaled_px(4))
    right_lay.addWidget(overlay._metrics_host)
    overlay._artifacts_host = QWidget(right_host)
    overlay._artifacts_host.setObjectName("quicklook_artifacts_host")
    overlay._artifacts_layout = QVBoxLayout(overlay._artifacts_host)
    overlay._artifacts_layout.setContentsMargins(0, 0, 0, 0)
    overlay._artifacts_layout.setSpacing(scaled_px(2))
    right_lay.addWidget(overlay._artifacts_host)
    # S4 mockup divider before the series context block (svg:462) — a
    # file-local 1px painted rule (W4 item 3); the toolkit Divider is a
    # button-region dataclass, not a widget.
    overlay._div_series = _RuleWidget(right_host)
    overlay._div_series.setObjectName("quicklook_div_series")
    right_lay.addWidget(overlay._div_series)
    overlay._series_header = _make_label("Series", parent=right_host, pixel_size=11, pt=13, bold=True)
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
    right_lay.addWidget(overlay._brief_label)
    right_scroll.setWidget(right_host)
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
    # W4 item 4: the Esc hint sits at the right end of the button bar row
    # (svg:198, right-aligned), out of the left column.
    overlay._hint_label = _make_label("Esc closes · ←→ walk series", parent=bar, pixel_size=10, pt=10)
    overlay._hint_label.setObjectName("quicklook_hint")
    bar_lay.addWidget(overlay._hint_label)
    outer.addWidget(bar)
    overlay.add_widget(overlay._content, slot=None)
    overlay._strip_buttons: list = []
    overlay._metric_rows: list = []
    overlay._artifact_rows: list = []
    overlay._strip_caption_labels: list = []


# -- populate helpers -------------------------------------------------------

def populate_preview(overlay, item) -> None:
    try:
        from sli_ui_toolkit.managers import scaled_px
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap
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

