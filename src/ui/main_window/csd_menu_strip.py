"""App-owned CSD menu strip (File / Help) for the main window title bar.

The toolkit ``CustomTitleBar`` is a generic shell: it hosts whatever leading-
zone widget the app injects via ``set_leading``. This module builds that widget
— the File/Help trigger buttons — and opens each dropdown as a toolkit
``SimpleOptionsFlyout`` filled with app-built rows: a ghost ``Button``
configured purely through the Button config API (``ButtonRegion`` +
``CustomSplit`` + ``ButtonRow``) so every row carries the label, right-aligned
shortcut and disabled/danger state — the classic menu look — while the flyout
composite handles the in-window overlay, positioning and scrolling.

Find Action reveal relies on two methods mirroring the old toolkit strip:
``buttons()`` and ``reveal_menu_action(button, action_id)``.
Audit-Meta: pattern=state-machine reason="single CSD menu strip — custom chrome + layout"
"""

from __future__ import annotations

import logging

logger = logging.getLogger("ImproveImgSLI")


def csd_debug(*args) -> None:
    logger.debug(*args)


def measure_text_width(fm, text: str) -> int:
    return fm.horizontalAdvance(text)

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QEvent, QRectF, QSize, QTimer, Qt
from PySide6.QtGui import QColor, QFontMetrics, QKeySequence
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QSizePolicy,
    QWidget,
)

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import ui_font
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.windows.custom_title_bar import (
    CustomTitleBar,
    resolve_titlebar_color,
)
from sli_ui_toolkit.widgets import (
    Button,
    ButtonRegion,
    ButtonRow,
    ContextMenuAction,
    CustomSplit,
    SimpleOptionsFlyout,
    measure_text_width,
)
from ui.theming import resolve_theme_color

logger = logging.getLogger("ImproveImgSLI")


_DANGER_COLOR = QColor("#e5484d")
_DISABLED_OPACITY = 0.4
_ROW_HEIGHT = 32
_SHORTCUT_GAP = 12
# Shortcut caption size (one step below the default UI font, still readable).
_SHORTCUT_PIXEL_SIZE = 12


def _estimate_menu_button_width(
    label: str,
    height: int,
    *,
    has_icon: bool = False,
    icon_size: int = 16,
    gap: int = 0,
    content_pad: int = 0,
) -> int:
    # Design px. ui_font() already applies UiScale, so the *measured text*
    # advance is scaled; divide only that back out to 1.0-baseline. The
    # icon/gap/padding constants are design values passed straight through —
    # Button(size=...) scales them (and the returned width) exactly once.
    # Dividing the constants by the factor as well under-scaled them at
    # factor > 1.0, shrinking the trigger below its real painted content
    # (icon + gap + text + padding) and eliding the label to "…".
    _SLACK = 4
    factor = UiScale.get_instance().factor()
    font = ui_font()
    fm = QFontMetrics(font)
    text_w = fm.horizontalAdvance(label)
    text_design = text_w / factor if factor else text_w
    if has_icon:
        width = (
            content_pad
            + icon_size
            + gap
            + text_design
            + content_pad
            + _SLACK
        )
    else:
        width = max(40, text_design + 16 + _SLACK)
    return int(round(width))


def _shortcut_display_text(shortcut: object) -> str:
    if not shortcut:
        return ""
    sequence = (
        shortcut if isinstance(shortcut, QKeySequence) else QKeySequence(str(shortcut))
    )
    return sequence.toString(QKeySequence.SequenceFormat.NativeText)


def _shortcut_color() -> QColor:
    tm = ThemeManager.get_instance()
    color = QColor(resolve_theme_color(tm, "dialog.text"))
    color.setAlpha(140 if tm.is_dark() else 120)
    return color


