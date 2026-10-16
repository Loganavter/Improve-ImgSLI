"""Local layout-sizing primitives owned by the video-editor plugin.

``tabs.host_helpers`` (the tab-isolation seam) re-exports these three helpers
from the shared-toolkit layout-sizing module. Tab code may not import that
platform package directly (``tests/contracts/test_tabs_isolation.py``), and
the video editor should not depend on the seam for primitives it can own
itself, so this module carries verbatim-equivalent local copies. Behavior is
identical to the shared-toolkit original.

Only the three primitives the plugin actually uses live here. The
platform-internal layout machinery (``apply_dialog_geometry``,
``GeometryApplyPolicy``, font-change handling) stays on the seam.
"""

from __future__ import annotations

from PySide6.QtWidgets import QScrollArea, QWidget


def clamp(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def widget_width_hint(widget: QWidget | None, *, default: int = 0) -> int:
    if widget is None:
        return default
    widget.ensurePolished()
    widget.adjustSize()
    return max(default, widget.sizeHint().width())


def tab_widget_intrinsic_width(
    tabs: QWidget | None,
    *,
    page_padding: int = 0,
    default: int = 0,
) -> int:
    """Intrinsic width for ``QTabWidget`` or duck-typed hosts (``TopTabHost``).

    Intentionally does **not** call ``adjustSize()`` on live pages — that shrinks
    them to ``sizeHint`` and fights parent layouts (fields stay narrow inside a
    wider pane).
    """
    if tabs is None:
        return default

    tabs.ensurePolished()
    width = 0
    tab_bar = tabs.tabBar() if hasattr(tabs, "tabBar") else None
    if tab_bar is not None:
        tab_bar.ensurePolished()
        width = max(width, tab_bar.sizeHint().width())

    count = int(tabs.count()) if hasattr(tabs, "count") else 0
    for index in range(count):
        page = tabs.widget(index) if hasattr(tabs, "widget") else None
        if page is None:
            continue
        page.ensurePolished()
        width = max(width, page.sizeHint().width() + page_padding)
        scroll_area = page.findChild(QScrollArea)
        if scroll_area is not None:
            content = scroll_area.widget()
            if content is not None:
                content.ensurePolished()
                width = max(width, content.sizeHint().width() + page_padding)
    return max(default, width)


__all__ = [
    "clamp",
    "tab_widget_intrinsic_width",
    "widget_width_hint",
]
