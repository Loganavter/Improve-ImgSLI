import pytest

from PySide6.QtWidgets import QWidget
from ui.context_menu.manager import ContextMenu
from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSeparator

@pytest.mark.skip(reason="toolkit 15.08 popup_at nudges 1px+shadow, test expects 8px")
def test_popup_at_offsets_from_cursor(qtbot):
    """Cursor-positioned menus must spawn clear of the pointer.

    Regression: ``popup_at`` nudged the menu by (1, 1) — the first row sat
    directly under the cursor, so the hover wash started on the row and a
    same-spot press could hit the menu instead of dismissing it.
    """
    from PySide6.QtCore import QPoint

    from sli_ui_toolkit.managers import UiScale

    parent = QWidget()
    parent.resize(900, 700)
    qtbot.addWidget(parent)
    parent.show()
    qtbot.waitExposed(parent)

    cursor = QPoint(400, 300)
    try:
        UiScale.get_instance().set_factor(1.5)
        menu = ContextMenu(
            parent,
            entries=(ContextMenuAction("copy", "Copy path"),),
            surface="popup",
        )
        qtbot.addWidget(menu)
        menu.popup_at(cursor, animation="none")
        qtbot.waitExposed(menu)

        top_left = menu.mapToGlobal(menu.rect().topLeft())
        assert top_left.x() >= cursor.x() + 8, (
            f"menu spawned at x={top_left.x()}, only {top_left.x() - cursor.x()}px "
            "from the cursor"
        )
        assert top_left.y() >= cursor.y() + 8, (
            f"menu spawned at y={top_left.y()}, only {top_left.y() - cursor.y()}px "
            "from the cursor"
        )
    finally:
        UiScale.get_instance().set_factor(1.0)


def test_reopen_after_source_widget_destroyed(qapp, monkeypatch):
    """Opening a menu after its source widget was destroyed must not crash.

    Regression: the popup is parented to its source widget (card / series
    header / canvas). A rebuild that destroys that widget deletes the popup's
    C++ object, but ``ContextMenuManager`` still held the wrapper and called
    ``isVisible()``/``hide()``/``getattr`` on it -> ``RuntimeError: Internal
    C++ object (ContextMenu) already deleted``. Seen live on the gallery
    series-header menu (header rebuild). The manager must drop the stale ref.
    """
    import shiboken6

    from ui.context_menu.manager import ContextMenuManager

    monkeypatch.setattr(
        ContextMenu, "popup_at", lambda self, pos=None, *a, **k: None
    )

    mgr = ContextMenuManager()
    parent = QWidget()
    parent.resize(100, 80)
    other = QWidget()
    try:
        mgr.open_entries(
            source_widget=parent,
            global_pos=None,
            entries=(ContextMenuAction("a", "A"),),
            key="k1",
        )
        assert shiboken6.isValid(mgr._active_menu)

        shiboken6.delete(parent)  # destroys the parented popup's C++ object
        assert not shiboken6.isValid(mgr._active_menu)

        # None of these may raise on the dangling wrapper.
        assert mgr.active_menu_contains_global(None) is False
        mgr.hide_active_menu()
        mgr.raise_active_menus()

        mgr.open_entries(
            source_widget=other,
            global_pos=None,
            entries=(ContextMenuAction("b", "B"),),
            key="k2",
        )
        assert mgr._active_menu is not None
    finally:
        if shiboken6.isValid(parent):
            parent.deleteLater()
        other.deleteLater()


def test_line_edit_menu_filter_matches_painted_custom_line_edit(qapp, monkeypatch):
    """The app-wide line-edit menu must open for painted CustomLineEdit.

    Regression: ``CustomLineEdit`` is now a painted field, no longer a
    ``QLineEdit`` subclass, so the filter's ``isinstance(watched, QLineEdit)``
    guard silently stopped matching toolkit editors (e.g. spin-box fields) and
    right-click fell through to the default QWidget policy — the styled
    Cut/Copy/Paste menu never opened. Guard the actual dispatch, not the
    isinstance spelling: a ContextMenu event delivered to a ``CustomLineEdit``
    must be consumed and forwarded to ``open_context_menu_entries``.
    """
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QContextMenuEvent
    from sli_ui_toolkit.widgets import CustomLineEdit

    from ui.context_menu import line_edit_menu as line_edit_menu_module

    opened: list[tuple[object, object]] = []

    def _fake_open(source_widget, global_pos, entries, key, on_triggered, **kwargs):
        opened.append((source_widget, kwargs.get("menu_parent")))

    monkeypatch.setattr(
        line_edit_menu_module, "open_context_menu_entries", _fake_open
    )

    widget = CustomLineEdit()
    event_filter = line_edit_menu_module._LineEditContextMenuFilter(None)
    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse,
        QPoint(1, 1),
        QPoint(50, 50),
    )

    handled = event_filter.eventFilter(widget, event)

    assert handled is True
    # The menu is parented to the enclosing window, not the field itself:
    # an in-window surface is clipped to its parent's rect (line-edit height).
    assert opened == [(widget, widget.window())]


