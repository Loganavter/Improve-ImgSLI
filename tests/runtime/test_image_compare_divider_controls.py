from types import SimpleNamespace

from tabs.image_compare.canvas.features.guides import toolbar as guides_toolbar
from tabs.image_compare.presenters.toolbar import orientation


class _Binding:
    def __init__(self, calls):
        self.calls = calls

    def on_right_clicked(self, _presenter):
        self.calls.append("right")


def test_scrollable_orientation_color_picker_is_expert_only(monkeypatch):
    calls = []

    def _binding(control_id):
        assert control_id == "divider.orientation"
        return _Binding(calls)

    monkeypatch.setattr(orientation, "get_canvas_feature_toolbar_binding", _binding)
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


def test_magnifier_guides_sync_does_not_color_laser_buttons(monkeypatch):
    monkeypatch.setattr(
        guides_toolbar,
        "get_guides_widget_state",
        lambda _view_state: SimpleNamespace(enabled=True, thickness=4, color=None),
    )
    monkeypatch.setattr(guides_toolbar, "_query_active_show_laser", lambda _store: True)

    btn_guides = _ProbeButton()
    btn_width = _ProbeButton()
    presenter = SimpleNamespace(
        store=SimpleNamespace(viewport=SimpleNamespace(view_state=SimpleNamespace())),
        ui=SimpleNamespace(
            btn_magnifier_guides=btn_guides,
            btn_magnifier_guides_simple=_ProbeButton(),
            btn_magnifier_guides_width=btn_width,
        ),
    )

    guides_toolbar.sync_guides_toolbar_state(presenter)

    assert btn_guides.underline_calls == []
    assert btn_width.underline_calls == []
