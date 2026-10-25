"""The two judge-cost rows are Steppers, not bare text fields.

Why (2026-10-25): both rows were ``SpinBox`` — a ``CustomLineEdit`` — so they
read as plain text fields with no way to step a value by mouse (owner report:
"какой-то дебил сделал здесь lineedit"). ``Stepper`` (toolkit PR #120) adds the
▲/▼ gutter that ``TimeLineEdit`` already had.

This test pins the wiring: the widget type, the per-row step size, the visible
gutter, and that a mouse press really moves the value through the store-owned
clamp (the toolkit's own tests cover the gauge mechanics).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings

from sli_ui_toolkit.widgets import Stepper, SpinBox
from tabs.image_gallery import services as _services  # noqa: F401  (import side effects)
from tabs.image_gallery.services import ai_settings_store as store_module
from tabs.image_gallery.services.ai_settings_store import AiSettingsStore

_GROUP = store_module._QS_GROUP
_MODELS_GROUP = "image_gallery_ai_models"


@pytest.fixture
def gallery_ai_store(qapp):
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    for group in (_GROUP, _MODELS_GROUP):
        settings.remove(group)
    yield
    for group in (_GROUP, _MODELS_GROUP):
        settings.remove(group)


@pytest.fixture
def dialog(qapp, gallery_ai_store, monkeypatch):
    from tabs.image_gallery.tests.test_settings_ai_providers import _build_dialog

    widget = _build_dialog(monkeypatch)
    try:
        yield widget
    finally:
        widget.close()
        widget.deleteLater()


@pytest.mark.parametrize("attr", ["gallery_ai_judge_ceiling", "gallery_ai_judge_concurrency"])
def test_the_row_is_a_stepper_with_a_visible_gutter(dialog, attr):
    widget = getattr(dialog, attr)

    assert isinstance(widget, Stepper), f"{attr} must not be a bare SpinBox"
    assert isinstance(widget, SpinBox), "Stepper stays a SpinBox (same value API)"
    assert widget.stepButtonsVisible() is True
    # isVisible() is False while the dialog itself is not shown; a button that
    # was switched on is not hidden.
    assert not widget._up_button.isHidden() and not widget._down_button.isHidden()


def test_the_step_sizes_suit_the_setting(dialog):
    assert dialog.gallery_ai_judge_concurrency.step() == 1
    assert dialog.gallery_ai_judge_ceiling.step() == 25, (
        "a call budget is stepped in tens, not ones"
    )


def test_a_mouse_step_writes_through_the_store_clamp(dialog):
    concurrency = dialog.gallery_ai_judge_concurrency
    concurrency.setValue(8)  # the store's max

    concurrency._up_button.pressed.emit()
    concurrency._up_button.released.emit()

    assert concurrency.value() == 8, "must clamp at JUDGE_CONCURRENCY_MAX"
    assert store_module.JUDGE_CONCURRENCY_MAX == 8
