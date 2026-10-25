import itertools
import logging
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

_TEXTURE_ID_SEQ = itertools.count(start=10_000)


def gen_texture_ids(count: int) -> list[int]:
    return [next(_TEXTURE_ID_SEQ) for _ in range(count)]


def ensure_feature_overlay_slot_capacity(widget, count: int):
    state = widget.runtime_state
    overlay = state._feature_overlay_gpu
    if count <= 0:
        return

    current = len(widget._feature_overlay_tex_ids)
    if count > current:
        additional = count - current
        new_tex_ids = gen_texture_ids(additional)
        new_aux_ids = gen_texture_ids(additional)
        widget._feature_overlay_tex_ids.extend(new_tex_ids)
        widget._feature_overlay_aux_tex_ids.extend(new_aux_ids)
        if widget._feature_overlay_tex_ids:
            widget._feature_overlay_tex_id = widget._feature_overlay_tex_ids[0]

    while len(overlay._quads) < count:
        overlay._quads.append(None)
    while len(overlay._use_circle_mask) < count:
        overlay._use_circle_mask.append(False)
    while len(overlay._gpu_slots) < count:
        overlay._gpu_slots.append(None)


def set_texture_filter(widget, texture_id: int, canvas_filter: int):
    """No-op in the QRhi pipeline (filtering is per-sampler in the SRB)."""
    return
