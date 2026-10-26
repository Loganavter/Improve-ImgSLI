"""Swap keeps the canvas geometry cache when the two images are the same size.

Symptom this guards (owner report): pressing swap made the whole scene reset
and then restore. Cause: ``swap_current_images`` always dropped the geometry
cache, whose sweep zeroes ``pixmap_width``/``pixmap_height`` and the display
rect (``GeometryStateReducer``), so the canvas rebuilt the whole presentation
(both slots re-picked and re-applied through ``apply_store_to_canvas``) even
when the exchange could not change the geometry at all -- two identically
sized images share one letterbox, so the derived content rect is identical.

Red-before/green-after story: on the pre-fix tree ``swap_current_images``
dispatches ``InvalidateGeometryCacheAction`` for equal-dims pairs too, so
``test_swap_of_equal_dim_images_keeps_geometry_cache`` fails there and passes
here. The differing-dims case is the control: it must still invalidate.
"""

from __future__ import annotations

from types import SimpleNamespace

from core.state_management.dispatcher import Dispatcher
from core.store import Store

import tabs.image_compare.bootstrap_reducers  # noqa: F401 — registers reducers
from core.store_viewport import SessionData
from tabs.image_compare.services import document_store_ops
from tabs.image_compare.services.playlist_components.list_operations import (
    PlaylistListOperations,
)
from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.state.models import ImageSessionState, RenderCacheState


class _SizedImage:
    """Minimal image duck type: ``get_image_dims`` reads ``size``."""

    def __init__(self, width: int, height: int) -> None:
        self.size = (width, height)
        self.is_open = True


def _make_store(*, size_a: tuple[int, int], size_b: tuple[int, int]) -> Store:
    store = Store()
    store.create_workspace_session(session_type="image_compare", activate=True)
    store.set_session_state_slot(
        "document",
        DocumentModel(
            image_list1=[ImageItem(path="/tmp/swap_a.png")],
            image_list2=[ImageItem(path="/tmp/swap_b.png")],
            current_index1=0,
            current_index2=0,
        ),
    )
    store.viewport.session_data = SessionData(
        image_state=ImageSessionState(), render_cache=RenderCacheState()
    )
    store.viewport.session_data.image_state.image1 = _SizedImage(*size_a)
    store.viewport.session_data.image_state.image2 = _SizedImage(*size_b)
    store.state_changed = type("Sig", (), {"emit": staticmethod(lambda *_a, **_k: None)})()
    store.set_dispatcher(Dispatcher(store))
    return store


def _dispatch_recorder(store: Store) -> list:
    seen: list = []
    original = store.get_dispatcher().dispatch

    def _record(action, *args, **kwargs):
        seen.append(action)
        return original(action, *args, **kwargs)

    store.get_dispatcher().dispatch = _record  # type: ignore[method-assign]
    return seen


def _swap(store: Store) -> list:
    seen = _dispatch_recorder(store)
    PlaylistListOperations(store).swap_current_images()
    return seen


def test_geometry_changes_on_swap_is_false_for_equal_dims():
    assert (
        document_store_ops.geometry_changes_on_swap(
            _SizedImage(800, 600), _SizedImage(800, 600)
        )
        is False
    )


def test_geometry_changes_on_swap_is_true_for_different_dims():
    assert (
        document_store_ops.geometry_changes_on_swap(
            _SizedImage(800, 600), _SizedImage(1024, 600)
        )
        is True
    )


def test_geometry_changes_on_swap_conservative_when_dims_unknown():
    assert document_store_ops.geometry_changes_on_swap(None, _SizedImage(800, 600)) is True
    assert document_store_ops.geometry_changes_on_swap(None, None) is True


def test_swap_of_equal_dim_images_keeps_geometry_cache():
    store = _make_store(size_a=(800, 600), size_b=(800, 600))
    actions = _swap(store)
    names = [type(a).__name__ for a in actions]
    assert "SetImageSessionImageAction" in names
    assert "InvalidateGeometryCacheAction" not in names, (
        "equal-size swap must not drop the geometry cache: it only makes the "
        "canvas rebuild the whole presentation (scene reset -> restore)"
    )


def test_swap_of_different_dim_images_still_invalidates_geometry():
    store = _make_store(size_a=(800, 600), size_b=(1024, 768))
    actions = _swap(store)
    names = [type(a).__name__ for a in actions]
    assert "InvalidateGeometryCacheAction" in names


def test_swap_exchanges_the_slot_images():
    store = _make_store(size_a=(800, 600), size_b=(640, 480))
    before_1 = store.viewport.session_data.image_state.image1
    before_2 = store.viewport.session_data.image_state.image2
    _swap(store)
    state = store.viewport.session_data.image_state
    assert state.image1 is before_2
    assert state.image2 is before_1
