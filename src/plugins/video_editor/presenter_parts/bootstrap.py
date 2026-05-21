import logging

from shared.image_processing.progressive_loader import load_full_image

from .common import VIDEO_EDITOR_AUTO_CROP

logger = logging.getLogger("ImproveImgSLI")

def initialize_editor_from_snapshots(view, editor_service, playback_engine, model):
    recording = editor_service.get_current_recording()
    if not recording or view is None:
        return False

    view.set_snapshots(
        [],
        fps=editor_service.get_fps(),
        timeline_model=recording.timeline,
        duration=editor_service.get_duration(),
    )

    total_frames = editor_service.get_frame_count()
    playback_engine.set_total_frames(total_frames)
    playback_engine.set_range(0, total_frames - 1)

    try:
        max_w, max_h = 0, 0
        seen_paths: set[str] = set()
        snapshots = editor_service.get_current_snapshots()
        for snap in snapshots:
            for path in (snap.image1_path, snap.image2_path):
                if not path or path in seen_paths:
                    continue
                seen_paths.add(path)
                img = load_full_image(path, auto_crop=VIDEO_EDITOR_AUTO_CROP)
                if img:
                    max_w = max(max_w, img.size[0])
                    max_h = max(max_h, img.size[1])
        if not snapshots:
            first_snap = editor_service.get_snapshot_at_time(0.0)
            if first_snap is not None:
                for path in (first_snap.image1_path, first_snap.image2_path):
                    img = load_full_image(path, auto_crop=VIDEO_EDITOR_AUTO_CROP)
                    if img:
                        max_w = max(max_w, img.size[0])
                        max_h = max(max_h, img.size[1])
        if max_w > 0 and max_h > 0:
            model.set_resolution(max_w, max_h)
            view.set_resolution(max_w, max_h)
    except Exception as exc:
        logger.error(f"Error calculating initial resolution: {exc}")

    return True
