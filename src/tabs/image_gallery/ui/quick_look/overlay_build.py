"""Quick look overlay chrome + construction — plain functions (no owner state).
Audit-Meta: pattern=thin-owner-target size=exempt reason="one overlay-build concern: painted chrome widgets + build_overlay_ui share one card layout"

Painted widgets (``_AccentPillHost`` / ``_CardPlate`` / ``_RuleWidget`` —
painter pipeline, no QSS) plus ``build_overlay_ui``.
Extracted verbatim from ``helpers.py`` per CODE_PATTERNS.md thin owner + ui/.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from tabs.image_gallery.ui.quick_look.labels_theme import (
    _apply_point_size,
    _is_dark_theme,
    _make_label,
    _set_colored_text,
    _token_color,
)
from tabs.image_gallery.ui.quick_look.resize import (
    reposition_grip,
)


class _AccentPillHost(QWidget):
    """Pill backdrop behind small header chips (explicit paint, no palette).

    ``fill="accent"`` (default): accent-tinted translucent pill (mode chip).
    ``fill="white"``: opaque white pill for dark-on-light chips
    (SHARPNESS CROP) — white in both themes by design; a future theme may
    define the ``gallery.pill.background`` token to take over.
    """

    def __init__(self, parent=None, *, fill: str = "accent") -> None:
        super().__init__(parent)
        self._fill = fill
        self._bg = self._resolve_bg(fill)
        self._border = self._resolve_border(fill)
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    @staticmethod
    def _resolve_bg(fill: str = "accent") -> QColor:
        if fill == "white":
            col = _token_color("gallery.pill.background", "#ffffff")
            if col is None:
                col = QColor(Qt.GlobalColor.white)
            try:
                col.setAlpha(255)
            except Exception:
                pass
            return col
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
            self._bg = self._resolve_bg(self._fill)
        except Exception:
            pass
        try:
            self._border = self._resolve_border(self._fill)
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    @staticmethod
    def _resolve_border(fill: str = "accent"):
        """Hairline for white pills: opaque white is invisible on the light
        card, so white capsules get a 1px separator border (both themes).
        Accent pills already read via their tint — no border."""
        if fill != "white":
            return None
        try:
            return _token_color("separator.color", "#e5e5e5")
        except Exception:
            return None

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
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(self._bg)
                p.drawRoundedRect(self.rect(), scaled_px(8), scaled_px(8))
                try:
                    border = getattr(self, "_border", None)
                except Exception:
                    border = None
                if border is not None:
                    half = max(1.0, scaled_px(1)) / 2.0
                    p.setPen(QPen(border, max(1.0, scaled_px(1))))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRoundedRect(QRectF(self.rect()).adjusted(half, half, -half, -half), scaled_px(8), scaled_px(8))
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
                    # Border fully inside the widget rect (not straddling):
                    # the outer half of a straddled 1px pen is clipped and
                    # its AA fade makes the visible line sit ~1px off the
                    # hit-band boundary. Experimental, revert if worse.
                    p.drawRoundedRect(r.adjusted(1, 1, -1, -1), rx, rx)
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

        # 1px rule + 7px breathing room (was 9): the readability sweep
        # (11px labels) leaves the right column exactly 1px over the
        # viewport — this absorbs it without touching content metrics.
        self.setFixedHeight(scaled_px(8))
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


# NOTE: the W8 corner _ResizeGrip was removed — the full-border (W9) and
# outer-ring (W10) drags remain the resize paths. ``overlay._resize_grip``
# stays None; ``reposition_grip`` keeps the card re-layout entry.


# -- UI construction helpers (thin owner delegation) -------------------------


def build_overlay_ui(overlay) -> None:
    """Construct QuickLookOverlay layout (thin owner delegator).

    Reads/writes overlay attributes directly per CODE_PATTERNS plain function.
    No QSS, painter pipeline only, lazy imports for theming.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QFrame, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

    from sli_ui_toolkit.managers import scaled_px
    from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow, CustomSplit

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
    # W8: NO maximum — the user drag-resizes via the card border / ring.
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
    # NOTE: no bold anywhere in Quick Look — all type is regular weight.
    # (If bold ever returns: pass it through the _make_label constructor,
    # never setBold after — setBold re-runs Label's pixel-based _apply_style
    # and would revert the mockup-pt font.)
    # Filename caption lives here, centered, where the mode pill used to be
    # (the report title already carries the mode: Fidelity/Camera/Batch).
    # S4 mockup meta order: name · dims · format · size (populated by
    # populate_filename_meta). Both labels keep natural widths so the pair
    # centers as one line; the name elides only when genuinely squeezed
    # (Preferred, not Ignored — Ignored parks labels at minimum width and
    # the caption collapses to "114…"). The leading spacer balances the
    # trailing close button (28 + 8 spacing) so the group is truly centered.
    overlay._filename_label = _make_label("", parent=overlay._content, pixel_size=14, pt=14, elide=True, minimum_width=40)
    overlay._filename_label.setObjectName("quicklook_filename")
    try:
        overlay._filename_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    except Exception:
        pass
    try:
        overlay._filename_label.setSizePolicy(QSizePolicy.Policy.Preferred, overlay._filename_label.sizePolicy().verticalPolicy())
    except Exception:
        pass
    overlay._meta_label = _make_label("", parent=overlay._content, pixel_size=11, pt=11.5, minimum_width=40)
    overlay._meta_label.setObjectName("quicklook_meta")
    try:
        overlay._meta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    except Exception:
        pass
    chip_row.addSpacing(36)
    chip_row.addStretch(1)
    chip_row.addWidget(overlay._filename_label)
    chip_row.addWidget(overlay._meta_label)
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
    overlay._prev_btn = Button(rows=[ButtonRow(text="‹", size=QUICK_LOOK_NAV_GLYPH_PT, ratio=1.0, color=_nav_glyph)], variant="surface", size=(36, 36), corner_radius=18, parent=overlay, defer_click="ripple")
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
    # Label Resize → preview refit (quick_look.eventFilter): layout passes
    # settle the label without a card resize; the size cache keeps it cheap.
    try:
        overlay._preview_label.installEventFilter(overlay)
    except Exception:
        pass
    preview_host_lay.addWidget(overlay._preview_label, 1)
    # Canvas preview slot: overlay._preview_canvas lives here when the GPU
    # path is available (preview.populate_preview creates it lazily; QLabel
    # fallback otherwise). Placeholders keep the slot shape explicit; the
    # label stays the default visible child.
    overlay._preview_canvas = None
    overlay._preview_store = None
    # Source inset, SHARPNESS-CROP parity: an absolute block bottom-left
    # OVER the preview image (not in the flow) — title pill above the
    # pixmap, like the crop block.
    overlay._source_inset_host = QWidget(overlay._preview_label)
    overlay._source_inset_host.setObjectName("quicklook_source_inset_host")
    src_lay = QVBoxLayout(overlay._source_inset_host)
    src_lay.setContentsMargins(0, 0, 0, 0)
    src_lay.setSpacing(scaled_px(2))
    overlay._source_inset_title = _make_label("SOURCE", parent=overlay._source_inset_host, pixel_size=11, pt=11.5, elide=True)
    overlay._source_inset_title.setObjectName("quicklook_source_inset_title")
    try:
        glyph = _token_color("gallery.nav.glyph", "#23262b")
        if glyph is not None:
            overlay._source_inset_title.setTextColor(glyph)
    except Exception:
        pass
    try:
        src_pill = _AccentPillHost(overlay._source_inset_host, fill="white")
        src_pill.setObjectName("quicklook_source_inset_title_pill")
        src_pill_lay = QHBoxLayout(src_pill)
        src_pill_lay.setContentsMargins(scaled_px(10), scaled_px(2), scaled_px(10), scaled_px(2))
        src_pill_lay.setSpacing(0)
        overlay._source_inset_title.setParent(src_pill)
        src_pill_lay.addWidget(overlay._source_inset_title)
        overlay._source_inset_title_pill = src_pill
        src_lay.addWidget(src_pill, 0, Qt.AlignmentFlag.AlignLeft)
        # Reparenting resets the explicit font — re-assert the pt size after.
        _apply_point_size(overlay._source_inset_title, 11.5)
    except Exception:
        try:
            src_lay.addWidget(overlay._source_inset_title)
        except Exception:
            pass
    # Compat: populate + tests read the caption through _source_inset_label.
    overlay._source_inset_label = overlay._source_inset_title
    overlay._source_inset_caption = None
    # Inset thumbs are inert card Buttons (gallery-card idiom): surface bg
    # region with 4px padding around the cover pixmap, rounded + bordered
    # by the painter pipeline — contrast without clickability (no
    # callbacks, no hover overlays via bg_locked, arrow cursor).
    from PySide6.QtCore import QRectF as _QRectF

    _inset_pad = 4

    def _inset_bg_rect(r):
        return _QRectF(0, 0, r.width(), r.height())

    def _inset_thumb_rect(r):
        return _QRectF(
            _inset_pad, _inset_pad,
            r.width() - _inset_pad * 2, r.height() - _inset_pad * 2,
        )

    def _make_inset_thumb_button(parent):
        btn = Button(
            text="",
            variant="surface",
            size=(scaled_px(150) + _inset_pad * 2, scaled_px(84) + _inset_pad * 2),
            parent=parent,
            regions=[
                ButtonRegion(
                    id="bg",
                    group="card",
                    corner_radii=(8, 8, 8, 8),
                    hover_color=QColor(0, 0, 0, 0),
                    bg_locked=True,
                ),
                ButtonRegion(
                    id="thumb",
                    pixmap=None,
                    image_fill="cover",
                    group="card",
                    corner_radii=(5, 5, 5, 5),
                    hover_color=QColor(0, 0, 0, 0),
                    bg_locked=True,
                ),
            ],
            split=CustomSplit(rect_fns=[_inset_bg_rect, _inset_thumb_rect]),
            corner_radius=8,
        )
        try:
            btn.setCursor(Qt.CursorShape.ArrowCursor)
        except Exception:
            pass
        return btn

    overlay._source_inset_pix = _make_inset_thumb_button(overlay._source_inset_host)
    overlay._source_inset_pix.setObjectName("quicklook_source_inset_pix")
    src_lay.addWidget(overlay._source_inset_pix)
    overlay._source_inset_host.raise_()
    overlay._source_inset_host.hide()
    # Crop block: absolute bottom-left over the preview, like the source
    # inset (not in the flow).
    overlay._crop_host = QWidget(overlay._preview_label)
    overlay._crop_host.setObjectName("quicklook_crop_host")
    crop_lay = QVBoxLayout(overlay._crop_host)
    crop_lay.setContentsMargins(0, 0, 0, 0)
    crop_lay.setSpacing(scaled_px(2))
    overlay._crop_title = _make_label("SHARPNESS CROP", parent=overlay._crop_host, pixel_size=11, pt=11.5)
    overlay._crop_title.setObjectName("quicklook_crop_title")
    # Capsule backing behind the title — opaque white pill (dark glyph text
    # for contrast in both themes), hugging the label width.
    try:
        glyph = _token_color("gallery.nav.glyph", "#23262b")
        if glyph is not None:
            overlay._crop_title.setTextColor(glyph)
    except Exception:
        pass
    try:
        crop_pill = _AccentPillHost(overlay._crop_host, fill="white")
        crop_pill.setObjectName("quicklook_crop_title_pill")
        crop_pill_lay = QHBoxLayout(crop_pill)
        crop_pill_lay.setContentsMargins(scaled_px(10), scaled_px(2), scaled_px(10), scaled_px(2))
        crop_pill_lay.setSpacing(0)
        overlay._crop_title.setParent(crop_pill)
        crop_pill_lay.addWidget(overlay._crop_title)
        overlay._crop_title_pill = crop_pill
        crop_lay.addWidget(crop_pill, 0, Qt.AlignmentFlag.AlignLeft)
        # Reparenting resets the explicit font — re-assert the pt size after.
        _apply_point_size(overlay._crop_title, 11.5)
    except Exception:
        try:
            crop_lay.addWidget(overlay._crop_title)
        except Exception:
            pass
    overlay._crop_pix = _make_inset_thumb_button(overlay._crop_host)
    overlay._crop_pix.setObjectName("quicklook_crop_pix")
    crop_lay.addWidget(overlay._crop_pix)
    overlay._crop_host.raise_()
    overlay._crop_host.hide()
    preview_row.addWidget(preview_host, 1)
    overlay._next_btn = Button(rows=[ButtonRow(text="›", size=QUICK_LOOK_NAV_GLYPH_PT, ratio=1.0, color=_nav_glyph)], variant="surface", size=(36, 36), corner_radius=18, parent=overlay, defer_click="ripple")
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
    overlay._report_title = _make_label("Fidelity report", parent=right_host, pixel_size=13, pt=13)
    overlay._report_title.setObjectName("quicklook_report_title")
    right_lay.addWidget(overlay._report_title)
    overlay._report_sub = _make_label("", parent=right_host, pixel_size=11, pt=11.0, elide=True, minimum_width=40)
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
    overlay._series_header = _make_label("Series", parent=right_host, pixel_size=13, pt=13, elide=True, minimum_width=40)
    overlay._series_header.setObjectName("quicklook_series_header")
    right_lay.addWidget(overlay._series_header)
    overlay._series_sub = _make_label("", parent=right_host, pixel_size=11, pt=11.0, elide=True, minimum_width=40)
    overlay._series_sub.setObjectName("quicklook_series_sub")
    right_lay.addWidget(overlay._series_sub)
    # Strip lives in its own horizontal scroller: 4×66px thumbs span 294px
    # and fit the 296px column, but 5+ thumbs (6×66+5×10=446px) forced the
    # whole right_host to 446px while the viewport is ~329px — every row
    # painted ~117px past the card edge. OverlayScrollArea (toolkit,
    # horizontal overlay bar + auto-hide included) confines the overflow
    # to the strip so the column never exceeds the viewport.
    from sli_ui_toolkit.widgets import OverlayScrollArea

    overlay._strip_scroll = OverlayScrollArea(
        right_host, widget_resizable=False, corner_radius=0
    )
    overlay._strip_scroll.setObjectName("quicklook_strip_scroll")
    try:
        # Ignored: the 446px strip content must never widen the column —
        # same trick as the elided labels (sizeHint ignored, minimum floors).
        overlay._strip_scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        overlay._strip_scroll.setMinimumWidth(scaled_px(120))
        overlay._strip_scroll.setMinimumHeight(scaled_px(48))
    except Exception:
        pass
    overlay._strip_host = QWidget(overlay._strip_scroll)
    overlay._strip_host.setObjectName("quicklook_strip_host")
    overlay._strip_layout = QHBoxLayout(overlay._strip_host)
    overlay._strip_layout.setContentsMargins(0, 0, 0, 0)
    overlay._strip_layout.setSpacing(scaled_px(6))
    overlay._strip_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
    try:
        overlay._strip_scroll.setWidget(overlay._strip_host)
    except Exception:
        pass
    right_lay.addWidget(overlay._strip_scroll)
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
    # Heavy bar actions run after the press ripple finishes (defer_click):
    # _populate / carry flows block the GUI thread for hundreds of ms, and
    # a synchronous clicked would freeze mid-ripple with no press feedback.
    overlay._compare_btn = Button(text="Compare →", variant="surface", parent=bar, defer_click="ripple")
    overlay._compare_btn.setObjectName("quicklook_compare")
    try:
        if accent is not None:
            overlay._compare_btn.set_background_color(accent)
            _set_colored_text(overlay._compare_btn, "Compare →", accent)
    except Exception:
        pass
    overlay._compare_btn.clicked.connect(overlay._on_compare)
    bar_lay.addWidget(overlay._compare_btn)
    overlay._multi_btn = Button(text="Add to Multi Compare", variant="surface", parent=bar, defer_click="ripple")
    overlay._multi_btn.setObjectName("quicklook_multi")
    overlay._multi_btn.clicked.connect(overlay._on_multi)
    bar_lay.addWidget(overlay._multi_btn)
    overlay._reject_btn = Button(text="✕ Reject", variant="surface", parent=bar, defer_click="ripple")
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
    overlay._set_source_btn = Button(text="Set as source", variant="surface", parent=bar, defer_click="ripple")
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
    outer.addWidget(bar)
    overlay.add_widget(overlay._content, slot=None)
    # D1: interactive buttons keep an explicit arrow cursor so a stale plate
    # resize cursor never leaks onto them (they inherit otherwise).
    try:
        from PySide6.QtCore import Qt as _Qt

        for _btn_attr in (
            "_compare_btn",
            "_multi_btn",
            "_reject_btn",
            "_set_source_btn",
            "_prev_btn",
            "_next_btn",
            "_close_btn",
        ):
            try:
                _btn = getattr(overlay, _btn_attr, None)
                if _btn is not None:
                    _btn.setCursor(_Qt.CursorShape.ArrowCursor)
            except Exception:
                pass
    except Exception:
        pass
    # No corner grip: border (W9) + outer ring (W10) are the resize paths.
    # The attribute stays None so grip-aware helpers no-op cleanly.
    overlay._resize_grip = None
    reposition_grip(overlay)
    overlay._strip_buttons: list = []
    overlay._metric_rows: list = []
    overlay._artifact_rows: list = []
    overlay._strip_caption_labels: list = []
