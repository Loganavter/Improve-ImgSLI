"""IC slots to demand pyramid: unify kicks demand, zoom demands, abort holds.

Exercises ONLY the tab-local kick policy
(``tabs.image_compare.use_cases.loading_pyramid``) against fake
coordinators — the engine ``demand_level`` / ``select_level`` /
``estimate_total_levels`` primitives are consumed verbatim (E1/E2), never
re-implemented here. Offscreen-Qt compatible, no live RHI, no threads.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from engine.cache.lod import select_level
from engine.store.pyramid_pixel_store import estimate_total_levels
from tabs.image_compare.use_cases import loading_pyramid as _lp


# --- fakes ---


class _DemandCoord:
    """Coordinator double with both demand + eager spies."""

    def __init__(self, *, demand_result=True):
        self.demand_calls: list[tuple] = []
        self.start_calls: list[tuple] = []
        self.demand_result = demand_result

    def demand_level(self, store, k, *, slot_id=None, **kw):
        self.demand_calls.append((store, int(k), slot_id))
        return self.demand_result

    def start_build(self, store, *, slot_id=None, **kw):
        self.start_calls.append((store, slot_id, kw.get("toast_live")))
        return True

    def on_level_ready(self, payload):
        pass


class _LegacyCoord:
    """Pre-demand coordinator (no demand_level): eager fallback must hold."""

    def __init__(self):
        self.start_calls: list[tuple] = []

    def start_build(self, store, *, slot_id=None, **kw):
        self.start_calls.append((store, slot_id, kw.get("toast_live")))
        return True

    def on_level_ready(self, payload):
        pass


def _store(w=4096, h=4096):
    return SimpleNamespace(width=w, height=h, is_open=True)


def _host(fb_w=1000, fb_h=800, zoom=0.125):
    from ui.canvas_infra.viewport import set_zoom_level

    host = SimpleNamespace(
        size=lambda: SimpleNamespace(width=lambda: fb_w, height=lambda: fb_h)
    )
    set_zoom_level(host, zoom)
    return host


def _controller(*, coord, host=None, image_state=None, session=None, finishes=None):
    finishes = finishes if finishes is not None else []
    ctrl = SimpleNamespace(
        pipeline=None,
        _pyramid_coordinator=coord,
        presenter=SimpleNamespace(widget=SimpleNamespace(image_label=host)),
        store=SimpleNamespace(
            viewport=SimpleNamespace(
                session_data=SimpleNamespace(image_state=image_state)
            )
        ),
        _finish_loading_toast=lambda slot: finishes.append(slot),
    )
    ctrl._get_image_session = lambda: session
    ctrl._finishes = finishes
    return ctrl


def _fit_zoom(fb_w, fb_h, w, h) -> float:
    return min(fb_w / w, fb_h / h)


# --- unify kick: demand, never full build ---


def test_unify_kick_demands_fit_level_not_full_build():
    coord = _DemandCoord()
    w = h = 4096
    fb_w, fb_h = 1000, 800
    zoom = _fit_zoom(fb_w, fb_h, w, h)
    ctrl = _controller(coord=coord, host=_host(fb_w, fb_h, zoom))
    store = _store(w, h)

    _lp.start_pyramid_builds(ctrl, store)

    dest = min(fb_w / w, fb_h / h) * zoom
    expected = select_level(dest, estimate_total_levels(w, h))
    assert expected > 0, "fixture must demand a real level"
    assert coord.demand_calls == [(store, expected, 1)]
    assert coord.start_calls == [], "no eager full build on the demand path"


def test_unify_kick_second_slot_positional():
    coord = _DemandCoord()
    ctrl = _controller(coord=coord, host=_host())
    s1, s2 = _store(), _store(2048, 2048)
    _lp.start_pyramid_builds(ctrl, s1, s2)
    assert [c[2] for c in coord.demand_calls] == [1, 2]
    assert coord.start_calls == []


def test_unify_kick_skips_none_positionally():
    coord = _DemandCoord()
    ctrl = _controller(coord=coord, host=_host())
    _lp.start_pyramid_builds(ctrl, None, _store())
    assert len(coord.demand_calls) == 1
    assert coord.demand_calls[0][2] == 2


def test_demand_target_bounded_below_full_depth():
    """Fit demand names the fit level; coarser levels wait (no build_all)."""
    coord = _DemandCoord()
    w = h = 16384
    fb_w, fb_h = 1000, 800
    zoom = 1.43  # zoomed toward 1:1: finer than fit, coarser than base
    ctrl = _controller(coord=coord, host=_host(fb_w, fb_h, zoom))
    store = _store(w, h)

    _lp.start_pyramid_builds(ctrl, store)

    total = estimate_total_levels(w, h)
    dest = min(fb_w / w, fb_h / h) * zoom
    expected = select_level(dest, total)
    assert 0 < expected < total - 1, "fixture must sit strictly inside the pyramid"
    assert coord.demand_calls == [(store, expected, 1)]
    assert coord.start_calls == []


def test_tiny_image_finishes_toast_without_worker():
    coord = _DemandCoord()
    ctrl = _controller(coord=coord, host=_host())
    _lp.start_pyramid_builds(ctrl, _store(512, 512))
    assert coord.demand_calls == []
    assert coord.start_calls == []
    assert ctrl._finishes == [1], "live toast still finishes (skip-path parity)"


def test_legacy_coordinator_falls_back_to_eager():
    coord = _LegacyCoord()
    ctrl = _controller(coord=coord, host=_host())
    _lp.start_pyramid_builds(ctrl, _store())
    assert len(coord.start_calls) == 1


def test_preview_race_keeps_non_live_eager_wiring():
    """Decode still in flight: no toast touch (today's toast_live=False)."""
    coord = _DemandCoord()
    sig = SimpleNamespace(is_aborted=lambda: False)
    ctrl = _controller(coord=coord, host=_host())
    ctrl.pipeline = SimpleNamespace(_inflight={(1, "p"): sig})
    store = _store()
    _lp.start_pyramid_builds(ctrl, store)
    assert coord.demand_calls == []
    assert coord.start_calls == [(store, 1, False)]


# --- zoom hook: demand newly needed, never rebuild ---


def _zoom_controller(coord, stores, *, zoom=0.125):
    state = SimpleNamespace(image1=None, image2=None)
    for i, s in enumerate(stores):
        setattr(state, f"image{i + 1}", s)
    return _controller(coord=coord, host=_host(zoom=zoom), image_state=state)


def test_zoom_change_demands_newly_needed_level():
    coord = _DemandCoord()
    w = h = 16384
    s1, s2 = _store(w, h), _store(w, h)
    ctrl = _zoom_controller(coord, [s1, s2])

    assert _lp.demand_for_zoom(ctrl, 1.43) is True

    total = estimate_total_levels(w, h)
    expected = select_level(min(1000 / w, 800 / h) * 1.43, total)
    assert coord.demand_calls == [(s1, expected, 1), (s2, expected, 2)]


def test_zoom_out_past_fit_demands_coarser_level():
    coord = _DemandCoord()
    w = h = 16384
    store = _store(w, h)
    ctrl = _zoom_controller(coord, [store])

    _lp.demand_for_zoom(ctrl, 1.43)
    _lp.demand_for_zoom(ctrl, 0.02)

    total = estimate_total_levels(w, h)
    k_near = select_level(min(1000 / w, 800 / h) * 1.43, total)
    k_far = select_level(min(1000 / w, 800 / h) * 0.02, total)
    assert k_far > k_near, "fixture must separate the two targets"
    assert coord.demand_calls[-1] == (store, k_far, 1)


def test_deep_zoom_in_demands_nothing():
    """Base always resident: k == 0 skips the coordinator entirely."""
    coord = _DemandCoord()
    ctrl = _zoom_controller(coord, [_store()])
    assert _lp.demand_for_zoom(ctrl, 50.0) is False
    assert coord.demand_calls == []


def test_zoom_with_aborted_session_demands_nothing():
    coord = _DemandCoord()
    ctrl = _zoom_controller(coord, [_store()])
    ctrl._get_image_session = lambda: SimpleNamespace(
        abort=SimpleNamespace(is_aborted=lambda: True)
    )
    assert _lp.demand_for_zoom(ctrl, 1.43) is False
    assert coord.demand_calls == []


def test_zoom_ignores_preview_tier():
    from PySide6.QtGui import QImage

    coord = _DemandCoord()
    preview = QImage(32, 32, QImage.Format.Format_RGBA8888)
    ctrl = _zoom_controller(coord, [preview, _store()])
    assert _lp.demand_for_zoom(ctrl, 1.43) is True
    assert len(coord.demand_calls) == 1
    assert coord.demand_calls[0][2] == 2


def test_in_flight_zoom_parks_pending_and_complete_retries(monkeypatch):
    coord = _DemandCoord(demand_result=False)  # refused: build in flight
    store = _store()
    ctrl = _zoom_controller(coord, [store])

    assert _lp.demand_for_zoom(ctrl, 1.43) is False
    pending = getattr(ctrl, "_pending_pyramid_demands", {})
    assert len(pending) == 1

    # Complete arrives while the session is live: parked demand retried.
    coord.demand_result = True
    monkeypatch.setattr(
        "engine.store.pyramid_registry.pyramid_for",
        lambda s: SimpleNamespace(is_level_built=lambda k: False),
    )
    _lp.on_pyramid_level_ready(ctrl, (123, 2, 5, True))
    assert coord.demand_calls, "parked demand retried on complete"
    assert getattr(ctrl, "_pending_pyramid_demands", {}) == {}


def test_supersede_drops_pending_without_retry():
    coord = _DemandCoord(demand_result=False)
    store = _store()
    ctrl = _zoom_controller(coord, [store])
    assert _lp.demand_for_zoom(ctrl, 1.43) is False
    assert getattr(ctrl, "_pending_pyramid_demands", {})

    # New unify task aborted the session: pending dies, no retry.
    ctrl._get_image_session = lambda: SimpleNamespace(
        abort=SimpleNamespace(is_aborted=lambda: True)
    )
    calls_before = len(coord.demand_calls)
    _lp.on_pyramid_level_ready(ctrl, (123, 2, 5, True))
    assert len(coord.demand_calls) == calls_before
    assert getattr(ctrl, "_pending_pyramid_demands", {}) == {}


# --- verbatim E2 reuse: built levels never rebuild, abort holds ---


def test_coordinator_short_circuits_built_level_without_worker():
    from engine.pyramid.coordinator import PyramidBuildCoordinator

    started: list = []

    class _NoPool:
        def start(self, worker):
            started.append(worker)
            raise AssertionError("no worker for a built level")

    pyramid = SimpleNamespace(is_level_built=lambda k: True)
    coord = PyramidBuildCoordinator(
        get_thread_pool=_NoPool,
        get_pyramid=lambda s: pyramid,
    )
    assert coord.demand_level(_store(), 3, slot_id=1) is True
    assert started == []


def test_coordinator_pre_abort_starts_nothing():
    from engine.pyramid.coordinator import PyramidBuildCoordinator

    coord = PyramidBuildCoordinator(
        get_thread_pool=lambda: SimpleNamespace(start=lambda w: None),
        get_pyramid=lambda s: SimpleNamespace(is_level_built=lambda k: False),
    )
    assert (
        coord.demand_level(_store(), 2, slot_id=1, should_abort=lambda: True)
        is False
    )
