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

from tabs.image_compare.presenters.image_canvas.background_parts import render_flow


class _ImageState:
    def __init__(self):
        self.image1 = None
        self.image2 = None


class _RenderCache:
    def __init__(self, unification_in_progress=False):
        self.unification_in_progress = unification_in_progress
        self.pending_unification_paths = None


class _GeometryState:
    def __init__(self):
        self.pixmap_width = 0
        self.pixmap_height = 0
        self.image_display_rect_on_label = None


class _SessionData:
    def __init__(self, unification_in_progress=False):
        self.image_state = _ImageState()
        self.render_cache = _RenderCache(unification_in_progress)


class _Viewport:
    def __init__(self, unification_in_progress=False):
        self.session_data = _SessionData(unification_in_progress)
        self.interaction_state = SimpleNamespace(resize_in_progress=False)
        self.view_state = SimpleNamespace(
            showing_single_image_mode=0,
            diff_mode="off",
            channel_view_mode="rgb",
        )
        self.geometry_state = _GeometryState()


class _Store:
    def __init__(self, document, unification_in_progress=False):
        self.document = document
        self.viewport = _Viewport(unification_in_progress)

    def get_session_state_slot(self, name):
        assert name == "document"
        return self.document


def _presenter(store):
    return SimpleNamespace(
        main_window_app=SimpleNamespace(
            _is_ui_stable=True,
            _closing=False,
            isVisible=lambda: True,
            isMinimized=lambda: False,
            ui=SimpleNamespace(workspace_stack=None),
        ),
        store=store,
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


def _qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_geometry_updates_during_unification_deferral():
    """The user-visible case: both previews are on the document, the unify
    worker is in flight (image_state.image1 still None), the gate defers the
    apply -- but the letterbox rect must already be the new comparison's."""
    _qapp()
    preview1 = Image.new("RGBA", (100, 50), "red")
    preview2 = Image.new("RGBA", (60, 60), "blue")
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
    store = _Store(document, unification_in_progress=True)
    presenter = _presenter(store)
    geometry = store.viewport.geometry_state

    assert render_flow.update_comparison_if_needed(presenter) is False
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
    document = SimpleNamespace(
        image1_path="/a.png",
        image2_path=None,
        full_res_image1=None,
        full_res_image2=None,
        preview_image1=preview1,
        preview_image2=None,
        original_image1=None,
        original_image2=None,
    )
    store = _Store(document)
    presenter = _presenter(store)
    geometry = store.viewport.geometry_state

    assert render_flow.update_comparison_if_needed(presenter) is False
    assert (geometry.pixmap_width, geometry.pixmap_height) == (400, 200)
    rect = geometry.image_display_rect_on_label
    assert (rect.x, rect.y, rect.w, rect.h) == (0, 100, 400, 200)


def test_geometry_unchanged_when_no_sources():
    """Nothing loaded: the previous rect is kept (no crash, no mutation)."""
    _qapp()
    document = SimpleNamespace(
        image1_path=None,
        image2_path=None,
        full_res_image1=None,
        full_res_image2=None,
        preview_image1=None,
        preview_image2=None,
        original_image1=None,
        original_image2=None,
    )
    store = _Store(document)
    presenter = _presenter(store)
    geometry = store.viewport.geometry_state

    assert render_flow.update_comparison_if_needed(presenter) is False
    assert (geometry.pixmap_width, geometry.pixmap_height) == (0, 0)
    assert geometry.image_display_rect_on_label is None