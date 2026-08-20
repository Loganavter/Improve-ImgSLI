# Audit-Meta: pattern=state-machine reason="single rating item painter — custom control"
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402
"""App-owned rating list row (moved out of sli-ui-toolkit).

The toolkit keeps the generic ListPanel row protocol; the rating row with
its +/- buttons and rating gestures is Improve-ImgSLI domain UI and lives
here. Build rows for a ListPanel/UnifiedFlyout through
``make_rating_row_factory``.
"""

from PySide6.QtCore import (
    QPoint,
    QPointF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)

from typing import Literal

from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from ui.theming import resolve_theme_color
from sli_ui_toolkit.ui.managers.ui_font import apply_text_color, rebase_family, rebase_font, ui_font
from sli_ui_toolkit.ui.widgets.atomic.tooltips import PathTooltip
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.layers import RippleLayer
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from typing import Literal

from ui.widgets.list_item import drag_drop, rating_gestures, tooltip

# Row kind tag shared with the picker's populate() ("image" vs "simple").
ListItemType = Literal["image", "simple"]

DEFAULT_MINUS_ICON = "remove"
DEFAULT_PLUS_ICON = "add"

RatingItemPosition = Literal["first", "middle", "last", "only"]


class _RatingRowBgLayer(Layer):
    """Position-aware rounded BG: outer corners use outer_r, internal use inner_r.

    Reads `widget.position` ∈ {"first","middle","last","only"} и `widget.is_current`,
    `widget._is_being_dragged`. Inset фон на 2px.
    """

    INNER_R = 5
    OUTER_R = 8

    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        states = ctx.effective_states
        is_selected = bool(getattr(widget, "is_selected", False))
        is_active = (
            widget.is_current
            or is_selected
            or ButtonState.HOVERED in states
            or ButtonState.PRESSED in states
        )
        key = "list_item.background.hover" if is_active else "list_item.background.normal"
        p = ctx.painter
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if widget._is_being_dragged:
            p.setOpacity(0.35)
        p.setPen(Qt.PenStyle.NoPen)
        if is_selected:
            # Soft accent wash for ctrl+LMB-selected rows — including the
            # current row when it is part of the selection (its accent bar
            # still shows on top).
            accent = QColor(resolve_theme_color(tm, "accent"))
            base = QColor(resolve_theme_color(tm, key))
            fill = QColor(
                int(round(accent.red() * 0.38 + base.red() * 0.62)),
                int(round(accent.green() * 0.38 + base.green() * 0.62)),
                int(round(accent.blue() * 0.38 + base.blue() * 0.62)),
            )
            p.setBrush(fill)
        else:
            p.setBrush(resolve_theme_color(tm, key))
        bg_rect = ctx.rect.toRect().adjusted(2, 2, -2, -2)
        pos = widget.position
        if pos == "middle":
            p.drawRoundedRect(bg_rect, self.INNER_R, self.INNER_R)
        else:
            r = bg_rect
            tl = self.OUTER_R if pos in ("first", "only") else self.INNER_R
            tr = self.OUTER_R if pos in ("first", "only") else self.INNER_R
            bl = self.OUTER_R if pos in ("last", "only") else self.INNER_R
            br = self.OUTER_R if pos in ("last", "only") else self.INNER_R
            path = QPainterPath()
            path.moveTo(r.left() + tl, r.top())
            path.lineTo(r.right() - tr, r.top())
            path.arcTo(r.right() - 2 * tr, r.top(), 2 * tr, 2 * tr, 90, -90)
            path.lineTo(r.right(), r.bottom() - br)
            path.arcTo(r.right() - 2 * br, r.bottom() - 2 * br, 2 * br, 2 * br, 0, -90)
            path.lineTo(r.left() + bl, r.bottom())
            path.arcTo(r.left(), r.bottom() - 2 * bl, 2 * bl, 2 * bl, -90, -90)
            path.lineTo(r.left(), r.top() + tl)
            path.arcTo(r.left(), r.top(), 2 * tl, 2 * tl, 180, -90)
            path.closeSubpath()
            p.drawPath(path)
        if widget._is_being_dragged:
            p.setOpacity(1.0)


class _RatingRowIndicatorLayer(Layer):
    """Левый accent-бар для current row."""

    def applies(self, ctx) -> bool:
        return bool(getattr(ctx.widget, "is_current", False))

    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        rect = ctx.rect.toRect()
        pen = QPen(resolve_theme_color(tm, "accent"))
        pen.setWidth(scaled_px(3))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p = ctx.painter
        if widget._is_being_dragged:
            p.setOpacity(0.35)
        p.setPen(pen)
        x = rect.left() + pen.width()
        p.drawLine(x, rect.top() + scaled_px(7), x, rect.bottom() - scaled_px(7))
        if widget._is_being_dragged:
            p.setOpacity(1.0)


