from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsEffect, QWidget

from sli_ui_toolkit.managers import AnchoredFlyoutAutoHide, UiScale, scaled_px
from sli_ui_toolkit.ui.in_window_surface import surface_anchor_rect
from sli_ui_toolkit.ui.managers.ui_font import ui_font
from sli_ui_toolkit.ui.widgets.buttons.layers.background import rounded_rect_path
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout

from ui.theming import resolve_theme_color

# ButtonGroup (sli_ui_toolkit/ui/widgets/buttons/button_group.py, paintEvent)
# insets its visible border box from the widget's own rect: margin_h=6 each
# side, and the box's bottom edge sits margin_v=3 + half the caption label's
# text height above the widget's bottom edge (room for the "лупа" caption
# below the line). Matching those constants here is what makes this flyout's
# box read as a continuation of that border instead of floating below it
# with a gap / being wider than it.
_GROUP_BORDER_MARGIN_H = 6
_GROUP_BORDER_MARGIN_V = 3
# Empirical fine-tune on top of the computed gap above -- the label-height
# math gets close but not pixel-exact (font hinting/leading rounds
# differently than QFontMetrics.height() alone accounts for).
_EXTRA_LIFT_PX = 6

# Caption capsule (mirrors the anchor group's own label, see paintEvent /
# _paint_caption): background/border box extends this far below the actual
# content before the border line, giving the panel a visible "backdrop"
# under the last row instead of the border hugging it directly.
_CAPTION_BOX_EXTRA_PX = 6
# Horizontal/vertical padding around the caption text inside its rounded
# capsule -- same values as ScrollValueButton's _CAPSULE_PAD_X/Y.
_CAPTION_PAD_X = 5
_CAPTION_PAD_Y = 4
# Gap between the capsule's bottom edge and the flyout's own bottom edge.
_CAPTION_BOTTOM_MARGIN_PX = 3


def _caption_capsule_height() -> int:
    return QFontMetrics(_caption_font()).height() + 2 * scaled_px(_CAPTION_PAD_Y)


def _caption_overlap_px(capsule_h: int) -> int:
    """How far the capsule's top pokes above the border line.

    Dead-center on the line (capsule_h // 2 above, the rest below) -- same
    straddling as ButtonGroup's own flat notch, just on a rounded capsule
    instead. The "lower than the group's own caption" effect comes from
    _CAPTION_BOX_EXTRA_PX moving the *line itself* down relative to the
    content above it, not from off-centering the capsule on that line.
    """
    return capsule_h // 2


def _caption_font():
    """Same font ButtonGroup.paintEvent uses for its own bottom caption --
    shared here so this flyout's mirrored caption (see paintEvent) matches
    it exactly, not just approximately."""
    factor = UiScale.get_instance().factor()
    return ui_font(point_size=max(8, ui_font().pointSizeF() / factor - 2))


def _group_border_geometry(group: QWidget) -> tuple[int, int]:
    """Return (visible border box width, gap between the widget's outer
    bottom edge and the border's bottom line).

    ButtonGroup's own border box is left-aligned at x=margin_h with an extra
    -1px shaved off the right (its own crisp-line pixel snap) -- fine for a
    widget that always draws from the left, but this flyout is positioned by
    *center* (show_aligned's "-center" points), so keeping that same -1
    would make the box asymmetric under a symmetric placement and shift the
    left edge half a pixel off the group's. Using the plain symmetric width
    here is what actually lines the two left edges up.
    """
    width = max(0, group.width() - scaled_px(_GROUP_BORDER_MARGIN_H) * 2)
    label = group.label() if hasattr(group, "label") else ""
    label_height = QFontMetrics(_caption_font()).height() if label else 0
    gap = (
        label_height // 2
        + scaled_px(_GROUP_BORDER_MARGIN_V)
        + scaled_px(_EXTRA_LIFT_PX)
    )
    return width, gap


def _open_top_border_path(rect: QRectF, radius: float) -> QPainterPath:
    """Left + rounded-bottom + right edges only, no top segment.

    Same corner geometry as ``rounded_rect_path(rect, (0, 0, r, r))`` but
    left un-closed at the top -- the group's own bottom border is what's
    visible there instead, so stroking a top line here would double it up.
    """
    r = radius
    path = QPainterPath()
    path.moveTo(rect.right(), rect.top())
    path.lineTo(rect.right(), rect.bottom() - r)
    if r > 0:
        path.arcTo(rect.right() - 2 * r, rect.bottom() - 2 * r, 2 * r, 2 * r, 0.0, -90.0)
    path.lineTo(rect.left() + r, rect.bottom())
    if r > 0:
        path.arcTo(rect.left(), rect.bottom() - 2 * r, 2 * r, 2 * r, 270.0, -90.0)
    path.lineTo(rect.left(), rect.top())
    return path


