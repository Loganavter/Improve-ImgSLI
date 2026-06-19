from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtWidgets import QWidget


_QSS_BLOCK_RE = re.compile(r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}", re.S)


@dataclass(frozen=True)
class QssRule:
    source: str
    selector: str
    body: str


class QssIndex:
    def __init__(self, rules: list[QssRule]):
        self._rules = tuple(rules)

    @classmethod
    def from_theme_manager(cls, theme_manager) -> "QssIndex":
        paths = tuple(getattr(theme_manager, "_qss_paths", ()) or ())
        return cls.from_paths(paths)

    @classmethod
    def from_paths(cls, paths: tuple[str, ...]) -> "QssIndex":
        rules: list[QssRule] = []
        for path in paths:
            if not path or not os.path.exists(path):
                continue
            text = Path(path).read_text(encoding="utf-8")
            rules.extend(_parse_rules(path, text))
        return cls(rules)

    def candidates_for(self, widget: QWidget) -> tuple[QssRule, ...]:
        parent_names = _parent_class_names(widget)
        class_name = type(widget).__name__
        object_name = widget.objectName()
        properties = {
            bytes(name).decode("utf-8", errors="replace"): str(
                widget.property(bytes(name).decode("utf-8", errors="replace"))
            )
            for name in widget.dynamicPropertyNames()
        }
        result = []
        for rule in self._rules:
            if _selector_may_match(
                rule.selector,
                class_name=class_name,
                object_name=object_name,
                properties=properties,
                parent_names=parent_names,
            ):
                result.append(rule)
        return tuple(result)


def _parse_rules(path: str, text: str) -> list[QssRule]:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    rules: list[QssRule] = []
    for match in _QSS_BLOCK_RE.finditer(text):
        body = match.group("body").strip()
        for selector in match.group("selectors").split(","):
            selector = " ".join(selector.strip().split())
            if selector:
                rules.append(QssRule(source=path, selector=selector, body=body))
    return rules


def _selector_may_match(
    selector: str,
    *,
    class_name: str,
    object_name: str,
    properties: dict[str, str],
    parent_names: tuple[str, ...],
) -> bool:
    leaf = selector.split(">")[-1].split()[-1].strip()
    if not leaf:
        return False

    if "#" in leaf:
        _, _, selector_object = leaf.partition("#")
        selector_object = re.split(r"[:\[]", selector_object, maxsplit=1)[0]
        if selector_object != object_name:
            return False

    type_match = re.match(r"^[A-Za-z_][A-Za-z0-9_]*", leaf)
    if type_match:
        selector_type = type_match.group(0)
        if selector_type not in {class_name, "QWidget"}:
            return False

    for prop, expected in re.findall(r"\[([^=\]]+)=\"([^\"]*)\"\]", selector):
        if properties.get(prop) != expected:
            return False

    prefix = selector.rsplit(leaf, 1)[0]
    for parent_type in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", prefix):
        if parent_type not in parent_names and parent_type != "QWidget":
            return False

    return bool(type_match or "#" in leaf or "[" in leaf)


def _parent_class_names(widget: QWidget) -> tuple[str, ...]:
    names: list[str] = []
    parent = widget.parentWidget()
    while parent is not None:
        names.append(type(parent).__name__)
        parent = parent.parentWidget()
    return tuple(names)
