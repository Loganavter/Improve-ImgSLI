from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QRhiWidget, QWidget


@dataclass(frozen=True)
class ThemeColorSource:
    path: str
    line: int | None
    theme: str
    key: str
    value: str

    def label(self) -> str:
        location = self.path if self.line is None else f"{self.path}:{self.line}"
        return f'{location} "{self.key}": "{self.value}"'


@dataclass(frozen=True)
class ColorValue:
    name: str
    value: str
    theme_keys: tuple[str, ...] = ()
    theme_sources: tuple[ThemeColorSource, ...] = ()


@dataclass(frozen=True)
class NativeWindowInfo:
    class_name: str
    object_name: str
    is_top_level: bool
    has_native_window: bool
    wa_native_window: bool
    wa_paint_on_screen: bool
    is_qrhiwidget: bool
    sibling_qrhiwidgets: tuple[str, ...] = ()

    @property
    def selector(self) -> str:
        if self.object_name:
            return f"{self.class_name}#{self.object_name}"
        return self.class_name


@dataclass(frozen=True)
class WidgetSnapshot:
    class_name: str
    object_name: str
    path: tuple[str, ...]
    geometry: QRect
    visible: bool
    enabled: bool
    has_focus: bool
    under_mouse: bool
    source_file: str = ""
    source_line: int | None = None
    dynamic_properties: dict[str, str] = field(default_factory=dict)
    inline_stylesheet: str = ""
    palette: tuple[ColorValue, ...] = ()
    theme_token_sources: dict[str, ThemeColorSource] = field(default_factory=dict)
    widget_theme_sources: tuple[ThemeColorSource, ...] = ()
    native_chain: tuple[NativeWindowInfo, ...] = ()
    window_has_qrhiwidget: bool = False

    @property
    def selector(self) -> str:
        if self.object_name:
            return f"{self.class_name}#{self.object_name}"
        return self.class_name

    @property
    def nearest_native_ancestor(self) -> NativeWindowInfo | None:
        for info in self.native_chain[1:]:
            if info.has_native_window:
                return info
        return None


PALETTE_ROLES: tuple[tuple[str, QPalette.ColorRole], ...] = (
    ("Window", QPalette.ColorRole.Window),
    ("WindowText", QPalette.ColorRole.WindowText),
    ("Base", QPalette.ColorRole.Base),
    ("AlternateBase", QPalette.ColorRole.AlternateBase),
    ("Text", QPalette.ColorRole.Text),
    ("Button", QPalette.ColorRole.Button),
    ("ButtonText", QPalette.ColorRole.ButtonText),
    ("Highlight", QPalette.ColorRole.Highlight),
    ("HighlightedText", QPalette.ColorRole.HighlightedText),
    ("ToolTipBase", QPalette.ColorRole.ToolTipBase),
    ("ToolTipText", QPalette.ColorRole.ToolTipText),
)


def inspect_widget(widget: QWidget, theme_manager=None) -> WidgetSnapshot:
    theme_lookup = _build_theme_lookup(theme_manager)
    theme_sources = _build_theme_source_lookup(theme_manager)
    token_sources = _build_theme_token_sources(theme_manager)
    palette = widget.palette()
    colors = []
    for role_name, role in PALETTE_ROLES:
        color = palette.color(role)
        color_name = _color_name(color)
        colors.append(
            ColorValue(
                name=role_name,
                value=color_name,
                theme_keys=theme_lookup.get(color_name, ()),
                theme_sources=theme_sources.get(color_name, ()),
            )
        )

    return WidgetSnapshot(
        class_name=type(widget).__name__,
        object_name=widget.objectName(),
        path=tuple(_widget_path(widget)),
        geometry=widget.geometry(),
        visible=widget.isVisible(),
        enabled=widget.isEnabled(),
        has_focus=widget.hasFocus(),
        under_mouse=widget.underMouse(),
        source_file=_source_file(widget),
        source_line=_source_line(widget),
        dynamic_properties=_dynamic_properties(widget),
        inline_stylesheet=widget.styleSheet(),
        palette=tuple(colors),
        theme_token_sources=token_sources,
        widget_theme_sources=_widget_theme_sources(widget, token_sources),
        native_chain=tuple(_native_chain(widget)),
        window_has_qrhiwidget=_window_has_qrhiwidget(widget),
    )


