"""A pair replacement must swap the content under the geometry it already has.

Repro (the owner's "при замене пары изображений мы заново чистим или
пересоздаем геометрию"): both slots are being replaced. ``set_current_image``
clears the outgoing side's ``image_state`` before its worker publishes, and the
pipeline peek for the incoming path still misses, so for one frame **both**
sides are absent while the document already points at the incoming pair. That
frame used to take ``have_gate``'s ``not have1 and not have2`` branch, which
calls ``image_label.clear()`` → ``layers.clear()``:

    state._content_rect_px = None
    state._inner_content_rect_px = None
    state._letterbox_params = [None, None]
    state._shader_letterbox_mode = False
    state._stored_pil_images = [None, None]

The next apply then captures the camera anchor with
``capture_letterbox_focus`` (``ui/canvas_infra/viewport/focus.py:19``), which
returns ``None`` once ``_letterbox_params[0] is None`` — so
``restore_letterbox_focus`` is a silent no-op and the incoming pair is
letterboxed from scratch with the camera unanchored. ``zoom``/``pan`` survive
numerically but pan is only stable *through* a letterbox
(``docs/dev/rendering/zoom-pan.md`` § Preserving the image sample point), so
the picture jumps.

Contract asserted here:

* a both-sides-absent frame that has a load in flight for a document side
  **waits** — exactly like the sibling one-side branch (reason
  ``"wait_other_side"``) — so the last frame and its letterbox survive;
* the arriving pair then converges **in place**: ``capture_letterbox_focus`` →
  ``update_common_letterbox_geometry`` → ``restore_letterbox_focus`` keeps the
  image sample point under the viewport centre unchanged;
* a genuinely empty session still clears (no stale pair left on screen) and the
  one-side path is untouched.

Measured offscreen on a real ``CanvasWidget`` (no RHI device needed for the
runtime geometry): before the frame above the widget carries
``content_rect=(0,0,1200,900)`` / ``letterbox=[(0,0,1,1),(0,0,1,1)]`` and a
capturable focus; after the unconditional ``clear()`` it carries ``None`` /
``[None, None]`` and no focus — the failure this file pins.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest
from PIL import Image

from tabs.image_compare.canvas.texture_parts.base_images import (
    update_common_letterbox_geometry,
)
from tabs.image_compare.presenters.image_canvas.background_parts.use_cases.have_gate import (
    handle_have_gate,
)
from ui.canvas_infra.viewport.focus import (
    capture_letterbox_focus,
    restore_letterbox_focus,
)
from ui.canvas_infra.viewport.state import set_pan_offsets, set_zoom_level

OLD_PAIR = ((1600, 1200), (1200, 1200))
NEW_PAIR = ((1000, 1400), (1800, 900))


def _app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _canvas_with_pair(sizes=OLD_PAIR):
    """Real canvas showing a letterboxed pair (offscreen: runtime geometry only)."""
    from tabs.image_compare.canvas.widget import CanvasWidget

    _app()
    canvas = CanvasWidget()
    canvas.resize(1200, 900)
    img1 = Image.new("RGB", sizes[0], (200, 30, 30))
    img2 = Image.new("RGB", sizes[1], (30, 200, 30))
    canvas.set_pil_layers(img1, img2, shader_letterbox=True)
    set_zoom_level(canvas, 2.0)
    set_pan_offsets(canvas, 0.12, -0.07)
    return canvas


class _LoadService:
    def __init__(self, loading=()):
        self._loading = set(loading)

    def is_loading(self, path, crop_service=None):
        return path in self._loading


class _Controller:
    def __init__(self, load_service):
        self._load_service = load_service

    def _get_image_session(self, _session_id=None):
        return SimpleNamespace(load_service=self._load_service)


class _Store:
    def __init__(self, image1, image2, document):
        self.viewport = SimpleNamespace(
            session_data=SimpleNamespace(
                image_state=SimpleNamespace(image1=image1, image2=image2)
            ),
            interaction_state=SimpleNamespace(is_interactive_mode=False),
            view_state=SimpleNamespace(showing_single_image_mode=0),
        )
        self._document = document

    def get_session_state_slot(self, name):
        return self._document if name == "document" else None

    def get_dispatcher(self):
        return None


def _document(path1=None, path2=None, items1=(), items2=()):
    return SimpleNamespace(
        image1_path=path1,
        image2_path=path2,
        image_list1=list(items1),
        image_list2=list(items2),
        current_index1=0,
        current_index2=0,
    )


def _presenter(canvas, document, *, image1=None, image2=None, loading=()):
    return SimpleNamespace(
        store=_Store(image1, image2, document),
        widget=SimpleNamespace(image_label=canvas),
        session_controller=_Controller(_LoadService(loading)),
        current_displayed_pixmap=object(),
    )


# -- the bug: the replacement frame tore the geometry down ---------------------


def test_pair_replacement_frame_keeps_geometry_and_reanchors():
    canvas = _canvas_with_pair()
    state = canvas.runtime_state
    rect_before = state._content_rect_px
    inner_before = state._inner_content_rect_px
    letterbox_before = list(state._letterbox_params)
    focus_before = capture_letterbox_focus(canvas)
    assert rect_before is not None
    assert inner_before is not None
    assert focus_before is not None

    # Both sides replaced: their image_state was cleared, the new paths are in
    # the document, and their loads are in flight (the pipeline peek misses).
    new1, new2 = "/pair-replace/a.png", "/pair-replace/b.png"
    document = _document(
        new1,
        new2,
        items1=[SimpleNamespace(path=new1)],
        items2=[SimpleNamespace(path=new2)],
    )
    presenter = _presenter(
        canvas, document, image1=None, image2=None, loading={new1, new2}
    )

    deferred = handle_have_gate(presenter, None, None, document, {})
    assert deferred is True, "a replacement frame must defer, not repaint"

    # The frame and its letterbox survive the replacement frame.
    assert state._content_rect_px == rect_before
    assert state._inner_content_rect_px == inner_before
    assert state._letterbox_params == letterbox_before
    assert state._stored_pil_images[0] is not None
    assert capture_letterbox_focus(canvas) == pytest.approx(focus_before, abs=1e-9)

    # ... so the arriving pair converges in place: same image sample point.
    update_common_letterbox_geometry(
        canvas,
        Image.new("RGB", NEW_PAIR[0], (20, 20, 200)),
        Image.new("RGB", NEW_PAIR[1], (20, 200, 200)),
    )
    assert restore_letterbox_focus(canvas, focus_before) is True
    assert capture_letterbox_focus(canvas) == pytest.approx(focus_before, abs=1e-9)


# -- controls: the cases that must keep today's behaviour ---------------------


def test_genuinely_empty_session_still_clears_the_frame():
    canvas = _canvas_with_pair()
    state = canvas.runtime_state
    document = _document()  # no paths, no lists, no load in flight
    presenter = _presenter(canvas, document)

    assert handle_have_gate(presenter, None, None, document, {}) is True

    assert state._content_rect_px is None
    assert state._letterbox_params == [None, None]
    assert state._stored_pil_images == [None, None]
    assert presenter.current_displayed_pixmap is None


def test_one_side_missing_still_waits_without_touching_geometry():
    canvas = _canvas_with_pair()
    state = canvas.runtime_state
    rect_before = state._content_rect_px
    letterbox_before = list(state._letterbox_params)

    live = Image.new("RGB", NEW_PAIR[0], (90, 90, 90))
    new1, new2 = "/pair-replace/only-a.png", "/pair-replace/pending-b.png"
    document = _document(
        new1,
        new2,
        items1=[SimpleNamespace(path=new1)],
        items2=[SimpleNamespace(path=new2)],
    )
    presenter = _presenter(canvas, document, image1=live, image2=None, loading={new2})

    assert handle_have_gate(presenter, live, None, document, {}) is True

    assert state._content_rect_px == rect_before
    assert state._letterbox_params == letterbox_before
    assert state._stored_pil_images[0] is not None


# -- the pre-step that emitted that frame: no no-op clears ---------------------


class _RecordingStore:
    """Minimal real-reducer store double for ``load_images_from_paths``."""

    def __init__(self):
        from tabs.image_compare.state.document import DocumentModel

        self.viewport = SimpleNamespace(
            session_data=SimpleNamespace(
                image_state=SimpleNamespace(image1=None, image2=None),
                render_cache=SimpleNamespace(
                    unification_in_progress=False,
                    pending_unification_paths=None,
                    cached_diff_image=None,
                ),
            )
        )
        self.settings = SimpleNamespace(current_language="en")
        self._document = DocumentModel()
        self.dispatched: list = []
        self.emitted: list[str] = []

    def get_session_state_slot(self, name, **_kw):
        return self._document if name == "document" else None

    def get_dispatcher(self):
        return self

    def dispatch(self, action, scope="viewport"):
        self._apply(action)
        self.dispatched.append(action)
        self.emit_state_change(scope)

    def transact(self, actions, scope="document"):
        for action in actions:
            self.dispatch(action, scope)

    def batch_changes(self):
        from contextlib import nullcontext

        return nullcontext()

    def emit_state_change(self, scope):
        self.emitted.append(scope)

    def invalidate_render_cache(self):
        pass

    def _apply(self, action):
        from dataclasses import replace

        from core.state_management.actions import (
            ClearImageSlotDataAction,
            SetCachedDiffImageAction,
            SetCurrentIndexAction,
            SetImageSessionImageAction,
            SetPendingUnificationPathsAction,
            SetUnificationInProgressAction,
        )
        from core.state_management.document_actions import AppendImageItemsAction

        doc = self._document
        images = self.viewport.session_data.image_state
        render_cache = self.viewport.session_data.render_cache
        if isinstance(action, AppendImageItemsAction):
            attr = "image_list1" if action.slot == 1 else "image_list2"
            self._document = replace(doc, **{attr: list(getattr(doc, attr)) + list(action.items)})
        elif isinstance(action, SetCurrentIndexAction):
            attr = "current_index1" if action.slot == 1 else "current_index2"
            self._document = replace(doc, **{attr: action.index})
        elif isinstance(action, ClearImageSlotDataAction):
            attr = "_last_display_name1" if action.slot == 1 else "_last_display_name2"
            self._document = replace(doc, **{attr: ""})
            setattr(images, f"image{action.slot}", None)
        elif isinstance(action, SetImageSessionImageAction):
            setattr(images, f"image{action.slot}", action.image)
        elif isinstance(action, SetUnificationInProgressAction):
            render_cache.unification_in_progress = action.enabled
        elif isinstance(action, SetPendingUnificationPathsAction):
            render_cache.pending_unification_paths = action.paths
        elif isinstance(action, SetCachedDiffImageAction):
            render_cache.cached_diff_image = action.image


def test_pair_load_into_a_pristine_session_clears_nothing():
    """Both lists empty + both slots hold nothing: a first drop must not clear.

    HEAD dispatched ``ClearImageSlotDataAction(1|2)`` +
    ``SetImageSessionImageAction(slot=1|2, image=None)`` unconditionally here;
    a no-op clear still emitted a viewport change, i.e. a no-sources frame that
    tore the canvas geometry down (see the module docstring).
    """
    from core.state_management.actions import (
        ClearImageSlotDataAction,
        SetImageSessionImageAction,
    )
    from tabs.image_compare.use_cases import slot as slot_uc

    store = _RecordingStore()
    controller = SimpleNamespace(
        store=store,
        set_current_image=lambda *a, **k: None,
        presenter=None,
        _get_crop_service=lambda: None,
        thread_pool=None,
        diff_service=None,
        event_bus=None,
        error_occurred=SimpleNamespace(emit=lambda *a, **k: None),
    )

    slot_uc.load_images_from_paths(controller, ["/pair-replace/first.png"], 1)

    destructive = [
        action
        for action in store.dispatched
        if isinstance(action, (ClearImageSlotDataAction, SetImageSessionImageAction))
        and not getattr(action, "image", None)
    ]
    assert destructive == []
    # The load itself still landed (append + current index).
    assert [item.path for item in store._document.image_list1] == [
        "/pair-replace/first.png"
    ]
    assert store._document.current_index1 == 0

