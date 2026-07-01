from __future__ import annotations

from plugins.video_editor.services.keyframing.types import FrameSnapshot


def _get_path_at_index(items, index):
    if 0 <= index < len(items):
        try:
            item = items[index]
            if hasattr(item, "path"):
                return item.path
            if isinstance(item, (list, tuple)) and len(item) > 1:
                return item[1]
        except (IndexError, TypeError, AttributeError):
            return None
    return None


def build_live_frame_snapshot(store) -> FrameSnapshot:
    document = store.document
    image1_path = getattr(document, "image1_path", None) or _get_path_at_index(
        getattr(document, "image_list1", ()),
        int(getattr(document, "current_index1", 0) or 0),
    )
    image2_path = getattr(document, "image2_path", None) or _get_path_at_index(
        getattr(document, "image_list2", ()),
        int(getattr(document, "current_index2", 0) or 0),
    )
    return FrameSnapshot(
        timestamp=0.0,
        viewport_state=store.viewport.freeze_for_export(),
        settings_state=store.settings.freeze_for_export(),
        image1_path=image1_path,
        image2_path=image2_path,
        name1=document.get_current_display_name(1),
        name2=document.get_current_display_name(2),
    )