class CsdMenuRow(Button):
    """One CSD dropdown row — a ghost Button with label + right-aligned shortcut.

    The label uses the toolkit's default UI font (``ButtonRow(size=None)`` —
    the same ``ui_font()`` the SimpleOptionsFlyout default rows / HUD labels
    render with) and widths are measured through the toolkit text normalizer
    (``measure_text_width``) so the panel never clips the painted text.
    """

    ROW_HEIGHT = _ROW_HEIGHT

    def __init__(self, action: ContextMenuAction, parent: QWidget | None = None):
        self._label = action.text
        self._shortcut = _shortcut_display_text(action.shortcut)
        shortcut_fm = QFontMetrics(ui_font(pixel_size=_SHORTCUT_PIXEL_SIZE))
        trailing = (
            measure_text_width(shortcut_fm, self._shortcut) + scaled_px(_SHORTCUT_GAP)
            if self._shortcut
            else 0
        )
        regions = [
            ButtonRegion(
                id="_main",
                rows=[
                    ButtonRow(
                        text=self._label,
                        # size=None = the default UI font (ui_font()) — matches
                        # the flyout's default rows, no hand-rolled conversion.
                        size=None,
                        # ratio=1.0 centers the text across the full row height
                        # (the default 0.5 squeezes it into the top half and the
                        # first row then looks glued to the panel's top edge).
                        ratio=1.0,
                        h_align=Qt.AlignmentFlag.AlignLeft,
                    )
                ],
                group="row",
            ),
        ]
        if trailing > 0:
            regions.append(
                ButtonRegion(
                    id="shortcut",
                    rows=[
                        ButtonRow(
                            text=self._shortcut,
                            size=_SHORTCUT_PIXEL_SIZE,
                            color=_shortcut_color(),
                            ratio=1.0,
                            h_align=Qt.AlignmentFlag.AlignRight,
                        )
                    ],
                    # NOT enabled=False: a DISABLED region makes
                    # controller.region_at() return None, so the pointer over
                    # the shortcut never reaches the group's hover mirroring.
                    group="row",
                )
            )
        super().__init__(
            text="",
            regions=regions,
            split=CustomSplit(
                [
                    # Plain abutting rects: the toolkit paints a grouped row's
                    # fill once over the united group rect (first member), so
                    # there is no seam at the split boundary.
                    lambda r: QRectF(
                        r.left(), r.top(), max(0.0, r.width() - trailing), r.height()
                    ),
                    lambda r: QRectF(
                        r.right() - trailing, r.top(), float(trailing), r.height()
                    ),
                ]
            ),
            variant="ghost",
            corner_radius=5,
            size=(0, self.ROW_HEIGHT),
            content_padding=(8, 0, 8, 0),
            parent=parent,
        )
        self.action_id = action.action_id
        self.setEnabled(action.enabled)
        if not action.enabled:
            effect = QGraphicsOpacityEffect(self)
            effect.setOpacity(_DISABLED_OPACITY)
            self.setGraphicsEffect(effect)
        if action.danger:
            self.setForegroundColor(_DANGER_COLOR)

    def sizeHint(self) -> QSize:
        label_fm = QFontMetrics(ui_font())
        shortcut_fm = QFontMetrics(ui_font(pixel_size=_SHORTCUT_PIXEL_SIZE))
        label_w = measure_text_width(label_fm, self._label)
        sc_w = measure_text_width(shortcut_fm, self._shortcut)
        trailing = sc_w + scaled_px(_SHORTCUT_GAP) if sc_w else 0
        return QSize(
            max(1, scaled_px(16) + label_w + trailing), scaled_px(self.ROW_HEIGHT)
        )

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()


@dataclass(slots=True)
class CsdMenuSpec:
    """One CSD dropdown: trigger label, entries, and the dispatch handler."""

    label: str
    entries: Sequence[object]  # ContextMenuAction | ContextMenuSeparator
    on_triggered: Callable[[str, object], None]
    icon: Any = None
    icon_size: int = 16


