"""Local "done" badge must not precede the card quality dots.

Falsification (pre-fix): the first-load path stamped the local ``done`` phase on
the *triage* worker result (``_start_triage``), while the card's dots come from
the Stage-2 proxy pass (artifacts/fidelity/camera) started later in
``_apply_triage_result`` — so the badge read "done" 1-2 s before the dots
recolored. The append path already gated done on the proxy ``on_done``
(``_finish_append_processing``).

This drives ``_apply_triage_result`` with a captured proxy ``on_done``: the badge
must stay non-done while the proxy is in flight, and flip to done only when the
proxy settles (or immediately when there is nothing to compute).
"""

from __future__ import annotations

import time
from types import SimpleNamespace

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import ActivityPhase
from tabs.image_gallery.services.activity import activity_of

_DONE = (ActivityPhase.DONE.value, "local")


def _item(path: str = "/x/a.jpg") -> SimpleNamespace:
    return SimpleNamespace(
        path=path,
        mtime_ns=1,
        artifacts=None,
        metrics=None,
        activity_phase=ActivityPhase.ANALYZING.value,
        activity_source="local",
        activity_at=time.monotonic(),
        analysis_status=None,
        analysis_error=None,
        thumbnail_status=None,
    )


def _controller(item: SimpleNamespace) -> SimpleNamespace:
    ctl = SimpleNamespace(
        state=SimpleNamespace(items=[item]),
        widget=SimpleNamespace(
            set_triage=lambda *a, **k: None,
            set_triage_done=lambda *a, **k: None,
        ),
        _last_analysis_fingerprint=None,
        run_tie_break_if_needed=lambda ser: None,
    )
    # Real _mark_local_pass, bound to this fake (its widget-refresh hook is absent
    # but guarded).
    ctl._mark_local_pass = lambda items, phase: GalleryController._mark_local_pass(ctl, items, phase)
    return ctl


def test_local_done_waits_for_proxy_settle() -> None:
    item = _item()
    ctl = _controller(item)
    captured: dict = {}

    def _fake_proxy(items, source, mode, *, on_done=None):
        captured["on_done"] = on_done

    ctl._start_proxy_analysis = _fake_proxy
    GalleryController._apply_triage_result(ctl, [], None, None)

    # Proxy in flight → the badge must NOT read done yet (dots are not ready).
    assert captured.get("on_done") is not None, "proxy on_done not wired"
    assert activity_of(item) != _DONE, "badge showed done before the proxy settled"

    # Proxy settles → now (and only now) the badge may show done.
    captured["on_done"]()
    assert activity_of(item) == _DONE


def test_local_done_immediate_when_nothing_to_compute() -> None:
    item = _item()
    ctl = _controller(item)
    ctl._last_analysis_fingerprint = GalleryController._analysis_fingerprint(
        list(ctl.state.items), None
    )

    def _boom(*a, **k):
        raise AssertionError("proxy must not start when analyses are current")

    ctl._start_proxy_analysis = _boom
    GalleryController._apply_triage_result(ctl, [], None, None)

    # No proxy will settle → the badge must be retired immediately, not stuck.
    assert activity_of(item) == _DONE
