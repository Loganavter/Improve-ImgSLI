from __future__ import annotations

from .models import PresentationImageSet, SnapshotStorePresentation

def build_live_store_presentation(store) -> SnapshotStorePresentation:
    cache = store.viewport.session_data.render_cache
    display_image1 = (
        cache.display_cache_image1
        or cache.scaled_image1_for_display
        or store.viewport.session_data.image_state.image1
    )
    display_image2 = (
        cache.display_cache_image2
        or cache.scaled_image2_for_display
        or store.viewport.session_data.image_state.image2
    )
    source_image1 = store.document.full_res_image1 or store.document.original_image1
    source_image2 = store.document.full_res_image2 or store.document.original_image2

    source_key = (
        store.document.image1_path,
        store.document.image2_path,
        id(source_image1) if source_image1 is not None else 0,
        id(source_image2) if source_image2 is not None else 0,
        source_image1.size if source_image1 is not None else None,
        source_image2.size if source_image2 is not None else None,
    )
    display_cache_key = (
        id(display_image1) if display_image1 is not None else 0,
        id(display_image2) if display_image2 is not None else 0,
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
    )
