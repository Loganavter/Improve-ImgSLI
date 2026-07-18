"""Duplicate / slot-clear must not blank the live half of the pair.

Repro: side 1 has a loaded image, side 2 empty. Context-menu Duplicate onto
side 2 used to call ``load_images_from_paths`` → ``clear_image_slot_data(2)``,
and ``ClearImageSlotDataAction`` wiped *both* ``scaled_image*_for_display``
caches — flashing the whole canvas. DnD onto a non-empty side never hit that
path; Duplicate onto an empty half did.
"""

from __future__ import annotations

from core.state_management.actions import ClearImageSlotDataAction
from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.state.models import RenderCacheState
from tabs.image_compare.state.reducers import RenderCacheReducer
from tabs.image_compare.use_cases import loading


class _RenderCache:
    def __init__(self):
        self.unification_in_progress = False
        self.pending_unification_paths = None
        self.display_cache_image1 = object()
        self.display_cache_image2 = None
        self.scaled_image1_for_display = object()
        self.scaled_image2_for_display = None
        self.unified_image_cache = {}
        self.last_display_cache_params = ("stale",)
        self.cached_scaled_image_dims = (1, 1)
        self.cached_diff_image = None


class _ImageState:
    def __init__(self):
        self.image1 = object()
        self.image2 = None


class _SessionData:
    def __init__(self):
        self.image_state = _ImageState()
        self.render_cache = _RenderCache()


class _Viewport:
    def __init__(self):
        self.session_data = _SessionData()


class _Store:
    def __init__(self, document: DocumentModel):
        self.document = document
        self.viewport = _Viewport()

    def get_session_state_slot(self, name):
        assert name == "document"
        return self.document

    def get_dispatcher(self):
        return None

    def invalidate_geometry_cache(self):
        pass

    def invalidate_render_cache(self):
        pass

    def emit_state_change(self, *_args, **_kwargs):
        pass


class _Controller:
    def __init__(self, store: _Store):
        self.store = store
        self.presenter = None
        self.diff_service = None
        self.set_current_calls: list[int] = []

    def set_current_image(self, image_number: int, *args, **kwargs):
        self.set_current_calls.append(image_number)


def test_clear_image_slot_data_keeps_other_side_scaled_cache():
    cache = RenderCacheState(
        display_cache_image1=object(),
        display_cache_image2=object(),
        scaled_image1_for_display=object(),
        scaled_image2_for_display=object(),
        cached_scaled_image_dims=(10, 10),
        last_display_cache_params=("x",),
    )
    live_scaled = cache.scaled_image1_for_display
    live_display = cache.display_cache_image1

    updated = RenderCacheReducer.reduce(
        cache, ClearImageSlotDataAction(slot=2)
    )

    assert updated.scaled_image1_for_display is live_scaled
    assert updated.display_cache_image1 is live_display
    assert updated.scaled_image2_for_display is None
    assert updated.display_cache_image2 is None
    assert updated.cached_scaled_image_dims is None
    assert updated.last_display_cache_params is None


def test_duplicate_image_to_slot_appends_without_wiping_live_side(monkeypatch):
    document = DocumentModel(
        image_list1=[ImageItem(path="/a.png", display_name="a")],
        image_list2=[],
        current_index1=0,
        current_index2=-1,
        image1_path="/a.png",
        full_res_image1=object(),
    )
    store = _Store(document)
    live_scaled = store.viewport.session_data.render_cache.scaled_image1_for_display
    live_display = store.viewport.session_data.render_cache.display_cache_image1
    controller = _Controller(store)

    timers: list[tuple] = []

    def _capture_timer(delay, callback):
        timers.append((delay, callback))

    monkeypatch.setattr(loading, "QTimer", type("T", (), {"singleShot": staticmethod(_capture_timer)}))

    loading.duplicate_image_to_slot(controller, source_slot=1, target_slot=2)

    assert len(document.image_list2) == 1
    assert document.image_list2[0].path == "/a.png"
    assert document.current_index2 == 0
    assert (
        store.viewport.session_data.render_cache.scaled_image1_for_display
        is live_scaled
    )
    assert (
        store.viewport.session_data.render_cache.display_cache_image1 is live_display
    )
    assert timers
    timers[0][1]()
    assert controller.set_current_calls == [2]


def test_duplicate_image_to_slot_selects_existing_path_on_target(monkeypatch):
    document = DocumentModel(
        image_list1=[ImageItem(path="/a.png", display_name="a")],
        image_list2=[
            ImageItem(path="/b.png", display_name="b"),
            ImageItem(path="/a.png", display_name="a"),
        ],
        current_index1=0,
        current_index2=0,
    )
    controller = _Controller(_Store(document))
    monkeypatch.setattr(
        loading,
        "QTimer",
        type("T", (), {"singleShot": staticmethod(lambda _d, cb: cb())}),
    )

    loading.duplicate_image_to_slot(controller, source_slot=1, target_slot=2)

    assert len(document.image_list2) == 2
    assert document.current_index2 == 1
    assert controller.set_current_calls == [2]


def test_render_flow_keeps_live_side_when_other_slot_empty():
    """Regression: missing side must not call image_label.clear()."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from tabs.image_compare.presenters.image_canvas.background_parts import (
        render_flow,
    )

    live = object()
    cleared: list[int] = []
    single: list[object] = []

    presenter = SimpleNamespace(
        main_window_app=SimpleNamespace(
            _closing=False,
            isVisible=lambda: True,
            isMinimized=lambda: False,
            _is_ui_stable=True,
        ),
        store=SimpleNamespace(
            viewport=SimpleNamespace(
                interaction_state=SimpleNamespace(
                    is_interactive_mode=False,
                    resize_in_progress=False,
                ),
                view_state=SimpleNamespace(
                    showing_single_image_mode=0,
                    diff_mode="off",
                    channel_view_mode="rgb",
                ),
                session_data=SimpleNamespace(
                    image_state=SimpleNamespace(image1=live, image2=None),
                    render_cache=SimpleNamespace(
                        unification_in_progress=False,
                        display_cache_image1=None,
                        display_cache_image2=None,
                        scaled_image1_for_display=live,
                        scaled_image2_for_display=None,
                        cached_diff_image=None,
                    ),
                ),
                geometry_state=SimpleNamespace(
                    pixmap_width=0,
                    pixmap_height=0,
                    image_display_rect_on_label=None,
                ),
                render_config=SimpleNamespace(display_resolution_limit=0),
            ),
            get_session_state_slot=lambda _n: SimpleNamespace(
                full_res_image1=live,
                full_res_image2=None,
                preview_image1=None,
                preview_image2=None,
                original_image1=None,
                original_image2=None,
                image1_path="/a.png",
                image2_path=None,
            ),
        ),
        widget=SimpleNamespace(
            image_label=SimpleNamespace(clear=lambda: cleared.append(1))
        ),
        view=SimpleNamespace(
            is_canvas_widget=lambda: False,
            display_single_image_on_label=lambda img: single.append(img),
        ),
        get_current_label_dimensions=lambda: (200, 200),
        current_displayed_pixmap=None,
        _update_scheduler_timer=SimpleNamespace(
            stop=lambda: None, start=lambda: None, isActive=lambda: False
        ),
        _pending_interactive_mode=None,
        background=MagicMock(),
        _last_label_dims=(200, 200),
        _cached_base_pixmap=None,
        _last_bg_signature=None,
    )

    assert render_flow.update_comparison_if_needed(presenter) is False
    assert cleared == []
    assert single == [live]
