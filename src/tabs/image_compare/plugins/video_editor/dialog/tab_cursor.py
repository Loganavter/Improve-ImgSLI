"""Keyboard cursor + focus ring for the video editor's export tab bar.

The workspace tab strip's idiom (pinned for the strip by
``tests/contracts/test_navigation_graph.py``): ``←``/``→`` move a keyboard
*cursor* without switching the page; ``Enter``/``Space`` activate the
cursor's tab; the cursor tab carries the focus ring while the bar holds
keyboard focus, and the active page's tab stays visually distinct.

The toolkit's ``TopTabBar`` owns neither a cursor nor a key handler — its tab
buttons are ``NoFocus`` and the dialog's nav section (``dialog/nav.py``) owns
the keys. The app therefore subclasses it: :class:`VideoEditorTabBar` tracks
the cursor index and the keyboard-focus modality, and
:class:`VideoEditorCursorRingLayer` paints the ring through each tab button's
painter pipeline — the same style as the toolkit's ``FocusLayer``, keyed on
the bar's cursor instead of the button's own focus. :class:`VideoEditorTopTabHost`
swaps the host's toolkit bar for the subclass so the rest of the dialog keeps
the plain ``TopTabHost`` API.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSizePolicy, QWidget

from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.layers import FocusLayer
from sli_ui_toolkit.ui.widgets.composite.adaptive_tab_strip import CloseButtonPolicy
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.bar import (
    TopTabBar,
    _CloseSlotBackgroundLayer,
    _CloseXLayer,
)
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.constants import (
    DEFAULT_PANE_RADIUS,
    DEFAULT_TAB_RADIUS,
    TAB_CLOSE_MARGIN,
    TAB_MIN_WIDTH,
)
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.host import TopTabHost
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.items import TabItem, TabSpec
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.tab_button import TopTabButton


class VideoEditorCursorRingLayer(FocusLayer):
    """Focus ring on the export bar's *cursor* tab.

    ``FocusLayer`` paints when its widget holds keyboard focus. The export
    bar's tab buttons are ``NoFocus`` (the bar itself holds focus), so this
    subclass keys the identical drawing on the bar's cursor index and
    keyboard modality — the ring follows ``cursor_tab_button()``.
    """

    scope = "widget"

    def applies(self, ctx) -> bool:  # noqa: ANN001
        bar = _cursor_bar(ctx.widget)
        if bar is None or not bar.hasFocus():
            return False
        if not bar.cursor_is_keyboard():
            return False
        return bar.cursor_tab_button() is ctx.widget


def _cursor_bar(button: QWidget | None) -> VideoEditorTabBar | None:
    """The :class:`VideoEditorTabBar` owning *button* (button → strip → bar)."""
    if button is None:
        return None
    strip = button.parentWidget()
    bar = strip.parentWidget() if strip is not None else None
    return bar if isinstance(bar, VideoEditorTabBar) else None


def _keyboard_focus(reason: Qt.FocusReason) -> bool:
    """Modality-aware keyboard-focus flag (same rule as the toolkit bars).

    Delegates to the toolkit's ``resolve_keyboard_focus`` — the single
    interpretation site for focus-ring modality; the degraded no-manager
    rule lives there, never inlined here (same idiom as the color-recents
    swatch button, ``ui/widgets/color/recents.py``).
    """
    try:
        from sli_ui_toolkit.ui.managers.navigation_manager import (
            resolve_keyboard_focus,
        )

        return bool(resolve_keyboard_focus(reason))
    except Exception:
        # Degraded (no manager / broken import — never in the app, where the
        # toolkit is a hard dependency): assume keyboard modality, the same
        # fallback as recents.py.
        return True


class VideoEditorTabBar(TopTabBar):
    """``TopTabBar`` with a keyboard cursor separate from the active page.

    ``_cursor_index`` is the ring's target; ``currentIndex()`` is the page.
    They diverge exactly while the user is moving the cursor — activating
    (Enter/Space, mouse click, programmatic page change) collapses them.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cursor_index = -1
        self._cursor_keyboard = False

    # -- cursor state ----------------------------------------------------

    def cursor_index(self) -> int:
        """The keyboard-cursor tab index (``-1`` when unset)."""
        return self._cursor_index

    def cursor_is_keyboard(self) -> bool:
        """True while the bar holds *keyboard* focus (mouse clicks hide the ring)."""
        return self._cursor_keyboard

    def cursor_tab_button(self) -> QWidget | None:
        """The tab button the ring currently targets."""
        if 0 <= self._cursor_index < len(self._tabs):
            return self._tabs[self._cursor_index].button
        return None

    def set_cursor_index(self, index: int) -> None:
        index = max(-1, min(int(index), len(self._tabs) - 1))
        if index == self._cursor_index:
            return
        self._cursor_index = index
        self._refresh_cursor_ring()

    def move_cursor(self, step: int) -> bool:
        """Move the cursor by *step* (no wrap). Always consumed — the key is
        the bar's own; a declined edge keeps the cursor put."""
        count = len(self._tabs)
        if count == 0:
            return True
        base = self._cursor_index if self._cursor_index >= 0 else self.currentIndex()
        if base < 0:
            base = 0
        target = base + step
        if 0 <= target < count:
            self.set_cursor_index(target)
        return True

    def activate_cursor(self) -> bool:
        """Activate the cursor's tab (Enter/Space). Always consumed."""
        index = self._cursor_index
        if 0 <= index < len(self._tabs):
            self.setCurrentIndex(index)
        return True

    def _refresh_cursor_ring(self) -> None:
        for tab in self._tabs:
            tab.button.update()

    # -- cursor follows the page on any selection change -----------------

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        super().setCurrentIndex(index)
        if 0 <= index < len(self._tabs):
            self._cursor_index = index
        self._refresh_cursor_ring()

    def clear(self) -> None:
        super().clear()
        self._cursor_index = -1

    # -- keyboard-focus modality ----------------------------------------

    def focusInEvent(self, event) -> None:  # noqa: N802
        self._cursor_keyboard = _keyboard_focus(event.reason())
        if not (0 <= self._cursor_index < len(self._tabs)):
            self._cursor_index = self.currentIndex()
        super().focusInEvent(event)
        self._refresh_cursor_ring()

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._cursor_keyboard = False
        super().focusOutEvent(event)
        self._refresh_cursor_ring()

    # -- tab construction: carry the cursor ring layer -------------------

    def add_item(self, text: str, data: object | None = None) -> TabItem:
        """Mirror of ``TopTabBar.add_item`` — only the cursor ring layer differs."""
        closable = self._close_policy is not CloseButtonPolicy.NONE
        tab_height = self._scaled_tab_height()
        button = TopTabButton(
            text=text,
            toggle=True,
            size=(0, tab_height),
            variant="top_tab",
            corner_radii=(self._corner_radius, self._corner_radius, 0, 0),
            close_zone=(
                self._scaled_close_size() + TAB_CLOSE_MARGIN if closable else 0
            ),
            extra_layers=[VideoEditorCursorRingLayer()],
        )
        button.set_show_indicator(self._show_indicator)
        button.setFixedHeight(tab_height)
        if self._expand_tabs:
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            button.setMinimumWidth(TAB_MIN_WIDTH)
        else:
            button.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
            )
            button.setFixedWidth(button.sizeHint().width())

        tab = TabSpec(text=text, button=button)
        if data is not None:
            tab.data_roles[int(Qt.ItemDataRole.UserRole)] = data
        self._tabs.append(tab)

        index = len(self._tabs) - 1
        button.clicked.connect(lambda _i=index: self._on_tab_clicked(_i))
        self._layout.addWidget(button)

        if closable:
            # Embedded in the tab's right edge (adaptive-tab close-slot
            # mechanics): the close button is a child of the tab button; its
            # background follows the tab's state, not its own hover.
            close_button = Button(
                size=(self._scaled_close_size(), self._scaled_close_size()),
                corner_radius=5,
                variant="default",
                layers=[_CloseSlotBackgroundLayer(), _CloseXLayer()],
            )
            close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            close_button.setToolTip("Close")
            close_button.clicked.connect(
                lambda _i=index: self.tabCloseRequested.emit(_i)
            )
            button.attach_close_button(close_button)
            tab.close_button = close_button

        self._sync_strip_geometry()
        return TabItem(self, index)


