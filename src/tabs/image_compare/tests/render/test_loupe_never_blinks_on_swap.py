"""A swap inside the pair must not blink the loupe (owner report 2026-10-27).

Two rules, both user-visible as "лупа подскакивает / пропадает на пару
мгновений" while swapping two images of different dimensions:

* the stored role degraded to the 1024-long-edge preview of an image that was
  ALREADY on screen in the other slot (the freshness test compared only this
  slot's last applied uid), so for a frame or two the canvas -- and with it
  every canvas-px overlay: loupe radius, capture ring, divider/border -- was
  fitted to a tier whose aspect differs from the pair's;
* ``swap_current_images`` invalidated the geometry cache, zeroing
  ``pixmap_width/height``: a swap exchanges the two images of ONE pair, so the
  comparison envelope and its drawn frame are unchanged and the scene must not
  be torn down for the frames before the next apply.
"""

from __future__ import annotations

from types import SimpleNamespace

from PIL import Image

from core.state_management.actions import InvalidateGeometryCacheAction
from tabs.image_compare.presenters.image_canvas.background_parts.use_cases.preview import (
    pick_display_with_preview_backing,
)


class _FakeDispatcher:
    def __init__(self) -> None:
        self.actions: list[object] = []

    def dispatch(self, action, scope=None):  # noqa: ANN001 - mirrors Dispatcher
        self.actions.append(action)


def _uid(image):
    from engine.cache.image_identity import image_uid

    return image_uid(image)


def test_a_swapped_image_is_not_degraded_to_its_preview():
    """Slot 1 now holds the image that was displayed in slot 2 last frame:
    that preview is not "fresh" (both uids are the pair's last applied)."""
    store_b = SimpleNamespace(size=(1600, 1200), width=1600, height=1200)
    preview_b = Image.new("RGBA", (1024, 768), "green")
    store_a = SimpleNamespace(size=(2000, 1000), width=2000, height=1000)

    picked = pick_display_with_preview_backing(
        store_b,
        preview_b,
        last_applied_uid=_uid(store_a),
        superseded_preview_uid=None,
        other_slot_applied_uid=_uid(store_b),
    )
    assert picked is store_b, "a swapped-in image was re-degraded to its preview"


def test_a_genuinely_new_image_still_prefers_its_fresh_preview():
    """The first-load reason for the preview preference is untouched: an image
    that was on neither slot keeps the preview as the fallback baseline."""
    store_new = SimpleNamespace(size=(800, 600), width=800, height=600)
    preview_new = Image.new("RGBA", (800, 600), "blue")
    store_a = SimpleNamespace(size=(2000, 1000), width=2000, height=1000)
    store_b = SimpleNamespace(size=(1600, 1200), width=1600, height=1200)

    picked = pick_display_with_preview_backing(
        store_new,
        preview_new,
        last_applied_uid=None,
        superseded_preview_uid=None,
        other_slot_applied_uid=_uid(store_b),
    )
    assert picked is preview_new


def test_a_swap_does_not_invalidate_the_pair_geometry():
    """The envelope is order-symmetric: switching slots changes no geometry,
    so nothing may zero pixmap_width/height (that emptied the scene graph and
    dropped the declared-visible loupe for a couple of frames)."""
    from tabs.image_compare.services.playlist_components.list_operations import (
        PlaylistListOperations,
    )

    dispatcher = _FakeDispatcher()
    document = SimpleNamespace(
        current_index1=0,
        current_index2=0,
        image_list1=[("a.png", "a")],
        image_list2=[("b.png", "b")],
    )
    image1 = SimpleNamespace(uid="image-1")
    image2 = SimpleNamespace(uid="image-2")
    store = SimpleNamespace(
        get_dispatcher=lambda: dispatcher,
        get_session_state_slot=lambda _name: document,
        viewport=SimpleNamespace(
            session_data=SimpleNamespace(
                image_state=SimpleNamespace(image1=image1, image2=image2)
            )
        ),
        batch_changes=_null_batch,
        invalidate_geometry_cache=lambda: dispatcher.dispatch(InvalidateGeometryCacheAction()),
    )
    PlaylistListOperations(store, main_controller=None).swap_current_images()

    # The pair is still published in ONE batch, but through the dispatcher
    # (copy-on-write document + viewport slots), so the assertion reads the
    # published actions instead of the mutated fake document object: the swap
    # must never edit a document other holders already describe (see
    # ``document_store_ops.swap_current_pair``).
    from core.state_management.document_actions import SetImageListAction

    published_lists = [
        action for action in dispatcher.actions if isinstance(action, SetImageListAction)
    ]
    assert [items.items[0] for items in published_lists] == [
        ("b.png", "b"),
        ("a.png", "a"),
    ]
    slot_writes = [
        a
        for a in dispatcher.actions
        if not isinstance(a, (SetImageListAction, InvalidateGeometryCacheAction))
    ]
    assert len(slot_writes) == 2, "the pair is published in one batch, two slot writes"
    assert not [
        a for a in dispatcher.actions if isinstance(a, InvalidateGeometryCacheAction)
    ], "a same-pair swap zeroed the geometry: the loupe disappears for a frame"


class _null_batch:
    def __enter__(self):
        return None

    def __exit__(self, *exc):  # noqa: ANN002, ANN003
        return False
