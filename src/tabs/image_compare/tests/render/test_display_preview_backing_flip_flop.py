"""Flip-flop regression: a same-image preview must never re-degrade the
display once its complete store is on screen.

``image_uid`` is a per-object identity, so a slot's 1024px preview and the
``TiledPixelStore`` built from the same image always have different uids.
``pick_display_with_preview_backing`` used to call any preview whose uid
differed from the display pair last applied "fresh" -- which made a
*same-image* preview look fresh the moment the store was applied. The
canvas flipped back to the blurry preview, then to the store, and so on,
re-applying textures every cycle ([ic-preview] log: tier1/uid1 alternating
store/preview with the same underlying image). The fix remembers, per slot,
the preview uid that the currently-installed store superseded; only a
preview belonging to a *different* image (or a reload) stays fresh.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from core.state_management.dispatcher import Dispatcher
from core.store import Store
from core.store_viewport import SessionData
from shared.image_processing import pyramid_registry
from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.image_identity import image_uid
from tabs.image_compare.pipeline.pipeline import ImagePipeline
from tabs.image_compare.presenters.image_canvas.background_parts import render_flow
from tabs.image_compare.presenters.image_canvas.background_parts.render_flow import (
    pick_display_with_preview_backing,
)
from tabs.image_compare.state.actions import PutPreviewAction
from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.state.models import ImageSessionState, RenderCacheState


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _complete_store(width=64, height=64):
    pyramid_registry.clear()
    store = TiledPixelStore.from_pil(Image.new("RGBA", (width, height), "red"))
    pyramid_registry.ensure_pyramid(store).build_all()
    assert pyramid_registry.pyramid_for(store).is_complete()
    return store


def test_same_image_preview_never_degrades_complete_store():
    """The flip-flop cycle, helper level: preview applied, then its store
    applied, then the next cycle must pick the store again -- the same
    image's preview must not look "fresh" next to the store that superseded
    it (last_applied now holds the store's uid)."""
    store = _complete_store()
    preview = Image.new("RGBA", (64, 64), "blue")
    preview_uid = image_uid(preview)
    try:
        first = pick_display_with_preview_backing(
            store, preview, None, last_applied_uid=None
        )
        assert first is preview  # (a) first load shows the preview

        flipped = pick_display_with_preview_backing(
            store, preview, None, last_applied_uid=preview_uid
        )
        assert flipped is store  # (b) pyramid-complete flips preview -> store

        steady = pick_display_with_preview_backing(
            store,
            preview,
            None,
            last_applied_uid=image_uid(store),
            superseded_preview_uid=preview_uid,
        )
        assert steady is store  # (d) no degrade back to the same preview
    finally:
        store.close()
        pyramid_registry.clear()


def test_new_image_preview_still_replaces_previous_images_store():
    """A genuinely different image's preview must still win immediately over
    the previous image's store (helper intent preserved): the superseded-uid
    guard only blocks the same image's own preview, not a new one."""
    store = _complete_store()
    old_preview = Image.new("RGBA", (32, 32), "blue")
    new_preview = Image.new("RGBA", (48, 48), "green")
    try:
        picked = pick_display_with_preview_backing(
            store,
            new_preview,
            None,
            last_applied_uid=image_uid(store),
            superseded_preview_uid=image_uid(old_preview),
        )
        assert picked is new_preview
    finally:
        store.close()
        pyramid_registry.clear()


def _make_store(document: DocumentModel) -> Store:
    import tabs.image_compare.bootstrap_reducers  # noqa: F401 — ensure PipelineCacheReducer registered

    store = Store()
    store.create_workspace_session(session_type="image_compare", activate=True)
    store.set_session_state_slot("document", document)
    store.viewport.session_data = SessionData(
        image_state=ImageSessionState(), render_cache=RenderCacheState()
    )
    store.viewport.interaction_state.resize_in_progress = False
    store.viewport.view_state.showing_single_image_mode = 0
    store.viewport.view_state.diff_mode = "off"
    store.viewport.view_state.channel_view_mode = "rgb"
    store.viewport.geometry_state.pixmap_width = 0
    store.viewport.geometry_state.pixmap_height = 0
    store.viewport.geometry_state.image_display_rect_on_label = None
    store.state_changed = type("Sig", (), {"emit": staticmethod(lambda *_a, **_k: None)})()
    store.set_dispatcher(Dispatcher(store))
    # ensure pipeline slot exists
    from tabs.image_compare.state.models import PipelineCacheState

    try:
        if store.get_session_state_slot("pipeline") is None:
            store.set_session_state_slot("pipeline", PipelineCacheState())
    except Exception:
        pass
    return store


class _StoreWrapper:
    """Simple wrapper for presenter store slot access."""

    def __init__(self, document):
        self.document = document
        self.viewport = SimpleNamespace(
            session_data=SimpleNamespace(
                image_state=SimpleNamespace(image1=None, image2=None),
                render_cache=SimpleNamespace(unification_in_progress=False, pending_unification_paths=None),
            ),
            interaction_state=SimpleNamespace(resize_in_progress=False),
            view_state=SimpleNamespace(showing_single_image_mode=0, diff_mode="off", channel_view_mode="rgb"),
            geometry_state=SimpleNamespace(pixmap_width=0, pixmap_height=0, image_display_rect_on_label=None),
        )

    def get_session_state_slot(self, name):
        assert name == "document"
        return self.document


def _presenter(store: Store, pipeline: ImagePipeline, applied):
    return SimpleNamespace(
        main_window_app=SimpleNamespace(
            _is_ui_stable=True,
            _closing=False,
            isVisible=lambda: True,
            isMinimized=lambda: False,
            ui=SimpleNamespace(workspace_stack=None),
        ),
        store=store,
        session_controller=SimpleNamespace(pipeline=pipeline),
        controller=SimpleNamespace(pipeline=pipeline),
        widget=SimpleNamespace(
            isVisible=lambda: True,
            image_label=SimpleNamespace(
                clear=lambda: None,
                runtime_state=SimpleNamespace(
                    _stored_pil_images=[None, None],
                    _union_letterbox_hold_until=0,
                    _tile_more_pending=None,
                    _store=None,
                ),
            ),
        ),
        view=SimpleNamespace(
            is_canvas_widget=lambda: True,
            display_single_image_on_label=lambda img: applied.append(img),
        ),
        get_current_label_dimensions=lambda: (400, 400),
        background=MagicMock(get_background_signature=MagicMock(return_value="bg")),
        overlay=MagicMock(),
        _last_label_dims=(400, 400),
        _cached_base_pixmap=None,
        _last_bg_signature=None,
        _last_img_sig=None,
        _last_mag_signature=None,
        current_displayed_pixmap=None,
    )


def _invalidate(presenter):
    """Simulate the load path's invalidate_render_state between cycles."""
    presenter._last_bg_signature = None
    presenter._last_img_sig = None


def test_gate_applies_preview_once_then_keeps_the_store(monkeypatch, qapp):
    """Gate-level reproduction of the [ic-preview] log: with a same-image
    preview + complete store installed, the apply sequence must be
    [preview, store, store, ...] -- never [store, preview, store, preview].

    Runs the real ``update_comparison_if_needed`` gate with fake
    store/presenter state across successive invalidation cycles."""
    complete = _complete_store()
    preview1 = Image.new("RGBA", (64, 64), "blue")
    preview2 = Image.new("RGBA", (64, 64), "green")
    document = DocumentModel(
        image_list1=[ImageItem(path="/a.png", display_name="a")],
        image_list2=[ImageItem(path="/b.png", display_name="b")],
        current_index1=0,
        current_index2=0,
    )
    store = _make_store(document)
    store.transact([PutPreviewAction(path="/a.png", qimage=preview1)], scope="pipeline")
    store.transact([PutPreviewAction(path="/b.png", qimage=preview2)], scope="pipeline")
    pipeline = ImagePipeline(store=store)
    state = store.viewport.session_data.image_state
    applied: list[tuple] = []
    presenter = _presenter(store, pipeline, applied)

    monkeypatch.setattr(
        render_flow,
        "apply_store_to_canvas",
        lambda _canvas, _store, img1, img2, **_kw: applied.append((img1, img2)),
    )
    monkeypatch.setattr(render_flow, "get_canvas_widget", lambda widget: widget.image_label)
    monkeypatch.setattr(render_flow, "reset_canvas_overlays", lambda *_a, **_k: None)
    monkeypatch.setattr(render_flow, "sync_diff_texture", lambda *_a, **_k: None)
    monkeypatch.setattr(render_flow, "build_render_scene", lambda *_a, **_k: None)

    # Cycle 1: only the preview exists -- first-load path shows it.
    render_flow.update_comparison_if_needed(presenter)
    assert applied == [(preview1, preview2)]
    assert presenter._last_display_uids == {1: image_uid(preview1), 2: image_uid(preview2)}

    # Cycle 2: the unified store lands (complete pyramid) -- flip to store.
    _invalidate(presenter)
    state.image1 = complete
    # need to seed pixel for a.png to allow pipeline peek for complete? Actually state already holds complete, picker will use state
    render_flow.update_comparison_if_needed(presenter)
    assert applied[-1][0] is complete
    assert presenter._last_superseded_preview_uid == {1: image_uid(preview1)}

    # Cycle 3: nothing changed, but the render state is invalidated again
    # (as the load path does) -- the same image's preview must NOT be picked
    # again. This cycle used to degrade back to preview1 (flip-flop).
    _invalidate(presenter)
    render_flow.update_comparison_if_needed(presenter)
    assert applied[-1][0] is complete, (
        "same-image preview re-degraded the complete store -- flip-flop"
    )

    # Cycle 4: a genuinely new image's preview arrives -- it must replace
    # the previous image's store immediately, even with superseded set.
    new_preview = Image.new("RGBA", (80, 80), "yellow")
    store.transact([PutPreviewAction(path="/a.png", qimage=new_preview)], scope="pipeline")
    _invalidate(presenter)
    render_flow.update_comparison_if_needed(presenter)
    assert applied[-1][0] is new_preview

    assert [applied[0][0], applied[1][0], applied[2][0]] == [
        preview1,
        complete,
        complete,
    ]
    complete.close()
    pyramid_registry.clear()
