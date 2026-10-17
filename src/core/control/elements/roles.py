"""Widget → role / label / menu detection for the element inventory.

Split out of :mod:`~core.control.elements.inventory` so the traversal stays a
traversal and the (surprisingly large) duck-typing rules live together. The
whole app's UI is ``sli-ui-toolkit`` widgets — plain ``QWidget`` subclasses,
not the stock Qt classes an ``isinstance``-only inventory recognises — so the
rules here are name/module based and never import the toolkit.

Nothing here touches live state; every function is a pure predicate over a
widget's class name, ``__module__``, ``flyout_group`` marker, or attributes.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRect
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSlider,
    QAbstractSpinBox,
    QComboBox,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

#: Import prefix of every ``sli-ui-toolkit`` widget (duck-typed, no import).
_TOOLKIT_MODULE_PREFIX = "sli_ui_toolkit"


def _text_of(widget: QWidget) -> str:
    """The dumper's label recipe (toolkit ``_text`` fallback), lazily imported.

    ``devtools.ui_layout_dump._text_of`` already resolves a toolkit
    ``Button``'s private ``_text`` caption; the control inventory reuses it
    instead of keeping a second, drifting copy. Imported on first use so the
    debug dumper is not a module-import dependency of the live control path.
    """
    try:
        from devtools.ui_layout_dump import _text_of as _dump_text_of

        return str(_dump_text_of(widget) or "")
    except Exception:
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
        return str(fallback) if fallback else ""


def _action_display(action: Any | None) -> str:
    """Resolve an action's human label from its i18n ``label_key``.

    Toolbar/menu widgets carry no text of their own — their caption lives on
    the bound ``ActionDescriptor``. ``_display`` is the snapshot's own key→text
    resolver (same one ``dump_actions`` uses), lazily imported.
    """
    key = getattr(action, "label_key", None) if action is not None else None
    if not key:
        return ""
    try:
        from devtools.app_snapshot import _display

        return str(_display(key) or "")
    except Exception:
        return ""


def _label_of(widget: QWidget, action: Any | None = None) -> str:
    """Best-effort human label, duck-typed across Qt and toolkit widgets.

    Order matters: the widget's own text (dumper recipe, toolkit ``_text``),
    then the bound action's resolved label (so an icon-only toolkit button
    reports its action caption, not the class-name fallback), then Qt's
    accessibility/object-name fallbacks.
    """
    text = _text_of(widget)
    if not text:
        title = getattr(widget, "title", None)
        if callable(title):
            try:
                text = str(title() or "")
            except Exception:
                text = ""
    if not text:
        text = _action_display(action)
    if text:
        return text
    try:
        accessible = widget.accessibleName()
    except Exception:
        accessible = ""
    if accessible:
        return str(accessible)
    try:
        name = widget.objectName()
    except Exception:
        name = ""
    return str(name or type(widget).__name__)


def _is_toolkit_widget(widget: QWidget) -> bool:
    """True when *widget*'s defining class comes from ``sli_ui_toolkit``.

    Duck-typed by ``__module__`` — no toolkit import, so the inventory still
    works in an environment where the toolkit is not installed.
    """
    module = type(widget).__module__ or ""
    return module == _TOOLKIT_MODULE_PREFIX or module.startswith(
        _TOOLKIT_MODULE_PREFIX + "."
    )


def _is_canvas_widget(widget: QWidget) -> bool:
    """True for a live ``QRhiWidget`` canvas (duck-typed, never raises).

    Canvases are the most interactive widget a tab owns -- zoom/pan/selection
    through wheel, keys and drag -- and they are neither stock Qt patents nor
    toolkit widgets, so without this they never appear in ``ui_elements``. A
    client then has no id to focus or to aim keys at, and canvas interaction
    is undrivable through the control surface (live 2026-10-17: the
    multi-compare zoom keys all landed on the main window).
    """
    try:
        from PySide6.QtWidgets import QRhiWidget
    except Exception:
        return False
    try:
        return isinstance(widget, QRhiWidget)
    except Exception:
        return False


def _is_menu_like(widget: QWidget) -> bool:
    """A menu/flyout: stock ``QMenu`` or a toolkit ``ContextMenu``/``BaseFlyout``.

    Toolkit menus are plain ``QWidget``s (in-window overlays), not ``QMenu``,
    so they are invisible to an ``isinstance``-only inventory. ``flyout_group``
    is the toolkit's own marker; the class-name test catches the base and
    per-feature flyouts (``*Flyout``) plus the context menu itself.
    """
    if isinstance(widget, QMenu):
        return True
    try:
        if getattr(widget, "flyout_group", None):
            return True
    except Exception:
        pass
    name = type(widget).__name__
    return (
        name == "BaseFlyout"
        or name.endswith("ContextMenu")
        or name.endswith("Flyout")
    )


def _toolkit_role(widget: QWidget, *, in_grid_view: bool) -> str | None:
    """Role for a toolkit widget (or an app subclass of one), else ``None``.

    Name-suffix mapping (documented in the package docstring):
    ``*Button``/``*Switch``/``*RadioButton``/``*CheckBox`` → ``button``;
    ``*Slider``/``*SpinBox``/``*ComboBox``/``*LineEdit`` → ``input``;
    ``*TabItem``/``*TabBar``/``*TabStrip`` → ``tab``. A toolkit ``Button``
    that sits inside a ``*GridView`` is a gallery/collection *card*.
    """
    name = type(widget).__name__
    lower = name.lower()
    toolkit = _is_toolkit_widget(widget)
    button_like = name.endswith("Button") or lower.endswith(
        ("switch", "radiobutton", "checkbox")
    )
    if button_like and (in_grid_view or "card" in lower):
        return "card"
    if button_like:
        return "button"
    if lower.endswith(("slider", "spinbox", "combobox", "lineedit")):
        return "input"
    if name.endswith(("TabItem", "TabBar", "TabStrip")):
        return "tab"
    if toolkit and "card" in lower:
        return "card"
    return None


def _role_of(
    widget: QWidget, *, in_menu: bool = False, in_grid_view: bool = False
) -> str | None:
    """Role string for an interactive widget, or ``None`` to skip it.

    ``in_menu`` / ``in_grid_view`` carry ancestor context from the traversal:
    rows inside an open menu become ``menu-row`` and a ``Button`` nested in a
    ``*GridView`` becomes ``card`` — neither is decidable from the widget
    alone.
    """
    if isinstance(widget, QMenu):
        return "menu"
    if _is_menu_like(widget):
        return "menu"
    if _is_canvas_widget(widget):
        # A live QRhi canvas: the surface a tab's zoom/pan/selection acts on.
        return "canvas"
    if in_menu:
        # Inside a toolkit flyout/menu: every row widget is a menu row.
        if isinstance(widget, QAbstractButton) or hasattr(widget, "_text"):
            return "menu-row"
        return None
    if isinstance(widget, QAbstractButton):
        return "button"
    if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox)):
        return "input"
    if isinstance(widget, (QAbstractSpinBox, QAbstractSlider)):
        return "input"
    if isinstance(widget, QAbstractItemView):
        return "view"
    toolkit_role = _toolkit_role(widget, in_grid_view=in_grid_view)
    if toolkit_role is not None:
        return toolkit_role
    if "card" in type(widget).__name__.lower():
        return "card"
    return None


def _has_area(rect: QRect) -> bool:
    """True when *rect* is non-degenerate (hidden/collapsed widgets are 0-area)."""
    return rect.width() > 0 and rect.height() > 0


def _safe_visible(widget: QWidget) -> bool:
    try:
        return bool(widget.isVisible())
    except Exception:
        return False


__all__ = [
    "_action_display",
    "_has_area",
    "_is_canvas_widget",
    "_is_menu_like",
    "_is_toolkit_widget",
    "_label_of",
    "_role_of",
    "_safe_visible",
    "_text_of",
    "_toolkit_role",
]
