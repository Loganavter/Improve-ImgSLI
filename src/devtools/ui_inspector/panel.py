from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication, QTextOption
from PySide6.QtWidgets import (
    QHBoxLayout,
    QFrame,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sli_ui_toolkit.widgets import Button, MinimalistScrollBar

from devtools.ui_inspector.qss_index import QssRule
from devtools.ui_inspector.widget_snapshot import (
    NativeWindowInfo,
    ThemeColorSource,
    WidgetSnapshot,
)


class InspectorPanel(QWidget):
    toggle_native_window_requested = Signal()
    force_repaint_requested = Signal()
    force_update_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        if parent is None:
            flags = Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint
        else:
            flags = Qt.WindowType.Widget
        super().__init__(parent, flags)
        self.setObjectName("UiInspectorPanel")
        self.setWindowTitle("UI Inspector")
        self.setProperty("_ui_inspector_owned", True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(380)
        self.setMinimumHeight(360)
        self.resize(460, 520)

        self._snapshot: WidgetSnapshot | None = None
        self._details = ""
        self._user_positioned = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.copy_selector_button = Button(
            text="Copy selector",
            variant="surface",
            size=(130, 32),
            parent=self,
        )
        self.copy_path_button = Button(
            text="Copy path",
            variant="surface",
            size=(106, 32),
            parent=self,
        )
        self.copy_details_button = Button(
            text="Copy details",
            variant="surface",
            size=(122, 32),
            parent=self,
        )
        buttons.addWidget(self.copy_selector_button)
        buttons.addWidget(self.copy_path_button)
        buttons.addWidget(self.copy_details_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        experiments = QHBoxLayout()
        experiments.setSpacing(6)
        self.toggle_native_button = Button(
            text="Toggle native window",
            variant="surface",
            size=(160, 32),
            parent=self,
        )
        self.force_repaint_button = Button(
            text="Force repaint()",
            variant="surface",
            size=(126, 32),
            parent=self,
        )
        self.force_update_button = Button(
            text="Force update()",
            variant="surface",
            size=(122, 32),
            parent=self,
        )
        experiments.addWidget(self.toggle_native_button)
        experiments.addWidget(self.force_repaint_button)
        experiments.addWidget(self.force_update_button)
        experiments.addStretch(1)
        layout.addLayout(experiments)

        self.text = QTextEdit(self)
        self.text.setObjectName("UiInspectorDetails")
        self.text.setFont(self.font())
        self.text.setReadOnly(True)
        self.text.setFrameShape(QFrame.Shape.NoFrame)
        self.text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.text.setVerticalScrollBar(MinimalistScrollBar(parent=self.text))
        text_option = self.text.document().defaultTextOption()
        text_option.setWrapMode(QTextOption.WrapMode.WrapAnywhere)
        self.text.document().setDefaultTextOption(text_option)
        layout.addWidget(self.text)

        self.copy_selector_button.clicked.connect(self.copy_selector)
        self.copy_path_button.clicked.connect(self.copy_path)
        self.copy_details_button.clicked.connect(self.copy_details)
        self.toggle_native_button.clicked.connect(
            self.toggle_native_window_requested
        )
        self.force_repaint_button.clicked.connect(self.force_repaint_requested)
        self.force_update_button.clicked.connect(self.force_update_requested)
        self.hide()

    def position_in_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            self.resize(self.width(), max(self.height(), 520))
            return
        margin = 14
        height = min(max(360, parent.height() - margin * 2), 720)
        self.resize(self.width(), height)
        if self._user_positioned:
            self.move(self._constrained_pos(self.pos()))
            return
        self.move(max(margin, parent.width() - self.width() - margin), margin)

    def _constrained_pos(self, pos: QPoint) -> QPoint:
        parent = self.parentWidget()
        if parent is None:
            return pos
        margin = 8
        max_x = max(margin, parent.width() - self.width() - margin)
        max_y = max(margin, parent.height() - self.height() - margin)
        return QPoint(
            max(margin, min(pos.x(), max_x)),
            max(margin, min(pos.y(), max_y)),
        )

    def set_snapshot(
        self,
        snapshot: WidgetSnapshot,
        qss_candidates: tuple[QssRule, ...],
        global_pos: QPoint | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._details = _format_full_snapshot(snapshot, qss_candidates)
        self.text.setHtml(_format_compact_snapshot_html(snapshot, qss_candidates))
        unsafe = snapshot.window_has_qrhiwidget
        self.toggle_native_button.setEnabled(not unsafe)
        self.toggle_native_button.setToolTip(
            "Disabled: this window contains a QRhiWidget. Forcing "
            "WA_NativeWindow here has been observed to corrupt QRhiWidget "
            "rendering app-wide on Wayland and cannot be cleanly undone "
            "(restart required)."
            if unsafe
            else "Force this widget to get its own native platform window."
        )
        if self.parentWidget() is None:
            self.position_as_window(global_pos)
        else:
            self.position_in_parent()
        self.show()
        self.raise_()

    def position_as_window(self, global_pos: QPoint | None = None) -> None:
        self.resize(self.width(), max(self.height(), 520))
        if self._user_positioned:
            return
        if global_pos is None:
            return
        self.move(global_pos + QPoint(18, 18))

    def copy_selector(self) -> None:
        if self._snapshot is not None:
            QGuiApplication.clipboard().setText(self._snapshot.selector)

    def copy_path(self) -> None:
        if self._snapshot is not None:
            QGuiApplication.clipboard().setText(" > ".join(self._snapshot.path))

    def copy_details(self) -> None:
        QGuiApplication.clipboard().setText(self._details)


def _format_compact_snapshot(
    snapshot: WidgetSnapshot,
    qss_candidates: tuple[QssRule, ...],
) -> str:
    lines = [
        "Object",
        f"  selector: {snapshot.selector}",
        f"  class: {snapshot.class_name}",
        f"  objectName: {snapshot.object_name or '-'}",
        f"{snapshot.geometry.width()}x{snapshot.geometry.height()} at {snapshot.geometry.x()},{snapshot.geometry.y()}",
    ]
    if snapshot.source_file:
        source = snapshot.source_file
        if snapshot.source_line is not None:
            source = f"{source}:{snapshot.source_line}"
        lines.append(f"  source: {source}")
    lines.append("")

    useful_props = _useful_properties(snapshot.dynamic_properties)
    if useful_props:
        lines.append("Properties")
        lines.extend(f"  {key}: {value}" for key, value in useful_props)
        lines.append("")

    nearest = snapshot.nearest_native_ancestor
    lines.append("Native window")
    lines.append(
        f"  this: native={_bool_yes_no(snapshot.native_chain[0].has_native_window) if snapshot.native_chain else '-'} "
        f"WA_NativeWindow={_bool_yes_no(snapshot.native_chain[0].wa_native_window) if snapshot.native_chain else '-'}"
    )
    if nearest is not None:
        lines.append(
            f"  nearest native ancestor: {nearest.selector}"
            f"{' (QRhiWidget)' if nearest.is_qrhiwidget else ''}"
        )
    else:
        lines.append("  nearest native ancestor: none (top-level window itself)")
    own_siblings = snapshot.native_chain[0].sibling_qrhiwidgets if snapshot.native_chain else ()
    if own_siblings:
        lines.append(
            "  QRhiWidget siblings (same parent): " + ", ".join(own_siblings)
        )
    ancestor_siblings = [
        (info, info.sibling_qrhiwidgets)
        for info in snapshot.native_chain[1:]
        if info.sibling_qrhiwidgets
    ]
    for info, siblings in ancestor_siblings:
        lines.append(
            f"  QRhiWidget siblings under {info.selector}'s parent: "
            + ", ".join(siblings)
        )
    lines.append("")

    theme_sources = _theme_sources_for_widget(snapshot, qss_candidates)
    if theme_sources:
        lines.append("Theme colors")
        lines.append(f"  {snapshot.class_name}:")
        for source_path, sources in theme_sources.items():
            lines.append(
                f"    source: {_display_path(source_path)} {_line_ranges_label(sources)}"
            )
            for source in sources:
                lines.append(f'        "{source.key}": "{source.value}" ■')
        lines.append("")

    if snapshot.inline_stylesheet.strip():
        lines.extend(["Inline style", f"  {snapshot.inline_stylesheet.strip()}", ""])

    candidates = _compact_qss_candidates(qss_candidates)
    lines.append("QSS candidates")
    if candidates:
        for rule in candidates:
            source = Path(rule.source).as_posix()
            lines.append(f"  {rule.selector}")
            lines.append(f"    file: {source}")
            for body_line in _important_qss_body_lines(rule.body):
                lines.append(f"    {body_line}")
    else:
        lines.append("  none")
    if len(qss_candidates) > len(candidates):
        lines.append(f"  +{len(qss_candidates) - len(candidates)} more in Copy details")

    hover_rules = _hover_qss_candidates(qss_candidates)
    if hover_rules:
        lines.append("")
        lines.append("Hover")
        for rule in hover_rules[:4]:
            lines.append(f"  {rule.selector}")
            lines.append(f"    file: {_display_path(rule.source)}")
            for body_line in _important_qss_body_lines(rule.body):
                lines.append(f"    {body_line}")

    lines.extend(["", "Full widget path is available via Copy path."])
    return "\n".join(lines)


def _format_compact_snapshot_html(
    snapshot: WidgetSnapshot,
    qss_candidates: tuple[QssRule, ...],
) -> str:
    lines = []
    for line in _format_compact_snapshot(snapshot, qss_candidates).splitlines():
        stripped = line.strip()
        if stripped.startswith('"') and '": "#' in stripped:
            color = stripped.rsplit('"', 2)[1]
            lines.append(f"{html.escape(line[:-1].rstrip())} {_swatch_html(color)}")
        else:
            lines.append(html.escape(line))
    return "<pre style='white-space: pre-wrap; margin: 0'>" + "\n".join(lines) + "</pre>"


def _format_full_snapshot(
    snapshot: WidgetSnapshot,
    qss_candidates: tuple[QssRule, ...],
) -> str:
    lines = [
        "Widget",
        f"  {snapshot.selector}",
        f"  class: {snapshot.class_name}",
        f"  objectName: {snapshot.object_name or '-'}",
        f"  path: {' > '.join(snapshot.path)}",
        f"  source: {_source_label(snapshot)}",
        "",
        "Geometry",
        (
            "  "
            f"x={snapshot.geometry.x()} y={snapshot.geometry.y()} "
            f"w={snapshot.geometry.width()} h={snapshot.geometry.height()}"
        ),
        (
            "  "
            f"visible={snapshot.visible} enabled={snapshot.enabled} "
            f"focus={snapshot.has_focus} underMouse={snapshot.under_mouse}"
        ),
        "",
        "Properties",
    ]
    if snapshot.dynamic_properties:
        for key, value in sorted(snapshot.dynamic_properties.items()):
            lines.append(f"  {key} = {value}")
    else:
        lines.append("  none")

    lines.extend(["", "Palette"])
    for color in snapshot.palette:
        suffix = f" -> {', '.join(color.theme_keys)}" if color.theme_keys else ""
        lines.append(f"  {color.name}: {color.value}{suffix}")

    lines.extend(["", "Native Window (widget -> top-level)"])
    if snapshot.native_chain:
        for info in snapshot.native_chain:
            lines.append(f"  {_native_info_line(info)}")
        nearest = snapshot.nearest_native_ancestor
        if nearest is not None:
            lines.append(
                f"  composited-children boundary: nearest native ancestor is "
                f"{nearest.selector}"
            )
    else:
        lines.append("  none")

    lines.extend(["", "Inline StyleSheet"])
    lines.append(snapshot.inline_stylesheet.strip() or "  none")

    lines.extend(["", "QSS Candidates"])
    if not qss_candidates:
        lines.append("  none")
    for rule in qss_candidates[:40]:
        source = Path(rule.source).as_posix()
        lines.append(f"  {source}")
        lines.append(f"    {rule.selector} {{")
        for body_line in rule.body.splitlines():
            body_line = body_line.strip()
            if body_line:
                lines.append(f"      {body_line}")
        lines.append("    }")
    if len(qss_candidates) > 40:
        lines.append(f"  ... {len(qss_candidates) - 40} more")
    return "\n".join(lines)


def _useful_properties(properties: dict[str, str]) -> list[tuple[str, str]]:
    hidden_prefixes = ("_", "icon", "corner", "density")
    result = []
    for key, value in sorted(properties.items()):
        if key.startswith(hidden_prefixes):
            continue
        if key in {"class", "variant", "state", "segment", "surfaceRole"}:
            result.append((key, value))
    return result[:8]


def _source_label(snapshot: WidgetSnapshot) -> str:
    if not snapshot.source_file:
        return "-"
    if snapshot.source_line is None:
        return snapshot.source_file
    return f"{snapshot.source_file}:{snapshot.source_line}"


def _compact_palette(snapshot: WidgetSnapshot):
    priority = {
        "WindowText",
        "Text",
        "ButtonText",
        "Button",
        "Window",
        "Base",
        "Highlight",
        "HighlightedText",
    }
    seen: set[str] = set()
    colors = []
    for color in snapshot.palette:
        if color.name not in priority or color.value in seen:
            continue
        seen.add(color.value)
        colors.append(color)
    return colors[:6]


def _theme_sources_for_widget(
    snapshot: WidgetSnapshot,
    qss_candidates: tuple[QssRule, ...],
) -> dict[str, list[ThemeColorSource]]:
    grouped: dict[str, dict[tuple[int | None, str], ThemeColorSource]] = {}

    for source in snapshot.widget_theme_sources:
        grouped.setdefault(source.path, {})[(source.line, source.key)] = source

    qss_source_count = sum(len(sources) for sources in grouped.values())
    qss_rules = (*_compact_qss_candidates(qss_candidates), *_hover_qss_candidates(qss_candidates))
    for rule in qss_rules:
        for line in _important_qss_body_lines(rule.body):
            for token in _tokens_in_line(line):
                source = snapshot.theme_token_sources.get(token)
                if source is not None:
                    grouped.setdefault(source.path, {})[(source.line, source.key)] = source

    if not grouped:
        for color in _compact_palette(snapshot):
            source = _source_for_role(color.name, color.theme_sources)
            if source is not None:
                grouped.setdefault(source.path, {})[(source.line, source.key)] = source
    elif qss_source_count == 0 and len(qss_candidates) == 0:
        for color in _compact_palette(snapshot):
            source = _source_for_role(color.name, color.theme_sources)
            if source is not None and source.key in {"WindowText", "Text", "ButtonText"}:
                grouped.setdefault(source.path, {})[(source.line, source.key)] = source

    return {
        path: sorted(sources.values(), key=lambda item: (item.line or 10**9, item.key))
        for path, sources in grouped.items()
    }


def _source_for_role(
    role_name: str,
    theme_sources: tuple[ThemeColorSource, ...],
) -> ThemeColorSource | None:
    for source in theme_sources:
        if source.key == role_name:
            return source
    return None


def _display_path(path: str) -> str:
    try:
        return Path(path).resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _line_ranges_label(sources: list[ThemeColorSource]) -> str:
    lines = sorted({source.line for source in sources if source.line is not None})
    if not lines:
        return ""
    ranges = []
    start = prev = lines[0]
    for line in lines[1:]:
        if line == prev + 1:
            prev = line
            continue
        ranges.append(_format_line_range(start, prev))
        start = prev = line
    ranges.append(_format_line_range(start, prev))
    return f"({', '.join(ranges)})"


def _format_line_range(start: int, end: int) -> str:
    if start == end:
        return str(start)
    return f"{start}-{end}"


def _tokens_in_line(line: str) -> list[str]:
    tokens = []
    for part in line.split("@")[1:]:
        token = ""
        for char in part:
            if char.isalnum() or char in "._-":
                token += char
            else:
                break
        if token:
            tokens.append(token)
    return tokens


def _compact_qss_candidates(qss_candidates: tuple[QssRule, ...]) -> tuple[QssRule, ...]:
    scored = []
    for index, rule in enumerate(qss_candidates):
        score = 0
        selector = rule.selector
        if "#" in selector:
            score += 4
        if "[" in selector:
            score += 3
        if ">" in selector:
            score += 2
        if any(prop in rule.body for prop in ("background", "color", "border")):
            score += 1
        scored.append((-score, index, rule))
    scored.sort()
    return tuple(item[2] for item in scored[:6])


def _hover_qss_candidates(qss_candidates: tuple[QssRule, ...]) -> tuple[QssRule, ...]:
    result = []
    for rule in qss_candidates:
        selector = rule.selector.lower()
        if ":hover" in selector or '[state="hover"]' in selector or ".hover" in selector:
            result.append(rule)
    return tuple(result)


def _native_info_line(info: NativeWindowInfo) -> str:
    flags = []
    if info.is_top_level:
        flags.append("top-level")
    if info.has_native_window:
        flags.append("native")
    if info.wa_native_window:
        flags.append("WA_NativeWindow")
    if info.wa_paint_on_screen:
        flags.append("WA_PaintOnScreen")
    if info.is_qrhiwidget:
        flags.append("QRhiWidget")
    suffix = f" [{', '.join(flags)}]" if flags else ""
    line = f"{info.selector}{suffix}"
    if info.sibling_qrhiwidgets:
        line += f" — QRhiWidget siblings: {', '.join(info.sibling_qrhiwidgets)}"
    return line


def _bool_yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _swatch_html(color: str) -> str:
    escaped = html.escape(color)
    return f"<span style='color:{escaped}; font-weight:bold'>&#9632;</span>"


def _important_qss_body_lines(body: str) -> list[str]:
    important = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(token in line for token in ("color", "background", "border")):
            important.append(line)
    return important[:3]