def _window_has_qrhiwidget(widget: QWidget) -> bool:
    top = widget.window()
    if top is None:
        return False
    if isinstance(top, QRhiWidget):
        return True
    return bool(top.findChildren(QRhiWidget))


def _native_chain(widget: QWidget) -> Iterable[NativeWindowInfo]:
    current: QWidget | None = widget
    while current is not None:
        yield NativeWindowInfo(
            class_name=type(current).__name__,
            object_name=current.objectName(),
            is_top_level=current.isWindow(),
            has_native_window=current.internalWinId() != 0,
            wa_native_window=current.testAttribute(
                Qt.WidgetAttribute.WA_NativeWindow
            ),
            wa_paint_on_screen=current.testAttribute(
                Qt.WidgetAttribute.WA_PaintOnScreen
            ),
            is_qrhiwidget=isinstance(current, QRhiWidget),
            sibling_qrhiwidgets=_sibling_qrhiwidgets(current),
        )
        if current.isWindow():
            break
        parent = current.parentWidget()
        current = parent if isinstance(parent, QWidget) else None


def _sibling_qrhiwidgets(widget: QWidget) -> tuple[str, ...]:
    parent = widget.parentWidget()
    if parent is None:
        return ()
    result: list[str] = []
    for child in parent.findChildren(
        QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
    ):
        if child is widget or not isinstance(child, QRhiWidget):
            continue
        label = type(child).__name__
        if child.objectName():
            label = f"{label}#{child.objectName()}"
        result.append(label)
    return tuple(result)


def _widget_path(widget: QWidget) -> Iterable[str]:
    parts: list[str] = []
    current = widget
    while current is not None:
        label = type(current).__name__
        object_name = current.objectName()
        if object_name:
            label = f"{label}#{object_name}"
        parts.append(label)
        parent = current.parentWidget()
        current = parent if isinstance(parent, QWidget) else None
    return reversed(parts)


def _dynamic_properties(widget: QWidget) -> dict[str, str]:
    props: dict[str, str] = {}
    for raw_name in widget.dynamicPropertyNames():
        name = bytes(raw_name).decode("utf-8", errors="replace")
        try:
            value = widget.property(name)
        except (RuntimeError, TypeError):
            continue
        props[name] = str(value)
    return props


def _source_file(widget: QWidget) -> str:
    try:
        path = inspect.getsourcefile(type(widget)) or inspect.getfile(type(widget)) or ""
    except (OSError, TypeError):
        return ""
    if not path or _is_binary_or_thirdparty(path):
        return ""
    return path


def _source_line(widget: QWidget) -> int | None:
    if not _source_file(widget):
        return None
    try:
        _, line = inspect.getsourcelines(type(widget))
        return int(line)
    except (OSError, TypeError):
        return None


def _is_binary_or_thirdparty(path: str) -> bool:
    norm = path.replace("\\", "/").lower()
    if norm.endswith((".so", ".pyd", ".dll")):
        return True
    if "/site-packages/pyside6" in norm or "/pyside6/" in norm:
        return True
    if "/site-packages/shiboken6" in norm or "/shiboken6/" in norm:
        return True
    return False


def _build_theme_lookup(theme_manager) -> dict[str, tuple[str, ...]]:
    if theme_manager is None:
        return {}
    palette = (
        getattr(theme_manager, "_dark_palette", {})
        if theme_manager.is_dark()
        else getattr(theme_manager, "_light_palette", {})
    )
    lookup: dict[str, list[str]] = {}
    for key, value in palette.items():
        color = QColor(value)
        if not color.isValid():
            continue
        lookup.setdefault(_color_name(color), []).append(str(key))
    return {color: tuple(keys) for color, keys in lookup.items()}


