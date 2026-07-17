"""Find Action palette row widget — layout, paint layers, region clicks."""

from __future__ import annotations

import math

from PySide6.QtCore import QLineF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from core.actions.types import ActionDescriptor
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons.layers import ContentLayer, RippleLayer
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.layers.background import rounded_rect_path
from sli_ui_toolkit.ui.widgets.buttons.layers.ripple import (
    RippleEffect,
    _is_group_ripple_paint_owner,
    _region_group,
    _ripple_for,
)
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow
from ui.actions.keymap import effective_shortcut
from ui.actions.palette.common import (
    current_keyboard_overrides,
    target_is_revealable,
    tr_action,
)
from ui.icon_manager import AppIcon

_ROW_HEIGHT = 48
_RUN_REGION_WIDTH = 28.0
# Gap only between different click targets (plate group vs run/learn), never
# between grouped siblings — a real pixel gap shows through shared ripple.
_ROW_GAP = 2.0
_ROW_INSET_LEFT = 12.0
# Trailing chrome that is not ``learn`` keeps this breathing room. ``learn``
# itself spans to the button's right edge so its wash meets the capsule.
_ROW_INSET_RIGHT = 10.0
_CHROME_TEXT_PAD = 10.0
_PLATE_GROUP = "plate"
_CHROME_REGION_IDS = frozenset({"run", "learn"})
_ROW_BG_INSET = (2, 1, -2, -1)
_ROW_CORNER_RADIUS = 6


def _breadcrumb_text(
    action: ActionDescriptor,
    query: str = "",
    *,
    active_tab: str | None = None,
) -> str:
    from ui.actions.registry import action_breadcrumb_text

    return action_breadcrumb_text(action, query, active_tab=active_tab)


def _text_width(text: str, *, pixel_size: int, padding: float) -> float:
    from sli_ui_toolkit.managers import ui_font

    font = ui_font(pixel_size=pixel_size)
    return float(QFontMetrics(font).horizontalAdvance(text)) + padding


class PaletteRowSplit:
    """Flexible plate + optional fixed chrome (shortcut / enter / learn more).

    Horizontal margins live in the split (once for the whole row). Do not put
    them in ``content_padding`` — that inset is applied to *every* region and
    would clip shortcut / Learn more text that was sized without it.
    """

    def __init__(
        self,
        fixed_widths: dict[str, float],
        *,
        gap: float = _ROW_GAP,
        inset_left: float = _ROW_INSET_LEFT,
        inset_right: float = _ROW_INSET_RIGHT,
    ) -> None:
        self._fixed = fixed_widths
        self.gap = max(0.0, float(gap))
        self.inset_left = max(0.0, float(inset_left))
        self.inset_right = max(0.0, float(inset_right))

    def compute(self, rect: QRectF, regions: list[ButtonRegion]) -> list[QRectF]:
        n = len(regions)
        if n == 0:
            return []
        # ``learn`` is allowed to consume the right inset so its hover wash
        # meets the capsule edge; other last regions keep the breathing room.
        last = regions[-1]
        right_inset = 0.0 if last.id == "learn" else self.inset_right
        usable = QRectF(rect).adjusted(self.inset_left, 0.0, -right_inset, 0.0)
        fixed_total = sum(self._fixed.get(region.id, 0.0) for region in regions)
        gaps = sum(
            self._gap_between(regions[i], regions[i + 1]) for i in range(n - 1)
        )
        flexible = max(0.0, usable.width() - fixed_total - gaps)
        x = usable.left()
        out: list[QRectF] = []
        for index, region in enumerate(regions):
            if index == n - 1:
                w = max(0.0, usable.right() - x)
            elif region.id in self._fixed:
                w = self._fixed[region.id]
            else:
                w = flexible
            out.append(QRectF(x, usable.top(), w, usable.height()))
            if index < n - 1:
                x += w + self._gap_between(region, regions[index + 1])
        return out

    def _gap_between(self, left: ButtonRegion, right: ButtonRegion) -> float:
        left_group = getattr(left, "group", None)
        right_group = getattr(right, "group", None)
        if left_group and left_group == right_group:
            return 0.0
        return self.gap

    def dividers(self, rects: list[QRectF]) -> list[QLineF]:
        return []


def row_capsule_rect(widget_rect: QRectF) -> QRectF:
    l, t, r, b = _ROW_BG_INSET
    return QRectF(widget_rect).adjusted(l, t, r, b)


def chrome_hover_color(tm: ThemeManager, *, strength: int = 118) -> QColor:
    """Deeper monochrome wash over the row hover — no accent tint."""
    base = QColor(tm.get_color("list_item.background.hover"))
    if tm.is_dark():
        return base.lighter(strength)
    return base.darker(strength)


