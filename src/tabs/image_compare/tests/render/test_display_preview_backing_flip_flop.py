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

from shared.image_processing import pyramid_registry
from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.image_identity import image_uid
from tabs.image_compare.presenters.image_canvas.background_parts import render_flow
from tabs.image_compare.presenters.image_canvas.background_parts.render_flow import (
    pick_display_with_preview_backing,
)


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


class _ImageState:
    def __init__(self):
        self.image1 = None
        self.image2 = None


class _RenderCache:
    def __init__(self):
        self.unification_in_progress = False
        self.pending_unification_paths = None


class _SessionData:
    def __init__(self):
        self.image_state = _ImageState()
        self.render_cache = _RenderCache()


class _Viewport:
    def __init__(self):
        self.session_data = _SessionData()
        self.interaction_state = SimpleNamespace(resize_in_progress=False)
        self.view_state = SimpleNamespace(
            showing_single_image_mode=0,
            diff_mode="off",
            channel_view_mode="rgb",
        )
        self.geometry_state = SimpleNamespace(
            pixmap_width=0,
            pixmap_height=0,
            image_display_rect_on_label=None,
        )


class _Store:
    def __init__(self, document):
        self.document = document
        self.viewport = _Viewport()

    def get_session_state_slot(self, name):
        assert name == "document"
        return self.document


def _presenter(store, applied):
    return SimpleNamespace(
        main_window_app=SimpleNamespace(
            _is_ui_stable=True,
            _closing=False,
            isVisible=lambda: True,
            isMinimized=lambda: False,
            ui=SimpleNamespace(workspace_stack=None),
        ),
        store=store,
        widget=SimpleNamespace(isVisible=lambda: True, image_label=object()),
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
    store = _complete_store()
    preview1 = Image.new("RGBA", (64, 64), "blue")
    preview2 = Image.new("RGBA", (64, 64), "green")
    document = SimpleNamespace(
        image1_path="/a.png",
        image2_path="/b.png",
        full_res_image1=None,
        full_res_image2=None,
        preview_image1=preview1,
        preview_image2=preview2,
        original_image1=None,
        original_image2=None,
    )
    store_obj = _Store(document)
    state = store_obj.viewport.session_data.image_state
    applied: list[tuple] = []
    presenter = _presenter(store_obj, applied)

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
    state.image1 = store
    render_flow.update_comparison_if_needed(presenter)
    assert applied[-1][0] is store
    assert presenter._last_superseded_preview_uid == {1: image_uid(preview1)}

    # Cycle 3: nothing changed, but the render state is invalidated again
    # (as the load path does) -- the same image's preview must NOT be picked
    # again. This cycle used to degrade back to preview1 (flip-flop).
    _invalidate(presenter)
    render_flow.update_comparison_if_needed(presenter)
    assert applied[-1][0] is store, (
        "same-image preview re-degraded the complete store -- flip-flop"
    )

    # Cycle 4: a genuinely new image's preview arrives -- it must replace
    # the previous image's store immediately, even with superseded set.
    new_preview = Image.new("RGBA", (80, 80), "yellow")
    document.preview_image1 = new_preview
    _invalidate(presenter)
    render_flow.update_comparison_if_needed(presenter)
    assert applied[-1][0] is new_preview

    assert [applied[0][0], applied[1][0], applied[2][0]] == [
        preview1,
        store,
        store,
    ]