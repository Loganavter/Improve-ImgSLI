"""Frozen action catalog types for Find Action / command palette."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActionTarget:
    """Explicit chrome widget ref for highlight / "show me where".

    Pass the live widget at registration time when it already exists — do not
    reverse-lookup by attribute name (``getattr(widget, "btn_x")``).

    Variants:
    - ``widget`` — pulse this control
    - ``widget`` + ``menu_action_id`` — open that title-bar menu and pulse the row
    - ``ensure_visible`` + ``resolve_widget`` — bring UI on screen (e.g. session
      picker), then pulse whatever ``resolve_widget`` returns
    - ``widget_family`` — resolve via ``WidgetRegistry`` (lazy, class-level)
    """

    widget: object | None = None
    menu_action_id: str | None = None
    ensure_visible: Callable[[], None] | None = None
    resolve_widget: Callable[[], object | None] | None = None
    widget_family: str | None = None

    def resolve_widget_instance(self) -> object | None:
        """Resolve the target widget, trying all resolution strategies."""
        # 1. Direct widget reference
        if self.widget is not None:
            return self.widget
        # 2. Lazy resolver
        if self.resolve_widget is not None:
            return self.resolve_widget()
        # 3. Widget family → WidgetRegistry → live widget instance
        if self.widget_family is not None:
            return _resolve_by_family(self.widget_family)
        return None


def _resolve_by_family(family: str) -> object | None:
    """Find a live widget instance by its ``WidgetDescriptor.family`` name.

    Walks all top-level widgets and their children looking for a widget
    whose ``widget_descriptor.family`` matches.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return None

    seen: set[int] = set()

    def _search(widget) -> object | None:
        wid = id(widget)
        if wid in seen:
            return None
        seen.add(wid)

        desc = getattr(widget, "widget_descriptor", None)
        if desc is not None and getattr(desc, "family", None) == family:
            return widget

        for child in widget.children():
            if isinstance(child, QWidget):
                result = _search(child)
                if result is not None:
                    return result
        return None

    from PySide6.QtWidgets import QWidget

    for w in app.topLevelWidgets():
        result = _search(w)
        if result is not None:
            return result
    return None


@dataclass(frozen=True, slots=True)
class ActionDescriptor:
    """One searchable, runnable host or tab action."""

    action_id: str
    label_key: str
    description_key: str | None = None
    breadcrumb: tuple[str, ...] = ()
    owner_tab: str | None = None
    topic: str | None = None
    shortcut: str | None = None
    help_page: str | None = None
    help_anchor: str | None = None
    # i18n keys resolved at query time, in addition to label/description/breadcrumb.
    search_keys: tuple[str, ...] = ()
    # Literal tokens (ids, English backend names) that are not i18n keys.
    search_terms: tuple[str, ...] = ()
    # Explicit position in the empty (unfiltered) palette, e.g. a Settings
    # page followed by its groups and their member slots. Empty means "no
    # preference" — falls back to id-based ordering. Owners set this instead
    # of encoding hierarchy into the action id for the palette to parse back.
    sort_key: tuple[int, ...] = ()
    run: Callable[[], None] | None = None
    target: ActionTarget | None = None