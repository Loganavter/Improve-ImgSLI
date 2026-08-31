"""Preview-phase geometry regression: the comparison letterbox rect must
update when the preview arrives, not only when the unified store's tiles
land.

The gate's early returns (unification deferral, one-side-missing) used to
skip the geometry computation, leaving the canvas letterboxed at the
*previous* comparison's rect until unify completed -- a visible resize
arriving "with the tiles" instead of "with the preview".
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from PIL import Image
from PySide6.QtWidgets import QApplication

from core.state_management.dispatcher import Dispatcher
from core.store import Store
from core.store_viewport import SessionData
from tabs.image_compare.pipeline.pipeline import ImagePipeline
from tabs.image_compare.presenters.image_canvas.background_parts import render_flow
from tabs.image_compare.state.actions import PutPreviewAction
from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.state.models import ImageSessionState, RenderCacheState


def _qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_store(document: DocumentModel, *, unification_in_progress: bool = False) -> Store:
    store = Store()
    store.create_workspace_session(session_type="image_compare", activate=True)
    store.set_session_state_slot("document", document)
    store.viewport.session_data = SessionData(
        image_state=ImageSessionState(),
        render_cache=RenderCacheState(unification_in_progress=unification_in_progress),
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
    return store


def _presenter(store: Store, pipeline: ImagePipeline):
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
        widget=SimpleNamespace(isVisible=lambda: True, image_label=SimpleNamespace(clear=lambda: None)),
        view=SimpleNamespace(
            is_canvas_widget=lambda: False,
            display_single_image_on_label=lambda img: None,
        ),
        get_current_label_dimensions=lambda: (400, 400),
        background=MagicMock(),
        overlay=MagicMock(),
        _last_label_dims=(400, 400),
        _cached_base_pixmap=None,
        _last_bg_signature=None,
        _last_img_sig=None,
        _last_mag_signature=None,
        current_displayed_pixmap=None,
    )


def test_geometry_updates_during_unification_deferral():
    """The user-visible case: both previews are on the pipeline, the unify
    worker is in flight (image_state.image1 still None), the gate defers the
    apply -- but the letterbox rect must already be the new comparison's."""
    _qapp()
    preview1 = Image.new("RGBA", (100, 50), "red")
    preview2 = Image.new("RGBA", (60, 60), "blue")
    document = DocumentModel(
        image_list1=[ImageItem(path="/a.png", display_name="a")],
        image_list2=[ImageItem(path="/b.png", display_name="b")],
        current_index1=0,
        current_index2=0,
    )
    store = _make_store(document, unification_in_progress=True)
    store.transact([PutPreviewAction(path="/a.png", qimage=preview1)], scope="pipeline")
    store.transact([PutPreviewAction(path="/b.png", qimage=preview2)], scope="pipeline")
    pipeline = ImagePipeline(store=store)
    presenter = _presenter(store, pipeline)
    geometry = store.viewport.geometry_state

    # keep fallback geometry path (no dispatcher) so _update_comparison_geometry mutates directly
    orig_get_dispatcher = store.get_dispatcher
    store.get_dispatcher = lambda: None  # type: ignore[assignment]
    try:
        assert render_flow.update_comparison_if_needed(presenter) is False
    finally:
        store.get_dispatcher = orig_get_dispatcher  # type: ignore[assignment]
    # Pair fit of 100x50 + 60x60 into 400x400: scale = min(4, 6.667) = 4
    # -> 400x200, centered.
    assert (geometry.pixmap_width, geometry.pixmap_height) == (400, 200)
    assert geometry.image_display_rect_on_label is not None
    rect = geometry.image_display_rect_on_label
    assert (rect.x, rect.y, rect.w, rect.h) == (0, 100, 400, 200)


def test_geometry_updates_when_one_side_missing():
    """One side empty (mid-reload): the rect converges to the available
    side's fit instead of staying at the previous comparison's layout."""
    _qapp()
    preview1 = Image.new("RGBA", (100, 50), "red")
    document = DocumentModel(
        image_list1=[ImageItem(path="/a.png", display_name="a")],
        image_list2=[],
        current_index1=0,
        current_index2=-1,
    )
    store = _make_store(document)
    store.transact([PutPreviewAction(path="/a.png", qimage=preview1)], scope="pipeline")
    pipeline = ImagePipeline(store=store)
    presenter = _presenter(store, pipeline)
    geometry = store.viewport.geometry_state

    orig_get_dispatcher = store.get_dispatcher
    store.get_dispatcher = lambda: None  # type: ignore[assignment]
    try:
        assert render_flow.update_comparison_if_needed(presenter) is False
    finally:
        store.get_dispatcher = orig_get_dispatcher  # type: ignore[assignment]
    assert (geometry.pixmap_width, geometry.pixmap_height) == (400, 200)
    rect = geometry.image_display_rect_on_label
    assert (rect.x, rect.y, rect.w, rect.h) == (0, 100, 400, 200)


def test_geometry_unchanged_when_no_sources():
    """Nothing loaded: the previous rect is kept (no crash, no mutation)."""
    _qapp()
    document = DocumentModel(
        image_list1=[],
        image_list2=[],
        current_index1=-1,
        current_index2=-1,
    )
    store = _make_store(document)
    pipeline = ImagePipeline(store=store)
    presenter = _presenter(store, pipeline)
    geometry = store.viewport.geometry_state

    orig_get_dispatcher = store.get_dispatcher
    store.get_dispatcher = lambda: None  # type: ignore[assignment]
    try:
        assert render_flow.update_comparison_if_needed(presenter) is False
    finally:
        store.get_dispatcher = orig_get_dispatcher  # type: ignore[assignment]
    assert (geometry.pixmap_width, geometry.pixmap_height) == (0, 0)
    assert geometry.image_display_rect_on_label is None