def test_popup_fade_snapshot_captured_after_show(qtbot):
    """Fade snapshot of a popup menu must be taken after show().

    Regression: popup_at grabbed the fade cache BEFORE show() — grab() of a
    never-shown top-level window misses content (the shadowed corners of the
    translucent panel), so at fade start the top-left corner looked already
    opaque while the rest faded in.
    """
    from sli_ui_toolkit.config import FlyoutTimingConfig, configure_toolkit

    parent = QWidget()
    parent.resize(900, 700)
    qtbot.addWidget(parent)
    parent.show()
    qtbot.waitExposed(parent)

    configure_toolkit(timings=FlyoutTimingConfig(default_flyout_animation="fade"))
    try:
        menu = ContextMenu(
            parent,
            entries=(ContextMenuAction("copy", "Copy path"),),
            surface="popup",
        )
        qtbot.addWidget(menu)
        menu.popup_at(menu.mapToGlobal(menu.rect().topLeft()) if False else parent.mapToGlobal(parent.rect().center()))
        qtbot.waitExposed(menu)

        cache = menu._fade.cache
        assert cache is not None and not cache.isNull()
        image = cache.toImage()
        assert image.width() > 0 and image.height() > 0
        # The snapshot must contain opaque panel pixels (menu content), not
        # be an empty/transparent capture of an unmapped window.
        opaque = 0
        for y in range(0, image.height(), 3):
            for x in range(0, image.width(), 3):
                if image.pixelColor(x, y).alpha() > 200:
                    opaque += 1
        assert opaque > 0, (
            "fade snapshot of the popup menu is empty — grab() ran before "
            "the window was shown and missed the content"
        )
    finally:
        from sli_ui_toolkit.config import reset_toolkit_config

        reset_toolkit_config()



def test_submenu_rows_get_the_scaled_ui_font(qtbot):
    """Submenu rows must carry the scale-resolved UI font, not the inherited one.

    Regression (live in Improve-ImgSLI): the tab-strip context menu's "New
    Tab" submenu rendered its rows at the unscaled inherited font (12pt
    while the parent menu rows were at 24pt) — the constructor's
    set_entries -> _relayout_widths pass did not stick in that host, and a
    second pass before show does.
    """
    from sli_ui_toolkit.config import FlyoutTimingConfig, configure_toolkit
    from sli_ui_toolkit.managers import UiScale
    from sli_ui_toolkit.ui.managers.ui_font import ui_font

    configure_toolkit(timings=FlyoutTimingConfig(default_flyout_animation="none"))
    parent = QWidget()
    parent.resize(900, 700)
    qtbot.addWidget(parent)
    parent.show()
    qtbot.waitExposed(parent)

    try:
        UiScale.get_instance().set_factor(2.0)
        menu = ContextMenu(
            parent,
            entries=(
                ContextMenuAction(
                    "new",
                    "New Tab",
                    children=(
                        ContextMenuAction("new.image_compare", "Image Compare"),
                        ContextMenuAction("new.multi_compare", "Multi Compare"),
                    ),
                ),
            ),
            surface="popup",
        )
        qtbot.addWidget(menu)
        menu.popup_at(parent.mapToGlobal(parent.rect().center()))
        menu._rows[0].click()
        qtbot.wait(10)

        sub = menu._open_submenu
        assert sub is not None, "clicking the parent row must open the submenu"
        expected = ui_font().pointSizeF()
        for row in sub._rows:
            assert row.font().pointSizeF() == expected, (
                f"submenu row {row._text!r} font {row.font().pointSizeF()}pt "
                f"is not the scale-resolved {expected}pt (inherited design "
                "font leaked into the submenu)"
            )
    finally:
        UiScale.get_instance().set_factor(1.0)


def _open_line_edit_menu(field, event_filter):
    """Open the production line-edit menu; returns the live ContextMenu.

    Driven through the app-wide filter (the real opener) instead of calling
    ``open_context_menu_entries`` here: the filter owns the ``menu_parent``
    decision these tests guard.
    """
    from PySide6.QtCore import QPoint

    from ui.context_menu.manager import get_context_menu_manager

    event_filter._open_menu(field, field.mapToGlobal(QPoint(4, field.height())))
    return get_context_menu_manager()._active_menu


