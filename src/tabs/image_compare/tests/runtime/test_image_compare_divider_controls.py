from types import SimpleNamespace

from domain.types import Color
from tabs.image_compare.canvas.features.guides.toolbar import bindings as guides_toolbar
from tabs.image_compare.presenters.toolbar import orientation


class _Binding:
    def __init__(self, calls):
        self.calls = calls

    def on_right_clicked(self, _presenter):
        self.calls.append("right")


def test_scrollable_orientation_color_picker_is_expert_only(monkeypatch):
    calls = []

    class _Registry:
        def get_feature_toolbar_binding(self, control_id):
            assert control_id == "divider.orientation"
            return _Binding(calls)

        def get_feature_command_by_alias(self, alias):
            return None

    monkeypatch.setattr(orientation, "registry", lambda: _Registry())
    presenter = SimpleNamespace(
        store=SimpleNamespace(settings=SimpleNamespace(ui_mode="beginner"))
    )

    orientation.on_orientation_right_clicked(presenter)
    presenter.store.settings.ui_mode = "advanced"
    orientation.on_orientation_right_clicked(presenter)
    presenter.store.settings.ui_mode = "expert"
    orientation.on_orientation_right_clicked(presenter)

    assert calls == ["right"]


class _ProbeButton:
    def __init__(self, value=1):
        self._value = value
        self.underline_calls = []
        self.checked = None
        self.saved = None

    def get_value(self):
        return self._value

    def set_value(self, value):
        self._value = value

    def blockSignals(self, _blocked):
        return None

    def setChecked(self, value, emit_signal=False):
        self.checked = value

    def isChecked(self):
        return bool(self.checked)

    def set_saved_value(self, value):
        self.saved = value

    def setUnderlineColor(self, value):
        self.underline_calls.append(value)


def test_magnifier_guides_sync_colors_both_thickness_buttons_from_state(monkeypatch):
    """sync_guides_toolbar_state has no laser-specific branch any more — the
    active/laser query was dropped (see guides/toolbar.py) and the underline
    color on both the enable and width buttons is driven solely by
    ``state.color``."""
    color = Color(10, 20, 30, 40)
    monkeypatch.setattr(
        guides_toolbar,
        "get_guides_widget_state",
        lambda _view_state: SimpleNamespace(enabled=True, thickness=4, color=color),
    )

    btn_guides = _ProbeButton()
    btn_width = _ProbeButton()
    presenter = SimpleNamespace(
        store=SimpleNamespace(viewport=SimpleNamespace(view_state=SimpleNamespace())),
        widget=SimpleNamespace(
            btn_magnifier_guides=btn_guides,
            btn_magnifier_guides_simple=_ProbeButton(),
            btn_magnifier_guides_width=btn_width,
        ),
    )

    guides_toolbar.sync_guides_toolbar_state(presenter)

    assert [c.getRgb() for c in btn_guides.underline_calls] == [(10, 20, 30, 40)]
    assert [c.getRgb() for c in btn_width.underline_calls] == [(10, 20, 30, 40)]