class RowBackgroundLayer(Layer):
    """Whole-row fill; region-scoped so it paints *before* ContentLayer.

    ``Painter`` draws widget-scoped layers after every region layer, so a
    widget-scoped fill would wipe region text/icons. Draw once from ``_main``
    using the full button rect instead.

    Only plate-group interaction drives this wash — Enter / Learn more use
    ``ChromeHoverLayer`` so their press/checked stays local to that chrome.
    """

    scope = "region"

    def applies(self, ctx) -> bool:
        return ctx.region_id == "_main"

    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        # Keyboard selection uses the left accent tick only — do not paint the
        # hover wash for ``is_current``, or the first row looks permanently
        # hovered when the palette opens.
        is_active = False
        for region in widget.regions():
            if region.id in _CHROME_REGION_IDS:
                continue
            states = widget.region_states(region.id)
            if (
                ButtonState.HOVERED in states
                or ButtonState.PRESSED in states
                or ButtonState.CHECKED in states
            ):
                is_active = True
                break
        key = "list_item.background.hover" if is_active else "list_item.background.normal"
        rect = row_capsule_rect(ctx.rect).toRect()
        painter = ctx.painter
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(tm.get_color(key)))
        painter.drawRoundedRect(rect, _ROW_CORNER_RADIUS, _ROW_CORNER_RADIUS)


class ChromeHoverLayer(Layer):
    """Full-region wash for Enter / Learn more, clipped to the row capsule."""

    scope = "region"

    def applies(self, ctx) -> bool:
        if ctx.region_id not in _CHROME_REGION_IDS:
            return False
        states = ctx.effective_states
        return (
            ButtonState.HOVERED in states
            or ButtonState.PRESSED in states
            or ButtonState.CHECKED in states
        )

    def draw(self, ctx, tm: ThemeManager) -> None:
        # Learn slightly deeper than Enter so the two chrome targets stay distinct.
        strength = 125 if ctx.region_id == "learn" else 118
        color = chrome_hover_color(tm, strength=strength)
        radius = _ROW_CORNER_RADIUS
        outer = rounded_rect_path(
            row_capsule_rect(ctx.rect),
            (radius, radius, radius, radius),
        )
        region_path = ctx.effective_fill_path
        painter = ctx.painter
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipPath(outer)
        painter.setClipPath(region_path, Qt.ClipOperation.IntersectClip)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPath(region_path)
        painter.restore()


class PaletteRippleLayer(RippleLayer):
    """Ripple clipped to the shared rounded row capsule.

    Default ``RippleLayer`` clips to the full widget rect (and a rectangular
    group union). Palette rows paint a smaller inset capsule via
    ``RowBackgroundLayer``, so the stock clip lets the wave spill past the
    visible plate — and for plate ``group=`` the rectangular clip does not
    follow the capsule corners across ``_main`` + ``shortcut``.
    """

    def draw(self, ctx, tm: ThemeManager) -> None:
        ripple = _ripple_for(ctx)
        if ripple is None:
            return
        center = ripple.center
        if center is None:
            return

        progress = ripple.progress()
        eased = 1.0 - (1.0 - progress) ** 2

        capsule = row_capsule_rect(ctx.rect)
        radius_rect = ctx.effective_ripple_rect
        if _region_group(ctx) is not None:
            draw_rect = radius_rect.intersected(capsule)
        elif ctx.region_rect is not None:
            draw_rect = QRectF(ctx.region_rect).intersected(capsule)
        else:
            draw_rect = QRectF(capsule)
        if draw_rect.isEmpty():
            return

        corners = (
            (draw_rect.left(), draw_rect.top()),
            (draw_rect.right(), draw_rect.top()),
            (draw_rect.left(), draw_rect.bottom()),
            (draw_rect.right(), draw_rect.bottom()),
        )
        max_radius = max(
            math.hypot(center.x() - cx, center.y() - cy) for cx, cy in corners
        )
        radius = max_radius * eased
        if radius <= 0:
            return

        p = ctx.painter
        p.save()
        outer = rounded_rect_path(
            capsule,
            (_ROW_CORNER_RADIUS, _ROW_CORNER_RADIUS, _ROW_CORNER_RADIUS, _ROW_CORNER_RADIUS),
        )
        p.setClipPath(outer)
        if _region_group(ctx) is not None:
            group_clip = QPainterPath()
            group_clip.addRect(draw_rect)
            p.setClipPath(group_clip, Qt.ClipOperation.IntersectClip)
        elif ctx.region_rect is not None:
            p.setClipPath(ctx.effective_fill_path, Qt.ClipOperation.IntersectClip)

        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        if ripple.color_from is not None and ripple.color_to is not None:
            p.setBrush(QBrush(ripple.color_from))
            p.drawRect(draw_rect)
            p.setBrush(QBrush(ripple.color_to))
            p.drawEllipse(center, radius, radius)
        else:
            try:
                is_dark = tm.is_dark()
            except Exception:
                is_dark = False
            peak = (
                RippleEffect.PEAK_ALPHA_DARK if is_dark else RippleEffect.PEAK_ALPHA_LIGHT
            )
            alpha = int(peak * (1.0 - progress))
            if alpha > 0:
                color = (
                    QColor(255, 255, 255, alpha) if is_dark else QColor(0, 0, 0, alpha)
                )
                p.setBrush(color)
                p.drawEllipse(center, radius, radius)

        p.restore()

    def applies(self, ctx) -> bool:
        ripple = _ripple_for(ctx)
        if ripple is None or not ripple.is_active():
            return False
        return _is_group_ripple_paint_owner(ctx)


