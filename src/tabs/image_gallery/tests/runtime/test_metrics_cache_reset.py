"""Reset-metrics-cache: the gallery genuinely RECOMPUTES, not just deletes files.

Falsification stories (each fails on the parent tree — the clear API does not
exist there, and a naive "just delete the cache files" implementation fails the
same assertions):

* ``test_clear_defeats_the_skip`` — a pool whose items carry
  ``metrics``/``artifacts``/``artifact_maps``/``analysis`` + ``_ai_cache_checked``
  and a non-None ``_last_analysis_fingerprint``, plus a stored metric profile and
  a seeded profile pin: without the clear the fingerprint/profile/pin all
  survive, so ``use_cases.proxy_pass._apply_triage_result`` reads
  ``fingerprint == owner._last_analysis_fingerprint`` and SKIPS the re-measure.
  Deleting cache files alone is a no-op — the test asserts every one of those is
  cleared.
* ``test_ai_cache_is_really_bypassed`` — a seeded AI scorecard is served by
  ``ai_cache.hydrate_item``; after the clear the same lookup must MISS and the
  item's ``_ai_cache_checked`` must be reset (a naive "drop the rows, keep the
  flag" clear leaves it True, so ``hydrate_item`` returns ``False`` *before* it
  ever reads the disk).
* ``test_reset_reenters_the_rebuild`` — ``reset_metrics_caches`` calls
  ``_start_triage(..., cover_grid=False)``; a missing folder / controller
  degrades to the clear-only path.
* ``test_menu_entry_and_registry_descriptor`` — the ad-hoc card menu carries
  gallery.reset_metrics with the frozen label AND the ActionRegistry contributes
  gallery.reset-metrics (Find Action / MCP) — the ad-hoc menu
  path never consults the registry on its own, so both wirings are required.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.models import AiAnalysisResult, AnalysisStatus, GalleryItem
from tabs.image_gallery.services import ai_cache, profile_cache
from tabs.image_gallery.services.metric_profile import MetricProfile


class _Owner:
    """Minimal controller double: ``state.items`` + the clear seam hooks."""

    def __init__(self, items, *, folder=Path("/folder")) -> None:
        self.state = SimpleNamespace(
            items=list(items), folder=folder, metric_profile=None
        )
        self._last_analysis_fingerprint: object = ("stale",)
        self.cleared = 0

    def clear_metric_profile(self) -> None:
        self.cleared += 1
        self.state.metric_profile = None


@pytest.fixture
def caches(tmp_path, monkeypatch):
    """Redirect the AI scorecard dir + the default profile pin cache to tmp."""
    ai_dir = tmp_path / "ai"
    ai_dir.mkdir()
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: ai_dir)
    pins = tmp_path / "pins"
    pins.mkdir()
    monkeypatch.setattr(profile_cache, "_default_cache", profile_cache.ProfileCache(pins))
    return ai_dir, pins


def _cached_result() -> AiAnalysisResult:
    return AiAnalysisResult(
        description="cached",
        tags=("sky",),
        model="test/model",
        analyzed_at_iso="2026-01-01T00:00:00+00:00",
        sharpness=80,
        verdict="keep",
    )


#: The identity these reset tests seed/read under (the reset itself is
#: identity-agnostic: it must drop every variant, see
#: ``test_clear_removes_every_identity_for_the_image`` in test_ai_cache_identity).
IDENTITY = ai_cache.analysis_cache_identity(None, mode="fidelity")


def test_clear_defeats_the_skip(tmp_path, caches) -> None:
    """Every skip gate (fingerprint / profile / pin / item state) is cleared."""
    from tabs.image_gallery.use_cases import cache_reset

    ai_dir, pins = caches
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\x00")
    mtime = img.stat().st_mtime_ns

    item = GalleryItem(path=img, mtime_ns=mtime)
    item.metrics = {"ssim": 0.9}
    item.artifacts = {"banding": "bad"}
    item.artifact_maps = {"banding": [[1]]}
    item.analysis = _cached_result()
    item.analysis_status = AnalysisStatus.DONE
    item.analysis_error = "boom"
    item._ai_cache_checked = True

    owner = _Owner([item])
    owner.state.metric_profile = MetricProfile(
        axis_ids=("ssim",), mode="fidelity", source="vlm"
    )
    # Seed the disk caches the reset must invalidate.
    ai_cache.save_analysis(img, mtime, item.analysis, IDENTITY)
    key = profile_cache.profile_cache_key([item], mode="fidelity", model="test/model")
    profile_cache.default_cache().put(key, owner.state.metric_profile)
    assert list(ai_dir.glob("*.json"))
    assert list(pins.glob("profile_*.json"))

    summary = cache_reset.clear_metrics_caches(owner)

    # The fingerprint gate would otherwise skip the whole re-measure.
    assert owner._last_analysis_fingerprint is None
    assert owner.state.metric_profile is None
    assert owner.cleared == 1
    assert list(pins.glob("profile_*.json")) == []
    assert list(ai_dir.glob("*.json")) == []
    # Items pristine: the proxy pass must repopulate them from scratch.
    assert item.metrics == {}
    assert item.artifacts == {}
    assert item.artifact_maps == {}
    assert item.analysis is None
    assert item.analysis_status == AnalysisStatus.NOT_ANALYZED
    assert item.analysis_error is None
    assert not item._ai_cache_checked
    assert summary == {"items": 1, "ai_files": 1, "profiles": 1}


def test_ai_cache_is_really_bypassed(tmp_path, caches) -> None:
    """The disk scorecard is served before the clear and misses after it."""
    from tabs.image_gallery.use_cases import cache_reset

    img = tmp_path / "a.jpg"
    img.write_bytes(b"\x00")
    mtime = img.stat().st_mtime_ns
    ai_cache.save_analysis(img, mtime, _cached_result(), IDENTITY)

    # Pre-state: a fresh item is hydrated straight from the disk cache.
    probe = GalleryItem(path=img, mtime_ns=mtime)
    assert ai_cache.hydrate_item(probe, IDENTITY) is True
    assert probe.analysis is not None

    item = GalleryItem(path=img, mtime_ns=mtime)
    owner = _Owner([item])
    cache_reset.clear_metrics_caches(owner)

    assert ai_cache.load_cached_analysis(img, mtime, IDENTITY) is None
    fresh = GalleryItem(path=img, mtime_ns=mtime)
    assert ai_cache.hydrate_item(fresh, IDENTITY) is False
    assert fresh.analysis is None
    # Explicit: the checked flag must be reset, or ``hydrate_item`` short-circuits
    # on it and never reads the (now deleted) file at all.
    assert not item._ai_cache_checked
    assert ai_cache.hydrate_item(item, IDENTITY) is False
    assert item.analysis is None


def test_reset_reenters_the_rebuild(tmp_path, caches) -> None:
    """``reset_metrics_caches`` re-enters the triage rebuild (no grid cover)."""
    from tabs.image_gallery.use_cases import cache_reset

    img = tmp_path / "a.jpg"
    img.write_bytes(b"\x00")
    items = [GalleryItem(path=img, mtime_ns=1)]
    owner = _Owner(items)
    calls: list = []
    owner._start_triage = lambda its, **kw: calls.append((list(its), kw))  # type: ignore[method-assign]

    summary = cache_reset.reset_metrics_caches(owner)

    assert summary["requeued"] is True
    assert summary["items"] == 1
    assert len(calls) == 1
    assert calls[0][0] == items
    assert calls[0][1] == {"cover_grid": False}
    assert owner._last_analysis_fingerprint is None


def test_reset_without_folder_is_clear_only(tmp_path, caches) -> None:
    """A missing folder degrades to the clear without raising."""
    from tabs.image_gallery.use_cases import cache_reset

    img = tmp_path / "a.jpg"
    img.write_bytes(b"\x00")
    owner = _Owner([GalleryItem(path=img, mtime_ns=1)], folder=None)
    calls: list = []
    owner._start_triage = lambda its, **kw: calls.append(its)  # type: ignore[method-assign]

    summary = cache_reset.reset_metrics_caches(owner)

    assert summary["requeued"] is False
    assert calls == []
    assert owner._last_analysis_fingerprint is None


def test_reset_without_controller_is_clear_only(tmp_path, caches) -> None:
    """A storeless owner without ``_start_triage`` still gets the clear."""
    from tabs.image_gallery.use_cases import cache_reset

    img = tmp_path / "a.jpg"
    img.write_bytes(b"\x00")
    owner = SimpleNamespace(
        state=SimpleNamespace(items=[GalleryItem(path=img, mtime_ns=1)], folder=Path("/f")),
        _last_analysis_fingerprint=("stale",),
    )

    summary = cache_reset.reset_metrics_caches(owner)

    assert summary["requeued"] is False
    assert owner._last_analysis_fingerprint is None


def _capture_menu(monkeypatch):
    import sli_ui_toolkit.widgets as _w
    import ui.context_menu.manager as _mgr

    captured: dict = {}

    class _FakeMenu:
        def __init__(self, parent, *, entries=(), on_triggered=None, **kwargs):
            captured["entries"] = tuple(entries)
            captured["on_triggered"] = on_triggered

        def popup_at(self, pos):
            captured["popup_at"] = pos

        def show(self):
            captured["shown"] = True

    def _fake_open(*, source_widget, global_pos, entries, key, on_triggered=None, **_kwargs):
        captured["entries"] = tuple(entries)
        captured["on_triggered"] = on_triggered
        return _FakeMenu(source_widget, entries=entries, on_triggered=on_triggered)

    monkeypatch.setattr(_mgr, "open_context_menu_entries", _fake_open)
    monkeypatch.setattr(_w, "ContextMenu", _FakeMenu)
    return captured


def _find_action(entries, action_id: str):
    from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSection

    for e in entries:
        items = e.entries if isinstance(e, ContextMenuSection) else (e,)
        for a in items:
            if isinstance(a, ContextMenuAction) and a.action_id == action_id:
                return a
    raise AssertionError(f"{action_id} entry missing")


def test_menu_entry_and_registry_descriptor(monkeypatch) -> None:
    """Menu entry + registry descriptor both carry the frozen label/id."""
    from tabs.image_gallery.actions import GALLERY_RESET_METRICS
    from tabs.image_gallery.tab import ImageGalleryTab
    from tabs.image_gallery.ui.card.context_menu import popup_gallery_card_context_menu

    captured = _capture_menu(monkeypatch)
    owner = SimpleNamespace(
        state=SimpleNamespace(selected_paths=set()), _judgment_domain="algorithms"
    )
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=0,
    )
    action = _find_action(captured["entries"], "gallery.reset_metrics")
    assert action.text == "Reset metrics cache"
    assert action.text_key == "image_gallery.card.reset_metrics_cache"

    class _Registry:
        def __init__(self):
            self.items: list = []

        def register(self, descriptor):
            self.items.append(descriptor)
            return True

    tab = ImageGalleryTab()
    registry = _Registry()
    assert tab.create_service("contribute_actions", registry) is True
    descs = [d for d in registry.items if d.action_id == GALLERY_RESET_METRICS]
    assert len(descs) == 1
    desc = descs[0]
    assert desc.label_key == "image_gallery.card.reset_metrics_cache"
    assert desc.owner_tab == tab.session_type
    assert desc.topic == "cache"
    assert desc.help_page == "workspace.image_gallery.triage"
    desc.run()  # ctrl is None -> guarded no-op, never raises
