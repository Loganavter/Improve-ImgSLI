import logging

from OpenGL import GL as gl

logger = logging.getLogger("ImproveImgSLI")

def gen_texture_ids(count: int) -> list[int]:
    generated = gl.glGenTextures(count)
    if count == 1:
        return [int(generated)]
    return [int(texture_id) for texture_id in generated]

def configure_dynamic_texture(texture_id: int):
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)

def ensure_magnifier_slot_capacity(widget, count: int):
    state = widget.runtime_state
    if count <= 0:
        return

    current = len(widget._mag_tex_ids)
    if count > current:
        widget.makeCurrent()
        additional = count - current
        new_tex_ids = gen_texture_ids(additional)
        new_combined_ids = gen_texture_ids(additional)
        for texture_id in new_tex_ids + new_combined_ids:
            configure_dynamic_texture(texture_id)
        widget._mag_tex_ids.extend(new_tex_ids)
        widget._mag_combined_tex_ids.extend(new_combined_ids)
        if widget._mag_tex_ids:
            widget._mag_tex_id = widget._mag_tex_ids[0]

    while len(state._mag_quads) < count:
        state._mag_quads.append(None)
    while len(state._mag_use_circle_mask) < count:
        state._mag_use_circle_mask.append(False)
    while len(state._mag_combined_params) < count:
        state._mag_combined_params.append(None)
    while len(state._mag_gpu_slots) < count:
        state._mag_gpu_slots.append(None)

def upload_pil_to_texture_id(widget, pil_image, texture_id: int, slot_index: int | None = None):
    if pil_image is None or not texture_id:
        return

    img = pil_image.convert("RGBA")
    raw = img.tobytes("raw", "RGBA")
    state = widget.runtime_state
    state._pending_texture_uploads.append((raw, img.width, img.height, texture_id, slot_index))
    if slot_index is not None and 0 <= slot_index < len(state._images_uploaded):
        state._images_uploaded[slot_index] = True

def set_texture_filter(widget, texture_id: int, gl_filter: int):
    if not texture_id:
        return
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl_filter)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl_filter)
