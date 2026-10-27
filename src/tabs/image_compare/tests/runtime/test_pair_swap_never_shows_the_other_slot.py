"""A pair swap/replace must never show the other slot's image.

Owner report (2026-10-27): after swapping/replacing one image of an IC pair,
for a couple of frames a slot shows an image that belongs to the OTHER slot
(or the previous one showing through). Identity outranks responsiveness: until
a side's new file is decoded the slot may show a placeholder, nothing, or the
SLOT'S OWN previous content — never the neighbour.

Two contracts are pinned here.

1. **The pair is published as one transition, copy-on-write.** A swap used to
   exchange ``DocumentModel.image_list1/2`` *in place* and only emit the
   ``viewport`` scope. The pair's PATHS therefore moved underneath every
   consumer that already held the document (undo snapshot, feature-worker
   snapshot, persistence capture) while the paired ``image_state.image1/2``
   pixels did not move with them, and no ``document`` scope was emitted, so
   nothing re-read the new pairing. A consumer left in that state resolves
   slot N's path to the other slot's pixels — exactly the frame the owner
   saw. ``document_store_ops.swap_current_pair`` publishes both roles in one
   batch, so the only state any listener can observe is the coherent pair.
   (Red-before: at ``821257b41`` the captured document reference flips its
   paths and no ``document`` scope is emitted.)

2. **No frame hands a slot content that belongs to the other slot's path.**
   The live gate (``update_comparison_if_needed``) is replayed across a
   slot replacement — clear, preview, settled store — with visually distinct
   per-slot content, and every applied pair is checked slot-by-slot. The
   only tolerated stale value is that slot's own previous image.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from core.state_management.dispatcher import Dispatcher
from core.store import Store
from core.store_viewport import SessionData
from engine.cache.image_identity import image_uid
from engine.store import pyramid_registry
from engine.store.tiled_pixel_store import TiledPixelStore
from tabs.image_compare.pipeline.pipeline import ImagePipeline
from tabs.image_compare.presenters.image_canvas.background_parts import render_flow
from tabs.image_compare.services import document_store_ops
from tabs.image_compare.state.actions import PutPreviewAction
from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.state.models import (
    ImageSessionState,
    PipelineCacheState,
    RenderCacheState,
)

PATH_A = "/pair-swap/1_1.png"
PATH_B = "/pair-swap/2_1.png"
PATH_C = "/pair-swap/2_3.png"

# Distinct content per side (the owner's 1_1 / 2_1 / 2_3): identical pixels
# would hide a slot mix-up.
COLOR_A = (220, 30, 30)
COLOR_B = (30, 60, 220)
COLOR_C = (30, 200, 60)
OWNER_OF = {COLOR_A: "A", COLOR_B: "B", COLOR_C: "C"}


def _qapp():
    return QApplication.instance() or QApplication([])


def _store(color, size=(64, 48)):
    import tabs.image_compare.bootstrap_reducers  # noqa: F401

    pixel_store = TiledPixelStore.from_pil(Image.new("RGBA", size, color))
    pyramid_registry.ensure_pyramid(pixel_store).build_all()
    assert pyramid_registry.pyramid_for(pixel_store).is_complete()
    return pixel_store


def _owner(img):
    """Which generated image this is (``A``/``B``/``C``), ``None`` when empty."""
    if img is None:
        return None
    if isinstance(img, TiledPixelStore):
        arr = img.read_array((0, 0, 1, 1))
        px = tuple(int(v) for v in arr[0, 0, :3])
    elif hasattr(img, "pixelColor"):
        col = img.pixelColor(0, 0)
        px = (col.red(), col.green(), col.blue())
    else:
        px = tuple(img.convert("RGB").getpixel((0, 0)))
    for color, name in OWNER_OF.items():
        if all(abs(a - b) <= 8 for a, b in zip(px, color)):
            return name
    raise AssertionError(f"unexpected content {px!r}")


def _make_store(document: DocumentModel) -> Store:
    import tabs.image_compare.bootstrap_reducers  # noqa: F401

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
    store.set_session_state_slot("pipeline", PipelineCacheState())
    store.viewport.session_data.image_state.image1 = None
    store.viewport.session_data.image_state.image2 = None
    return store


def _presenter(store: Store, pipeline: ImagePipeline, applied: list):
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
            is_canvas_widget=lambda: True,
            display_single_image_on_label=lambda img: applied.append(("single", img, img)),
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


# -- (1) the swap is one coherent, copy-on-write publication -------------------


def _pair_store():
    document = DocumentModel(
        image_list1=[ImageItem(path=PATH_A, display_name="A")],
        image_list2=[ImageItem(path=PATH_B, display_name="B")],
        current_index1=0,
        current_index2=0,
    )
    store = _make_store(document)
    image_state = store.viewport.session_data.image_state
    image_state.image1 = _store(COLOR_A)
    image_state.image2 = _store(COLOR_B)
    return store


def test_a_pair_swap_publishes_paths_and_pixels_in_one_transition():
    """Red-before (``821257b41``): ``swap_current_images`` mutated the live
    ``DocumentModel.image_list1/2`` in place and emitted only ``viewport``, so
    a reader that held the pair saw the paths move while its pixels did not."""
    store = _pair_store()
    scopes: list[str] = []
    store.on_change(lambda scope: scopes.append(scope))
    held = store.get_session_state_slot("document")

    from tabs.image_compare.services.playlist_components.list_operations import (
        PlaylistListOperations,
    )

    PlaylistListOperations(store, main_controller=None).swap_current_images()

    # The previously published document still describes the previous pair:
    # the swap is a new document, never an in-place edit.
    assert (held.image1_path, held.image2_path) == (PATH_A, PATH_B), (
        "the swap mutated the already-published document in place — every "
        "holder of the pair now names the other slot's path"
    )

    live = store.get_session_state_slot("document")
    assert (live.image1_path, live.image2_path) == (PATH_B, PATH_A)
    # Paths and pixels travelled together (slot 1 keeps the path its image
    # belongs to: B's store landed in slot 1 together with B's path).
    image_state = store.viewport.session_data.image_state
    assert _owner(image_state.image1) == "B"
    assert _owner(image_state.image2) == "A"
    # Every consumer keyed on the document must be told about the new pairing.
    assert "document" in scopes, (
        "a pair swap published no document-scope change: path-keyed consumers "
        "keep the pre-swap pairing while the viewport already changed"
    )
    assert "viewport" in scopes


def test_a_pair_swap_keeps_the_loupe_geometry_contract():
    """#737 parity: a swap exchanges one pair's images, so the envelope is
    unchanged and the geometry cache must not be zeroed."""
    from core.state_management.actions import InvalidateGeometryCacheAction

    store = _pair_store()
    dispatched: list = []
    original = store.get_dispatcher()

    class _Recording:
        def dispatch(self, action, scope=None):  # noqa: ANN001 - mirrors Dispatcher
            dispatched.append(action)
            return original.dispatch(action, scope)

    store.set_dispatcher(_Recording())

    from tabs.image_compare.services.playlist_components.list_operations import (
        PlaylistListOperations,
    )

    PlaylistListOperations(store, main_controller=None).swap_current_images()

    assert not [
        action for action in dispatched if isinstance(action, InvalidateGeometryCacheAction)
    ], "a same-pair swap zeroed the geometry: the loupe disappears for a frame"


def test_swap_current_pair_reports_an_incomplete_pair():
    """No current item on a side ⇒ nothing is published (legacy early return)."""
    store = _make_store(DocumentModel(image_list1=[], image_list2=[]))
    assert document_store_ops.swap_current_pair(store) is False


def test_a_whole_list_swap_never_aliases_another_documents_lists():
    """``swap_entire_lists`` publishes a new document; it must not share list
    objects with the document it replaced (an in-place edit of one would then
    travel into the other — the same identity hazard as ``swap_current_pair``).
    """
    store = _pair_store()
    before = store.get_session_state_slot("document")

    document_store_ops.swap_all_image_data(store)

    after = store.get_session_state_slot("document")
    assert (after.image1_path, after.image2_path) == (PATH_B, PATH_A)
    assert (before.image1_path, before.image2_path) == (PATH_A, PATH_B)
    assert after.image_list1 is not before.image_list2
    assert after.image_list2 is not before.image_list1


# -- (2) no frame hands a slot the other slot's content -----------------------


def _gate_frame(presenter, applied, frames):
    """Run one gate frame; ``applied``/``frames`` are the test's own sinks."""
    applied.clear()
    render_flow.update_comparison_if_needed(presenter)
    frames.append(list(applied))


