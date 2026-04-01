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
        first_snap = editor_service.get_snapshot_at_time(0.0)
        if first_snap is None:
            raise RuntimeError("Missing initial snapshot")
        img1 = load_full_image(first_snap.image1_path, auto_crop=VIDEO_EDITOR_AUTO_CROP)
        img2 = load_full_image(first_snap.image2_path, auto_crop=VIDEO_EDITOR_AUTO_CROP)
        w1, h1 = img1.size if img1 else (0, 0)
        w2, h2 = img2.size if img2 else (0, 0)
        max_w = max(w1, w2)
        max_h = max(h1, h2)
        if max_w > 0 and max_h > 0:
            model.set_resolution(max_w, max_h)
            view.set_resolution(max_w, max_h)
    except Exception as exc:
        logger.error(f"Error calculating initial resolution: {exc}")

    return True
