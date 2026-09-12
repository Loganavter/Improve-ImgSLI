"""W3d regression: magnifier diffs honor the crop box.

The lens capture remaps over the crop windows (W3b); the SSIM diff behind
the lens must compute over those same windows, not full frames. Covers the
threading from the warmed boxes through magnifier's
``ensure_cached_diff_image`` → ``request_cached_diff_image_async`` → build
task into ``build_cached_diff_image(..., box1=..., box2=...)``:

* build task with boxes sizes to the box window and matches a hand-computed
  diff over manually cropped PILs (highlight pixel-equality, SSIM sizing);
* plain-tuple boxes (what ``box_remap`` resolves) behave like ``CropBox``;
* both boxes ``None`` → pixel-identical to today, legacy 5-tuple key;
* the request key carries box tuples so a box change recomputes instead of
  hitting a stale-box entry;
* ``ensure_cached_diff_image`` forwards the boxes to the async request.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image

from shared.image_processing.autocrop.model import CropBox
from shared.rendering.image_identity import image_uid
from tabs.image_compare.canvas.features.magnifier.workers import diff_cache
from tabs.image_compare.presenters.image_canvas.background_parts import diff_toasts
from tabs.image_compare.services.analysis.background_layers import (
    build_cached_diff_image,
)

BOX = CropBox(40, 40, 160, 120)  # 120x80 content window in a 200x160 frame
BOX_T = BOX.to_tuple()
FULL = (200, 160)
WINDOW = (120, 80)


def _bordered_frame(path, center):
    canvas = Image.new("RGBA", FULL, (0, 0, 0, 255))
    canvas.paste(Image.new("RGBA", WINDOW, center + (255,)), (40, 40))
    canvas.save(path)
    return str(path)


def _frame_a(tmp_path):
    return _bordered_frame(tmp_path / "a.png", (200, 180, 160))


def _frame_b(tmp_path):
    return _bordered_frame(tmp_path / "b.png", (120, 100, 220))


def _pil_pair(tmp_path):
    return (
        Image.open(_frame_a(tmp_path)).convert("RGBA"),
        Image.open(_frame_b(tmp_path)).convert("RGBA"),
    )


# --------------------------------------------------------------------------
# build task over the crop window
# --------------------------------------------------------------------------


def test_task_boxed_matches_manual_crop(tmp_path):
    """Highlight over full frames + boxes == diff over hand-cropped PILs."""
    img1, img2 = _pil_pair(tmp_path)
    boxed = diff_cache.build_cached_diff_image_task(
        img1, img2, "highlight", None, None, box1=BOX, box2=BOX
    )
    manual = build_cached_diff_image(
        img1.crop(BOX_T), img2.crop(BOX_T), "highlight", "RGB"
    )
    assert boxed is not None and manual is not None
    assert boxed.size == manual.size == WINDOW
    assert list(boxed.getdata()) == list(manual.getdata())
    # highlight is a per-pixel op, so interior pixels equal the full-frame
    # diff cropped to the window (sizes prove the box takes effect: the
    # boxed diff carries no border pixels at all).
    full = diff_cache.build_cached_diff_image_task(img1, img2, "highlight", None, None)
    assert full is not None and full.size == FULL
    assert list(boxed.getdata()) == list(full.crop(BOX_T).getdata())


def test_task_ssim_boxed_sizes_to_window(tmp_path):
    """The magnifier's own mode (ssim) computes over the crop window."""
    img1, img2 = _pil_pair(tmp_path)
    boxed = diff_cache.build_cached_diff_image_task(
        img1, img2, "ssim", None, None, box1=BOX, box2=BOX
    )
    assert boxed is not None
    assert boxed.size == WINDOW


def test_task_plain_tuple_boxes_equal_cropbox(tmp_path):
    """Warmed boxes arrive as plain tuples — same result as CropBox."""
    img1, img2 = _pil_pair(tmp_path)
    via_tuple = diff_cache.build_cached_diff_image_task(
        img1, img2, "highlight", None, None, box1=BOX_T, box2=BOX_T
    )
    via_box = diff_cache.build_cached_diff_image_task(
        img1, img2, "highlight", None, None, box1=BOX, box2=BOX
    )
    assert via_tuple is not None and via_box is not None
    assert via_tuple.size == WINDOW
    assert list(via_tuple.getdata()) == list(via_box.getdata())


def test_task_none_box_parity(tmp_path):
    """Both boxes None → pixel-identical to today's full-frame call."""
    img1, img2 = _pil_pair(tmp_path)
    without = diff_cache.build_cached_diff_image_task(
        img1, img2, "grayscale", None, None
    )
    with_none = diff_cache.build_cached_diff_image_task(
        img1, img2, "grayscale", None, None, box1=None, box2=None
    )
    assert without is not None and with_none is not None
    assert without.size == with_none.size == FULL
    assert list(without.getdata()) == list(with_none.getdata())


# --------------------------------------------------------------------------
# box-aware request key
# --------------------------------------------------------------------------


def _presenter():
    render_cache = SimpleNamespace(
        cached_diff_image=None,
        cached_diff_source_key=None,
    )
    session_data = SimpleNamespace(render_cache=render_cache)
    viewport = SimpleNamespace(session_data=session_data)
    store = SimpleNamespace(viewport=viewport)
    thread_pool = SimpleNamespace(start=MagicMock())
    main_window_app = SimpleNamespace(thread_pool=thread_pool)
    return SimpleNamespace(
        store=store,
        main_window_app=main_window_app,
        schedule_update=MagicMock(),
    )


