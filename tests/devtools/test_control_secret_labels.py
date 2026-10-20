"""A masked text field must not publish its contents as an element label.

Live 2026-10-20: ``ui_elements{role=input}`` on Settings -> AI returned the full
API key as the element's ``label`` — the widget masks it with ``EchoMode.Password``
but the inventory read ``.text()`` anyway. Anyone who can reach the control socket
(same uid / any MCP client) could read a secret the UI deliberately hides.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLineEdit  # noqa: E402

from core.control.elements import roles  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_password_field_label_is_masked(app):
    field = QLineEdit()
    field.setText("sk-or-v1-deadbeefdeadbeef")
    field.setEchoMode(QLineEdit.EchoMode.Password)

    label = roles._label_of(field)

    assert "sk-or-v1" not in label
    assert label == roles._SECRET_LABEL


def test_normal_field_label_is_its_text(app):
    field = QLineEdit()
    field.setText("https://openrouter.ai/api/v1")

    assert roles._label_of(field) == "https://openrouter.ai/api/v1"


def test_secret_label_length_is_fixed(app):
    short = QLineEdit()
    short.setText("a")
    short.setEchoMode(QLineEdit.EchoMode.Password)
    long = QLineEdit()
    long.setText("a" * 64)
    long.setEchoMode(QLineEdit.EchoMode.Password)

    assert roles._label_of(short) == roles._label_of(long) == roles._SECRET_LABEL
