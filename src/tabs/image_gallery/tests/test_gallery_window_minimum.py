"""Gallery page window floor — the toolbar's real minimum, not the 250 px base.

Owner report 2026-10-25: on the Gallery tab the main window could still be
squeezed to the base floor (``MAIN_WINDOW_MIN_WIDTH_FLOOR`` = 250 px) and the
toolbar clipped — chips overlapped, the series header and the first card were
cut. ``SessionPickerWidget`` was the only page declaring
``window_minimum_size()``, so ``minimum_floor_for_main_window`` fell back to the
250 px constant while the toolbar row alone needs 870 px at UI factor 1.0
(906 px with the scanning slot visible) plus the page's 24 px horizontal
padding per side.

Measured 2026-10-25, offscreen, factor 1.0:
``GalleryToolbar.minimumSizeHint().width()`` = 870 px idle / 906 px scanning /
850 px after triage; the page wrapper's own ``minimumSizeHint()`` = 918 px
(toolbar + 48 px padding) — i.e. exactly the toolbar, nothing narrower.

This was MASKED until app #677: the judge-budget activity ``Text`` used to
inflate the row to ~1181 px by accident. That fix (``_ActivityText`` reporting a
zero minimum width so the sentence elides) is right — the missing page floor is
the actual bug, so these tests read the toolbar's own minimum, not the label's.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from tabs.image_gallery.widget import ImageGalleryWidget


def _page_margins(page: QWidget):
    return page.layout().contentsMargins()


def _host_window(page: QWidget, *, stack_pages: tuple[QWidget, ...] = ()) -> QWidget:
    """A minimal stand-in for the main window: ``ui.workspace_stack`` only.

    ``_active_workspace_page`` reads ``window.ui.workspace_stack.currentWidget()``
    and ``_resolve_canvas`` reads ``window.presenter`` (None here, so the
    layout measurement falls back to the declared floor).
    """
    window = QWidget()
    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    stack = QStackedWidget()
    layout.addWidget(stack)
    for extra in stack_pages:
        stack.addWidget(extra)
    stack.addWidget(page)
    stack.setCurrentWidget(page)
    window.ui = SimpleNamespace(workspace_stack=stack)
    window.presenter = None
    window._is_ui_stable = True
    return window


# -- the declaration itself ---------------------------------------------------


def test_declared_floor_covers_the_toolbar_and_the_page_padding(qapp):
    page = ImageGalleryWidget()
    try:
        floor_w, floor_h = page.window_minimum_size()
        margins = _page_margins(page)
        idle = page.toolbar.minimumSizeHint().width()
        assert floor_w >= idle, "the floor must not be narrower than the toolbar row"
        assert floor_w >= idle + margins.left() + margins.right()

        # Worst measured toolbar state (spinner + activity slot visible).
        page.toolbar.set_scanning(1, 10)
        scanning = page.toolbar.minimumSizeHint().width()
        assert scanning > idle, "precondition: the scanning slot really widens the row"
        assert floor_w >= scanning + margins.left() + margins.right()

        page.toolbar.set_triage_done()
        # Height: the floor must hold the page's own stacked rows.
        assert floor_h >= page.layout().minimumSize().height()
    finally:
        page.deleteLater()


def test_floor_is_design_space_not_scaled(qapp):
    """A scaled floor exceeds the user's saved window (session-picker rationale)."""
    from sli_ui_toolkit.managers import UiScale

    page = ImageGalleryWidget()
    try:
        baseline = page.window_minimum_size()
        UiScale.get_instance().set_factor(1.5)
        try:
            assert page.window_minimum_size() == baseline
        finally:
            UiScale.get_instance().set_factor(1.0)
    finally:
        page.deleteLater()


# -- the host window honours it ----------------------------------------------


def test_gallery_floor_reaches_the_host_window(qapp):
    page = ImageGalleryWidget()
    window = _host_window(page)
    try:
        from ui.layout_geometry import (
            apply_main_window_minimum,
            minimum_floor_for_main_window,
        )

        assert minimum_floor_for_main_window(window) == page.window_minimum_size()
        apply_main_window_minimum(window)
        floor_w, floor_h = page.window_minimum_size()
        assert window.minimumWidth() == floor_w
        assert window.minimumHeight() == floor_h

        # A resize below the floor is clamped, not honoured (Qt clamps a
        # hidden widget too — the window is never shown here on purpose: a
        # shown top-level would take focus from later keyboard/focus suites).
        window.resize(200, 200)
        assert window.width() >= floor_w
        assert window.height() >= floor_h
        # ... and the minimum itself never moved.
        assert window.minimumWidth() == floor_w
        assert window.minimumHeight() == floor_h
    finally:
        window.close()
        window.deleteLater()


