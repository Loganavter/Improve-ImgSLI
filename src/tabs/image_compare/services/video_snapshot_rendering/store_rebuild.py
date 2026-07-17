"""Build a transient Store for one snapshot frame."""

from __future__ import annotations

from tabs.image_compare.services.video_snapshot_rendering.models import ImagePrepCacheEntry


def rebuild_snapshot_store(
    snap,
    entry: ImagePrepCacheEntry,
    fit_content,
    scaled_global_bounds,
    normalize_snapshot_store_enabled,
):
    from core.store import Store
    from tabs.image_compare.state.document import DocumentModel, ImageItem
    from tabs.image_compare.canvas.registry import registry

    store = Store()
    # `resolve_feature_virtual_layout` (invoked via SnapshotRenderPlanBuilder
    # below) looks up the canvas feature registry keyed by the active
    # session's `session_type`; the default session `Store()` creates is
    # "session_picker", which has no registered features, so it must be
    # switched to an "image_compare" session before any layout-dependent
    # feature (e.g. magnifier) can be resolved.
    store.create_workspace_session(session_type="image_compare", activate=True)
    store.set_session_state_slot("document", DocumentModel())
    store.viewport = snap.viewport_state.clone()
    store.settings = snap.settings_state.freeze_for_export()
    store.runtime_cache.overlay_clip_rect = None

    normalize_snapshot = registry().get_feature_command_by_alias("overlay.snapshot_normalize")
    if (
        normalize_snapshot_store_enabled
        and normalize_snapshot is not None
        and not (fit_content and scaled_global_bounds is not None)
    ):
        normalize_snapshot(store)

    store.viewport.session_data.image_state.image1 = entry.display_img1
    store.viewport.session_data.image_state.image2 = entry.display_img2
    document = store.get_session_state_slot("document")
    document.image1_path = getattr(snap, "image1_path", None)
    document.image2_path = getattr(snap, "image2_path", None)
    document.image_list1 = [
        ImageItem(
            image=entry.source_img1,
            path=getattr(snap, "image1_path", None) or "",
            display_name=getattr(snap, "name1", None) or "",
        )
    ]
    document.image_list2 = [
        ImageItem(
            image=entry.source_img2,
            path=getattr(snap, "image2_path", None) or "",
            display_name=getattr(snap, "name2", None) or "",
        )
    ]
    document.current_index1 = 0 if document.image_list1 else -1
    document.current_index2 = 0 if document.image_list2 else -1
    document.original_image1 = entry.source_img1
    document.original_image2 = entry.source_img2
    document.full_res_image1 = entry.source_img1
    document.full_res_image2 = entry.source_img2
    store.viewport.interaction_state.is_interactive_mode = False
    store.viewport.geometry_state.pixmap_width = entry.render_w
    store.viewport.geometry_state.pixmap_height = entry.render_h

    if fit_content and scaled_global_bounds is not None:
        apply_virtual_layout = registry().get_feature_command_by_alias(
            "overlay.snapshot_apply_virtual_layout"
        )
        if apply_virtual_layout is not None:
            apply_virtual_layout(
                store,
                base_w=int(scaled_global_bounds.base_width),
                base_h=int(scaled_global_bounds.base_height),
                virtual_layout=scaled_global_bounds.to_virtual_layout(),
            )

    return store
