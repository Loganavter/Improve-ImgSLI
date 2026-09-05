"""Zoom-tick fan-out: a wheel burst must do bounded sync work per tick.

Covers the mc-zoom-fanout findings (wheelEvent -> handle_wheel_event ->
set_zoom dispatch fan-out): at most 1 dispatch per tick, zero dispatches for
clamped/float-dust ticks, no texture uploads on zoom-only changes, toolbar
sync skipped for pure view actions, ``ensure_window_active`` never fires on
wheel ticks (F1: IC parity -- settle sync owns the catch-up), and
the cursor-anchor math + clamps pinned byte-identical.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QImage

from tabs.multi_compare.canvas import interaction as mc_interaction
from tabs.multi_compare.models import (
    CompareSlot,
    LeafNode,
    MultiCompareDividerSettings,
    MultiCompareState,
)
from tabs.multi_compare.pipeline.cache import MultiComparePixelCache
from tabs.multi_compare.scene import actions as mc_actions
from tabs.multi_compare.scene.store import MultiCompareStore


class _WheelEvent:
    def __init__(self, delta, x=100, y=100):
        self._delta = delta
        self._pos = QPoint(x, y)
        self.accepted = False
        self.ignored = False

    def angleDelta(self):
        return SimpleNamespace(y=lambda: self._delta)

    def position(self):
        pos = self._pos
        return SimpleNamespace(
            toPoint=lambda: pos,
            x=lambda: float(pos.x()),
            y=lambda: float(pos.y()),
        )

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


def _slot_image(tmp_path, name="img0.png", w=64, h=48):
    p = tmp_path / name
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x808080)
    assert img.save(str(p))
    return p


def _wheel_widget(store, cache, rects):
    class _FakeCanvas:
        ZOOM_MIN = 1.0
        ZOOM_MAX = 50.0
        ZOOM_STEP = 1.1

    w = _FakeCanvas()
    w.state = store.state
    w.pixel_cache = cache
    w.window = lambda: None
    dispatched = []

    def _do_dispatch(action):
        dispatched.append(action)
        store.dispatch(action)
        w.state = store.state

    w._do_dispatch = _do_dispatch
    w._leaf_rects = lambda: rects
    w.dispatched = dispatched
    return w


@pytest.fixture()
def zoom_env(tmp_path):
    cache = MultiComparePixelCache()
    paths = [_slot_image(tmp_path, f"img{i}.png") for i in range(2)]
    for p in paths:
        cache.put_preview(p, QImage(str(p)))
    slots = [
        CompareSlot(id=i + 1, path=p, label=p.name, revision=0)
        for i, p in enumerate(paths)
    ]
    store = MultiCompareStore(initial=MultiCompareState(slots=slots))
    rects = [
        (LeafNode(s.id), QRect(i * 200, 0, 200, 200)) for i, s in enumerate(slots)
    ]
    widget = _wheel_widget(store, cache, rects)
    return SimpleNamespace(
        widget=widget, store=store, cache=cache, rects=rects, slots=slots
    )


def test_wheel_burst_dispatches_at_most_one_per_tick(zoom_env):
    w = zoom_env.widget
    for _ in range(20):
        mc_interaction.handle_wheel_event(w, _WheelEvent(120))
    assert len(w.dispatched) == 20
    assert all(a.type == "multi_compare/set_zoom" for a in w.dispatched)
    zooms = [a.zoom for a in w.dispatched]
    assert zooms == sorted(zooms)
    # cursor-anchor at cell center keeps pan at origin
    first = w.dispatched[0]
    assert first.zoom == pytest.approx(1.1)
    assert first.pan_x == pytest.approx(0.0)
    assert first.pan_y == pytest.approx(0.0)


def test_wheel_cursor_anchor_math_pinned(zoom_env):
    """Off-center wheel position shifts pan by the anchored amount (golden)."""
    store = zoom_env.store
    store.dispatch(mc_actions.set_zoom(2.0, 0.0, 0.0))
    w = zoom_env.widget
    w.state = store.state
    # img0 is 64x48 in a 200x200 cell: img_ar > cell_ar -> fit == (1.0, 0.75)
    mc_interaction.handle_wheel_event(w, _WheelEvent(120, x=150, y=100))
    assert len(w.dispatched) == 1
    action = w.dispatched[0]
    assert action.zoom == pytest.approx(2.2)
    # cell_u = 0.75, fit_x = 1.0: pan_x = 0.25 * (1/2.2 - 1/2.0)
    assert action.pan_x == pytest.approx(0.25 * (1.0 / 2.2 - 1.0 / 2.0))
    # cell_v = 0.5 -> pan_y unchanged
    assert action.pan_y == pytest.approx(0.0)


def test_wheel_clamped_ticks_dispatch_nothing(zoom_env, monkeypatch):
    from ui.canvas_infra.rhi import rhi_present_sync as present_sync

    calls = []
    monkeypatch.setattr(
        present_sync, "ensure_window_active_for_qrhi", lambda _w: calls.append(1)
    )
    # park at the zoom ceiling, then push further: pure no-ops
    zoom_env.store.dispatch(mc_actions.set_zoom(50.0, 0.0, 0.0))
    zoom_env.widget.state = zoom_env.store.state
    events = [_WheelEvent(120) for _ in range(10)]
    for ev in events:
        mc_interaction.handle_wheel_event(zoom_env.widget, ev)
        assert ev.accepted
    assert zoom_env.widget.dispatched == []
    # ... and no-op ticks never touch window activation either
    assert calls == []
    # zoom floor behaves the same (clamp + pan snap preserved)
    zoom_env2_widget = zoom_env.widget
    zoom_env.store.dispatch(mc_actions.set_zoom(1.0, 0.0, 0.0))
    zoom_env2_widget.state = zoom_env.store.state
    ev = _WheelEvent(-120)
    mc_interaction.handle_wheel_event(zoom_env2_widget, ev)
    assert ev.accepted
    assert zoom_env.widget.dispatched == []
    assert calls == []


def test_wheel_float_dust_swallowed_ic_parity(zoom_env):
    """Sub-epsilon zoom deltas dispatch nothing (IC ``1e-6`` parity)."""
    w = zoom_env.widget
    orig_class = type(w)

    class _DustyCanvas(orig_class):
        ZOOM_STEP = 1.0 + 1e-9

    w.__class__ = _DustyCanvas
    try:
        for _ in range(5):
            mc_interaction.handle_wheel_event(w, _WheelEvent(120))
    finally:
        w.__class__ = orig_class
    assert w.dispatched == []


def test_wheel_delta_zero_is_free(zoom_env, monkeypatch):
    from ui.canvas_infra.rhi import rhi_present_sync as present_sync

    calls = []
    monkeypatch.setattr(
        present_sync, "ensure_window_active_for_qrhi", lambda _w: calls.append(1)
    )
    leaf_calls = []
    orig_leafs = zoom_env.widget._leaf_rects
    zoom_env.widget._leaf_rects = lambda: leaf_calls.append(1) or orig_leafs()
    ev = _WheelEvent(0)
    mc_interaction.handle_wheel_event(zoom_env.widget, ev)
    assert ev.accepted
    assert zoom_env.widget.dispatched == []
    assert calls == []
    assert leaf_calls == []


def test_identical_set_zoom_is_single_notify_no_reemit():
    store = MultiCompareStore(initial=MultiCompareState())
    seen = []
    store.subscribe(lambda a, s: seen.append((a, s)))
    first = store.dispatch(mc_actions.set_zoom(2.0, 0.1, 0.2))
    second = store.dispatch(mc_actions.set_zoom(2.0, 0.1, 0.2))
    assert second is first
    assert len(seen) == 1


def test_zoom_only_change_uploads_nothing_new():
    """``_sync_textures`` must not re-upload on identical sources (zoom tick)."""
    from tabs.multi_compare.ui.canvas_widget import MultiCompareCanvasWidget

    source = object()
    uploads = []
    renderer = SimpleNamespace(
        has_slot_texture=lambda _sid: True,
        slot_texture_source=lambda _sid: source,
        queue_upload=lambda sid, src: uploads.append((sid, src)),
        queue_remove=lambda _sid: uploads.append(("remove", None)),
        slot_texture_ids=lambda: [1],
    )
    canvas = SimpleNamespace(
        _slot_sources=lambda: {1: source},
        _active_composition=None,
        _renderer=renderer,
        upload_pixel_source=lambda sid, src: uploads.append((sid, src)),
        remove_texture=lambda sid: uploads.append(("remove", sid)),
        update=lambda: None,
    )
    MultiCompareCanvasWidget._sync_textures(canvas)
    assert uploads == []
    # sanity: a genuinely new source still uploads through the same path
    canvas2 = SimpleNamespace(
        _slot_sources=lambda: {1: object()},
        _active_composition=None,
        _renderer=SimpleNamespace(
            has_slot_texture=lambda _sid: False,
            slot_texture_source=lambda _sid: None,
            queue_upload=lambda sid, src: uploads.append((sid, src)),
            queue_remove=lambda _sid: None,
            slot_texture_ids=lambda: [],
        ),
        upload_pixel_source=lambda sid, src: uploads.append((sid, src)),
        remove_texture=lambda sid: None,
        update=lambda: None,
    )
    MultiCompareCanvasWidget._sync_textures(canvas2)
    assert len(uploads) == 1


def test_fit_cache_skips_resolve_after_first_tick(zoom_env, monkeypatch):
    w = zoom_env.widget
    resolve_calls = []
    orig_resolve = zoom_env.cache.resolve
    monkeypatch.setattr(
        zoom_env.cache,
        "resolve",
        lambda path: resolve_calls.append(1) or orig_resolve(path),
    )
    for _ in range(10):
        mc_interaction.handle_wheel_event(w, _WheelEvent(120, x=50, y=50))
    # first tick resolves once; the rest hit the fit cache (no os.stat path)
    assert len(resolve_calls) == 1
    # a decoded-tier arrival (revision bump via the real action) invalidates
    w._do_dispatch(mc_actions.note_slot_pixels(w.state.slots[0].id, "pixel"))
    w.dispatched.clear()
    mc_interaction.handle_wheel_event(w, _WheelEvent(120, x=50, y=50))
    assert len(resolve_calls) == 2


def test_divider_toolbar_skipped_for_view_actions(qapp, monkeypatch):
    from tabs.multi_compare.ui import divider_sync

    store = MultiCompareStore(initial=MultiCompareState())
    btn_ops = []

    class _Btn:
        def blockSignals(self, _b):
            btn_ops.append("block")

        def setChecked(self, _b):
            btn_ops.append("checked")

        def get_value(self):
            btn_ops.append("get")
            return 4

        def set_value(self, _v):
            btn_ops.append("set")

        def setUnderlineColor(self, _c):
            btn_ops.append("color")

    canvas_calls = []
    canvas = SimpleNamespace(
        set_state=lambda _s: canvas_calls.append("set_state"),
        request_view_update=lambda: canvas_calls.append("request_view_update"),
    )
    toolbar = SimpleNamespace(
        btn_divider_visible=_Btn(),
        btn_divider_width=_Btn(),
        btn_divider_color=_Btn(),
    )
    widget = SimpleNamespace(
        canvas=canvas,
        toolbar=toolbar,
        store=store,
        _focus_dim_toolbar=None,
        _focus_dim_footer=None,
        _font_popup_open=False,
        _divider_toolbar_sync_pending=False,
    )
    widget._sync_zoom_indicator = lambda: canvas_calls.append("sync_indicator")
    widget.sync_divider_toolbar = lambda: divider_sync.sync_divider_toolbar(widget)

    fired = []
    store.subscribe(lambda a, s: fired.append(a.type) or divider_sync.on_store_change(widget, a, s))
    store.dispatch(mc_actions.set_zoom(2.0, 0.1, 0.2))
    assert canvas_calls == ["set_state", "sync_indicator", "request_view_update"]
    assert btn_ops == []
    assert widget._divider_toolbar_sync_pending is False

    store.dispatch(
        mc_actions.set_divider_settings(
            MultiCompareDividerSettings(
                visible=True, thickness=6, color_rgba=(255, 0, 0, 255)
            )
        )
    )
    assert btn_ops != []
    assert fired == ["multi_compare/set_zoom", "multi_compare/set_divider_settings"]


def test_ensure_active_never_fires_on_wheel_ticks(tmp_path, monkeypatch):
    # F1 (task-mc-zoom-remove-wheel-kick): the wheel path no longer kicks
    # window activation at all (IC parity) -- was throttled to one per
    # burst before. The Wayland stale-canvas catch-up is handled on gesture
    # settle by schedule_compositor_sync instead (see
    # test_mc_zoom_no_busy_cursor.py catch-up guard).
    from ui.canvas_infra.rhi import rhi_present_sync as present_sync

    calls = []
    monkeypatch.setattr(
        present_sync, "ensure_window_active_for_qrhi", lambda _w: calls.append(1)
    )
    path = _slot_image(tmp_path, "throttle.png")
    cache = MultiComparePixelCache()
    cache.put_preview(path, QImage(str(path)))
    store = MultiCompareStore(
        initial=MultiCompareState(
            slots=[CompareSlot(id=1, path=path, label="t", revision=0)]
        )
    )
    w = _wheel_widget(store, cache, [(LeafNode(1), QRect(0, 0, 200, 200))])
    mc_interaction.handle_wheel_event(w, _WheelEvent(120))
    mc_interaction.handle_wheel_event(w, _WheelEvent(120))
    assert w.dispatched and len(w.dispatched) == 2
    assert calls == []
    # a longer burst still never kicks -- no widget-level throttle attr left
    assert not hasattr(w, "_last_zoom_activate_ms")
    mc_interaction.handle_wheel_event(w, _WheelEvent(120))
    assert calls == []


def _indicator_widget(zoom=2.0, pan_x=0.0, pan_y=0.0, lang="en"):
    updates = []
    indicator = SimpleNamespace(
        update_zoom=lambda z, px=0.0, py=0.0: updates.append((z, px, py)),
        _lang_provider=lambda: lang,
        _target_widget=None,
    )
    widget = SimpleNamespace(
        zoom_indicator=indicator,
        store=SimpleNamespace(
            state=SimpleNamespace(zoom=zoom, pan_x=pan_x, pan_y=pan_y)
        ),
    )
    return widget, indicator, updates


def test_zoom_indicator_memo_skips_redundant_updates():
    from tabs.multi_compare.ui import chrome

    widget, _ind, updates = _indicator_widget(zoom=2.0)
    chrome.sync_zoom_indicator(widget)
    chrome.sync_zoom_indicator(widget)
    chrome.sync_zoom_indicator(widget)
    assert len(updates) == 1
    # a real percent change still propagates
    widget.store.state.zoom = 3.0
    chrome.sync_zoom_indicator(widget)
    assert len(updates) == 2
    assert updates[-1][0] == pytest.approx(3.0)


def test_zoom_indicator_memo_refreshes_on_language_switch():
    from tabs.multi_compare.ui import chrome

    widget, indicator, updates = _indicator_widget(zoom=2.0, lang="en")
    chrome.sync_zoom_indicator(widget)
    assert len(updates) == 1
    indicator._lang_provider = lambda: "ru"
    chrome.sync_zoom_indicator(widget)
    assert len(updates) == 2