class _RatingRowSeparatorLayer(Layer):
    """Вертикальный separator между rating_label и name_label (только image-type)."""

    def applies(self, ctx) -> bool:
        widget = ctx.widget
        return widget.item_type == "image" and getattr(widget, "rating_label", None) is not None

    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        p = ctx.painter
        if widget._is_being_dragged:
            p.setOpacity(0.35)
        p.setPen(QPen(resolve_theme_color(tm, "separator.color"), 1))
        x_pos = widget.rating_label.geometry().right() + widget._row_layout.spacing() // 2
        p.drawLine(x_pos, scaled_px(6), x_pos, widget.height() - scaled_px(6))
        if widget._is_being_dragged:
            p.setOpacity(1.0)


class RatingListItem(Button):
    itemSelected = Signal(int)
    itemSelectionToggled = Signal(int)
    itemRightClicked = Signal(int)

    def __init__(
        self,
        index,
        text,
        rating,
        full_path: str,
        list_num: int | None = None,
        get_rating=None,
        increment_rating=None,
        decrement_rating=None,
        create_rating_gesture=None,
        on_update_drop_indicator=None,
        on_clear_drop_indicator=None,
        parent=None,
        is_current: bool = False,
        item_height: int = 36,
        item_font: QFont | None = None,
        item_type: ListItemType = "image",
        position: RatingItemPosition = "middle",
        wheel_requires_focus: bool = False,
        *,
        image_number: int | None = None,
    ):
        # `item_type`/`position` нужны кастомным layer'ам ещё до super().__init__,
        # потому что Button.__init__ может вызвать update()/paint в зависимости
        # от theme bootstrap.
        self.item_type = item_type
        self.position = position
        self.is_current = is_current
        self.is_selected = False
        self._is_being_dragged = False
        self.rating_label: QLabel | None = None
        # item_height is a live (already scale-resolved) anchor metric; Button
        # scales its size= design px by the factor, so divide the factor back
        # out here to keep the row at the anchor's actual height (and have
        # Button re-apply it proportionally on live scale changes).
        factor = UiScale.get_instance().factor()
        design_height = max(1, round(item_height / factor)) if factor > 0 else item_height
        super().__init__(
            text="",
            size=(0, design_height),
            corner_radius=8,
            wheel_requires_focus=wheel_requires_focus,
            layers=[
                _RatingRowBgLayer(),
                RippleLayer(),
                _RatingRowIndicatorLayer(),
                _RatingRowSeparatorLayer(),
            ],
            parent=parent,
        )
        self.index = index
        self.full_path = full_path
        if list_num is None:
            list_num = image_number
        if list_num is None:
            raise TypeError("RatingListItem requires list_num (or legacy image_number)")
        self.list_num = int(list_num)
        self._get_rating = get_rating
        self._increment_rating = increment_rating
        self._decrement_rating = decrement_rating
        self._create_rating_gesture = create_rating_gesture
        self._on_update_drop_indicator = on_update_drop_indicator
        self._on_clear_drop_indicator = on_clear_drop_indicator

        self.theme_manager.theme_changed.connect(self.update_styles)

        self.drag_start_pos = QPoint()
        self._drag_start_pos_global = QPointF()

        self.tooltip_timer = QTimer(self)
        self.tooltip_timer.setSingleShot(True)
        self.tooltip_timer.setInterval(500)
        self.tooltip_timer.timeout.connect(self._show_tooltip)

        # Row click → external selection. Button.clicked не срабатывает, если
        # release пришёл по child-Button'у (Qt потребит event на ребёнке) или
        # если start drag отменил его (см. mouseReleaseEvent).
        # Guard: nested +/- must never select/close the flyout even if a press
        # still bubbles (pre-accept Button handlers).
        self.clicked.connect(self._emit_item_selected_from_row)
        self.rightClicked.connect(lambda: self.itemRightClicked.emit(self.index))

        self._row_layout = QHBoxLayout(self)

        # Right margin is wider so the + button keeps a visible gap from the
        # (2px-inset) row background edge. Rows are rebuilt per flyout open,
        # so build-time scaled_px keeps these in step with the row size at
        # the current interface scale.
        self._row_layout.setContentsMargins(
            scaled_px(2), scaled_px(2), scaled_px(4), scaled_px(2)
        )
        self._row_layout.setSpacing(scaled_px(6))

        if self.item_type == "image":
            self.rating_label = QLabel(str(rating), self)
            self.rating_label.setFixedWidth(scaled_px(25))
            self.rating_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.rating_label.setObjectName("ratingLabel")

        self.name_label = QLabel(text, self)
        self.name_label.setObjectName("nameLabel")
        self.name_label.setMinimumWidth(0)
        self.name_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.NoTextInteraction
        )

        self.name_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )

        base_font = rebase_family(item_font) if item_font else ui_font()
        self.name_label.setFont(base_font)

        if self.item_type == "image":
            assert self.rating_label is not None

            # base_px is already scale-resolved (live item_font); express the
            # "3px smaller" delta in design space so rebase scales it once.
            base_px = base_font.pixelSize()
            if base_px <= 0:
                base_px = QFontMetrics(base_font).height()
            design_base = (
                base_px / factor if factor > 0 else base_px
            )
            rating_font = rebase_font(
                base_font, pixel_size=max(8, round(design_base - 3))
            )
            self.rating_label.setFont(rating_font)

            self.btn_minus = Button(
                resolve_icon(DEFAULT_MINUS_ICON),
                icon_size=14,
                size=(22, 22),
                parent=self,
            )
            self.btn_plus = Button(
                resolve_icon(DEFAULT_PLUS_ICON),
                icon_size=14,
                size=(22, 22),
                parent=self,
            )
            self.btn_minus.setObjectName("minusButton")
            self.btn_plus.setObjectName("plusButton")
            for btn in [self.btn_minus, self.btn_plus]:
                btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

            self._row_layout.addWidget(self.rating_label)
            self._row_layout.addWidget(self.name_label, 1)
            self._row_layout.addWidget(self.btn_minus)
            self._row_layout.addWidget(self.btn_plus)

            self.btn_plus.clicked.connect(self._on_plus_clicked)
            self.btn_minus.clicked.connect(self._on_minus_clicked)
            self.btn_plus.pressed.connect(lambda: self._on_button_pressed(self.btn_plus))
            self.btn_minus.pressed.connect(lambda: self._on_button_pressed(self.btn_minus))
            self.btn_plus.released.connect(
                lambda: self._on_button_released(self.btn_plus)
            )
            self.btn_minus.released.connect(
                lambda: self._on_button_released(self.btn_minus)
            )
            self._gesture_tx = None
            self._active_button = None
            self._is_drag_initiated = False
            self.btn_plus.installEventFilter(self)
            self.btn_minus.installEventFilter(self)
        else:
            self._row_layout.addWidget(self.name_label, 1)

        self.update_styles()

    def set_dragging_state(self, is_dragging: bool):
        self._is_being_dragged = bool(is_dragging)
        self.update()

    @property
    def image_number(self) -> int:
        return self.list_num

    @image_number.setter
    def image_number(self, value: int) -> None:
        self.list_num = int(value)

    def set_selected(self, selected: bool) -> None:
        selected = bool(selected)
        if self.is_selected == selected:
            return
        self.is_selected = selected
        self._sync_rating_button_selection_background()
        self.update()

    def _sync_rating_button_selection_background(self) -> None:
        if self.item_type != "image":
            return
        color = QColor(resolve_theme_color(self.theme_manager, "accent")) if self.is_selected else None
        self.btn_minus.set_override_bg_color(color)
        self.btn_plus.set_override_bg_color(color)

    def _find_panel(self):
        return drag_drop.find_panel(self)

    def drag_indices(self) -> list[int]:
        """Indices to move: multi-selection if this row is in it, else self."""
        return drag_drop.drag_indices(self)

    def set_batch_dragging_state(self, dragging: bool, indices) -> None:
        drag_drop.set_batch_dragging_state(self, dragging, indices)

    def eventFilter(self, obj, event):
        item_type = getattr(self, "item_type", None)
        if item_type != "image":
            return super().eventFilter(obj, event)

        handled = drag_drop.handle_button_event_filter(self, obj, event)
        if handled is not None:
            return handled

        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        if not self.shouldHandleWheelEvent(event):
            return
        rating_gestures.wheel_event(self, event)

    def update_styles(self):
        tm = self.theme_manager
        apply_text_color(self.name_label, resolve_theme_color(tm, "list_item.text.normal"))
        if self.item_type == "image":
            apply_text_color(
                self.rating_label, resolve_theme_color(tm, "list_item.text.rating")
            )
            self.btn_minus.setIcon(resolve_icon(DEFAULT_MINUS_ICON))
            self.btn_plus.setIcon(resolve_icon(DEFAULT_PLUS_ICON))
            self._sync_rating_button_selection_background()
        self.update()

    def enterEvent(self, event):
        super().enterEvent(event)
        tooltip.enter_event(self)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        tooltip.leave_event(self)

    def mousePressEvent(self, event: QMouseEvent):
        self.tooltip_timer.stop()
        PathTooltip.get_instance().hide_tooltip()
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.position().toPoint()
            self._drag_start_pos_global = event.globalPosition()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        super().mouseMoveEvent(event)
        drag_drop.mouse_move_event(self, event)

    def _drag_allowed(self) -> bool:
        return drag_drop.drag_allowed(self)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._is_drag_initiated:
            # Drag swallowed the click — clear PRESSED state without firing
            # Button.clicked → itemSelected.
            self._pressed = False
            self._pressed_region = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

        rating_gestures.maybe_commit_gesture(self)

        self._is_drag_initiated = False
        self._active_button = None
        drag_drop.notify_flyout_clear_indicator(self)

    def _emit_item_selected_from_row(self) -> None:
        if self.item_type == "image":
            # Nested +/- previously bubbled an unaccepted press to this row,
            # which selected the item and closed UnifiedFlyout.
            under = self.childAt(self.mapFromGlobal(QCursor.pos()))
            if under is self.btn_plus or under is self.btn_minus:
                return
            if under is not None and (
                self.btn_plus.isAncestorOf(under) or self.btn_minus.isAncestorOf(under)
            ):
                return
        modifiers = QApplication.keyboardModifiers()
        if modifiers & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
        ):
            self.itemSelectionToggled.emit(self.index)
            return
        self.itemSelected.emit(self.index)

    def _on_plus_clicked(self):
        rating_gestures.on_plus_clicked(self)

    def _on_minus_clicked(self):
        rating_gestures.on_minus_clicked(self)

    def _on_button_pressed(self, button):
        rating_gestures.on_button_pressed(self, button)

    def _on_button_released(self, button):
        rating_gestures.on_button_released(self, button)

    def _cancel_button_interaction(self):
        rating_gestures.cancel_button_interaction(self)

    def _update_label_from_store(self):
        rating_gestures.update_label_from_store(self)

    def _show_tooltip(self):
        tooltip.show_tooltip(self)

    def _notify_flyout_drop_indicator(self, global_pos):
        self._on_update_drop_indicator(global_pos)

    def _notify_flyout_clear_indicator(self):
        self._on_clear_drop_indicator()


