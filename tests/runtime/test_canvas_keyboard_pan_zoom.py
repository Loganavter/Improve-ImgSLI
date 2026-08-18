"""Arrow-key pan + `+`/`-` zoom on the Image Compare and Multi Compare
canvases (fixed chords; see the keyboard-navigation plan Phase 2).

Checks the applied math at the canvas-interaction level with lightweight
fakes, mirroring the wheel/pan-drag formulas so parity holds.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QRect, Qt

from tabs.image_compare.canvas import interaction as ic_interaction
from tabs.multi_compare.canvas import interaction as mc_interaction


class _KeyEvent:
    def __init__(self, key):
        self._key = key
        self.accepted = False

    def key(self):
        return self._key

    def accept(self):
        self.accepted = True


class _ZoomSignal:
    def emit(self, *_args, **_kwargs):
        pass


class _IcRuntimeState:
    _read_only = False
    _render_scene = None
    _split_position_sync = None
    _store = None
    _stored_pil_images = []
    _inner_content_rect_px = None
    _content_rect_px = None


class _IcFakeWidget:
    def __init__(self):
        self.runtime_state = _IcRuntimeState()
        self.zoomChanged = _ZoomSignal()
        self.updated = 0

    def update(self):
        self.updated += 1

    def width(self):
        return 1000

    def height(self):
        return 800


def _mc_fake_widget(*, zoom=1.0, pan_x=0.0, pan_y=0.0, is_focused=False):
    state = SimpleNamespace(
        zoom=zoom,
        pan_x=pan_x,
        pan_y=pan_y,
        is_focused=is_focused,
        slots=[],
    )

    class _FakeMC:
        ZOOM_MIN = 1.0
        ZOOM_MAX = 50.0
        ZOOM_STEP = 1.1
        dispatched = []

        def __init__(self):
            self.state = state

        def _do_dispatch(self, action):
            self.dispatched.append(action)

        def _leaf_rects(self):
            return []

        def rect(self):
            return QRect(0, 0, 1000, 800)

    return _FakeMC()


def test_ic_arrow_right_pans_positive_x():
    widget = _IcFakeWidget()
    event = _KeyEvent(Qt.Key.Key_Right)
    ic_interaction.handle_key_press_event(widget, event)
    assert event.accepted
    from ui.canvas_infra.viewport.state import get_pan_offset_x

    assert get_pan_offset_x(widget) == 0.05


def test_ic_arrow_up_pans_negative_y():
    widget = _IcFakeWidget()
    event = _KeyEvent(Qt.Key.Key_Up)
    ic_interaction.handle_key_press_event(widget, event)
    from ui.canvas_infra.viewport.state import get_pan_offset_y

    assert get_pan_offset_y(widget) == -0.05


def test_ic_plus_minus_zoom_in_and_out():
    widget = _IcFakeWidget()
    from ui.canvas_infra.viewport.state import get_zoom_level

    ic_interaction.handle_key_press_event(widget, _KeyEvent(Qt.Key.Key_Plus))
    z1 = get_zoom_level(widget)
    assert z1 > 1.0
    ic_interaction.handle_key_press_event(widget, _KeyEvent(Qt.Key.Key_Minus))
    z2 = get_zoom_level(widget)
    assert z2 < z1
    assert z2 >= 1.0


def test_ic_non_canvas_key_still_emits():
    widget = _IcFakeWidget()
    emitted = []
    widget.keyPressed = SimpleNamespace(emit=lambda event: emitted.append(event))
    event = _KeyEvent(Qt.Key.Key_P)
    ic_interaction.handle_key_press_event(widget, event)
    assert not event.accepted
    assert emitted == [event]


def test_mc_arrow_right_dispatches_set_pan():
    widget = _mc_fake_widget()
    mc_interaction.handle_key_press_event(widget, _KeyEvent(Qt.Key.Key_Right))
    assert widget.dispatched
    action = widget.dispatched[-1]
    assert action.type == "multi_compare/set_pan"
    assert abs(action.pan_x - 0.05) < 1e-9
    assert action.pan_y == 0.0


def test_mc_arrow_up_dispatches_set_pan_negative_y():
    widget = _mc_fake_widget()
    mc_interaction.handle_key_press_event(widget, _KeyEvent(Qt.Key.Key_Up))
    action = widget.dispatched[-1]
    assert action.type == "multi_compare/set_pan"
    assert abs(action.pan_y + 0.05) < 1e-9


def test_mc_plus_dispatches_set_zoom_around_center_pan_unchanged():
    widget = _mc_fake_widget(zoom=2.0, pan_x=0.1, pan_y=0.2)
    mc_interaction.handle_key_press_event(widget, _KeyEvent(Qt.Key.Key_Plus))
    action = widget.dispatched[-1]
    assert action.type == "multi_compare/set_zoom"
    assert abs(action.zoom - 2.2) < 1e-9
    assert action.pan_x == 0.1 and action.pan_y == 0.2


def test_mc_zoom_min_clamps_to_floor_and_snaps_pan():
    widget = _mc_fake_widget(zoom=1.05, pan_x=0.1, pan_y=0.2)
    mc_interaction.handle_key_press_event(widget, _KeyEvent(Qt.Key.Key_Minus))
    action = widget.dispatched[-1]
    assert action.type == "multi_compare/set_zoom"
    assert action.zoom == widget.ZOOM_MIN
    assert action.pan_x == 0.0 and action.pan_y == 0.0


def test_mc_arrow_zooms_do_not_steal_escape_or_zero():
    widget = _mc_fake_widget(is_focused=True)
    mc_interaction.handle_key_press_event(widget, _KeyEvent(Qt.Key.Key_Escape))
    assert widget.dispatched[-1].type == "multi_compare/set_focus"
    widget = _mc_fake_widget()
    mc_interaction.handle_key_press_event(widget, _KeyEvent(Qt.Key.Key_0))
    assert widget.dispatched[-1].type == "multi_compare/reset_view"