class _MonolithClipEffect(QGraphicsEffect):
    """Square top corners, rounded bottom — clips content to the same shape
    ``MagnifierSettingsFlyout.paintEvent`` draws, instead of ``RoundedClipEffect``'s
    uniform 4-corner rounding."""

    def __init__(self, radius: float, parent=None) -> None:
        super().__init__(parent)
        self._radius = float(radius)

    def draw(self, painter: QPainter) -> None:
        src = self.sourceBoundingRect()
        if src.isEmpty():
            self.drawSource(painter)
            return
        path = rounded_rect_path(src, (0, 0, self._radius, self._radius))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipPath(path, Qt.ClipOperation.IntersectClip)
        self.drawSource(painter)
        painter.restore()


class MagnifierSettingsFlyout(BaseFlyout):
    """Hover flyout hosting the magnifier sliders + interpolation row.

    Painted as a seamless downward continuation of the magnifier button
    group instead of a floating popup: no shadow, no gap, square top
    corners flush with the group's bottom edge, same border/background
    tokens as ``ButtonGroup``. Width matches the group (border included).
    """

    # Deliberately not one of the mutually-exclusive groups in
    # ui/flyout_policy.py's _EXCLUSIVE_GROUPS: this flyout hosts
    # ``combo_interpolation``, whose own dropdown is an "options" flyout —
    # letting that dismiss us on open would close the parent mid-pick.
    flyout_group = "canvas_feature_settings"

    SHADOW_RADIUS = 0
    CONTENT_RADIUS = 8

    def __init__(self, parent_widget: QWidget, content: QWidget) -> None:
        # pinned=True: this panel's closing is deliberately hover/timer-driven
        # (see MagnifierSettingsHoverController), not click-driven -- without
        # it, FlyoutManager._dismiss_passive() hides it on *any* click outside
        # its own body, including a click on a sibling toolbar button (e.g.
        # channel-mode) that only opens *another* flyout. That passive-dismiss
        # path doesn't consult GroupShowPolicy or FlyoutManager.link() family
        # ties at all, so linking siblings here never helped -- pinned is the
        # only way to opt this panel out of it. Diagnosed by a hide()
        # traceback showing the call came from FlyoutManager.eventFilter ->
        # _dismiss_passive() on MouseButtonPress, not from any timer/hover path.
        super().__init__(parent_widget, pinned=True)
        self._anchor_group: QWidget | None = None
        self._anchor_original_radii: tuple[int, int, int, int] | None = None
        self._label = ""
        self.content_layout.addWidget(content)
        # Room below the container for the mirrored group caption capsule
        # (see paintEvent/_paint_caption) -- same idea as ButtonGroup
        # reserving space under its buttons for its own caption.
        # SHADOW_RADIUS=0 means main_layout's outer margins would otherwise
        # be (0, 0, 0, 0), leaving the container filling the whole flyout
        # with nowhere for the capsule to sit below the border line.
        capsule_h = _caption_capsule_height()
        caption_reserve = (
            scaled_px(_CAPTION_BOX_EXTRA_PX)
            + capsule_h
            - _caption_overlap_px(capsule_h)
            + scaled_px(_CAPTION_BOTTOM_MARGIN_PX)
        )
        self._main_layout.setContentsMargins(0, 0, 0, caption_reserve)
        # widgets.qss has a global `QWidget#FlyoutContainer { border-radius:
        # 8px; border: 1px solid @flyout.border; ... }` rule keyed on this
        # objectName. WA_StyledBackground=False (set by BaseFlyout.__init__)
        # is meant to suppress it, but a later app.setStyleSheet()/polish
        # pass can re-flip that attribute back on for any widget the sheet
        # still matches by name -- clearing the name is what actually starves
        # the rule, instead of racing the attribute. Without this, that QSS
        # border rendered on top of our own square-top paintEvent below,
        # showing as a rounded "inner" border no amount of custom painting
        # could cover.
        self.container.setObjectName("")
        # Replace the base class's uniform-radius clip with one matching the
        # square-top/round-bottom shape paintEvent draws below.
        self._container_clip = _MonolithClipEffect(scaled_px(self.CONTENT_RADIUS), self.container)
        self.container.setGraphicsEffect(self._container_clip)
        self._auto_hide = AnchoredFlyoutAutoHide(
            flyout=self,
            anchor_getter=lambda: self._anchor_group,
            parent=self,
        )

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        full_rect = self.rect()
        # Box bottom sits _CAPTION_BOX_EXTRA_PX below the actual content
        # (container's own height), not at the widget's true bottom edge --
        # the caption capsule (see _paint_caption) then sits mostly *below*
        # that line, in the margin reserved in __init__, instead of at the
        # widget's true edge.
        box_bottom = (
            self.container.geometry().height() + scaled_px(_CAPTION_BOX_EXTRA_PX)
            if self._label
            else full_rect.height()
        )
        rect = QRectF(0, 0, full_rect.width(), box_bottom)
        stroke_rect = rect.adjusted(0.5, 0.5, -0.5, -0.5)
        r = scaled_px(self.CONTENT_RADIUS)
        path = rounded_rect_path(stroke_rect, (0, 0, r, r))
        # Same tokens ButtonGroup itself paints with (dialog.border / Window)
        # by default -- overridable per anchor via set_background_brush, see
        # show_for_group, which samples the checkbox row's actual background
        # instead of trusting the token to resolve identically.
        background = self._background_brush or QBrush(
            resolve_theme_color(self.theme_manager, "Window")
        )
        border = self._border_color_override or resolve_theme_color(
            self.theme_manager, "dialog.border"
        )
        painter.setBrushOrigin(stroke_rect.topLeft())
        painter.setBrush(background)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)
        # Border stroke on left/bottom/right only -- see _open_top_border_path.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(border, 1))
        painter.drawPath(_open_top_border_path(stroke_rect, float(r)))
        if self._label:
            self._paint_caption(painter, stroke_rect, background, border)
        painter.end()

    def _paint_caption(
        self, painter: QPainter, stroke_rect: QRectF, background, border
    ) -> None:
        """Mirror the anchor group's own caption below this flyout's border
        line, as a small rounded capsule (same idea as ScrollValueButton's
        own value capsule) instead of a plain rectangular notch -- it
        overlaps the line (see _caption_overlap_px) rather than sitting
        flush on it or floating disconnected below it."""
        font = _caption_font()
        painter.setFont(font)
        fm = QFontMetrics(font)
        label_w = fm.horizontalAdvance(self._label)
        label_h = fm.height()
        center_x = stroke_rect.center().x()

        capsule_w = label_w + 2 * scaled_px(_CAPTION_PAD_X)
        capsule_h = label_h + 2 * scaled_px(_CAPTION_PAD_Y)
        capsule_rect = QRectF(
            center_x - capsule_w / 2,
            stroke_rect.bottom() - _caption_overlap_px(capsule_h),
            capsule_w,
            capsule_h,
        )

        radius = capsule_h / 4
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(capsule_rect, radius, radius)
        # Same 1px stroke as the panel's own border, so the capsule reads as
        # part of the same outline system instead of a flat color patch --
        # but only its bottom half: the capsule straddles the panel's own
        # border line (see _caption_overlap_px), so the top half already
        # sits inside the already-outlined panel area and stroking it too
        # would double the line right where the two overlap.
        painter.save()
        painter.setClipRect(
            QRectF(
                capsule_rect.left() - scaled_px(2),
                capsule_rect.center().y(),
                capsule_rect.width() + scaled_px(4),
                capsule_rect.height() / 2 + scaled_px(2),
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(
            capsule_rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius
        )
        painter.restore()

        painter.setPen(resolve_theme_color(self.theme_manager, "WindowText"))
        painter.drawText(capsule_rect, Qt.AlignmentFlag.AlignCenter, self._label)

    def trigger_widgets(self):
        # This flyout isn't click-toggled -- it's hover-driven (see
        # MagnifierSettingsHoverController). Its anchor (see show_for_group)
        # is the *whole* magnifier button group, used only for positioning,
        # not a single trigger button -- leaving it coupled to the toolkit's
        # default trigger_widgets()==anchor_widgets() would make toggling
        # e.g. btn_magnifier while the panel is open read as "clicked the
        # trigger, dismiss" (FlyoutManager.eventFilter's click heuristic).
        return ()

    def keyPressEvent(self, event) -> None:
        # This panel + the magnifier button group above it are meant to
        # read as one continuous unit (the panel is a seamless flush
        # continuation of the group's own border, see paintEvent) rather
        # than an isolated popover -- so unlike every other flyout, Escape
        # does not dismiss it. It only closes when keyboard focus actually
        # leaves the group+panel for some other toolbar control (handled by
        # MagnifierSettingsHoverController._handle_button_focus_event's
        # FocusOut -> _schedule_hide, mirroring the mouse-hover-leave path).
        if event.key() == Qt.Key.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)

    def reposition(self) -> None:
        # BaseFlyout.reposition() (now also called by FlyoutManager itself
        # for pinned=True flyouts like this one on anchor move/resize, see
        # its CHANGELOG entry) only re-runs show_aligned() with the plain
        # anchor/flyout point + offset -- it doesn't know about the extra
        # move(x, y - gap) show_for_group applies afterwards to close the
        # label-padding gap (see below). Calling the base version here would
        # silently drop that gap adjustment on every anchor move, snapping
        # the panel back down by `gap` px. Redo the whole show_for_group
        # instead, which already re-derives and reapplies it.
        anchor_group = self._anchor_group
        if anchor_group is None or not self.isVisible():
            return
        try:
            if not anchor_group.isVisible():
                return
        except RuntimeError:
            return
        self.show_for_group(anchor_group)

    def show_for_group(self, anchor_group: QWidget) -> None:
        self._anchor_group = anchor_group
        self._label = anchor_group.label() if hasattr(anchor_group, "label") else ""
        width, gap = _group_border_geometry(anchor_group)
        if width > 0:
            self.container.setFixedWidth(width)
        checkbox_row = anchor_group.parentWidget()
        row_bg = getattr(checkbox_row, "_bg_color", None)
        self.set_background_brush(QBrush(row_bg) if row_bg is not None else None)
        self._flatten_anchor_group(anchor_group)
        # offset=0 places the flyout flush with the group *widget's* bottom
        # edge; show_aligned clamps offset at a minimum of 0 (it only
        # guarantees clearance, never overlap), so the label-padding gap
        # above has to be closed with an explicit move() afterwards instead
        # of a negative offset. animation="none" is deliberate: this panel is
        # a seamless flush continuation of the button group (no shadow, square
        # top), its own paintEvent doesn't composite the toolkit's fade
        # opacity, and the slide would fight the move() below and snap the
        # panel back down by `gap` px on every fresh open. Opting out of the
        # app-wide default fade keeps show/hide instant and the position exact.
        # grab_focus=False: this panel is a continuation of the magnifier
        # button group, not an isolated popover (see keyPressEvent) -- the
        # user must be free to keep arrow-key/Tab-navigating every button in
        # the group while it's open, so opening it must not steal focus onto
        # the panel's own first slider the instant it appears.
        # register_nav_section=True: without this, the panel would be
        # entirely invisible to arrow-key navigation -- Down from a group
        # button would skip straight over it to whatever's next in the
        # app's unrelated tab order instead of entering the panel. With it
        # registered (but not focused), the toolbar row's section keeps
        # routing Left/Right across the whole group as normal, and Down/Up
        # now hand off into and back out of this panel's own controls at
        # its boundary (see _FlyoutNavigationSection.navigate() in the
        # toolkit).
        self.show_aligned(
            anchor_group,
            "bottom-center",
            "top-center",
            offset=0,
            animation="none",
            grab_focus=False,
            register_nav_section=True,
        )
        # show_aligned centers this flyout's box on the group *widget*
        # center, which only puts the box's left edge exactly on the
        # group's painted border-box left edge (scaled_px(MARGIN_H)) when
        # the two centering halves round the same way. With an odd group
        # width and an odd scaled margin (150% UI scale: m=scaled_px(6)=9,
        # W odd) the halves round in opposite directions (banker's
        # rounding) and the whole panel lands 1px left of the group
        # border. Snap x to the border-box left edge explicitly, the same
        # way the label-padding gap on y is closed just below.
        anchor_left = surface_anchor_rect(self, anchor_group, self.overlay_layer).x()
        target_x = anchor_left + scaled_px(_GROUP_BORDER_MARGIN_H)
        if gap > 0 or self.x() != target_x:
            self.move(target_x, self.y() - gap)

    def _flatten_anchor_group(self, anchor_group: QWidget) -> None:
        """Square off the group's own bottom corners via ButtonGroup's
        ``set_corner_radii`` API, so its border reads as a straight
        continuation into this flyout instead of curving away from it."""
        get_radii = getattr(anchor_group, "corner_radii", None)
        set_radii = getattr(anchor_group, "set_corner_radii", None)
        if not callable(get_radii) or not callable(set_radii):
            return
        tl, tr, br, bl = get_radii()
        if (br, bl) == (0, 0):
            return
        self._anchor_original_radii = (tl, tr, br, bl)
        set_radii((tl, tr, 0, 0))

    def _restore_anchor_group(self) -> None:
        anchor_group = self._anchor_group
        original = self._anchor_original_radii
        self._anchor_original_radii = None
        if anchor_group is None or original is None:
            return
        set_radii = getattr(anchor_group, "set_corner_radii", None)
        if callable(set_radii):
            set_radii(original)

    def schedule_auto_hide(self, ms: int) -> None:
        self._auto_hide.schedule(ms)

    def cancel_auto_hide(self) -> None:
        self._auto_hide.cancel()

    def hide(self) -> None:
        # BaseFlyout.__init__ calls hide() (via the overlay layer's attach())
        # before _auto_hide/_anchor_original_radii exist yet.
        auto_hide = getattr(self, "_auto_hide", None)
        if auto_hide is not None:
            auto_hide.cancel()
        if getattr(self, "_anchor_original_radii", None) is not None:
            self._restore_anchor_group()
        super().hide()