def _stub_toasts(monkeypatch):
    for name in (
        "show_or_reuse_diff_toast",
        "complete_diff_toast",
        "dismiss_active_diff_toast",
        "update_diff_toast_progress",
    ):
        monkeypatch.setattr(diff_toasts, name, MagicMock())


def test_request_none_box_key_is_legacy_shape(monkeypatch):
    """No boxes → the exact 5-tuple key existing served entries use."""
    _stub_toasts(monkeypatch)
    presenter = _presenter()
    img1 = Image.new("RGB", (10, 10))
    img2 = Image.new("RGB", (10, 10))

    diff_cache.request_cached_diff_image_async(presenter, img1, img2, "ssim")

    assert presenter._pending_cached_diff_request_key == (
        "ssim",
        image_uid(img1),
        image_uid(img2),
        img1.size,
        img2.size,
    )


def test_request_box_change_recomputes(monkeypatch):
    """Same pair, different box → new request; same box → deduped."""
    _stub_toasts(monkeypatch)
    presenter = _presenter()
    img1 = Image.new("RGB", (10, 10))
    img2 = Image.new("RGB", (10, 10))
    start = presenter.main_window_app.thread_pool.start

    diff_cache.request_cached_diff_image_async(presenter, img1, img2, "ssim")
    assert start.call_count == 1
    # repeat unboxed: already pending → skipped
    diff_cache.request_cached_diff_image_async(presenter, img1, img2, "ssim")
    assert start.call_count == 1

    # boxed: box tuples ride the key → recomputes, not a stale-box hit
    diff_cache.request_cached_diff_image_async(
        presenter, img1, img2, "ssim", box1=BOX_T, box2=BOX_T
    )
    assert start.call_count == 2
    assert presenter._pending_cached_diff_request_key == (
        "ssim",
        image_uid(img1),
        image_uid(img2),
        img1.size,
        img2.size,
        (BOX_T, BOX_T),
    )
    # same boxes again → deduped
    diff_cache.request_cached_diff_image_async(
        presenter, img1, img2, "ssim", box1=BOX, box2=BOX
    )
    assert start.call_count == 2

    # a different box → recomputes again
    other = (0, 0, 5, 5)
    diff_cache.request_cached_diff_image_async(
        presenter, img1, img2, "ssim", box1=other, box2=other
    )
    assert start.call_count == 3


def test_request_boxed_served_key_skips(monkeypatch):
    """A served boxed key suppresses repeat requests for the same boxes."""
    _stub_toasts(monkeypatch)
    presenter = _presenter()
    img1 = Image.new("RGB", (10, 10))
    img2 = Image.new("RGB", (10, 10))
    served = (
        "ssim",
        image_uid(img1),
        image_uid(img2),
        img1.size,
        img2.size,
        (BOX_T, BOX_T),
    )
    presenter.store.viewport.session_data.render_cache.cached_diff_image = object()
    presenter.store.viewport.session_data.render_cache.cached_diff_source_key = served

    diff_cache.request_cached_diff_image_async(
        presenter, img1, img2, "ssim", box1=BOX_T, box2=BOX_T
    )

    presenter.main_window_app.thread_pool.start.assert_not_called()


# --------------------------------------------------------------------------
# ensure forwards boxes
# --------------------------------------------------------------------------


def _ensure_presenter():
    render_cache = SimpleNamespace(
        cached_diff_image=None,
        unification_in_progress=False,
    )
    session_data = SimpleNamespace(render_cache=render_cache)
    view_state = SimpleNamespace(diff_mode="ssim")
    viewport = SimpleNamespace(session_data=session_data, view_state=view_state)
    store = SimpleNamespace(viewport=viewport)
    return SimpleNamespace(store=store)


def test_ensure_forwards_boxes_to_async_request(monkeypatch):
    seen = {}

    def _record(presenter, s1, s2, mode, box1=None, box2=None):
        seen["box1"] = box1
        seen["box2"] = box2
        seen["mode"] = mode

    monkeypatch.setattr(
        diff_cache, "request_cached_diff_image_async", _record
    )
    presenter = _ensure_presenter()
    img1 = Image.new("RGB", (10, 10))
    img2 = Image.new("RGB", (10, 10))

    assert (
        diff_cache.ensure_cached_diff_image(
            presenter, img1, img2, box1=BOX_T, box2=BOX_T
        )
        is None
    )
    assert seen == {"box1": BOX_T, "box2": BOX_T, "mode": "ssim"}


def test_ensure_none_box_parity_forwards_nones(monkeypatch):
    seen = {}

    def _record(presenter, s1, s2, mode, box1=None, box2=None):
        seen["box1"] = box1
        seen["box2"] = box2

    monkeypatch.setattr(
        diff_cache, "request_cached_diff_image_async", _record
    )
    presenter = _ensure_presenter()
    img1 = Image.new("RGB", (10, 10))
    img2 = Image.new("RGB", (10, 10))

    diff_cache.ensure_cached_diff_image(presenter, img1, img2)
    assert seen == {"box1": None, "box2": None}
