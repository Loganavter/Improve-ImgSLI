"""W5b: per-image crop override steers box resolution in every IC consumer.

The persisted ``ImageItem.crop_override`` tristate (``None`` == Auto,
``True`` == On, ``False`` == Off) must steer the single box-resolution path:

* ``effective_crop_box_for_path`` semantics — Off → ``None`` WITHOUT
  touching detection (``CropService.get`` never called); Auto/On →
  detection as today (On with no detected box yields ``None`` naturally);
* the pure-read accessor ``crop_override_for_path`` (``state/document.py``)
  — scans ``image_list1/2`` by path, unknown → ``None``;
* forwarding at all three resolve points — texture seam
  (``resolve_slot_boxes`` / ``box_for_texture_key``), analysis
  (``resolve_crop_boxes_for_paths``), plan helper
  (``_box_clipped_live_inputs``).
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image

from shared.image_processing.autocrop.model import CropBox
from tabs.image_compare.pipeline.crop_box import effective_crop_box_for_path
from tabs.image_compare.state.document import (
    DocumentModel,
    ImageItem,
    crop_override_for_path,
)

BOX = CropBox(40, 40, 160, 120)  # 120x80 content window in a 200x160 frame
FULL = (200, 160)
WINDOW = (120, 80)


class _FakeCropService:
    """Warmed detection stand-in: fixed box for known paths, None otherwise."""

    def __init__(self, paths=()):
        self._paths = {os.path.normpath(p) for p in paths}
        self.calls = []

    def _has_cached(self, path):
        return True

    def get(self, path):
        self.calls.append(str(path))
        if os.path.normpath(str(path)) in self._paths:
            return BOX
        return None


def _bordered_png(path):
    canvas = Image.new("RGBA", FULL, (0, 0, 0, 255))
    canvas.paste(Image.new("RGBA", WINDOW, (200, 180, 160, 255)), (40, 40))
    canvas.save(str(path))
    return str(path)


def _doc(p1, p2, ov1=None, ov2=None):
    return DocumentModel(
        image_list1=[ImageItem(path=p1, display_name="a", crop_override=ov1)],
        image_list2=[ImageItem(path=p2, display_name="b", crop_override=ov2)],
        current_index1=0,
        current_index2=0,
    )


# --------------------------------------------------------------------------
# accessor: pure read over image_list1/2
# --------------------------------------------------------------------------


def test_accessor_tristate_and_unknown(tmp_path):
    p1 = _bordered_png(tmp_path / "a.png")
    p2 = _bordered_png(tmp_path / "b.png")
    assert crop_override_for_path(_doc(p1, p2), p1) is None  # Auto default
    assert crop_override_for_path(_doc(p1, p2, True, False), p1) is True
    assert crop_override_for_path(_doc(p1, p2, True, False), p2) is False
    assert crop_override_for_path(_doc(p1, p2), str(tmp_path / "zzz.png")) is None
    assert crop_override_for_path(None, p1) is None
    assert crop_override_for_path(_doc(p1, p2), None) is None
    # legacy item shape without the field → Auto, never raises
    legacy = SimpleNamespace(image_list1=[SimpleNamespace(path=p1)], image_list2=[])
    assert crop_override_for_path(legacy, p1) is None


# --------------------------------------------------------------------------
# helper semantics: Off skips detection, Auto/On detect
# --------------------------------------------------------------------------


def test_effective_off_skips_detection(tmp_path):
    p = _bordered_png(tmp_path / "a.png")
    svc = _FakeCropService([p])
    assert effective_crop_box_for_path(p, crop_service=svc, override=False) is None
    assert svc.calls == []  # detection never touched


def test_effective_auto_and_on_detect(tmp_path):
    p = _bordered_png(tmp_path / "a.png")
    svc = _FakeCropService([p])
    assert effective_crop_box_for_path(p, crop_service=svc, override=None) == BOX
    assert effective_crop_box_for_path(p, crop_service=svc, override=True) == BOX
    assert effective_crop_box_for_path(p, crop_service=svc) == BOX  # parity


def test_effective_on_without_box_yields_none(tmp_path):
    p = _bordered_png(tmp_path / "a.png")
    svc = _FakeCropService([])  # nothing detected
    assert effective_crop_box_for_path(p, crop_service=svc, override=True) is None
    assert effective_crop_box_for_path(p, crop_service=None, override=True) is None


# --------------------------------------------------------------------------
# texture seam: resolve_slot_boxes / box_for_texture_key
# --------------------------------------------------------------------------


def _seam_widget(doc):
    store = SimpleNamespace(
        get_session_state_slot=lambda name: doc if name == "document" else None
    )
    return SimpleNamespace(
        runtime_state=SimpleNamespace(_store=store),
        texture_ids=["tex0", "tex1"],
    )


def test_seam_off_none_despite_warmed_box(tmp_path):
    from tabs.image_compare.canvas.texture_parts.crop_clip import resolve_slot_boxes

    p1 = _bordered_png(tmp_path / "a.png")
    p2 = _bordered_png(tmp_path / "b.png")
    svc = _FakeCropService([p1, p2])
    widget = _seam_widget(_doc(p1, p2, ov1=False, ov2=False))
    assert resolve_slot_boxes(widget, source_key=(p1, p2), crop_service=svc) == (
        None,
        None,
    )
    assert svc.calls == []  # neither slot consulted detection


def test_seam_mixed_off_and_auto(tmp_path):
    from tabs.image_compare.canvas.texture_parts.crop_clip import resolve_slot_boxes

    p1 = _bordered_png(tmp_path / "a.png")
    p2 = _bordered_png(tmp_path / "b.png")
    svc = _FakeCropService([p1, p2])
    widget = _seam_widget(_doc(p1, p2, ov1=False, ov2=None))
    assert resolve_slot_boxes(widget, source_key=(p1, p2), crop_service=svc) == (
        None,
        BOX,
    )


def test_seam_on_and_explicit_document(tmp_path):
    from tabs.image_compare.canvas.texture_parts.crop_clip import (
        box_for_texture_key,
        resolve_slot_boxes,
    )

    p1 = _bordered_png(tmp_path / "a.png")
    p2 = _bordered_png(tmp_path / "b.png")
    svc = _FakeCropService([p1, p2])
    # no store on the widget: explicit document still forwards
    bare = SimpleNamespace(runtime_state=SimpleNamespace(_store=None))
    doc = _doc(p1, p2, ov1=True, ov2=True)
    assert resolve_slot_boxes(
        bare, source_key=(p1, p2), crop_service=svc, document=doc
    ) == (BOX, BOX)
    # texture-key entry point honors the same override (Off → None)
    off_widget = _seam_widget(_doc(p1, p2, ov1=False, ov2=True))
    assert (
        box_for_texture_key(off_widget, "tex0", source_key=(p1, p2), crop_service=svc)
        is None
    )
    assert box_for_texture_key(
        off_widget, "tex1", source_key=(p1, p2), crop_service=svc
    ) == BOX
    assert box_for_texture_key(off_widget, "diff", source_key=(p1, p2)) is None


# --------------------------------------------------------------------------
# analysis: resolve_crop_boxes_for_paths
# --------------------------------------------------------------------------


def test_analysis_forwards_override(tmp_path):
    from tabs.image_compare.services.analysis.analysis_pair import (
        resolve_crop_boxes_for_paths,
    )

    p1 = _bordered_png(tmp_path / "a.png")
    p2 = _bordered_png(tmp_path / "b.png")
    svc = _FakeCropService([p1, p2])
    getter = lambda: svc  # noqa: E731
    assert resolve_crop_boxes_for_paths(
        p1, p2, getter, document=_doc(p1, p2, False, False)
    ) == (None, None)
    assert resolve_crop_boxes_for_paths(
        p1, p2, getter, document=_doc(p1, p2, True, None)
    ) == (BOX, BOX)
    # no document → today's behavior bit-identical
    assert resolve_crop_boxes_for_paths(p1, p2, getter) == (BOX, BOX)


# --------------------------------------------------------------------------
# plan helper: _box_clipped_live_inputs (+ live plan stays full-frame on Off)
# --------------------------------------------------------------------------


def _plan_store(p1, p2, disp1, disp2, doc, crop_service):
    import tabs.image_compare.bootstrap_reducers  # noqa: F401

    from core.state_management.dispatcher import Dispatcher
    from core.store import Store
    from core.store_viewport import SessionData
    from tabs.image_compare.state.models import (
        ImageSessionState,
        PipelineCacheState,
        RenderCacheState,
    )

    store = Store()
    store.create_workspace_session(session_type="image_compare", activate=True)
    store.set_session_state_slot("document", doc)
    store.viewport.session_data = SessionData(
        image_state=ImageSessionState(), render_cache=RenderCacheState()
    )
    store.state_changed = type(
        "Sig", (), {"emit": staticmethod(lambda *_a, **_k: None)}
    )()
    store.set_dispatcher(Dispatcher(store))
    pipe = PipelineCacheState()
    pipe.crop_service = crop_service
    store.set_session_state_slot("pipeline", pipe)
    store.viewport.session_data.image_state.image1 = disp1
    store.viewport.session_data.image_state.image2 = disp2
    return store


def _warmed_service(p1, p2):
    from shared.image_processing.autocrop import CropService

    svc = CropService()
    assert svc.get(p1) is not None and svc.get(p2) is not None
    return svc


def test_plan_helper_off_is_none_on_is_clipped(tmp_path):
    from tabs.image_compare.canvas.presentation.plan_builder import (
        _box_clipped_live_inputs,
    )

    p1 = _bordered_png(tmp_path / "a.png")
    p2 = _bordered_png(tmp_path / "b.png")
    disp1 = Image.open(p1).convert("RGBA")
    disp2 = Image.open(p2).convert("RGBA")
    off = _plan_store(p1, p2, disp1, disp2, _doc(p1, p2, False, False),
                      _warmed_service(p1, p2))
    assert _box_clipped_live_inputs(off, disp1, disp2) is None
    on = _plan_store(p1, p2, disp1, disp2, _doc(p1, p2, True, True),
                     _warmed_service(p1, p2))
    boxed = _box_clipped_live_inputs(on, disp1, disp2)
    assert boxed is not None
    assert (boxed[2], boxed[3]) == WINDOW


@pytest.fixture(autouse=True)
def _register_image_compare_canvas_features():
    from tabs.image_compare.tab import ImageCompareTab

    ImageCompareTab().register_canvas_features()


def test_live_plan_off_stays_full_frame(tmp_path):
    from tabs.image_compare.canvas.presentation.plan_builder import build_canvas_plan

    p1 = _bordered_png(tmp_path / "a.png")
    p2 = _bordered_png(tmp_path / "b.png")
    disp1 = Image.open(p1).convert("RGBA")
    disp2 = Image.open(p2).convert("RGBA")
    store = _plan_store(p1, p2, disp1, disp2, _doc(p1, p2, False, False),
                        _warmed_service(p1, p2))
    plan = build_canvas_plan(store, disp1, disp2)
    assert (plan.canvas_w, plan.canvas_h) == FULL
    assert plan.image1 is disp1
    assert plan.image2 is disp2
