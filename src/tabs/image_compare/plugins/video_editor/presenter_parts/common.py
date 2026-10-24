VIDEO_EDITOR_AUTO_CROP = False

def first_snapshot_from_source(source):
    if source is None:
        return None
    if isinstance(source, (list, tuple)):
        return source[0] if source else None
    if hasattr(source, "evaluate_at"):
        try:
            return source.evaluate_at(0.0)
        except Exception:
            return None
    return None

def resolve_initial_fps(view, snapshots, main_controller) -> int:
    first_snapshot = first_snapshot_from_source(snapshots)
    if first_snapshot and hasattr(first_snapshot, "settings_state"):
        snapshot_fps = getattr(first_snapshot.settings_state, "video_recording_fps", None)
        if snapshot_fps:
            return snapshot_fps

    if main_controller and getattr(main_controller, "store", None):
        return getattr(main_controller.store.settings, "video_recording_fps", 60)

    export_controller = getattr(view, "export_controller", None)
    if export_controller and getattr(export_controller, "store", None):
        return getattr(export_controller.store.settings, "video_recording_fps", 60)

    return 60

def default_downloads_dir() -> str:
    # Single implementation lives with the export state; imported lazily so
    # this module stays free of the export-service import graph at load time.
    from tabs.image_compare.services.image_export.state import (
        default_downloads_dir as _resolve_default_downloads_dir,
    )

    return _resolve_default_downloads_dir()
