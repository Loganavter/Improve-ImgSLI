"""Headless dump of the live widget tree — layout + geometry + bound actions.

Complements the Find Action catalog (``ui/actions/registry.py``), which lists
*what* the app can do but not *where* those controls sit. This walks the real
widget tree from a running window and cross-references each widget against
the ``ActionRegistry`` so the output answers both questions in one JSON blob.

Launch via ``launcher.sh run --dump-ui-layout <path>`` (see ``__main__.py``).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRect, QRectF, QSize, QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QWidget

from ui.actions.registry import ActionRegistry


def _jsonable(value):
    """Best-effort JSON-safe conversion for inspector state values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        import enum

        if isinstance(value, enum.Enum):
            return value.name
    except Exception:
        pass
    if isinstance(value, QColor):
        try:
            return value.name()
        except Exception:
            return str(value)
    if isinstance(value, QRect):
        return [value.x(), value.y(), value.width(), value.height()]
    if isinstance(value, QRectF):
        return [value.x(), value.y(), value.width(), value.height()]
    if isinstance(value, QSize):
        return [value.width(), value.height()]
    if isinstance(value, QPoint):
        return [value.x(), value.y()]
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value][:32]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in list(value.items())[:32]}
    try:
        text = str(value)
    except Exception:
        return "<?>"
    return text if len(text) <= 200 else text[:200] + "…"


def _resolve_state_field(widget: QWidget, field) -> tuple[str, Any] | None:
    """Resolve one inspector ``SpecField`` against a live widget.

    Mirrors the toolkit inspector's own resolution (plain attribute first,
    then zero-arg method call) without pulling the full inspection build —
    the dump walks thousands of nodes and only needs the declared state.
    """
    source = getattr(field, "source", None) or getattr(field, "label", "")
    label = getattr(field, "label", None) or str(source)
    if not source or not label:
        return None
    try:
        if callable(source) and not isinstance(source, str):
            return label, _jsonable(source(widget))
        value = getattr(widget, source, None)
        if callable(value):
            try:
                value = value()
            except Exception:
                return None
        if value is None:
            return None
        return label, _jsonable(value)
    except Exception:
        return None


def _spec_state(widget: QWidget) -> tuple[str | None, dict[str, Any] | None]:
    """Declared inspector state for ``widget`` (family + state dict).

    Returns ``(None, None)`` when the widget declares no spec — most stock
    Qt widgets. Reads only ``state`` fields (never ``config`` constructors),
    so even hidden subtrees explain themselves: e.g. a closed flyout still
    reports its mode, active panel, and item counts.
    """
    try:
        from sli_ui_toolkit.ui.inspector.spec import spec_of
    except Exception:
        return None, None
    try:
        spec = spec_of(widget)
    except Exception:
        return None, None
    if spec is None:
        return None, None
    family = getattr(spec, "family", None)
    state: dict[str, Any] = {}
    try:
        fields = getattr(spec, "state", None) or ()
    except Exception:
        fields = ()
    for field in fields:
        resolved = _resolve_state_field(widget, field)
        if resolved is not None:
            state[resolved[0]] = resolved[1]
    return family, (state or None)


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
        value, minimum, maximum = (g() for g in getters)  # type: ignore[misc]  # guarded by all(callable) above
    except Exception:
        return None
    return {"value": value, "min": minimum, "max": maximum}


def _node(
    widget: QWidget,
    action_map: dict[int, list[str]],
    used_families: dict[str, tuple] | None = None,
) -> dict[str, Any]:
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
    family, state = _spec_state(widget)
    if family:
        node["family"] = family
        if used_families is not None:
            try:
                from sli_ui_toolkit.ui.inspector.spec import spec_of
            except Exception:
                spec_of = None  # type: ignore[assignment]
            if spec_of is not None:
                try:
                    spec = spec_of(widget)
                    tokens = tuple(getattr(spec, "token_family", None) or ())
                except Exception:
                    tokens = ()
                if tokens:
                    used_families.setdefault(family, tokens)
    if state:
        node["state"] = state
    action_ids = action_map.get(id(widget))
    if action_ids:
        node["action_ids"] = sorted(action_ids)
    children = [
        _node(child, action_map, used_families)
        for child in widget.findChildren(
            QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
        )
    ]
    if children:
        node["children"] = children
    return node


def _resolve_theme_tokens(used_families: dict[str, tuple]) -> dict[str, Any]:
    """Resolve ``token_family`` tokens per widget family: direct value.

    Answers "where does this color come from" for any dumped widget.
    Tokens resolve directly via ``try_get_color`` — no remapping, no
    alias chains. Best-effort: never breaks the dump.
    """
    try:
        from sli_ui_toolkit.theme import ThemeManager
    except Exception:
        return {}
    try:
        from devtools.ui_inspector.theme_sources import token_sources
    except Exception:
        token_sources = None  # type: ignore[assignment]
    try:
        manager = ThemeManager.get_instance()
    except Exception:
        return {}
    try:
        sources = token_sources(manager) if token_sources is not None else {}
    except Exception:
        sources = {}
    theme: dict[str, Any] = {}
    for family, tokens in used_families.items():
        resolved: dict[str, Any] = {}
        for token in tokens:
            try:
                chain = [str(token)]
                try:
                    color = manager.try_get_color(str(token))
                    value = color.name() if color is not None else None
                except Exception:
                    value = None
                terminal = chain[-1]
                if terminal in sources:
                    source = sources[terminal]
                elif value is None:
                    source = "missing"
                else:
                    source = "palette"
                resolved[str(token)] = {
                    "value": value,
                    "chain": chain if len(chain) > 1 else None,
                    "source": source,
                }
            except Exception:
                continue
        if resolved:
            theme[family] = resolved
    return theme


def dump_ui_layout(root: QWidget, registry: ActionRegistry) -> dict[str, Any]:
    """Recursively snapshot ``root``'s widget tree, tagging each node with the
    Find Action ids (if any) whose ``ActionTarget.widget`` is that exact widget.
    """
    used_families: dict[str, tuple] = {}
    node = _node(root, _widget_action_map(registry), used_families)
    theme = _resolve_theme_tokens(used_families)
    if theme:
        node["theme"] = theme
    return node


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
    windows = list(app.topLevelWidgets()) if isinstance(app, QApplication) else []  # ALLOWED: devtools dump — enumerates all top-level windows generically, not tab-specific
    used_families: dict[str, tuple] = {}
    nodes = [_node(w, action_map, used_families) for w in windows]
    out: dict[str, Any] = {"windows": nodes}
    theme = _resolve_theme_tokens(used_families)
    if theme:
        out["theme"] = theme
    return out