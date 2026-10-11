"""Per-item activity status: derivation, AI/local hooks, pill render, pulse.

Falsification: the pill-render tests fail if ``paint_item_activity`` is not
wired into the grid or list overlay; the idle-repaint test fails if the pulse
ever registers an idle card.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.models import (
    ActivityPhase,
    AnalysisStatus,
    GalleryItem,
    ThumbnailStatus,
)
from tabs.image_gallery.services import activity as act
from tabs.image_gallery.services import ai_client
from tabs.image_gallery.ui.card import build_gallery_card
from tabs.image_gallery.ui.card import activity_pill
from tabs.image_gallery.ui.card import activity_pulse as pulse_mod
from tabs.image_gallery.ui.card.activity_pulse import ActivityPulse
from tabs.image_gallery.ui.list.card import build_gallery_list_card


def _item(name: str = "a.png") -> GalleryItem:
    return GalleryItem(path=Path("/gallery") / name, mtime_ns=1)


# -- derivation ------------------------------------------------------------


def test_idle_item_has_no_activity() -> None:
    assert act.activity_of(_item(), now=0.0) is None


def test_analysis_status_maps_to_ai_phases() -> None:
    it = _item()
    it.analysis_status = AnalysisStatus.PENDING
    assert act.activity_of(it, now=0.0) == ("queued", "ai")
    it.analysis_status = AnalysisStatus.DONE
    assert act.activity_of(it, now=0.0) == ("done", "ai")
    it.analysis_status = AnalysisStatus.ERROR
    assert act.activity_of(it, now=0.0) == ("error", "ai")


def test_thumbnail_loading_maps_to_local_analyzing() -> None:
    it = _item()
    it.thumbnail_status = ThumbnailStatus.LOADING
    assert act.activity_of(it, now=0.0) == ("analyzing", "local")


def test_unreadable_wins_over_everything() -> None:
    it = _item()
    it.thumbnail_status = ThumbnailStatus.ERROR
    it.analysis_status = AnalysisStatus.PENDING
    act.set_activity(it, ActivityPhase.ANALYZING, "ai")
    assert act.activity_of(it) == ("unreadable", "local")


def test_non_unreadable_analysis_error_maps_to_error_ai() -> None:
    it = _item()
    it.analysis_error = "rate limited"
    it.analysis_status = AnalysisStatus.PENDING
    assert act.activity_of(it, now=0.0) == ("error", "ai")


def test_fresh_explicit_phase_beats_status_and_ttl_expires() -> None:
    it = _item()
    it.analysis_status = AnalysisStatus.PENDING
    act.set_activity(it, ActivityPhase.WAITING, "ai")
    stamped = it.activity_at
    assert act.activity_of(it, now=stamped + 1.0) == ("waiting", "ai")
    expired = stamped + act.ACTIVITY_TTL_S + 0.5
    assert act.activity_of(it, now=expired) == ("queued", "ai")


def test_explicit_source_defaults_to_local_when_missing() -> None:
    it = _item()
    it.activity_phase = "analyzing"
    it.activity_at = 10.0
    assert act.activity_of(it, now=10.0) == ("analyzing", "local")


def test_set_activity_reports_change_and_refreshes_timestamp() -> None:
    it = _item()
    assert act.set_activity(it, ActivityPhase.QUEUED, "ai") is True
    first = it.activity_at
    assert act.set_activity(it, ActivityPhase.QUEUED, "ai") is False
    assert it.activity_at >= first
    assert act.set_activity(it, ActivityPhase.DONE, "ai") is True
    with pytest.raises(ValueError):
        act.set_activity(it, ActivityPhase.DONE, "cloud")


def test_clear_activity_resets_transient_fields() -> None:
    it = _item()
    act.set_activity(it, ActivityPhase.DONE, "local")
    act.clear_activity(it)
    assert (it.activity_phase, it.activity_source, it.activity_at) == (None, None, 0.0)


# -- AI hook order -----------------------------------------------------------


def test_analyze_image_sync_emits_analyzing_then_waiting(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    monkeypatch.setattr(ai_client, "build_request", lambda *a, **k: calls.append("built") or {})
    monkeypatch.setattr(ai_client, "call_sync", lambda *a, **k: calls.append("sent") or {})
    monkeypatch.setattr(ai_client, "parse_response", lambda raw, model: "result")

    phases: list[str] = []
    out = ai_client.analyze_image_sync(
        tmp_path / "x.png",
        base_url="http://h",
        api_key="k",
        model="m",
        on_phase=lambda p: phases.append(p) or calls.append(f"phase:{p}"),
    )
    assert out == "result"
    assert phases == ["analyzing", "waiting"]
    assert calls == ["phase:analyzing", "built", "phase:waiting", "sent"]


def test_failing_phase_hook_never_breaks_analysis(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(ai_client, "build_request", lambda *a, **k: {})
    monkeypatch.setattr(ai_client, "call_sync", lambda *a, **k: {})
    monkeypatch.setattr(ai_client, "parse_response", lambda raw, model: "ok")

    def boom(_phase: str) -> None:
        raise RuntimeError("ui gone")

    assert ai_client.analyze_image_sync(
        tmp_path / "x.png", base_url="http://h", api_key="k", model="m", on_phase=boom
    ) == "ok"


# -- controller hooks ----------------------------------------------------------


class _Recorder:
    def __init__(self) -> None:
        self.refreshed: list[GalleryItem] = []

    def refresh_card(self, item: GalleryItem) -> None:
        self.refreshed.append(item)


def _bare_controller(items: list[GalleryItem]):
    from tabs.image_gallery.controller import GalleryController

    ctl = GalleryController.__new__(GalleryController)
    ctl.state = SimpleNamespace(items=items)
    ctl.widget = _Recorder()
    ctl._folder_gen = 0
    ctl._tr = lambda key, default: default
    ctl._ai_settings_store = SimpleNamespace(
        load=lambda: SimpleNamespace(
            enabled=True, api_key="k", model="m", base_url="http://h"
        )
    )
    return ctl


def test_begin_analysis_marks_queued_then_claimed_at_pool_start(monkeypatch) -> None:
    item = _item()
    ctl = _bare_controller([item])
    seen_at_start: list[tuple[str | None, str | None]] = []

    def fake_start(worker, priority) -> None:
        seen_at_start.append((item.activity_phase, item.activity_source))

    monkeypatch.setattr(ctl, "_pool_start", fake_start, raising=False)
    ctl._begin_analysis(item)
    assert seen_at_start == [("claimed", "ai")]
    assert act.activity_of(item) == ("claimed", "ai")


def test_apply_ai_phase_drops_stale_item_and_refreshes_current() -> None:
    item = _item()
    stale = _item()
    ctl = _bare_controller([item])
    ctl._apply_ai_phase(stale, "analyzing")
    assert ctl.widget.refreshed == []
    ctl._apply_ai_phase(item, "analyzing")
    assert item.activity_phase == "analyzing"
    assert ctl.widget.refreshed == [item]


def test_analysis_ready_and_error_set_terminal_phases() -> None:
    item = _item()
    ctl = _bare_controller([item])
    ctl._save = None
    from tabs.image_gallery.services import ai_client as _ac

    ctl._merge_measured_metrics = lambda result, it: result
    import tabs.image_gallery.controller as ctl_mod

    saved = ctl_mod.save_analysis
    ctl_mod.save_analysis = lambda *a, **k: None
    try:
        result = _ac.AiAnalysisResult(
            description="", tags=(), model="m", analyzed_at_iso="t"
        )
        ctl._on_analysis_ready(item.path, item.mtime_ns, result, None)
    finally:
        ctl_mod.save_analysis = saved
    assert act.activity_of(item) == ("done", "ai")

    ctl._on_analysis_error(item.path, (ValueError, ValueError("boom"), None), None)
    assert act.activity_of(item) == ("error", "ai")


# -- render: label per phase on grid + list --------------------------------------


@pytest.mark.parametrize("phase", ["queued", "claimed", "analyzing", "waiting", "error", "unreadable"])
def test_grid_and_list_pills_render_label_for_phase(qtbot, monkeypatch, phase) -> None:
    labels: list[str] = []
    real = activity_pill.activity_label

    def spy(p: str, translate=None) -> str:
        labels.append(p)
        return real(p, translate)

    monkeypatch.setattr(activity_pill, "activity_label", spy)
    item = _item(f"{phase}.png")
    act.set_activity(item, phase, "ai")
    grid = build_gallery_card(item)
    lst = build_gallery_list_card(item)
    qtbot.addWidget(grid)
    qtbot.addWidget(lst)
    grid.show()
    lst.show()
    grid.grab()
    lst.grab()
    assert labels.count(phase) >= 2
    assert all("image_gallery.activity." not in real(p) for p in labels)


def test_activity_label_uses_tab_translator() -> None:
    seen: list[tuple[str, str]] = []

    def tr(key: str, default: str) -> str:
        seen.append((key, default))
        return "Очередь"

    assert activity_pill.activity_label("queued", tr) == "Очередь"
    assert seen == [("image_gallery.activity.queued", "Queued")]
    assert activity_pill.activity_label("queued") == "Queued"


def test_done_pill_is_silent_when_settled(qtbot, monkeypatch) -> None:
    labels: list[str] = []
    monkeypatch.setattr(activity_pill, "activity_label", lambda p, t=None: labels.append(p) or p)
    item = _item("settled.png")
    item.analysis_status = AnalysisStatus.DONE
    card = build_gallery_card(item)
    qtbot.addWidget(card)
    card.show()
    card.grab()
    assert "done" not in labels


# -- pulse: fade lifecycle + idle never repaints ---------------------------------


def _counting(card) -> list[int]:
    counter = [0]
    real = card.update

    def counted(*a, **k):
        counter[0] += 1
        return real(*a, **k)

    card.update = counted
    return counter


def test_done_card_fades_then_clears_phase(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(pulse_mod, "DONE_LINGER_MS", 10)
    monkeypatch.setattr(pulse_mod, "DONE_FADE_MS", 10)
    item = _item("fade.png")
    card = build_gallery_card(item)
    qtbot.addWidget(card)
    card.show()
    pulse = ActivityPulse(card)
    act.set_activity(item, ActivityPhase.DONE, "ai")
    pulse.sync(card)
    assert pulse.tracked_count() == 1
    qtbot.waitUntil(lambda: item.activity_phase is None, timeout=3000)
    assert pulse.tracked_count() == 0
    assert card._gallery_activity_alpha is None


def test_idle_cards_never_repaint(qtbot) -> None:
    item = _item("idle.png")
    card = build_gallery_card(item)
    qtbot.addWidget(card)
    card.show()
    pulse = ActivityPulse(card)
    ticks: list[int] = []
    real_tick = pulse._tick
    pulse._timer.timeout.disconnect()
    pulse._timer.timeout.connect(lambda: ticks.append(1) or real_tick())
    pulse.sync(card)
    qtbot.wait(300)
    assert pulse.tracked_count() == 0
    assert not pulse._timer.isActive()
    assert ticks == []


def test_active_card_repaints_until_phase_clears(qtbot) -> None:
    item = _item("busy.png")
    card = build_gallery_card(item)
    qtbot.addWidget(card)
    card.show()
    counter = _counting(card)
    pulse = ActivityPulse(card)
    act.set_activity(item, ActivityPhase.ANALYZING, "ai")
    pulse.sync(card)
    assert pulse.tracked_count() == 1
    qtbot.waitUntil(lambda: counter[0] >= 3, timeout=2000)
    act.clear_activity(item)
    item.analysis_status = AnalysisStatus.NOT_ANALYZED
    qtbot.waitUntil(lambda: pulse.tracked_count() == 0, timeout=2000)
