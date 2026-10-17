"""The live keyboard-navigation model for the control channel (read side).

The app's keyboard cursor is **not** ``QApplication.focusWidget()``. Arrow keys
belong to ``sli_ui_toolkit``'s ``NavigationManager``, which keeps an ordered list
of *sections* (title bar → tab strip → session picker → a tab's toolbar/grid
rows) and hands a key to the section whose ``owns()`` accepts the focused
widget, delegating across section boundaries on a boundary key. Whole surfaces
(the Quick Look overlay, flyouts) instead handle keys in their own
``keyPressEvent`` and belong to no section at all — invisible to every Qt-level
read of focus.

``press_keys`` therefore cannot judge that model, and neither can
``ui_elements``: this module is the read half that can. It reports what the
model *is* over the live app:

* the ordered ``sections`` (section class + owner class + ``extra_keys``);
* the focus widget — the window's own, not only the app-wide one, because the
  control channel drives an app that may be in the background;
* the last keyboard-granted widget and the input modality;
* every open in-window overlay with the children Qt *could* focus, each
  carrying ``owned_by_section`` (``null`` = no section drives it: the honest
  "a keyboard cannot reach this" signal) and ``keyboard_ring`` (the toolkit's
  own cursor-visibility flag).

Key *delivery* lives in :mod:`core.control.nav_keys` — reads and writes are
separate tools, here and on the wire.

Live-only, GUI-thread only (the control server dispatches there).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from .elements.inventory import Element, collect_elements, rect_list, screen_rect_of

#: Overlay children reported in one call (a Quick Look overlay owns dozens).
MAX_OVERLAY_CHILDREN = 80


def nav_manager():
    """The toolkit ``NavigationManager`` singleton, or ``None`` (import-guarded)."""
    try:
        from sli_ui_toolkit.managers import NavigationManager

        return NavigationManager.get_instance()
    except Exception:
        return None


def _sections_of(manager) -> list[tuple[Any, Any]]:
    """Ordered ``(owner, section)`` pairs.

    Prefers a public ``sections()`` accessor when the toolkit grows one and
    falls back to the manager's own list, so the control channel never guesses
    the navigation graph from widget types.
    """
    if manager is None:
        return []
    accessor = getattr(manager, "sections", None)
    if callable(accessor):
        try:
            return [(owner, spec) for owner, spec in accessor()]
        except Exception:
            pass
    try:
        return [(owner, spec) for owner, spec in (getattr(manager, "_sections", None) or ())]
    except Exception:
        return []


def owner_of(manager, widget: QWidget | None) -> str | None:
    """Class name of the section that owns *widget*, or ``None``."""
    if widget is None or manager is None:
        return None
    for owner, spec in _sections_of(manager):
        try:
            if callable(getattr(spec, "owns", None)) and spec.owns(widget):
                return type(spec).__name__
        except Exception:
            continue
    return None


def _focus_policy_name(widget: QWidget) -> str:
    try:
        policy = widget.focusPolicy()
    except Exception:
        return "?"
    try:
        return policy.name
    except Exception:
        return str(policy)


def _keyboard_ring(widget: QWidget) -> bool | None:
    """The toolkit's own keyboard-ring flag (``None``: not a toolkit widget).

    The app draws the keyboard cursor from ``_keyboard_focus`` (see
    ``NavigationManager``), not from Qt's ``hasFocus()`` — so this is the
    honest "the user can see the cursor here" bit.
    """
    try:
        flag = getattr(widget, "_keyboard_focus", None)
    except Exception:
        return None
    return bool(flag) if isinstance(flag, bool) else None


def element_map(registry: Any) -> dict[int, Element]:
    """``id(widget)`` → its inventory element (so rows can carry element ids)."""
    try:
        collected = collect_elements(registry=registry, include_disabled=True)
    except Exception:
        return {}
    out: dict[int, Element] = {}
    for element in collected:
        out.setdefault(id(element.widget), element)
    return out


def widget_row(
    widget: QWidget | None,
    elements: dict[int, Element],
    manager,
) -> dict[str, Any] | None:
    """One widget's honest description, or ``None`` for "nothing focused"."""
    if widget is None:
        return None
    element = elements.get(id(widget))
    try:
        screen_rect: list[int] | None = rect_list(screen_rect_of(widget, widget.rect()))
    except Exception:
        screen_rect = None
    return {
        "widget": type(widget).__name__,
        "object_name": widget.objectName() if hasattr(widget, "objectName") else "",
        "label": element.label if element is not None else "",
        "role": element.role if element is not None else None,
        "element_id": element.id if element is not None else None,
        "focus_policy": _focus_policy_name(widget),
        "keyboard_ring": _keyboard_ring(widget),
        "owned_by_section": owner_of(manager, widget),
        "enabled": bool(element.enabled) if element is not None else None,
        "visible": bool(element.visible) if element is not None else None,
        "screen_rect": screen_rect,
    }


