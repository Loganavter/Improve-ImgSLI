from __future__ import annotations

from shared.rendering.display_image_picker import pick_display_image, pick_first_real
from shared.rendering.image_identity import image_uid
from shared.image_processing.tiled_pixel_store import autocrop_debug
from ui.canvas_presentation.models import PresentationImageSet, SnapshotStorePresentation

def _peek_slot(store, slot: int):
    doc = store.get_session_state_slot("document")
    path = doc.image1_path if slot == 1 else doc.image2_path
    if not path:
        return None
    try:
        vp = store.viewport.session_data.image_state
        cand = vp.image1 if slot == 1 else vp.image2
        if cand is not None and getattr(cand, "is_open", True):
            try:
                if hasattr(cand, "isNull") and cand.isNull():
                    cand = None
                elif hasattr(cand, "is_open") and not cand.is_open:
                    cand = None
            except Exception:
                pass
            if cand is not None:
                return cand
    except Exception:
        pass
    try:
        ps = store.get_session_state_slot("pipeline")
        if ps is not None:
            import os

            from tabs.image_compare.pipeline.cache import _pixel_key, _preview_key

            for cache_dict, key_fn in ((ps.pixel, _pixel_key), (ps.preview, _preview_key)):
                try:
                    k = key_fn(path, None, None)
                    v = cache_dict.get(k)
                    if v is not None:
                        if hasattr(v, "is_open") and not v.is_open:
                            continue
                        if hasattr(v, "isNull") and v.isNull():
                            continue
                        return v
                except Exception:
                    pass
                try:
                    norm = os.path.normpath(path)
                    for kk, vv in cache_dict.items():
                        if kk[0] == norm:
                            if hasattr(vv, "is_open") and not vv.is_open:
                                continue
                            if hasattr(vv, "isNull") and vv.isNull():
                                continue
                            return vv
                except Exception:
                    pass
    except Exception:
        pass
    return None


def build_live_store_presentation(store) -> SnapshotStorePresentation:
    document = store.get_session_state_slot("document")
    p1 = _peek_slot(store, 1)
    p2 = _peek_slot(store, 2)
    display_image1 = pick_display_image(
        store.viewport.session_data.image_state.image1,
        p1,
    )
    display_image2 = pick_display_image(
        store.viewport.session_data.image_state.image2,
        p2,
    )
    # PipelineView is single source — preview via cache, not document fields
    source_image1 = store.viewport.session_data.image_state.image1 or p1
    source_image2 = store.viewport.session_data.image_state.image2 or p2

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