class VideoEditorTopTabHost(TopTabHost):
    """``TopTabHost`` whose tab bar is the app's cursor-capable subclass."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tab_height: int = 32,
        pane_radius: int | tuple[int, int, int, int] = DEFAULT_PANE_RADIUS,
        expand_tabs: bool = False,
        close_policy: CloseButtonPolicy = CloseButtonPolicy.NONE,
    ) -> None:
        super().__init__(
            parent,
            tab_height=tab_height,
            pane_radius=pane_radius,
            expand_tabs=expand_tabs,
            close_policy=close_policy,
        )
        self._install_cursor_bar(
            tab_height=tab_height,
            expand_tabs=expand_tabs,
            close_policy=close_policy,
        )

    def _install_cursor_bar(
        self,
        *,
        tab_height: int,
        expand_tabs: bool,
        close_policy: CloseButtonPolicy,
    ) -> None:
        toolkit_bar = self.tab_bar
        bar = VideoEditorTabBar(
            self,
            tab_height=tab_height,
            expand_tabs=expand_tabs,
            show_indicator=False,
            corner_radius=DEFAULT_TAB_RADIUS,
            close_policy=close_policy,
        )
        bar.setObjectName("TopTabBar")
        layout = self.layout()
        layout.removeWidget(toolkit_bar)
        layout.insertWidget(0, bar)
        bar.tabCloseRequested.connect(self.tabCloseRequested.emit)
        bar.currentChanged.connect(self._on_bar_changed)
        self.tab_bar = bar
        # Hide before unparent: detaching a still-visible widget maps a
        # stillborn toplevel (Wayland busy cursor — the contract ratchet).
        toolkit_bar.hide()
        toolkit_bar.setParent(None)
        toolkit_bar.deleteLater()