class CurrentIndicatorLayer(Layer):
    scope = "widget"

    def applies(self, ctx) -> bool:
        return bool(getattr(ctx.widget, "is_current", False))

    def draw(self, ctx, tm: ThemeManager) -> None:
        rect = ctx.rect.toRect()
        pen = QPen(tm.get_color("accent"))
        pen.setWidth(3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter = ctx.painter
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(pen)
        x = rect.left() + pen.width()
        painter.drawLine(x, rect.top() + 8, x, rect.bottom() - 8)


class ActionPaletteRow(Button):
    rowActivated = Signal(str)
    rowRevealRequested = Signal(str)
    learnMoreRequested = Signal(str)

    def __init__(
        self,
        action: ActionDescriptor,
        *,
        query: str = "",
        active_tab: str | None = None,
        is_current: bool = False,
        keyboard_overrides: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        tm = ThemeManager.get_instance()
        rating = tm.get_color("list_item.text.rating")
        accent = tm.get_color("accent")

        title = tr_action(action.label_key, action.label_key)
        crumb = _breadcrumb_text(action, query, active_tab=active_tab)
        plate_rows = [
            ButtonRow(
                text=title,
                size=13,
                weight="bold",
                h_align=Qt.AlignmentFlag.AlignLeft,
            )
        ]
        if crumb:
            plate_rows.append(
                ButtonRow(
                    text=crumb,
                    size=11,
                    color=rating,
                    h_align=Qt.AlignmentFlag.AlignLeft,
                )
            )

        regions: list[ButtonRegion] = [
            ButtonRegion(
                id="_main",
                rows=plate_rows,
                group=_PLATE_GROUP,
                # Plate is one visual capsule: CHECKED mirrors across group=
                # (toolkit) so title + shortcut highlight together on press.
                toggle=True,
            )
        ]
        fixed_widths: dict[str, float] = {"run": _RUN_REGION_WIDTH}

        overrides = (
            keyboard_overrides
            if keyboard_overrides is not None
            else current_keyboard_overrides()
        )
        shortcut = (effective_shortcut(action, overrides) or "").strip()
        if shortcut:
            fixed_widths["shortcut"] = _text_width(
                shortcut, pixel_size=11, padding=_CHROME_TEXT_PAD
            )
            regions.append(
                ButtonRegion(
                    id="shortcut",
                    rows=[
                        ButtonRow(
                            text=shortcut,
                            size=11,
                            color=rating,
                            h_align=Qt.AlignmentFlag.AlignRight,
                        )
                    ],
                    group=_PLATE_GROUP,
                    toggle=True,
                )
            )

        regions.append(
            ButtonRegion(
                id="run",
                icon=AppIcon.ENTER,
                icon_size_px=16,
                cursor=QCursor(Qt.CursorShape.ArrowCursor),
            )
        )

        has_help = bool(getattr(action, "help_page", None))
        learn_label = tr_action("action.palette.learn_more", "Learn more")
        if has_help:
            fixed_widths["learn"] = _text_width(
                learn_label, pixel_size=11, padding=_CHROME_TEXT_PAD
            )
            regions.append(
                ButtonRegion(
                    id="learn",
                    rows=[
                        ButtonRow(
                            text=learn_label,
                            size=11,
                            color=accent,
                            h_align=Qt.AlignmentFlag.AlignHCenter,
                        )
                    ],
                    cursor=QCursor(Qt.CursorShape.PointingHandCursor),
                )
            )

        super().__init__(
            regions=regions,
            split=PaletteRowSplit(fixed_widths),
            size=(0, _ROW_HEIGHT),
            corner_radius=6,
            # Vertical breathing room only — horizontal inset is in the split.
            content_padding=(0, 4, 0, 4),
            icon_size=16,
            layers=[
                RowBackgroundLayer(),
                ChromeHoverLayer(),
                PaletteRippleLayer(),
                ContentLayer(),
                CurrentIndicatorLayer(),
            ],
            parent=parent,
        )
        self._rows_compact = True
        self.action_id = action.action_id
        self.is_current = is_current
        self._has_help = has_help
        self._has_target = target_is_revealable(getattr(action, "target", None))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.regionClicked.connect(self._on_region_clicked)

    @property
    def has_learn_more(self) -> bool:
        return self._has_help

    def _on_region_clicked(self, region_id: str) -> None:
        if region_id in ("_main", "shortcut"):
            if self._has_target:
                self.rowRevealRequested.emit(self.action_id)
            return
        if region_id == "run":
            self.rowActivated.emit(self.action_id)
            return
        if region_id == "learn" and self._has_help:
            self.learnMoreRequested.emit(self.action_id)

    def set_current(self, current: bool) -> None:
        if self.is_current == current:
            return
        self.is_current = current
        self.update()
