"""Layout dump embeds declared inspector state (family + state fields)."""

from __future__ import annotations

import json

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