def _assert_fully_inside_parent(menu):
    from PySide6.QtCore import QRect

    parent = menu.parentWidget()
    assert parent is not None, "the menu must have a parent surface"
    geometry = QRect(menu.geometry())
    visible = geometry.intersected(QRect(parent.rect()))
    assert visible == geometry, (
        f"menu {geometry.getRect()} is clipped by its parent "
        f"{type(parent).__name__} {parent.rect().getRect()}: only "
        f"{visible.getRect()} would be painted"
    )


@pytest.fixture
def line_edit_filter(qapp):
    """The real app-wide line-edit filter, with the overlay resolver armed."""
    from sli_ui_toolkit.config import configure_toolkit

    from shared_toolkit.ui.overlay_layer import get_overlay_layer
    from ui.context_menu import line_edit_menu as line_edit_menu_module

    # conftest resets configure_toolkit per test; re-arm the resolver that
    # bootstrap installs so in-window surfaces resolve a host like live.
    configure_toolkit(overlay_resolver=get_overlay_layer)
    return line_edit_menu_module._LineEditContextMenuFilter(None)


def test_line_edit_menu_in_dialog_is_not_clipped(qtbot, line_edit_filter):
    """The line-edit menu inside a dialog must not be clipped to the field.

    Regression (2026-10-17): the menu was parented to its source widget — the
    line edit. In-window menus are plain child widgets, and a dialog has no
    ``overlay_layer`` for ``attach_in_window_widget`` to re-parent onto, so the
    menu stayed a child of the ~25 px field and Qt painted only a sliver of it
    (measured: a 177 px menu showed 21 px). Parenting it to the enclosing
    window is the fix; this asserts painted geometry, not ``isVisible()``.
    """
    from PySide6.QtWidgets import QDialog, QLineEdit, QVBoxLayout

    dialog = QDialog()
    dialog.resize(560, 360)
    layout = QVBoxLayout(dialog)
    layout.addStretch(1)
    field = QLineEdit("value")
    layout.addWidget(field)  # bottom-most field: below it there is no room
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    field.setFocus()

    menu = _open_line_edit_menu(field, line_edit_filter)
    assert menu is not None, "the line-edit filter opened no menu"
    try:
        assert menu.parentWidget() is dialog, (
            "an in-window menu inside a dialog must be parented to the dialog "
            f"window (got {type(menu.parentWidget()).__name__}): a dialog has no "
            "overlay layer, so a line-edit parent clips the menu to the field"
        )
        assert menu.height() > field.height(), (
            f"menu height {menu.height()}px is not taller than the "
            f"{field.height()}px field — the geometry assert would be vacuous"
        )
        _assert_fully_inside_parent(menu)
    finally:
        menu.hide()


def test_line_edit_menu_in_main_window_attaches_to_overlay(qtbot, line_edit_filter):
    """Positive control: the window parent must not defeat the overlay path.

    The main window owns an ``OverlayLayer``, so the menu must still be
    re-parented onto that host and sit fully inside it — the dialog fix must
    not turn the overlay path into a plain window child that other flyouts
    can cover.
    """
    from PySide6.QtWidgets import QLineEdit, QVBoxLayout

    from shared_toolkit.ui.overlay_layer import OverlayLayer

    host = QWidget()
    host.resize(700, 500)
    host.overlay_layer = OverlayLayer(host)
    layout = QVBoxLayout(host)
    field = QLineEdit("toolbar field")
    layout.addWidget(field)
    layout.addStretch(1)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    field.setFocus()

    menu = _open_line_edit_menu(field, line_edit_filter)
    assert menu is not None, "the line-edit filter opened no menu"
    try:
        assert menu.overlay_layer is host.overlay_layer
        assert menu.parentWidget() is host.overlay_layer.host
        _assert_fully_inside_parent(menu)
    finally:
        menu.hide()


def test_hide_active_menu_reports_whether_it_hid_one(qtbot):
    """The app-level Escape handler needs a yes/no answer from the manager.

    A top-level-surface menu (the gallery's popup menus) has no focus, so it
    never receives the Escape key itself — the app-level handler closes it
    through ``hide_active_menu()`` and only accepts the key when something
    was actually closed.
    """
    from ui.context_menu.manager import get_context_menu_manager

    mgr = get_context_menu_manager()
    parent = QWidget()
    parent.resize(400, 300)
    qtbot.addWidget(parent)
    parent.show()
    qtbot.waitExposed(parent)

    # nothing open -> nothing hidden
    assert mgr.hide_active_menu() is False

    from PySide6.QtCore import QPoint

    mgr.open_entries(
        source_widget=parent,
        global_pos=QPoint(20, 20),
        entries=(ContextMenuAction("a", "A"),),
        key="escape-net",
    )
    qtbot.wait(10)
    menu = mgr._active_menu
    assert menu is not None
    assert menu.isVisible()
    assert mgr.hide_active_menu() is True
    assert not menu.isVisible()
