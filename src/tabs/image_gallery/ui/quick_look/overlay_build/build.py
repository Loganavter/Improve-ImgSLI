"""Quick look overlay construction — ``build_overlay_ui`` (thin owner delegator).
Audit-Meta: pattern=thin-owner-target size=exempt reason="one overlay-build concern: the single Quick Look card layout assembled by build_overlay_ui (chrome widgets/icons live in the sibling widgets/icons modules)"

Constructs the QuickLookOverlay layout (card plate, preview + sidebar +
filmstrip + bottom bar) — reads/writes overlay attributes directly per
``CODE_PATTERNS.md`` plain function; no QSS, painter pipeline only, lazy
imports for theming.

Module → package (plan-gallery-split-2026-10-17, Part C2): moved here verbatim
from ``ui/quick_look/overlay_build.py`` — name and signature unchanged,
re-exported by the ``overlay_build`` package for importers and tests.
"""

from __future__ import annotations

from PySide6.QtGui import QColor

from tabs.image_gallery.ui.quick_look.labels_theme import (
    _apply_point_size,
    _is_dark_theme,
    _make_label,
    _token_color,
)
from tabs.image_gallery.ui.quick_look.resize import (
    reposition_grip,
)

from .icons import _danger_trash_icon
from .inset_frame import (
    SOURCE_INSET_FRAME_RADIUS,
    SOURCE_INSET_H,
    SOURCE_INSET_PAD,
    SOURCE_INSET_THUMB_RADIUS,
    SOURCE_INSET_W,
)
from .widgets import (
    _AccentPillHost,
    _CardPlate,
    _RuleWidget,
)


# W11: nav chevron glyph size (pt rows). The mockup chevron path spans
# ~18px in the 36px circle (svg prev/next); the text ‹ › at 18pt rendered
# small, so the rows size up to 24 — circles stay 36px, ring untouched.
QUICK_LOOK_NAV_GLYPH_PT = 24


# NOTE: the W8 corner _ResizeGrip was removed — the full-border (W9) and
# outer-ring (W10) drags remain the resize paths. ``overlay._resize_grip``
# stays None; ``reposition_grip`` keeps the card re-layout entry.


# -- UI construction helpers (thin owner delegation) -------------------------


def _nav_walk(overlay, delta: int) -> None:
    """Walk the series one item — the ‹/› circles are prev/next, not a cursor.

    The click path runs the SAME walk the ring/plate fall-through uses
    (``nav._walk_for_nav_button`` → ``overlay._walk``): one seam, two entry
    points. A mouse has no Enter step, so a ring move the user cannot see is a
    dead control (live 2026-10-22: circle clicks changed no picture and dropped
    the keyboard ring onto the bare overlay).
    """
    try:
        from tabs.image_gallery.ui.quick_look.nav import _walk_for_nav_button

        btn = (
            getattr(overlay, "_prev_btn", None)
            if int(delta) < 0
            else getattr(overlay, "_next_btn", None)
        )
        _walk_for_nav_button(overlay, btn)
    except Exception:
        pass