def test_a_slot_replace_never_shows_the_other_slot(monkeypatch):
    """Owner scenario: pair (1_1, 2_1) → replace slot 2 with 2_3.

    Every frame's applied pair must keep slot 1 on A's content and slot 2 on
    B's or C's content (its own previous image is allowed; A's is not).
    """
    _qapp()
    pyramid_registry.clear()
    document = DocumentModel(
        image_list1=[ImageItem(path=PATH_A, display_name="A")],
        image_list2=[ImageItem(path=PATH_B, display_name="B"), ImageItem(path=PATH_C, display_name="C")],
        current_index1=0,
        current_index2=0,
    )
    store = _make_store(document)
    preview_a = Image.new("RGBA", (64, 48), COLOR_A)
    preview_b = Image.new("RGBA", (48, 64), COLOR_B)
    preview_c = Image.new("RGBA", (72, 40), COLOR_C)
    store.transact([PutPreviewAction(path=PATH_A, qimage=preview_a)], scope="pipeline")
    store.transact([PutPreviewAction(path=PATH_B, qimage=preview_b)], scope="pipeline")
    pipeline = ImagePipeline(store=store)
    applied: list = []
    frames: list = []
    presenter = _presenter(store, pipeline, applied)

    monkeypatch.setattr(
        render_flow, "apply_store_to_canvas", lambda _c, _s, i1, i2, **_kw: applied.append((i1, i2))
    )
    monkeypatch.setattr(render_flow, "get_canvas_widget", lambda widget: widget.image_label)
    monkeypatch.setattr(render_flow, "reset_canvas_overlays", lambda *_a, **_k: None)
    monkeypatch.setattr(render_flow, "sync_diff_texture", lambda *_a, **_k: None)
    monkeypatch.setattr(render_flow, "build_render_scene", lambda *_a, **_k: None)

    state = store.viewport.session_data.image_state
    state.image1 = preview_a
    state.image2 = preview_b
    _gate_frame(presenter, applied, frames)  # first paint: both previews

    store_a, store_b = _store(COLOR_A), _store(COLOR_B, (48, 64))
    state.image1 = store_a
    state.image2 = store_b
    presenter._last_img_sig = None
    _gate_frame(presenter, applied, frames)  # settled pair

    # Replace slot 2 with C: the document already points at C, the slot is
    # cleared while C decodes (set_current_image's cache-miss clear).
    from dataclasses import replace

    store.set_session_state_slot(
        "document",
        replace(store.get_session_state_slot("document"), current_index2=1),
    )
    state.image2 = None
    presenter._last_img_sig = None
    _gate_frame(presenter, applied, frames)

    # C's preview arrives.
    store.transact([PutPreviewAction(path=PATH_C, qimage=preview_c)], scope="pipeline")
    state.image2 = preview_c
    presenter._last_img_sig = None
    _gate_frame(presenter, applied, frames)

    # C's full store lands (unify publishes the pair).
    store_c = _store(COLOR_C, (72, 40))
    state.image1 = _store(COLOR_A)
    state.image2 = store_c
    presenter._last_img_sig = None
    _gate_frame(presenter, applied, frames)

    assert frames, "the gate never applied a frame"
    for index, frame in enumerate(frames):
        for slot, pair in enumerate(frame, start=1):
            image = pair[slot - 1]
            owner = _owner(image) if image is not None else None
            if slot == 1:
                assert owner in (None, "A"), (
                    f"frame {index}: slot 1 shows {owner}'s content — the other slot's image"
                )
            else:
                assert owner in (None, "B", "C"), (
                    f"frame {index}: slot 2 shows {owner}'s content — the other slot's image"
                )
        if len(frame) == 2 and frame[0] is not None and frame[1] is not None:
            assert image_uid(frame[0]) != image_uid(frame[1]), (
                f"frame {index}: the same image was applied to BOTH slots"
            )

