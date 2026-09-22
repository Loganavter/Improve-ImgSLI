"""Explicit per-image On (True) must crop even with the global flag OFF.

The OFF gate nulls the session/cached services (``_get_crop_service()`` →
None), which used to leave an explicit On with no detection service anywhere
(``resolve_box_for_path(path, None, True)`` → None). The controller-owned
detection-only spare (``_get_crop_service_forced``) fills that hole; Auto and
Off behavior stays bit-identical with the flag on or off.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image

from shared.image_processing.autocrop.model import CropBox
from shared.image_processing.autocrop.service import CropService
from tabs.image_compare._session_controller import SessionController
from tabs.image_compare.canvas.texture_parts.crop_clip import resolve_box_for_path
from tabs.image_compare.services.analysis.analysis_pair import (
    forced_service_from,
    resolve_crop_boxes_for_paths,
)
from tabs.image_compare.state.document import DocumentModel, ImageItem

FULL = (200, 160)
WINDOW = (120, 80)
BOX = CropBox(40, 40, 160, 120)


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


def _warmed_service(p1, p2):
    svc = CropService()
    assert svc.get(p1) == BOX
    assert svc.get(p2) == BOX
    return svc


def test_forced_spare_is_live_and_cached():
    spare = SessionController._get_crop_service_forced(SimpleNamespace())
    assert isinstance(spare, CropService)
    # Same spare on repeat (detection cache must survive across frames).
    assert SessionController._get_crop_service_forced(
        SimpleNamespace(_forced_crop_service=spare)
    ) is spare


def test_resolve_true_with_off_uses_forced(tmp_path):
    p1 = _bordered_png(tmp_path / "a.png")
    forced = _warmed_service(p1, p1)
    assert resolve_box_for_path(p1, None, override=True, forced_service=forced) == BOX
    # Auto/Off never touch the spare, even when it is handed in.
    assert resolve_box_for_path(p1, None, override=None, forced_service=forced) is None
    assert resolve_box_for_path(p1, None, override=False, forced_service=forced) is None
    assert resolve_box_for_path(p1, None, override=True) is None


def test_analysis_seam_true_with_off_uses_forced(tmp_path):
    p1 = _bordered_png(tmp_path / "a.png")
    p2 = _bordered_png(tmp_path / "b.png")
    forced = _warmed_service(p1, p2)
    assert resolve_crop_boxes_for_paths(
        p1,
        p2,
        lambda: None,
        document=_doc(p1, p2, True, None),
        get_forced_crop_service=lambda: forced,
    ) == (BOX, None)  # slot 2 is Auto → stays None under OFF
    # Auto slot stays None under OFF even with a warmed spare around.
    assert resolve_crop_boxes_for_paths(
        p1,
        p2,
        lambda: None,
        document=_doc(p1, p2, False, None),
        get_forced_crop_service=lambda: forced,
    ) == (None, None)


def test_forced_service_from_bound_getter():
    real = CropService()

    class _Ctrl:
        def _get_crop_service(self):
            return None

        def _get_crop_service_forced(self):
            return real

    ctrl = _Ctrl()
    assert forced_service_from(ctrl._get_crop_service) is real
    assert forced_service_from(lambda: None) is None
    assert forced_service_from(None) is None
    assert forced_service_from(object()) is None


def test_magnifier_gate_true_bypasses_off(tmp_path):
    from tabs.image_compare.canvas.features.magnifier.geometry.box_remap import (
        resolve_crop_boxes_for_store,
    )

    p1 = _bordered_png(tmp_path / "a.png")
    p2 = _bordered_png(tmp_path / "b.png")
    # Keep a reference: the loupe scans CropService._live_services (weakrefs),
    # a discarded spare is GC'd and invisible to the scan.
    forced = _warmed_service(p1, p2)
    assert forced.get(p1) == BOX
    off_store = SimpleNamespace(
        settings=SimpleNamespace(auto_crop_black_borders=False),
        get_session_state_slot=lambda _name: _doc(p1, p2, True, None),
    )
    assert resolve_crop_boxes_for_store(off_store) == (BOX, None)
    auto_store = SimpleNamespace(
        settings=SimpleNamespace(auto_crop_black_borders=False),
        get_session_state_slot=lambda _name: _doc(p1, p2, None, None),
    )
    assert resolve_crop_boxes_for_store(auto_store) == (None, None)