def focus_widget(window: Any) -> QWidget | None:
    """The focus widget the app itself would act on.

    The window's own ``focusWidget()`` comes first, even while that window is
    not the compositor's active one — the control channel drives an app that may
    be in the background, where ``QApplication.focusWidget()`` reports ``None``
    while the app's navigation still works off the in-window focus.
    """
    if isinstance(window, QWidget):
        try:
            child = window.focusWidget()
            if child is not None:
                return child
        except Exception:
            pass
    return QApplication.focusWidget()


def _focusables(root: QWidget) -> list[QWidget]:
    """Widgets under *root* that Qt would let a Tab reach (any area, visible)."""
    out: list[QWidget] = []
    try:
        children = root.findChildren(QWidget)
    except Exception:
        return out
    for child in children:
        try:
            if child.focusPolicy() == Qt.FocusPolicy.NoFocus:
                continue
            if not child.isVisibleTo(root) or not child.isEnabled():
                continue
            if child.width() <= 0 or child.height() <= 0:
                continue
        except Exception:
            continue
        out.append(child)
    return out


def _overlays(
    window: QWidget | None,
    elements: dict[int, Element],
    manager,
    focused: QWidget | None,
) -> list[dict[str, Any]]:
    """Visible in-window overlays (Quick Look, clean review, flyouts) with their
    focusable children and whether any navigation section owns them."""
    if window is None:
        return []
    rows: list[dict[str, Any]] = []
    try:
        children = window.findChildren(QWidget)
    except Exception:
        return rows
    for child in children:
        if not type(child).__name__.endswith("Overlay"):
            continue
        try:
            if not child.isVisible() or child.isWindow():
                continue
        except Exception:
            continue
        focusables = _focusables(child)
        row = widget_row(child, elements, manager) or {}
        row.update(
            {
                "children_total": len(focusables),
                "children_shown": min(len(focusables), MAX_OVERLAY_CHILDREN),
                "children_truncated": len(focusables) > MAX_OVERLAY_CHILDREN,
                "focused_child": widget_row(focused, elements, manager)
                if focused is not None and child.isAncestorOf(focused)
                else None,
                "children": [
                    widget_row(item, elements, manager)
                    for item in focusables[:MAX_OVERLAY_CHILDREN]
                ],
            }
        )
        rows.append(row)
    return rows


def _modality(manager) -> dict[str, Any]:
    payload: dict[str, Any] = {"last_input_was_keyboard": None, "focus_reason": None}
    if manager is None:
        return payload
    try:
        payload["last_input_was_keyboard"] = bool(manager.last_input_was_keyboard())
    except Exception:
        pass
    try:
        payload["focus_reason"] = manager.current_focus_reason().name
    except Exception:
        pass
    return payload


def _key_names(keys) -> list[str]:
    out: list[str] = []
    for key in keys or ():
        try:
            out.append(Qt.Key(key).name)
        except Exception:
            out.append(str(key))
    return out


def extra_keys_of(spec) -> list[str]:
    """A section's claimed extra keys, names sorted.

    ``NavigationSection.extra_keys`` is a *method* (the toolkit's protocol and
    the flyout sections implement it; app sections often omit it entirely), so
    this calls it when callable — reading it as an attribute crashed
    ``ui_nav_state`` the first time a section that declares it was registered
    (the Quick Look section, 2026-10-17).
    """
    raw = getattr(spec, "extra_keys", None)
    if callable(raw):
        try:
            raw = raw()
        except Exception:
            raw = None
    return sorted(_key_names(raw or ()))


def nav_state_payload(*, registry: Any, app: Any, window: Any) -> dict[str, Any]:
    """The live navigation model: sections, focus, modality, open overlays."""
    manager = nav_manager()
    elements = element_map(registry)
    focused = focus_widget(window)
    last_keyboard = None
    try:
        last_keyboard = manager.last_keyboard_focus() if manager is not None else None
    except Exception:
        last_keyboard = None
    sections = [
        {
            "index": index,
            "section": type(spec).__name__,
            "owner": type(owner).__name__,
            "extra_keys": extra_keys_of(spec),
        }
        for index, (owner, spec) in enumerate(_sections_of(manager))
    ]
    return {
        "source": "live",
        "modality": _modality(manager),
        "focus": widget_row(focused, elements, manager),
        "last_keyboard_focus": widget_row(last_keyboard, elements, manager),
        "owner_section": owner_of(manager, focused),
        "sections": sections,
        "sections_count": len(sections),
        "overlays": _overlays(window, elements, manager, focused),
    }


__all__ = [
    "MAX_OVERLAY_CHILDREN",
    "element_map",
    "extra_keys_of",
    "focus_widget",
    "nav_manager",
    "nav_state_payload",
    "owner_of",
    "widget_row",
]