def make_rating_row_factory(
    get_rating,
    increment_rating,
    decrement_rating,
    create_rating_gesture,
):
    """Build a ``ListPanel`` row factory rendering :class:`RatingListItem`.

    The callbacks are the host's rating behavior (read/mutate the store);
    the panel hands the factory a :class:`ListRowSpec` per row.
    """

    def build(spec):
        return RatingListItem(
            index=spec.index,
            text=spec.text,
            rating=spec.rating,
            full_path=spec.full_path,
            list_num=spec.list_num,
            get_rating=get_rating,
            increment_rating=increment_rating,
            decrement_rating=decrement_rating,
            create_rating_gesture=create_rating_gesture,
            on_update_drop_indicator=spec.on_update_drop_indicator,
            on_clear_drop_indicator=spec.on_clear_drop_indicator,
            is_current=spec.is_current,
            item_height=spec.item_height,
            item_font=spec.item_font,
            item_type=spec.item_type,
            position=spec.position,
        )

    return build

RatingListItem.inspect_spec = InspectSpec(
    family="RatingListItem",
    state=(
        SpecField("index", "index"),
        SpecField("full_path", "full_path"),
        SpecField("list_num", "list_num"),
        SpecField("image_number", "image_number"),
        SpecField("item_type", "item_type"),
        SpecField("position", "position"),
        SpecField("is_current", "is_current"),
        SpecField("is_selected", "is_selected"),
    ),
    token_family=(
        "list_item.background.normal",
        "list_item.background.hover",
        "list_item.background.selected",
        "accent",
    ),
    regions=True,
    layers=True,
    docs="docs/dev/widgets/rating_item.md",
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor
RatingListItem.widget_descriptor = WidgetDescriptor(
    family=RatingListItem.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(RatingListItem.inspect_spec, 'config', ()),
        state=RatingListItem.inspect_spec.state,
        token_family=getattr(RatingListItem.inspect_spec, 'token_family', ()),
        regions=getattr(RatingListItem.inspect_spec, 'regions', False),
        layers=getattr(RatingListItem.inspect_spec, 'layers', False),
        docs=getattr(RatingListItem.inspect_spec, 'docs', ''),
        preview_seed=getattr(RatingListItem.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(RatingListItem.inspect_spec, 'apply_config_refresh', None),
    ),
)