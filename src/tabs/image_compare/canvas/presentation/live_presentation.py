from __future__ import annotations

from shared.rendering.display_image_picker import pick_first_real
from shared.rendering.image_identity import image_uid
from ui.canvas_presentation.models import PresentationImageSet, SnapshotStorePresentation

def build_live_store_presentation(store) -> SnapshotStorePresentation:
    cache = store.viewport.session_data.render_cache
    document = store.get_session_state_slot("document")
    display_image1 = pick_first_real(
        cache.display_cache_image1,
        cache.scaled_image1_for_display,
        store.viewport.session_data.image_state.image1,
        document.preview_image1,
    )
    display_image2 = pick_first_real(
        cache.display_cache_image2,
        cache.scaled_image2_for_display,
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

    source_key = (
        document.image1_path,
        document.image2_path,
        image_uid(source_image1),
        image_uid(source_image2),
        source_image1.size if source_image1 is not None else None,
        source_image2.size if source_image2 is not None else None,
    )
    display_cache_key = (
        image_uid(display_image1),
        image_uid(display_image2),
        display_image1.size if display_image1 is not None else None,
        display_image2.size if display_image2 is not None else None,
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

