"""Preview-first invariant: IC full-res publish implies a preview tier.

``handle_full_image_loaded`` (``use_cases/slot.py``) must ensure the
preview tier exists in the ``PipelineCache`` BEFORE the PutPixelAction /
image_state transact (Lightroom Standard model) — via the frozen seam
``tabs._shared.loading_pipeline.get_or_load_preview`` (bounded ~1024px
decode, fail-open). Data/identity only, offscreen-Qt compatible.

Invariant under test: store transact implies preview present.
"""

from __future__ import annotations

from PIL import Image
from PySide6.QtGui import QColor, QImage

from core.state_management.dispatcher import Dispatcher
from core.store import Store
from core.store_viewport import SessionData
from tabs.image_compare.pipeline.pipeline import ImagePipeline
from tabs.image_compare.state.actions import PutPixelAction
from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.state.models import ImageSessionState, RenderCacheState
from tabs.image_compare.use_cases import loading


def _make_store(document: DocumentModel) -> Store:
    import tabs.image_compare.bootstrap_reducers  # noqa: F401

    store = Store()
    store.create_workspace_session(session_type="image_compare", activate=True)
    store.set_session_state_slot("document", document)
    store.viewport.session_data = SessionData(
        image_state=ImageSessionState(), render_cache=RenderCacheState()
    )
    store.state_changed = type("Sig", (), {"emit": staticmethod(lambda *_a, **_k: None)})()
    store.set_dispatcher(Dispatcher(store))
    from tabs.image_compare.state.models import PipelineCacheState

    try:
        if store.get_session_state_slot("pipeline") is None:
            store.set_session_state_slot("pipeline", PipelineCacheState())
    except Exception:
        pass
    return store


class _FakeController:
    def __init__(self, store: Store):
        self.store = store
        self.pipeline = ImagePipeline(store=store)
        self.presenter = None
        self.event_bus = None
        self.diff_service = None
        self.finished_toasts: list = []

    def _invalidate_image_canvas_render_state(self, *_a, **_kw):
        pass

    def _schedule_image_canvas_update(self, *_a, **_kw):
        pass

    def _update_image_slot(self, image_number, *, image=None, path=None, is_full_res=False, is_preview=False):
        pass

    def _mark_full_res_ready(self, image_number):
        pass

    def _finish_loading_toast(self, image_number):
        self.finished_toasts.append(image_number)

    def _start_pyramid_builds(self, *_a, **_kw):
        pass


def _doc(path: str) -> DocumentModel:
    return DocumentModel(
        image_list1=[ImageItem(path=path, display_name=path)],
        image_list2=[],
        current_index1=0,
        current_index2=-1,
    )


def _color_image(r: int, g: int, b: int) -> QImage:
    img = QImage(8, 8, QImage.Format.Format_RGBA8888)
    img.fill(QColor(r, g, b))
    assert not img.isNull()
    return img


def _spy_events(controller: _FakeController) -> list:
    """Record preview-fill vs store-publish ordering across the call."""
    events: list = []
    cache = controller.pipeline.cache
    orig_put_preview = cache.put_preview
    orig_transact = controller.store.transact

    def _put_preview(*args, **kwargs):
        events.append("put_preview")
        return orig_put_preview(*args, **kwargs)

    def _transact(actions, **kwargs):
        for action in actions or []:
            events.append(f"transact:{type(action).__name__}")
        return orig_transact(actions, **kwargs)

    cache.put_preview = _put_preview  # type: ignore[method-assign]
    controller.store.transact = _transact  # type: ignore[method-assign]
    return events


def test_preview_miss_fills_before_pixel_transact(monkeypatch, tmp_path):
    """Full without preview: the fill lands before the store publishes."""
    import shared.image_processing.progressive_loader as pl

    path = str(tmp_path / "full-no-preview.png")
    tmp_path.joinpath("full-no-preview.png").write_bytes(b"fake-png-payload")
    preview = _color_image(10, 120, 200)
    calls: list[str] = []
    monkeypatch.setattr(pl, "load_preview_image", lambda p: (calls.append(str(p)), preview)[1])

    store = _make_store(_doc(path))
    controller = _FakeController(store)
    events = _spy_events(controller)
    full = Image.new("RGBA", (4, 4), "red")

    loading.handle_full_image_loaded(controller, full, path, 1, 0)

    assert calls == [path], "one bounded fill decode for the preview gap"
    assert "put_preview" in events, "fill must land in the PipelineCache"
    pixel_idx = events.index("transact:PutPixelAction")
    assert events.index("put_preview") < pixel_idx, "preview fill precedes the store transact"
    assert controller.pipeline.cache.get_preview(path) is not None
    assert store.viewport.session_data.image_state.image1 is not None, "publish preserved"


def test_preview_hit_is_noop_never_double_decodes(monkeypatch, tmp_path):
    """Preview already cached: no re-decode, publish still happens."""
    import shared.image_processing.progressive_loader as pl

    path = str(tmp_path / "full-with-preview.png")
    tmp_path.joinpath("full-with-preview.png").write_bytes(b"fake-png-payload")
    seeded = _color_image(200, 40, 40)

    store = _make_store(_doc(path))
    controller = _FakeController(store)
    controller.pipeline.cache.put_preview(path, seeded)

    def _boom(p):
        raise AssertionError("cached preview must never re-decode")

    monkeypatch.setattr(pl, "load_preview_image", _boom)
    events = _spy_events(controller)
    full = Image.new("RGBA", (4, 4), "green")

    loading.handle_full_image_loaded(controller, full, path, 1, 0)

    assert "put_preview" not in events, "cache hit is a no-op (peek first)"
    assert "transact:PutPixelAction" in events, "publish preserved on the hit path"
    assert controller.pipeline.cache.get_preview(path) is seeded
    assert store.viewport.session_data.image_state.image1 is not None


def test_fill_none_still_publishes_fail_open_preserved(monkeypatch, tmp_path):
    """Unreadable preview (fill returns None): store still published."""
    import shared.image_processing.progressive_loader as pl

    path = str(tmp_path / "full-unreadable-preview.png")
    tmp_path.joinpath("full-unreadable-preview.png").write_bytes(b"fake-png-payload")
    monkeypatch.setattr(pl, "load_preview_image", lambda p: None)

    store = _make_store(_doc(path))
    controller = _FakeController(store)
    events = _spy_events(controller)
    full = Image.new("RGBA", (4, 4), "blue")

    loading.handle_full_image_loaded(controller, full, path, 1, 0)

    assert "transact:PutPixelAction" in events, "fill-None never gates the publish"
    assert store.viewport.session_data.image_state.image1 is not None, "image_state still published"
    assert controller.pipeline.cache.get_preview(path) is None, "miss plants nothing"
