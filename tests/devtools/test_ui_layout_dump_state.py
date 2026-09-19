"""Layout dump embeds declared inspector state (family + state fields)."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QLabel, QWidget

from devtools.ui_layout_dump import dump_ui_layout


class _FakeRegistry:
    def all_actions(self):
        return []


def test_dump_embeds_declared_spec_state(qapp):
    from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField

    class Stateful(QLabel):
        inspect_spec = InspectSpec(
            family="Stateful",
            state=(
                SpecField("mode", lambda w: w.mode),
                SpecField("count", "count"),
            ),
        )

        def __init__(self, parent=None):
            super().__init__(parent)
            self.mode = "DOUBLE"
            self.count = 3

    host = QWidget()
    label = Stateful(host)
    host.show()
    qapp.processEvents()
    try:
        tree = dump_ui_layout(host, _FakeRegistry())
    finally:
        host.close()
        host.deleteLater()
    json.dumps(tree)  # must stay JSON-serializable
    kids = tree.get("children") or []
    assert len(kids) == 1
    node = kids[0]
    assert node["family"] == "Stateful"
    assert node["state"] == {"mode": "DOUBLE", "count": 3}


def test_dump_skips_state_for_plain_widgets(qapp):
    host = QWidget()
    plain = QLabel("hi", host)
    plain.setObjectName("Plain")
    host.show()
    qapp.processEvents()
    try:
        tree = dump_ui_layout(host, _FakeRegistry())
    finally:
        host.close()
        host.deleteLater()
    node = (tree.get("children") or [])[0]
    assert node["text"] == "hi"
    assert "state" not in node


def test_dump_reports_explicit_palette_color(qapp):
    host = QWidget()
    child = QLabel("hi", host)
    pal = child.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor("#112233"))
    child.setPalette(pal)
    host.show()
    qapp.processEvents()
    try:
        tree = dump_ui_layout(host, _FakeRegistry())
    finally:
        host.close()
        host.deleteLater()
    json.dumps(tree)  # must stay JSON-serializable
    node = (tree.get("children") or [])[0]
    assert node["colors"]["palette"]["Window"] == "#112233"


def test_dump_reports_alpha_palette_color_with_suffix(qapp):
    host = QWidget()
    child = QLabel("hi", host)
    translucent = QColor("#112233")
    translucent.setAlpha(128)
    pal = child.palette()
    pal.setColor(QPalette.ColorRole.Window, translucent)
    child.setPalette(pal)
    host.show()
    qapp.processEvents()
    try:
        tree = dump_ui_layout(host, _FakeRegistry())
    finally:
        host.close()
        host.deleteLater()
    json.dumps(tree)
    node = (tree.get("children") or [])[0]
    assert node["colors"]["palette"]["Window"] == "#112233@128"


def test_dump_reports_transparency_flags(qapp):
    host = QWidget()
    child = QLabel("hi", host)
    child.setAttribute(Qt.WA_TranslucentBackground, True)
    host.show()
    qapp.processEvents()
    try:
        tree = dump_ui_layout(host, _FakeRegistry())
    finally:
        host.close()
        host.deleteLater()
    json.dumps(tree)
    colors = (tree.get("children") or [])[0]["colors"]
    assert colors["translucent_bg"] is True
    assert isinstance(colors["no_system_bg"], bool)
    assert colors["auto_fill_background"] is False
    assert colors["background_role"] == "Window"


def test_dump_reports_stylesheet_snippet(qapp):
    host = QWidget()
    child = QLabel("hi", host)
    child.setStyleSheet("QLabel { background: red; } " + "x" * 300)
    host.show()
    qapp.processEvents()
    try:
        tree = dump_ui_layout(host, _FakeRegistry())
    finally:
        host.close()
        host.deleteLater()
    json.dumps(tree)
    node = (tree.get("children") or [])[0]
    assert node["colors"]["stylesheet"] == child.styleSheet()[:200]
    assert len(node["colors"]["stylesheet"]) == 200


def test_dump_omits_stylesheet_and_opacity_when_default(qapp):
    host = QWidget()
    child = QLabel("hi", host)
    host.show()
    qapp.processEvents()
    try:
        tree = dump_ui_layout(host, _FakeRegistry())
    finally:
        host.close()
        host.deleteLater()
    json.dumps(tree)
    colors = (tree.get("children") or [])[0]["colors"]
    assert "stylesheet" not in colors
    assert "opacity" not in colors