def _build_theme_source_lookup(theme_manager) -> dict[str, tuple[str, ...]]:
    token_sources = _build_theme_token_sources(theme_manager)
    result: dict[str, list[ThemeColorSource]] = {}
    for source in token_sources.values():
        color = _color_name(QColor(source.value))
        result.setdefault(color, []).append(source)
    return {color: tuple(sources) for color, sources in result.items()}


def _build_theme_token_sources(theme_manager) -> dict[str, ThemeColorSource]:
    if theme_manager is None:
        return {}
    theme_name = "dark" if theme_manager.is_dark() else "light"
    source_path = _theme_source_path(theme_manager)
    key_lines = _theme_key_lines(source_path, theme_name)
    palette = (
        getattr(theme_manager, "_dark_palette", {})
        if theme_manager.is_dark()
        else getattr(theme_manager, "_light_palette", {})
    )
    result: dict[str, ThemeColorSource] = {}
    for key, value in palette.items():
        color = QColor(value)
        if not color.isValid():
            continue
        result[str(key)] = ThemeColorSource(
            path=source_path,
            line=key_lines.get(str(key)),
            theme=theme_name,
            key=str(key),
            value=_display_color(color),
        )
    return result


def _widget_theme_sources(
    widget: QWidget,
    token_sources: dict[str, ThemeColorSource],
) -> tuple[ThemeColorSource, ...]:
    button_keys = _toolkit_button_theme_keys(widget)
    if button_keys:
        return tuple(
            token_sources[key]
            for key in button_keys
            if key in token_sources
        )
    return ()


def _toolkit_button_theme_keys(widget: QWidget) -> tuple[str, ...]:
    try:
        from sli_ui_toolkit.widgets import Button
        from sli_ui_toolkit.ui.widgets.buttons.variants import get_variant
    except Exception:
        return ()

    if not isinstance(widget, Button):
        return ()

    variant_name = str(getattr(widget, "_variant", None) or widget.property("variant") or "default")
    spec = get_variant(variant_name)
    prefix = spec.token_prefix

    if spec.name == "ghost":
        return (
            "button.toggle.background.hover",
            "button.toggle.background.pressed",
        )

    if prefix == "button.toggle":
        return (
            "button.toggle.background.normal",
            "button.toggle.background.hover",
            "button.toggle.background.pressed",
            "button.toggle.background.checked",
            "button.toggle.background.checked.hover",
        )

    return (
        f"{prefix}.background",
        f"{prefix}.background.hover",
        f"{prefix}.background.pressed",
        f"{prefix}.background.disabled",
        f"{prefix}.border",
    )


def _theme_source_path(theme_manager) -> str:
    for path in getattr(theme_manager, "_qss_paths", ()) or ():
        if path.endswith("resources/styles/app.qss"):
            return str(Path(path).parents[1] / "themes.json")
    return "resources/themes.json"


def _theme_key_lines(source_path: str, theme_name: str) -> dict[str, int]:
    path = Path(source_path)
    if not path.exists():
        return {}
    result: dict[str, int] = {}
    in_theme = False
    theme_header = f'"{theme_name}"'
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith('"') and stripped.endswith("{"):
            in_theme = stripped.startswith(theme_header)
            continue
        if in_theme and stripped.startswith("}"):
            break
        if not in_theme:
            continue
        if not stripped.startswith('"'):
            continue
        key = stripped.split('"', 2)[1]
        result.setdefault(key, line_no)
    return result


def _color_name(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexArgb).lower()


def _display_color(color: QColor) -> str:
    if color.alpha() == 255:
        return color.name(QColor.NameFormat.HexRgb).lower()
    return color.name(QColor.NameFormat.HexArgb).lower()
