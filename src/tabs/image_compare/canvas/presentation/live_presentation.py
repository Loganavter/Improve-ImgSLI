from __future__ import annotations

from shared.rendering.display_image_picker import pick_display_image, pick_first_real
from shared.rendering.image_identity import image_uid
from shared.image_processing.tiled_pixel_store import autocrop_debug
from ui.canvas_presentation.models import PresentationImageSet, SnapshotStorePresentation

def build_live_store_presentation(store) -> SnapshotStorePresentation:
    document = store.get_session_state_slot("document")
    display_image1 = pick_display_image(
        store.viewport.session_data.image_state.image1,
        document.preview_image1,
    )
    display_image2 = pick_display_image(
        store.viewport.session_data.image_state.image2,
        document.preview_image2,
    )
    # The live high-resolution source pair must use the same unified canvas
    # coordinate system as the display pair. Document full-res images may have
    # different dimensions; binding them directly makes each side use a
    # different letterbox transform after zooming.
    source_image1 = (
        store.viewport.session_data.image_state.image1
        or document.full_res_image1
        or document.preview_image1
        or document.original_image1
    )
    source_image2 = (
        store.viewport.session_data.image_state.image2
        or document.full_res_image2
        or document.preview_image2
        or document.original_image2
    )

    if display_image1 is None and source_image1 is not None:
        display_image1 = pick_first_real(source_image1)
    if display_image2 is None and source_image2 is not None:
        display_image2 = pick_first_real(source_image2)

    def _size(img):
        if img is None:
            return None
        # QImage.size is a method, TiledPixelStore.size is a tuple property
        try:
            from shared.image_processing.tiled_pixel_store import TiledPixelStore
            from PySide6.QtGui import QImage, QPixmap

            if isinstance(img, TiledPixelStore):
                return img.size
            if isinstance(img, (QImage, QPixmap)):
                s = img.size()
                return (s.width(), s.height())
        except Exception:
            pass
        # Fallback: _size_or_none style
        try:
            sz = getattr(img, "size", None)
            if callable(sz):
                s = sz()
                try:
                    return (s.width(), s.height())
                except Exception:
                    return s
            return sz
        except Exception:
            return None

    def _kind(img):
        return (type(img).__name__, _size(img)) if img is not None else None

    autocrop_debug(
        "presentation paths=%s | %s sources=%s | %s displays=%s | %s",
        document.image1_path,
        document.image2_path,
        _kind(source_image1),
        _kind(source_image2),
        _kind(display_image1),
        _kind(display_image2),
    )

    source_key = (
        document.image1_path,
        document.image2_path,
        image_uid(source_image1),
        image_uid(source_image2),
        _size(source_image1),
        _size(source_image2),
    )
    display_cache_key = (
        image_uid(display_image1),
        image_uid(display_image2),
        _size(display_image1),
        _size(display_image2),
    )

    return SnapshotStorePresentation(
        store=store,
        images=PresentationImageSet(
            display_image1=display_image1,
            display_image2=display_image2,
            source_image1=source_image1 or display_image1,
            source_image2=source_image2 or display_image2,
            source_key=source_key,
            display_cache_key=display_cache_key,
        ),
        virtual_layout=None,
    )