class CsdMenuStrip(QWidget):
    """Horizontal row of menu triggers for a title bar leading zone."""

    # Equal top/bottom inset so File/Help don't flush against the chrome edges.
    V_INSET = 4
    # Left inset from the title-bar edge to the first menu trigger.
    H_INSET = 8
    # Space between adjacent menu triggers (File | Help).
    SPACING = 8
    # Internal icon↔label spacing inside a single trigger capsule.
    GAP = 8
    # Text triggers default to radius 2 in Button — force a visible round.
    CORNER_RADIUS = 6
    # Horizontal inset inside an icon+label trigger (icon/text ↔ button edge).
    CONTENT_PAD = 6

    def __init__(
        self,
        menus: Sequence[CsdMenuSpec],
        *,
        parent: QWidget | None = None,
        height: int = CustomTitleBar.HEIGHT,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CsdMenuStrip")
        self._height = height
        self.setFixedHeight(scaled_px(height))
        self._menus = list(menus)
        self._buttons: list[Button] = []
        self._flyouts: dict[int, SimpleOptionsFlyout] = {}
        self._row_actions: dict[int, list[str | None]] = {}
        self._theme_manager = ThemeManager.get_instance()
        self._theme_manager.theme_changed.connect(self._on_theme_changed)
        UiScale.get_instance().scale_changed.connect(self.remeasure)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            scaled_px(self.H_INSET), scaled_px(self.V_INSET), 0, scaled_px(self.V_INSET)
        )
        layout.setSpacing(scaled_px(self.SPACING))
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        for spec in self._menus:
            button = self._build_trigger(spec)
            self._buttons.append(button)
            layout.addWidget(button)

    def _build_trigger(self, spec: CsdMenuSpec) -> Button:
        trigger_height = max(20, self._height - 2 * self.V_INSET)
        has_icon = spec.icon is not None
        icon_size = max(12, min(spec.icon_size, trigger_height - 4))
        gap = self.GAP if has_icon else 6
        content_pad = self.CONTENT_PAD if has_icon else 0
        width = _estimate_menu_button_width(
            spec.label,
            trigger_height,
            has_icon=has_icon,
            icon_size=icon_size,
            gap=gap if has_icon else 0,
            content_pad=content_pad,
        )
        button = Button(
            icon=spec.icon if has_icon else None,
            text=spec.label,
            variant="ghost",
            size=(width, trigger_height),
            icon_size=icon_size,
            gap=gap,
            corner_radius=self.CORNER_RADIUS,
            content_padding=(content_pad, 0, content_pad, 0) if has_icon else 0.0,
            content_align=(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                if has_icon
                else Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
            ),
            parent=self,
        )
        button.setObjectName("CsdMenuTrigger")
        button.setCursor(Qt.CursorShape.ArrowCursor)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._apply_trigger_style(button)
        button.clicked.connect(
            lambda *,
            _button=button,
            _spec=spec: self._show_options(_button, _spec)
        )
        return button

    def _apply_trigger_style(self, button: Button) -> None:
        button.setForegroundColor(
            resolve_titlebar_color("titlebar.text", fallback="WindowText")
        )

    def _on_theme_changed(self, *_args) -> None:
        for button in self._buttons:
            self._apply_trigger_style(button)
            button.update()

    def remeasure(self) -> None:
        """Recompute trigger widths from the current UiFont and sync title balance.

        Call after the host applies the UI face (menus are often built before
        ``FontManager`` runs), after a language switch so Cyrillic labels do
        not clip, or on a UiScale factor change (also connected via
        ``scale_changed``).
        """
        self.setFixedHeight(scaled_px(self._height))
        for spec, button in zip(self._menus, self._buttons):
            trigger_height = max(20, self._height - 2 * self.V_INSET)
            has_icon = spec.icon is not None
            icon_size = max(12, min(spec.icon_size, trigger_height - 4))
            gap = self.GAP if has_icon else 6
            content_pad = self.CONTENT_PAD if has_icon else 0
            width = _estimate_menu_button_width(
                spec.label,
                trigger_height,
                has_icon=has_icon,
                icon_size=icon_size,
                gap=gap if has_icon else 0,
                content_pad=content_pad,
            )
            button.setFixedSize(scaled_px(width), scaled_px(trigger_height))
            button.update()
        self.updateGeometry()
        self.update()
        parent = self.parent()
        while parent is not None:
            sync = getattr(parent, "_sync_balance_spacer", None)
            if callable(sync):
                sync()
                repaint = getattr(parent, "repaint", None)
                if callable(repaint):
                    repaint()
                break
            parent_widget = getattr(parent, "parentWidget", None)
            parent = parent_widget() if callable(parent_widget) else None

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.FontChange,
            QEvent.Type.ApplicationFontChange,
        ):
            self.remeasure()

    # -------- opening / closing --------

    def _build_rows(self, spec: CsdMenuSpec) -> tuple[list[QWidget], list[str | None]]:
        """Build the dropdown rows from the spec entries (separators skipped).

        Returns ``(rows, action_ids)`` aligned by index so row clicks map back
        to their action without re-parsing the entries.
        """
        rows: list[QWidget] = []
        action_ids: list[str | None] = []
        for entry in spec.entries:
            if isinstance(entry, ContextMenuAction) and entry.visible:
                rows.append(CsdMenuRow(entry))
                action_ids.append(entry.action_id)
        return rows, action_ids

    def _show_options(
        self,
        anchor: Button,
        spec: CsdMenuSpec,
        *,
        force_open: bool = False,
    ) -> SimpleOptionsFlyout | None:
        key = id(anchor)
        if getattr(anchor, "_suppress_next_context_menu", False):
            anchor._suppress_next_context_menu = False
            return None

        flyout = self._flyouts.get(key)
        if flyout is not None and not self._widget_alive(flyout):
            self._flyouts.pop(key, None)
            flyout = None

        if not force_open and flyout is not None and flyout.isVisible():
            flyout.hide()
            csd_debug("[csd-menu] %s flyout -> hide (toggle)", spec.label)
            return flyout

        parent = anchor.window()
        if parent is None:
            return None
        if flyout is None:
            flyout = SimpleOptionsFlyout(parent_widget=parent)
            # Rows are rounded ghost Buttons — keep them clear of the panel
            # border and the rounded-corner clip.
            flyout.set_list_padding(6)
            flyout.item_chosen.connect(
                lambda idx, _k=key, _s=spec: self._dispatch(_k, _s, idx)
            )
            self._flyouts[key] = flyout

        rows, action_ids = self._build_rows(spec)
        self._row_actions[key] = action_ids
        flyout.set_rows(rows)
        csd_debug(
            "[csd-menu] %s flyout -> show rows=%d actions=%s force_open=%s",
            spec.label,
            len(rows),
            [a for a in action_ids if a is not None],
            force_open,
        )
        try:
            flyout.show_aligned(
                anchor,
                anchor_point="bottom-left",
                flyout_point="top-left",
                offset=2,
                animation_axis="vertical",
            )
        except (RuntimeError, SystemError):
            self._flyouts.pop(key, None)
            self._row_actions.pop(key, None)
            return None
        return flyout

    @staticmethod
    def _widget_alive(widget) -> bool:
        try:
            from shiboken6 import isValid

            return bool(isValid(widget))
        except Exception:
            try:
                widget.objectName()
                return True
            except RuntimeError:
                return False

    def _dispatch(self, key: int, spec: CsdMenuSpec, index: int) -> None:
        import traceback

        action_ids = self._row_actions.get(key)
        if not action_ids or not (0 <= index < len(action_ids)):
            return
        action_id = action_ids[index]
        if action_id is None:
            return
        _caller = "".join(traceback.format_stack()[-4:-2])
        csd_debug("[csd-menu] %s dispatch action_id=%s caller=%s", spec.label, action_id, _caller.strip())
        # Let the flyout hide (and its row ripple settle) first — handlers can
        # open modal dialogs (Find Action, file pickers).
        QTimer.singleShot(0, lambda a=action_id: spec.on_triggered(a, None))

    def reveal_menu_action(self, button: Button, action_id: str) -> QWidget | None:
        """Force-open the dropdown for ``button`` and return the row for ``action_id``."""
        try:
            index = self._buttons.index(button)
        except ValueError:
            return None
        if index < 0 or index >= len(self._menus):
            return None
        spec = self._menus[index]
        flyout = self._show_options(button, spec, force_open=True)
        if flyout is None:
            return None
        for row in flyout.rows():
            if getattr(row, "action_id", None) == action_id:
                return row
        return None

    def buttons(self) -> tuple[Button, ...]:
        return tuple(self._buttons)