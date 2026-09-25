"""Overlay topology conformity (Wave E/C): default-deny harness.

Default-deny over ALL current and future overlays, regardless of class
names: every tab in ``TabRegistry`` owns a journey (parametrized from
``registered_types`` — a future tab becomes a journey automatically),
and every tab answers the generic
``create_service("topology_overlays", parent)`` hook with the list of
its window-parented modals (``[]`` when it owns none). The meta-assert
guards the hook instead of a table: a tab without the branch fails it.
Each journey runs against a REAL shell (``WorkspaceTabStrip`` +
``QStackedWidget`` + real tab pages, no fake doubles):

- snapshot globals before/after (focusWidget, activeWindow, mouse/keyboard
  grabbers, overrideCursor, topLevelWidgets set) and assert restored;
- walk ``main_window.findChildren(QWidget)``: any VISIBLE widget
  intersecting the strip band whose family is not allowlisted in
  ``tests/topology_allowlist.json`` FAILS;
- tab-switch step: activate another tab, assert no visible widget owned by
  the previous tab remains. The 3 grandfathered window-parented modals
  (QuickLook / CleanReview / PasteDirection) violate this by design:
  pinned with strict xfail (linked) so the suite stays green while the
  violation is documented. Grandfathered modals are NOT exempt from
  dismissal asserts.

Dogma source: Wave E topology conformity (default-deny harness),
Wave C isolation closure (generic hook consumption, zero concrete
tab references in tests/).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import json
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QStackedWidget, QWidget

ROOT = Path(__file__).resolve().parent.parent.parent
ALLOWLIST_PATH = ROOT / "tests" / "topology_allowlist.json"

WINDOW_W, WINDOW_H = 1280, 800
STRIP_H = 60

# Grandfathered window-parented modals: tab-switch ownership violations are
# known, documented, and pinned (strict xfail). Fixing the parenting removes
# the marker; XPASS-strict then goes red to force marker removal.
GRANDFATHERED_MODALS: dict[str, str] = {
    # Empty: all previously grandfathered tab modals (QuickLook,
    # CleanReview, PasteDirection) are dismissed on tab switch since the
    # modal-lifetime waves. Keep the dict + loop as the pinning mechanism:
    # re-adding a modal here re-arms its strict-xfail.
}


def load_allowlist() -> dict:
    return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))


def registry_types() -> list[str]:
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    registry.discover()
    return list(registry.registered_types)


def make_shell():
    """REAL shell: window + WorkspaceTabStrip + content host + real pages."""
    from tabs.contract import TabContext
    from tabs.registry import TabRegistry
    from ui.icon_manager import AppIcon
    from ui.widgets.workspace_tab_strip import WorkspaceTabStrip

    window = QWidget()
    window.setObjectName("MainWindow")
    window.setGeometry(0, 0, WINDOW_W, WINDOW_H)
    strip = WorkspaceTabStrip(
        add_icon=AppIcon.ADD, close_icon=AppIcon.CLOSE, parent=window
    )
    strip.setObjectName("WorkspaceTabsBar")
    strip.setGeometry(0, 0, WINDOW_W, STRIP_H)
    content = QWidget(window)
    content.setObjectName("workspace_content_widget")
    content.setGeometry(0, STRIP_H, WINDOW_W, WINDOW_H - STRIP_H)
    window.workspace_content_widget = content  # same exposure as LayoutComposer
    stack = QStackedWidget(content)
    stack.setObjectName("workspace_stack")
    stack.setGeometry(0, 0, WINDOW_W, WINDOW_H - STRIP_H)

    registry = TabRegistry()
    registry.discover()
    context = TabContext()
    pages: dict[str, QWidget] = {}
    for session_type in registry.registered_types:
        tab = registry.get_tab(session_type)
        page = tab.create_page(stack, context)  # REAL page, no doubles
        stack.addWidget(page)
        pages[session_type] = page
    stack.setCurrentWidget(pages[registry.registered_types[0]])
    window.show()
    QApplication.processEvents()
    return window, strip, content, stack, pages


def snapshot_globals() -> dict:
    app = QApplication.instance()
    return {
        "focus": app.focusWidget(),
        "active": app.activeWindow(),
        "mouse_grab": QWidget.mouseGrabber(),
        "keyboard_grab": QWidget.keyboardGrabber(),
        "cursor": app.overrideCursor(),
        "toplevels": set(app.topLevelWidgets()),
    }


def assert_globals_restored(before: dict, context: str) -> None:
    after = snapshot_globals()
    assert after["focus"] is before["focus"], f"{context}: focusWidget leaked"
    assert after["active"] is before["active"], (
        f"{context}: activeWindow changed "
        f"({before['active']!r} -> {after['active']!r})"
    )
    assert after["mouse_grab"] is None or after["mouse_grab"] is before["mouse_grab"], (
        f"{context}: mouseGrabber leaked ({after['mouse_grab']!r})"
    )
    assert after["keyboard_grab"] is None or after["keyboard_grab"] is before["keyboard_grab"], (
        f"{context}: keyboardGrabber leaked ({after['keyboard_grab']!r})"
    )
    assert after["cursor"] == before["cursor"], f"{context}: overrideCursor leaked"
    leaked = after["toplevels"] - before["toplevels"]
    assert not leaked, f"{context}: topLevelWidgets leaked: {leaked!r}"


def family_of(widget: QWidget, strip: QWidget, allowlist: dict) -> str | None:
    """Allowlisted family name, or None = violation (default-deny)."""
    if widget is strip or _is_descendant(widget, strip):
        return "strip"
    if isinstance(widget, QMenu):
        return "menu"
    if isinstance(widget, QDialog):
        return "dialog"
    object_name = widget.objectName() or ""
    class_name = type(widget).__name__
    for fam in (allowlist.get("strip_overlaps") or {}).get("families", []):
        by, pattern = fam.get("by"), fam.get("pattern") or ""
        if by == "objectname":
            import re

            if re.search(pattern, object_name):
                return fam.get("name")
        elif by == "classname":
            import re

            if re.search(pattern, class_name):
                return fam.get("name")
        elif by == "flag" and pattern == "QDialog" and isinstance(widget, QDialog):
            return fam.get("name")
    tab_modals = (allowlist.get("strip_overlaps") or {}).get("tab_modals", [])
    modal_classes = {entry.get("class") for entry in tab_modals}
    if class_name in modal_classes:
        return f"tab_modal:{class_name}"
    # The modal's whole subtree (cards, nav circles, grips) belongs to the
    # named modal: walk ancestors before default-denying.
    node = widget.parentWidget()
    for _ in range(100):
        if node is None:
            break
        try:
            ancestor_class = type(node).__name__
            node = node.parentWidget()
        except RuntimeError:
            break
        if ancestor_class in modal_classes:
            return f"tab_modal:{ancestor_class}"
    return None


def _is_descendant(widget: QWidget, ancestor: QWidget) -> bool:
    node = widget.parentWidget()
    for _ in range(100):
        if node is None:
            return False
        if node is ancestor:
            return True
        try:
            node = node.parentWidget()
        except RuntimeError:
            return False
    return False


def strip_band_global(strip: QWidget):
    from PySide6.QtCore import QRect

    top_left = strip.mapToGlobal(strip.rect().topLeft())
    return QRect(top_left, strip.size())


def assert_no_unlisted_strip_overlap(window: QWidget, strip: QWidget, allowlist: dict, context: str) -> None:
    band = strip_band_global(strip)
    violations: list[str] = []
    for widget in window.findChildren(QWidget):
        try:
            if not widget.isVisible():
                continue
            if widget.size().isEmpty():
                continue
            top_left = widget.mapToGlobal(widget.rect().topLeft())
            from PySide6.QtCore import QRect

            rect = QRect(top_left, widget.size())
            if not rect.intersects(band):
                continue
        except RuntimeError:
            continue
        if family_of(widget, strip, allowlist) is None:
            violations.append(
                f"{type(widget).__name__} objectName={widget.objectName()!r}"
            )
    assert not violations, f"{context}: unlisted strip-band overlap: {violations}"


def assert_no_previous_tab_widgets(window: QWidget, previous_tab: str, context: str) -> None:
    """No VISIBLE widget owned by the previous tab survives a tab switch."""
    lingering = []
    for widget in window.findChildren(QWidget):
        try:
            if not widget.isVisible():
                continue
            if widget.property("owner_tab") == previous_tab:
                lingering.append(type(widget).__name__)
        except RuntimeError:
            continue
    assert not lingering, (
        f"{context}: widgets owned by {previous_tab!r} visible after "
        f"tab switch: {lingering}"
    )


def show_overlays_for(session_type: str, window: QWidget) -> list[QWidget]:
    """Tab-owned overlays for the journey's tab via the generic hook.

    The tab's ``create_service("topology_overlays", parent)`` builds and
    shows its own grandfathered modals (or answers ``[]`` when it owns
    none). Unknown tabs fail open to ``[]`` without crashing. Every
    overlay is tagged owner_tab=<journey tab> for the switch-step assert.
    """
    from tabs.registry import TabRegistry

    tab = TabRegistry().get_tab(session_type)
    if tab is None:
        return []
    overlays = list(tab.create_service("topology_overlays", window) or [])
    for overlay in overlays:
        overlay.setProperty("owner_tab", session_type)
    QApplication.processEvents()
    return overlays


def test_meta_every_registry_tab_answers_topology_overlays_hook(qapp):
    """Every registered tab answers the generic overlays hook with a list.

    Guards the hook instead of a table: a future tab without a
    ``create_service("topology_overlays", parent)`` branch fails here
    (the base contract answers None) and must add one — ``[]`` when it
    owns no window-parented modals. Shown overlays are dismissed after
    the isinstance check so the meta-assert leaves no globals behind.
    """
    from tabs.registry import TabRegistry

    window = QWidget()
    shown: list[QWidget] = []
    try:
        registry = TabRegistry()
        registry.discover()
        missing = [t for t in registry.registered_types if registry.get_tab(t) is None]
        assert not missing, f"registered tabs without an instance: {missing}"
        for journey_tab in registry.registered_types:
            tab = registry.get_tab(journey_tab)
            assert tab is not None
            result = tab.create_service("topology_overlays", window)
            assert isinstance(result, list), (
                f"{journey_tab!r} does not answer "
                "create_service('topology_overlays', parent) with a list: "
                f"{result!r}"
            )
            shown.extend(result)
    finally:
        for overlay in shown:
            try:
                if hasattr(overlay, "dismiss"):
                    overlay.dismiss()
                else:
                    overlay.close()
            except RuntimeError:
                pass
        QApplication.processEvents()
        window.close()
        window.deleteLater()
@pytest.mark.parametrize("session_type", sorted(registry_types()))
def test_journey_topology_conformity(qapp, session_type):
    allowlist = load_allowlist()
    window, strip, content, stack, pages = make_shell()
    try:
        assert session_type in pages, f"no real page for {session_type!r}"
        before = snapshot_globals()

        # Step 1: activate this tab's real page.
        stack.setCurrentWidget(pages[session_type])
        QApplication.processEvents()
        assert_no_unlisted_strip_overlap(window, strip, allowlist, f"{session_type}:activated")

        # Step 2: show the journey overlays (real grandfathered modals where listed).
        overlays = show_overlays_for(session_type, window)
        for overlay in overlays:
            assert overlay.isVisible()
        if overlays:
            # Window-parented modal covers the strip band: allowed ONLY as a
            # listed tab_modal with dismissal proof (default-deny exercises here).
            assert_no_unlisted_strip_overlap(window, strip, allowlist, f"{session_type}:overlay-shown")

        # Step 3: tab-switch — activate another tab.
        others = [t for t in pages if t != session_type]
        assert others, "need >=2 real pages for the tab-switch step"
        stack.setCurrentWidget(pages[others[0]])
        QApplication.processEvents()

        # Step 4: previous-tab ownership. Grandfathered modals violate by
        # design (window-parented): pinned strict-xfail, suite stays green.
        # The grandfathered set derives from the shown overlays' runtime
        # class names — no per-tab tables. Manual strict semantics
        # (pytest.xfail has no strict kwarg here): XPASS fails the suite
        # to force marker removal once fixed.
        grandfathered = [
            type(overlay).__name__
            for overlay in overlays
            if type(overlay).__name__ in GRANDFATHERED_MODALS
        ]
        for modal in grandfathered:
            try:
                assert_no_previous_tab_widgets(window, session_type, f"{session_type}:switched")
            except AssertionError:
                pytest.xfail(
                    f"{GRANDFATHERED_MODALS[modal]}: {modal} is window-parented "
                    "and survives tab switches; reparent to content layer to un-xfail"
                )
            pytest.fail(
                f"XPASS(strict): {modal} no longer lingers after tab switch — "
                "remove the grandfathered xfail marker"
            )
        if not grandfathered:
            assert_no_previous_tab_widgets(window, session_type, f"{session_type}:switched")

        # Step 5: dismissal proof — grandfathered modals are NOT exempt.
        for overlay in overlays:
            if hasattr(overlay, "dismiss"):
                overlay.dismiss()
            else:
                overlay.close()
            QApplication.processEvents()
            assert not overlay.isVisible(), (
                f"{session_type}: {type(overlay).__name__} did not dismiss"
            )

        assert_globals_restored(before, f"{session_type}:journey")
    finally:
        window.close()
        window.deleteLater()


def test_help_dialog_releases_mouse_nav_filter_on_hide(qapp, qtbot):
    """Hide (not just close) must release the app-wide mouse-nav filter."""
    from PySide6.QtWidgets import QApplication

    from plugins.help.dialog import HelpDialog

    dialog = HelpDialog(current_language="en", app_name="Test")
    qtbot.addWidget(dialog)
    dialog.show()
    QApplication.processEvents()
    assert dialog._mouse_nav_filter is not None
    dialog.hide()
    QApplication.processEvents()
    assert dialog._mouse_nav_filter is None, "hideEvent did not release mouse-nav filter"
    dialog.show()
    QApplication.processEvents()
    dialog.close()
    QApplication.processEvents()
    assert dialog._mouse_nav_filter is None, "closeEvent did not release mouse-nav filter"