# -- a tab switch re-applies it (presenter, not a timer) ---------------------


class _Session:
    def __init__(self, session_type: str) -> None:
        self.id = f"{session_type}-1"
        self.session_type = session_type
        self.title = session_type


class _SessionManager:
    def __init__(self, active: _Session) -> None:
        self._active = active

    def get_active_session(self):
        return self._active

    def list_sessions(self):
        return (self._active,)

    def switch_to_session(self, session_id: str) -> bool:
        return False


class _WorkspaceUi:
    """Mimics the host workspace UI: ``sync_session_mode`` swaps the stack page."""

    def __init__(self, stack: QStackedWidget, pages: dict[str, QWidget]) -> None:
        self._stack = stack
        self._pages = pages
        self.seen: list[str] = []

    def sync_workspace_tabs(self, sessions, active_session_id) -> None:
        return None

    def sync_session_mode(self, session_type: str, session_title=None) -> None:
        self.seen.append(session_type)
        page = self._pages.get(session_type)
        if page is not None:
            self._stack.setCurrentWidget(page)


def _presenter_for(window: QWidget, stack: QStackedWidget, pages, active: _Session):
    presenter = SimpleNamespace(
        session_manager=_SessionManager(active),
        ui=_WorkspaceUi(stack, pages),
        main_window_app=window,
        features=SimpleNamespace(),
    )
    return presenter


def test_tab_switch_reapplies_the_active_page_floor(qapp):
    """Presenters must re-derive the floor per activation, in BOTH directions.

    ``sync_session_mode`` (ui/presenters/main_window/workspace.py) is what a
    workspace state change reaches; it runs *after* the stack page swap, so the
    floor it applies belongs to the page that just became current. A stale
    (latching) minimum would keep the gallery's 970 px while a canvas tab is
    active — the canvas tabs must keep the 250 px base floor.
    """
    from ui.layout_geometry import MAIN_WINDOW_MIN_WIDTH_FLOOR
    from ui.presenters.main_window.workspace import sync_session_mode

    gallery = ImageGalleryWidget()
    other = QWidget()  # stand-in for a canvas tab page (declares no floor)
    window = _host_window(gallery, stack_pages=(other,))
    stack = window.ui.workspace_stack
    pages = {"image_gallery": gallery, "image_compare": other}

    sessions = {"image_gallery": _Session("image_gallery"), "image_compare": _Session("image_compare")}
    try:
        presenter = _presenter_for(window, stack, pages, sessions["image_gallery"])
        sync_session_mode(presenter)
        assert stack.currentWidget() is gallery
        floor_w, floor_h = gallery.window_minimum_size()
        assert window.minimumWidth() == floor_w
        assert window.minimumHeight() == floor_h

        # Switch away: the plain page declares nothing -> base floor is back.
        presenter.session_manager._active = sessions["image_compare"]
        sync_session_mode(presenter)
        assert stack.currentWidget() is other
        assert other.minimumWidth() < floor_w
        assert window.minimumWidth() == MAIN_WINDOW_MIN_WIDTH_FLOOR

        # And back again.
        presenter.session_manager._active = sessions["image_gallery"]
        sync_session_mode(presenter)
        assert window.minimumWidth() == floor_w
        assert presenter.ui.seen == [
            "image_gallery",
            "image_compare",
            "image_gallery",
        ]
    finally:
        window.close()
        window.deleteLater()


def test_canvas_tabs_keep_their_current_floor(qapp):
    """Image Compare / Multi Compare declare nothing -> the 250 px base floor."""
    from ui.layout_geometry import (
        MAIN_WINDOW_MIN_HEIGHT_FLOOR,
        MAIN_WINDOW_MIN_WIDTH_FLOOR,
        minimum_floor_for_main_window,
    )
    from tabs.image_compare.widget import ImageCompareWidget
    from tabs.multi_compare.widget import MultiCompareWidget

    for cls in (ImageCompareWidget, MultiCompareWidget):
        assert not hasattr(cls, "window_minimum_size"), (
            f"{cls.__name__} gained a window floor; declare its rationale here "
            "and update this test deliberately"
        )
        page = QWidget()
        window = _host_window(page)
        try:
            assert minimum_floor_for_main_window(window) == (
                MAIN_WINDOW_MIN_WIDTH_FLOOR,
                MAIN_WINDOW_MIN_HEIGHT_FLOOR,
            )
        finally:
            window.deleteLater()
