"""Headless dump of the live widget tree — layout + geometry + bound actions.

Complements the Find Action catalog (``ui/actions/registry.py``), which lists
*what* the app can do but not *where* those controls sit. This walks the real
widget tree from a running window and cross-references each widget against
the ``ActionRegistry`` so the output answers both questions in one JSON blob.

Launch via ``launcher.sh run --dump-ui-layout <path>`` (see ``__main__.py``).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from ui.actions.registry import ActionRegistry


def _widget_action_map(registry: ActionRegistry) -> dict[int, list[str]]:
    """Map live widgets to the action ids that target them.

    Two kinds of ``ActionTarget``: a fixed ``widget`` (toolbar buttons — see
    ``_action_chrome_is_available``'s ``isHidden`` check), or a lazy
    ``resolve_widget()`` (flyout/panel members that exist as real widgets
    before their container is ever shown — sliders, color swatches,
    visibility-flyout buttons). Calling ``resolve_widget()`` costs nothing
    extra here since it never triggers ``ensure_visible`` — it just returns
    the widget reference the action already captured at registration time.
    """
    mapping: dict[int, list[str]] = {}
    for action in registry.all_actions():
        target = action.target
        if target is None:
            continue
        widget = getattr(target, "widget", None)
        if widget is not None:
            mapping.setdefault(id(widget), []).append(action.action_id)
        resolve = getattr(target, "resolve_widget", None)
        if callable(resolve):
            try:
                resolved = resolve()
            except Exception:
                resolved = None
            if resolved is not None and resolved is not widget:
                mapping.setdefault(id(resolved), []).append(action.action_id)
    return mapping


def _text_of(widget: QWidget) -> str | None:
    """Best-effort label/value text, duck-typed across Qt and toolkit widgets.

    ``Button`` (sli-ui-toolkit) has no public text getter, so this falls back
    to its private ``_text`` attribute — acceptable for a debug-only dumper.
    """
    for attr in ("text", "currentText", "placeholderText"):
        getter = getattr(widget, attr, None)
        if callable(getter):
            try:
                value = getter()
            except Exception:
                continue
            if value:
                return str(value)
    fallback = getattr(widget, "_text", None)
    if fallback:
        return str(fallback)
    return None


def _range_of(widget: QWidget) -> dict[str, int] | None:
    getters = [getattr(widget, name, None) for name in ("value", "minimum", "maximum")]
    if not all(callable(g) for g in getters):
        return None
    try:
        value, minimum, maximum = (g() for g in getters)
    except Exception:
        return None
    return {"value": value, "min": minimum, "max": maximum}


def _node(widget: QWidget, action_map: dict[int, list[str]]) -> dict[str, Any]:
    geo = widget.geometry()
    node: dict[str, Any] = {
        "class": type(widget).__name__,
        "object_name": widget.objectName(),
        "geometry": [geo.x(), geo.y(), geo.width(), geo.height()],
        "visible": widget.isVisible(),
        "enabled": widget.isEnabled(),
    }
    text = _text_of(widget)
    if text:
        node["text"] = text
    tooltip = widget.toolTip()
    if tooltip:
        node["tooltip"] = tooltip
    range_info = _range_of(widget)
    if range_info is not None:
        node["range"] = range_info
    layout = widget.layout()
    if layout is not None:
        node["layout"] = type(layout).__name__
    action_ids = action_map.get(id(widget))
    if action_ids:
        node["action_ids"] = sorted(action_ids)
    children = [
        _node(child, action_map)
        for child in widget.findChildren(
            QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
        )
    ]
    if children:
        node["children"] = children
    return node


def dump_ui_layout(root: QWidget, registry: ActionRegistry) -> dict[str, Any]:
    """Recursively snapshot ``root``'s widget tree, tagging each node with the
    Find Action ids (if any) whose ``ActionTarget.widget`` is that exact widget.
    """
    return _node(root, _widget_action_map(registry))


def dump_all_windows(registry: ActionRegistry) -> dict[str, Any]:
    """Snapshot every top-level window in the process, not just the main one.

    Settings, Help, Video Editor, Export, … are separate top-level widgets
    (``QApplication.topLevelWidgets()``), most built lazily on first open —
    they only appear here once something has actually shown them (e.g. via
    ``--run-action platform.settings``). Includes hidden/closed-but-not-yet
    -destroyed windows; check each node's own ``visible`` field.
    """
    action_map = _widget_action_map(registry)
    app = QApplication.instance()
    windows = list(app.topLevelWidgets()) if app is not None else []
    return {"windows": [_node(w, action_map) for w in windows]}
