"""The preview tier and the store tier must agree on the cropped envelope.

Rule (b) — the envelope is built from SOURCE dims + the effective crop box
(``envelope_source_size``), never from the tier's own dims.

Why the tiers disagreed before: the preview tier decodes FULL-FRAME and
boxless (``pipeline/cache`` W1+W2 — a box is side metadata, never baked into
the decode), while a display/store tier produced by ``upload_pil_images`` is
already box-clipped. Fed back through the box, the pre-clipped tier got
double-clipped (1440x1056 → 1440x1033, aspect 1.394) and the boxless preview
kept the uncropped 4:3 aspect (1024x768), so the first preview frame showed a
different letterbox than the store frame one tick later. Both tiers now yield
the source frame clipped by the box (1440x1056), so the flip changes nothing
visually.

Asserts computed rects (not pixels): the two frames' ``image_display_rect_on_label``
and the envelope the store path itself would produce.
"""

from __future__ import annotations

from types import SimpleNamespace

from PIL import Image

from engine.cache.unified_envelope import eager_envelope_rect
from tabs.image_compare.presenters.image_canvas.background_parts.use_cases.geometry import (
    envelope_source_size,
    update_comparison_geometry,
)

SOURCE = (1440, 1080)  # original file
BOX = (0, 0, 1440, 1056)  # detected crop: 24px of uniform border at the bottom
PREVIEW = (1024, 768)  # boxless preview tier (full-frame, 4:3)
CLIPPED_DISPLAY = (1440, 1056)  # display tier after upload_pil_images clipping
LABEL = (1200, 900)


class _WarmedService:
    """Warmed CropService fake: cached, serves the same box for any path."""

    def __init__(self, box):
        self._box = box

    def _has_cached(self, path):
        return True

    def get(self, path):
        return self._box


def _source_png(tmp_path, name, size=SOURCE):
    """Real file so the header probe reports the source dims."""
    path = tmp_path / name
    Image.new("RGB", size, (30, 30, 30)).save(str(path))
    return str(path)


def _presenter(document, *, state1, state2, service, geometry_state):
    store = SimpleNamespace(
        viewport=SimpleNamespace(
            session_data=SimpleNamespace(
                image_state=SimpleNamespace(image1=state1, image2=state2)
            ),
            geometry_state=geometry_state,
        ),
        get_session_state_slot=lambda key: document if key == "document" else None,
        get_dispatcher=lambda: None,
    )
    return SimpleNamespace(
        store=store,
        session_controller=SimpleNamespace(_get_crop_service=lambda: service),
    )


def _frame_rect(document, *, state1, state2, source1, source2, service):
    """Run one geometry frame and return its computed letterbox rect."""
    geometry_state = SimpleNamespace(
        pixmap_width=0, pixmap_height=0, image_display_rect_on_label=None
    )
    presenter = _presenter(
        document, state1=state1, state2=state2, service=service,
        geometry_state=geometry_state,
    )
    update_comparison_geometry(presenter, source1, source2, LABEL[0], LABEL[1])
    rect = geometry_state.image_display_rect_on_label
    assert rect is not None, "geometry never produced a rect"
    return (rect.x, rect.y, rect.w, rect.h)


def _document(p1, p2):
    return SimpleNamespace(image1_path=p1, image2_path=p2)


# -- the resolver --------------------------------------------------------------


def test_envelope_source_size_uses_source_dims_not_the_tier(tmp_path):
    p1 = _source_png(tmp_path, "a.png")
    svc = _WarmedService(BOX)
    # Preview tier (boxless, 4:3) and display tier (already clipped) resolve to
    # the same source+crop dims.
    assert envelope_source_size(p1, svc, PREVIEW) == (1440, 1056)
    assert envelope_source_size(p1, svc, CLIPPED_DISPLAY) == (1440, 1056)


def test_envelope_source_size_without_crop_is_the_source_frame(tmp_path):
    p1 = _source_png(tmp_path, "a.png")
    assert envelope_source_size(p1, _WarmedService(None), PREVIEW) == SOURCE
    # Full-frame box == no crop (sanitize parity).
    assert envelope_source_size(p1, _WarmedService(SOURCE + (0, 0)), PREVIEW) == SOURCE


def test_envelope_source_size_off_override_skips_detection(tmp_path):
    p1 = _source_png(tmp_path, "a.png")
    assert envelope_source_size(p1, _WarmedService(BOX), PREVIEW, override=False) == SOURCE


def test_envelope_source_size_falls_back_to_live_dims_without_a_probe():
    # No file behind the pixels (embedded/project-cache source): the live tier
    # stays the reference and the boxed dims are sanitized against it.
    assert envelope_source_size("/nonexistent/fake.png", _WarmedService(BOX), PREVIEW) == PREVIEW
    assert envelope_source_size("/nonexistent/fake.png", None, PREVIEW) == PREVIEW


# -- red-before: the two tiers disagreed ---------------------------------------


def test_cropped_preview_and_store_frames_letterbox_identically(tmp_path):
    """The bug: the preview frame letterboxed differently than the store frame.

    Before the fix this compared a boxless 1024x768 preview (4:3 envelope,
    1200x900) against a pre-clipped 1440x1056 display tier re-clipped to
    1440x1033 (1200x861) — two different rects for one document.
    """
    p1 = _source_png(tmp_path, "a.png")
    svc = _WarmedService(BOX)
    document = _document(p1, p1)
    preview_img = Image.new("RGBA", PREVIEW, (200, 40, 40))
    clipped_img = Image.new("RGBA", CLIPPED_DISPLAY, (40, 200, 40))

    # Frame 1: only the preview tier exists (image_state still empty).
    preview_rect = _frame_rect(
        document, state1=None, state2=None,
        source1=preview_img, source2=preview_img, service=svc,
    )
    # Frame 2: the store/display tier took over.
    store_rect = _frame_rect(
        document, state1=clipped_img, state2=clipped_img,
        source1=clipped_img, source2=clipped_img, service=svc,
    )

    assert preview_rect == store_rect
    # ... and both are the store path's own source+crop envelope, not 4:3.
    _lb, expected = eager_envelope_rect(
        LABEL[0], LABEL[1], [(1440, 1056), (1440, 1056)]
    )
    assert preview_rect == expected
    _lb_full, full_rect = eager_envelope_rect(LABEL[0], LABEL[1], [SOURCE, SOURCE])
    assert preview_rect != full_rect


# -- no regression for the common (uncropped) case ----------------------------


def test_uncropped_preview_and_store_frames_are_unchanged(tmp_path):
    p1 = _source_png(tmp_path, "a.png")
    document = _document(p1, p1)
    preview_img = Image.new("RGBA", PREVIEW, (200, 40, 40))
    store_img = Image.new("RGBA", SOURCE, (40, 200, 40))

    preview_rect = _frame_rect(
        document, state1=None, state2=None,
        source1=preview_img, source2=preview_img, service=_WarmedService(None),
    )
    store_rect = _frame_rect(
        document, state1=store_img, state2=store_img,
        source1=store_img, source2=store_img, service=_WarmedService(None),
    )

    _lb, expected = eager_envelope_rect(LABEL[0], LABEL[1], [SOURCE, SOURCE])
    assert preview_rect == store_rect == expected
    # Same aspect as the legacy tier-dims envelope (preview 1024x768 is 4:3
    # too), so nothing moves for the uncropped document.
    _lb_legacy, legacy_rect = eager_envelope_rect(
        LABEL[0], LABEL[1], [PREVIEW, PREVIEW]
    )
    assert preview_rect == legacy_rect
