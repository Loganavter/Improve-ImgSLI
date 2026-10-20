"""Pool (re)build must restore cached AI analyses (closed-tab / reload bug).

Repro: analyze a batch, close the gallery tab, reopen it and load the same
batch again — the images came back "not analyzed" even though the results
sat in the disk cache: the pool rebuild (session restore / folder open /
append) never hydrated the cache. ``GalleryController._hydrate_ai_cache`` now
fills items from the cache on every pool (re)build — cache-only, no API call
(the AI-domain scorecards the Jev rank reads are re-derived later, at the
metrics pass settle).

Red-before: the assertions fail on the pre-change controller (``analysis``
stays ``None``).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import AiAnalysisResult, AnalysisStatus
from tabs.image_gallery.services import ai_cache
from tabs.image_gallery.state.models import GalleryItemMeta
from tabs.image_gallery.tests._gallery_dispatch_doubles import (
    gallery_slot,
    make_gallery_context,
)


class _SignalStub:
    def __init__(self):
        self._slots = []

    def connect(self, fn):
        self._slots.append(fn)

    def emit(self, *a, **kw):
        for fn in self._slots:
            fn(*a, **kw)


class _WidgetStub:
    def __init__(self):
        self.folder_pick_requested = _SignalStub()
        self.analyze_requested = _SignalStub()
        self.filter_text_changed = _SignalStub()

    def set_folder_label(self, folder) -> None:
        pass

    def rebuild_grid(self, items) -> None:
        pass

    def refresh_card(self, item) -> None:
        pass

    def set_card_visible(self, path, visible: bool) -> None:
        pass

    def set_triage(self, *a) -> None:
        pass

    def set_scanning(self, *a) -> None:
        pass

    def pick_folder_dialog(self, start_dir: str = ""):
        return None


def _make_ctrl() -> tuple[GalleryController, _WidgetStub]:
    widget = _WidgetStub()
    context, _store = make_gallery_context()
    ctrl = GalleryController(
        widget, thread_pool=QThreadPool.globalInstance(), context=context
    )
    ctrl._start_triage = lambda items, **kw: None  # type: ignore[method-assign]
    ctrl._load_thumbnail = lambda item: None  # type: ignore[method-assign]
    return ctrl, widget


def _cached(
    ctrl: GalleryController, path: Path, mtime_ns: int, *, description: str = "cached"
) -> AiAnalysisResult:
    """Seed ONE identity-scoped scorecard, as the analyze path would have.

    The identity is the controller's own (``analysis_identity_for``), so this
    seeds exactly what the hydrate pass looks up — the identity semantics are
    covered by ``test_ai_cache_identity.py``.
    """
    from tabs.image_gallery.use_cases.ai_analysis import analysis_identity_for

    result = AiAnalysisResult(
        description=description,
        tags=("sky",),
        model="test/model",
        analyzed_at_iso="2026-01-01T00:00:00+00:00",
        sharpness=80,
        verdict="keep",
    )
    ai_cache.save_analysis(path, mtime_ns, result, analysis_identity_for(ctrl))
    return result


def test_open_paths_hydrates_cached_ai(tmp_path, monkeypatch):
    """Reloading a batch (append) shows cached analyses, not "not analyzed"."""
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path / "cache")
    (tmp_path / "cache").mkdir()
    ctrl, _widget = _make_ctrl()
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\x00")
    _cached(ctrl, img, img.stat().st_mtime_ns)

    ctrl.open_paths([img])

    item = next(it for it in ctrl.state.items if it.path == img)
    assert item.analysis is not None
    assert item.analysis.description == "cached"
    assert item.analysis_status == AnalysisStatus.DONE


def test_sync_from_slot_hydrates_cached_ai(tmp_path, monkeypatch):
    """Reopening the tab (slot restore) shows cached analyses for the pool."""
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path / "cache")
    (tmp_path / "cache").mkdir()
    context, store = make_gallery_context()
    ctrl = GalleryController(
        _WidgetStub(), thread_pool=QThreadPool.globalInstance(), context=context
    )
    ctrl._start_triage = lambda items, **kw: None  # type: ignore[method-assign]
    ctrl._load_thumbnail = lambda item: None  # type: ignore[method-assign]
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\x00")
    mtime = img.stat().st_mtime_ns
    _cached(ctrl, img, mtime)

    slot = gallery_slot(store)
    slot.items.append(GalleryItemMeta(path=str(img), mtime_ns=mtime))

    ctrl._sync_from_slot()

    assert len(ctrl.state.items) == 1
    item = ctrl.state.items[0]
    assert item.analysis is not None
    assert item.analysis.description == "cached"
    assert item.analysis_status == AnalysisStatus.DONE


def test_hydrate_is_identity_scoped(tmp_path, monkeypatch):
    """A scorecard cached under ANOTHER backend must not be hydrated on rebuild."""
    from tabs.image_gallery.services.ai_settings_store import AiSettings
    from tabs.image_gallery.use_cases.ai_analysis import analysis_identity_for

    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path / "cache")
    (tmp_path / "cache").mkdir()
    ctrl, _widget = _make_ctrl()
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\x00")
    mtime = img.stat().st_mtime_ns
    other_backend = ai_cache.analysis_cache_identity(
        AiSettings(model="other/model"), mode="camera"
    )
    assert other_backend != analysis_identity_for(ctrl)
    ai_cache.save_analysis(
        img,
        mtime,
        AiAnalysisResult(
            description="other backend",
            tags=(),
            model="other/model",
            analyzed_at_iso="2026-01-01T00:00:00+00:00",
        ),
        other_backend,
    )

    ctrl.open_paths([img])

    item = next(it for it in ctrl.state.items if it.path == img)
    assert item.analysis is None


def test_uncached_item_is_not_analyzed_on_load(tmp_path, monkeypatch):
    """Cache-only: an uncached item stays NOT_ANALYZED (no API on load)."""
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path / "cache")
    (tmp_path / "cache").mkdir()
    ctrl, _widget = _make_ctrl()
    img = tmp_path / "b.jpg"
    img.write_bytes(b"\x00")

    ctrl.open_paths([img])

    item = next(it for it in ctrl.state.items if it.path == img)
    assert item.analysis is None
    assert item.analysis_status == AnalysisStatus.NOT_ANALYZED