def build_overlay_ui(overlay) -> None:
    """Construct QuickLookOverlay layout (thin owner delegator).

    Reads/writes overlay attributes directly per CODE_PATTERNS plain function.
    No QSS, painter pipeline only, lazy imports for theming.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QHBoxLayout, QFrame, QSizePolicy, QVBoxLayout, QWidget

    from sli_ui_toolkit.managers import scaled_px
    from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow, CustomSplit, OverlayScrollArea

    # Translator seam: QuickLookOverlay sets ``self._tr`` before calling
    # build_overlay_ui; guard with getattr so the EN defaults still build if
    # a caller constructs without it.
    _tr = getattr(overlay, "_tr", None)

    def _t(key: str, default: str) -> str:
        if _tr is None:
            return default
        try:
            return _tr(key, default)
        except Exception:
            return default

    overlay._content = _CardPlate(overlay)
    overlay._content.setObjectName("QuickLookContent")
    # W9: the whole border is a resize strip — hover cursors need
    # button-free MouseMove delivery on the plate (no QSS involved).
    try:
        overlay._content.setMouseTracking(True)
    except Exception:
        pass
    overlay._border_drag = None
    # S4 mockup panel was 1040x620 — the floor grew to 680 for the third
    # artifact row (report rows = card dots triple). Minimum, not a suggestion.
    # W8: NO maximum — the user drag-resizes via the card border / ring.
    overlay._content.setMinimumSize(scaled_px(1040), scaled_px(680))
    outer = QVBoxLayout(overlay._content)
    outer.setContentsMargins(scaled_px(16), scaled_px(12), scaled_px(16), scaled_px(12))
    # W5: the 680-tall card must fit without scrollbars (S4 mockup: none) —
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
    # The dims/format/size meta line lives in the right sidebar as its top
    # row (populated by populate_filename_meta), not in this row.
    # The name keeps its natural width so it centers as one line; it
    # elides only when genuinely squeezed (Preferred, not Ignored —
    # Ignored parks labels at minimum width and the caption collapses to
    # "114…"). The leading spacer balances the trailing close button
    # (28 + 8 spacing) so the group is truly centered.
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
    chip_row.addSpacing(36)
    chip_row.addStretch(1)
    chip_row.addWidget(overlay._filename_label)
    chip_row.addStretch(1)
    overlay._close_btn = Button(text="✕", variant="surface", size=(28, 28), parent=overlay._content)
    overlay._close_btn.setObjectName("quicklook_close")
    # Full dismiss (filters + dismissed signal), not bare hide().
    overlay._close_btn.clicked.connect(lambda _checked=False: overlay.dismiss())
    # The panel's HEADER ROW IS THIS BUTTON (nav_section.rows()): single-control
    # row, so it must stay StrongFocus — arrows reach it (Up from the strip /
    # Down from the action bar) and the toolkit Button activates it on
    # Enter/Space. It stays in the title layout; only the row declaration makes
    # it owned (audit inv-nav-coverage-audit-2026-10-19 rank 4: it used to live
    # outside every row and was keyboard-unreachable).
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
    # ‹/› are prev/next: a click WALKS the series (same ``_walk`` seam as the
    # ring/plate fall-through and as the pre-#381 behaviour). The ql-nav-rows
    # wave (#381) rewired them to a ring step instead, on the theory that ←/→
    # already move the ring — but a mouse has no Enter step, so the circles
    # became a dead control that also dropped the keyboard ring (live
    # 2026-10-22). They stay CLICK-ONLY (NoFocus): ←/→ already move the ring
    # through the section, and living in overlay coords outside every declared
    # row these circles were an unowned Tab stop (audit
    # inv-nav-coverage-audit-2026-10-19 rank 4) — NoFocus keeps the Tab ring on
    # the row controls.
    overlay._prev_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    overlay._prev_btn.clicked.connect(
        lambda: _nav_walk(overlay, -1)
    )
    preview_host = QWidget(left)
    # Expanding on both axes: the host is the sole laid-out slot child, so
    # it must claim the preview area's stretch itself (previously the
    # in-layout label's Expanding policy did this indirectly). Preferred
    # left it at its 456 floor when the card grew.
    preview_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    preview_host.setObjectName("QuickLookPreviewHost")
    # Slot frame (IC parity, see StartupPlaceholder/HUD in image_compare):
    # the host is the SINGLE laid-out geometry authority (added to
    # preview_row with stretch 1). The GPU canvas and the first-frame cover
    # are layout-external children that mirror ``preview_host.rect()`` via
    # ``_fit_preview_slot`` — one geometry source, so the cover<->canvas
    # swap is seamless by construction (no hand-copied sibling geometry).
    # Mockup preview floor is 640x456 (svg): host min holds the min-card
    # proportions (640 preview + 296 column) so grow->shrink settles back
    # instead of splitting the leftover 1:1 (which stranded ~496px on the
    # scroll and clipped the preview). Pixmaps stay aspect-kept (W-B).
    preview_host.setMinimumSize(scaled_px(640), scaled_px(456))
    overlay._preview_host = preview_host
    preview_host_lay = QVBoxLayout(preview_host)
    preview_host_lay.setContentsMargins(0, 0, 0, 0)
    preview_host_lay.setSpacing(scaled_px(6))
    # Host Resize → refit every slot child (quick_look.eventFilter).
    try:
        preview_host.installEventFilter(overlay)
    except Exception:
        pass
    # Canvas preview slot: overlay._preview_canvas is the only live image
    # surface (preview.populate_preview creates it lazily); the first-frame
    # cover plate and the source/crop insets are layout-external siblings in
    # the same slot frame.
    overlay._preview_canvas = None
    overlay._preview_store = None
    # Source inset: an absolute block bottom-left OVER the preview image
    # (not in the flow) — title pill above the pixmap.
    overlay._source_inset_host = QWidget(preview_host)
    overlay._source_inset_host.setObjectName("quicklook_source_inset_host")
    src_lay = QVBoxLayout(overlay._source_inset_host)
    src_lay.setContentsMargins(0, 0, 0, 0)
    src_lay.setSpacing(scaled_px(2))
    overlay._source_inset_title = _make_label(_t("image_gallery.badge.source", "SOURCE"), parent=overlay._source_inset_host, pixel_size=11, pt=11.5, elide=True)
    overlay._source_inset_title.setObjectName("quicklook_source_inset_title")
    try:
        # SOURCE badge sits on the opaque WHITE pill (fill="white") in both
        # themes, so its ink is the fixed dark ``gallery.pill.text`` — NOT
        # ``gallery.nav.glyph``, which flips to ``#dfdfdf`` in the dark theme
        # (that token is the prev/next chevron on a dark disc).
        glyph = _token_color("gallery.pill.text", "#23262b")
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
    # NoFocus by the same "no callbacks" rule: a StrongFocus control that does
    # nothing on Enter is a dead keyboard stop (audit
    # inv-nav-coverage-audit-2026-10-19 rank 4; the caption/tooltip stays
    # readable, it was never an action).
    from PySide6.QtCore import QRectF as _QRectF

    _inset_pad = SOURCE_INSET_PAD

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
            size=(
                SOURCE_INSET_W + _inset_pad * 2,
                SOURCE_INSET_H + _inset_pad * 2,
            ),
            parent=parent,
            regions=[
                ButtonRegion(
                    id="bg",
                    group="card",
                    corner_radii=(SOURCE_INSET_FRAME_RADIUS,) * 4,
                    hover_color=QColor(0, 0, 0, 0),
                    bg_locked=True,
                ),
                ButtonRegion(
                    id="thumb",
                    pixmap=None,
                    image_fill="cover",
                    group="card",
                    corner_radii=(SOURCE_INSET_THUMB_RADIUS,) * 4,
                    hover_color=QColor(0, 0, 0, 0),
                    bg_locked=True,
                ),
            ],
            split=CustomSplit(rect_fns=[_inset_bg_rect, _inset_thumb_rect]),
            corner_radius=SOURCE_INSET_FRAME_RADIUS,
        )
        try:
            btn.setCursor(Qt.CursorShape.ArrowCursor)
        except Exception:
            pass
        try:
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        except Exception:
            pass
        return btn

    overlay._source_inset_pix = _make_inset_thumb_button(overlay._source_inset_host)
    overlay._source_inset_pix.setObjectName("quicklook_source_inset_pix")
    # Engine-canvas view surfaces (source_canvas): created lazily on the
    # first source populate, geometry mirrored from the plate's thumb rect.
    overlay._source_inset_canvas = None
    overlay._source_inset_cover = None
    overlay._source_inset_frame = None
    overlay._source_inset_store = None
    overlay._source_inset_store_key = None
    overlay._source_inset_token = 0
    overlay._source_inset_path = None
    src_lay.addWidget(overlay._source_inset_pix)
    overlay._source_inset_host.raise_()
    overlay._source_inset_host.hide()
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
    overlay._next_btn.clicked.connect(
        lambda: _nav_walk(overlay, 1)
    )
    # Same seam as ‹ (see the comment above _prev_btn): click walks the
    # series, click-only (NoFocus).
    overlay._next_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    left_lay.addLayout(preview_row, 1)
    # W4 item 4: the Esc hint lives at the right end of the bottom button
    # bar (built below), not in the left column. Nothing added here.
    mid.addWidget(left, 1)
    # Unification: the sidebar rides the toolkit overlay scrollbar like the
    # strip and the grid (corner_radius=0 keeps the current square look —
    # only the scrollbar changes, not the column shape).
    right_scroll = OverlayScrollArea(overlay._content, corner_radius=0)
    right_scroll.setObjectName("quicklook_right_scroll")
    # The sidebar scroller takes no keyboard focus (same reason the strip
    # scroller below documents): QAbstractScrollArea is StrongFocus by default,
    # so it was a Tab stop outside every declared nav row where Enter does
    # nothing — an inert stop. Wheel + the overlay bar still scroll it, and the
    # panel's arrows belong to the row section. (Audit
    # inv-nav-coverage-audit-2026-10-19 rank 4 found it while enforcing "every
    # focus stop is actionable".)
    try:
        right_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    except Exception:
        pass
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
    # Native bars stay AlwaysOff (overlay widget invariant — the floating
    # custom bar appears on overflow by itself); re-enforced by the
    # toolkit scrollbar policy at polish time.
    right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
    # 680 card with metrics + 3 artifact rows + series + brief, no scroll).
    # The dims/format/size meta row on top costs ~25px — gaps densify 4→3
    # to keep the same no-scroll budget with one more row.
    right_lay.setSpacing(scaled_px(3))
    right_lay.setAlignment(Qt.AlignmentFlag.AlignTop)
    # S4 mockup meta order (dims · format · size, populated by
    # populate_filename_meta) rides the sidebar as its top row, above the
    # report title. Elided to the column like the sublines (Ignored keeps
    # the full-text hint from widening the 296px column).
    overlay._meta_label = _make_label("", parent=right_host, pixel_size=11, pt=11.5, elide=True, minimum_width=40)
    overlay._meta_label.setObjectName("quicklook_meta")
    try:
        overlay._meta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    except Exception:
        pass
    right_lay.addWidget(overlay._meta_label)
    # The gap between the dims/format/size (resolution) row and the first
    # metric row is owned by relayout_report_rows' leading stretch spacer —
    # the first row breathes from this meta row exactly like rows from each
    # other (uniform share). A fixed widget here would make that one seam
    # disproportionately large.
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
    # Sidebar scroll pair auto-fills the raw Qt ``Window`` role (dark
    # #1e1e1e) — a near-black panel inside the #383838 plate. Route through
    # ``gallery.panel.background``.
    try:
        from tabs.image_gallery.ui.quick_look.labels_theme import _apply_panel_background

        _apply_panel_background(right_scroll)
        _apply_panel_background(right_host)
    except Exception:
        pass
    # S4 mockup divider before the brief block (svg:462) — a file-local 1px
    # painted rule (W4 item 3); the toolkit Divider is a button-region
    # dataclass, not a widget.
    overlay._div_series = _RuleWidget(right_host)
    overlay._div_series.setObjectName("quicklook_div_series")
    right_lay.addWidget(overlay._div_series)
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
    # and the 680px card gains a 4px v-scroll. The label always lays out
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
    # expanding preview pane. W8 min-only stays (minimum 1040×680, no
    # maximum); the column floor is the 296px minimum above.
    mid.addWidget(right_scroll, 1)
    outer.addLayout(mid, 1)
    # Series strip row (full card width under preview + sidebar): the
    # horizontal filmstrip breathes beyond 296px; the column keeps report
    # rows + brief only. No series text block — counts/hub are gone, the
    # size note rides the sidebar meta line instead.
    strip_row = QWidget(overlay._content)
    strip_row.setObjectName("quicklook_strip_row")
    overlay._strip_row = strip_row
    strip_lay = QHBoxLayout(strip_row)
    strip_lay.setContentsMargins(0, 0, 0, 0)
    strip_lay.setSpacing(scaled_px(16))
    strip_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
    # The filmstrip lives in its own horizontal scroller (toolkit
    # OverlayScrollArea: horizontal overlay bar + auto-hide included) so
    # any thumb count fits the row without widening the card.
    overlay._strip_scroll = OverlayScrollArea(
        strip_row, widget_resizable=False, corner_radius=0
    )
    # The strip scroller itself takes no keyboard focus: it is a StrongFocus
    # child of the strip row (QAbstractScrollArea's default), so the row's
    # navigation section (quick_look/nav_section.py — ToolbarRowsSection over
    # [strip_row, action_bar]) would otherwise count it as a cursor target and
    # arrow steps would park the ring on the scroller — a frame that paints no
    # indication. Measured 2026-10-17 on the real overlay: the strip row
    # reported 5 cursor targets (4 thumbs + the scroller, ``col_idx=0/5`` in the
    # nav trace). The section's own _ensure_visible scrolls the focused thumb
    # into view instead.
    try:
        overlay._strip_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    except Exception:
        pass
    overlay._strip_scroll.setObjectName("quicklook_strip_scroll")
    try:
        overlay._strip_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        overlay._strip_scroll.setMinimumHeight(scaled_px(56))
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
    # The scroll area + its content host auto-fill the raw Qt ``Window`` role
    # (dark #1e1e1e) — a black band under the plate. Route both through
    # ``gallery.panel.background``.
    try:
        from tabs.image_gallery.ui.quick_look.labels_theme import _apply_panel_background

        _apply_panel_background(overlay._strip_scroll)
        _apply_panel_background(overlay._strip_host)
    except Exception:
        pass
    strip_lay.addWidget(overlay._strip_scroll, 1)
    outer.addWidget(strip_row)
    # S4 mockup divider above the bottom action bar (svg:648) — painted
    # rule, see _div_series.
    overlay._div_bar = _RuleWidget(overlay._content)
    overlay._div_bar.setObjectName("quicklook_div_bar")
    outer.addWidget(overlay._div_bar)
    # bottom bar
    bar = QWidget(overlay._content)
    bar.setObjectName("quicklook_bottom_bar")
    # Exposed like the strip row: it is the panel's second navigation row
    # (quick_look/nav_section.py). Plain attribute, no layout change.
    overlay._action_bar = bar
    bar_lay = QHBoxLayout(bar)
    bar_lay.setContentsMargins(0, scaled_px(4), 0, 0)
    bar_lay.setSpacing(scaled_px(8))
    dark_bottom = _is_dark_theme()
    # NOTE: old fallbacks were dark-only (#D93025) — now light/dark chain.
    danger = _token_color("gallery.status.danger", "#c0392b" if not dark_bottom else "#d64545")
    # Heavy bar actions run after the press ripple finishes (defer_click):
    # _populate / carry flows block the GUI thread for hundreds of ms, and
    # a synchronous clicked would freeze mid-ripple with no press feedback.
    # Compare actions removed from quick look (no Compare → / Add to Multi
    # Compare here) — triage only (Reject / Set as source).
    overlay._compare_btn = None
    overlay._multi_btn = None
    # Set as source / Reject are plain default surface buttons (no accent,
    # gold or danger tint): the label itself carries the state
    # (Set as source ↔ Unset, Reject ↔ Restore). Set as source sits
    # at the left edge; Delete keeps its danger tint.
    overlay._set_source_btn = Button(text=_t("image_gallery.action.set_as_source", "Set as source"), variant="surface", parent=bar, defer_click="ripple")
    overlay._set_source_btn.setObjectName("quicklook_set_source")
    overlay._set_source_btn.clicked.connect(overlay._on_set_source)
    bar_lay.addWidget(overlay._set_source_btn)
    overlay._reject_btn = Button(text=f'✕ {_t("image_gallery.quick_look.reject", "Reject")}', variant="surface", parent=bar, defer_click="ripple")
    overlay._reject_btn.setObjectName("quicklook_reject")
    overlay._reject_text_color = None
    overlay._reject_btn.clicked.connect(overlay._on_reject)
    bar_lay.addWidget(overlay._reject_btn)
    overlay._delete_btn = Button(
        text=_t("image_gallery.quick_look.delete", "Delete"), icon=_danger_trash_icon(danger),
        variant="surface", parent=bar, defer_click="ripple",
    )
    overlay._delete_btn.setObjectName("quicklook_delete")
    overlay._delete_text_color = danger
    try:
        if danger is not None:
            overlay._delete_btn.set_border_color(danger)
            overlay._delete_btn.setForegroundColor(danger)
    except Exception:
        pass
    overlay._delete_btn.clicked.connect(overlay._on_delete)
    bar_lay.addWidget(overlay._delete_btn)
    bar_lay.addStretch(1)
    outer.addWidget(bar)
    overlay.add_widget(overlay._content, slot=None)
    # D1: interactive buttons keep an explicit arrow cursor so a stale plate
    # resize cursor never leaks onto them (they inherit otherwise).
    try:
        from PySide6.QtCore import Qt as _Qt

        for _btn_attr in (
            "_reject_btn",
            "_delete_btn",
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
    # No corner grip: the card is resizable via border+ring (QL_RESIZABLE=True) — no
    # corner handle. The attribute stays None so grip-aware helpers
    # no-op cleanly.
    overlay._resize_grip = None
    reposition_grip(overlay)
    overlay._strip_buttons: list = []
    overlay._metric_rows: list = []
    overlay._artifact_rows: list = []
    overlay._strip_caption_labels: list = []
    # Marquee (rubber-band) selection state: picked item paths + trailing-
    # click swallow flag for the lasso filter (see strip._StripLassoFilter).
    overlay._strip_selected_paths: set = set()
    overlay._strip_lasso_ate_click = False
    overlay._strip_lasso_filter = None
