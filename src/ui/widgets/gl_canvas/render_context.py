from __future__ import annotations

import logging
from dataclasses import dataclass

from OpenGL import GL as gl

logger = logging.getLogger("ImproveImgSLI")
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QImage
from PyQt6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
)

from .shaders import (
    MagnifierShaderVariantKey,
    build_base_fragment_shader,
    build_base_vertex_shader,
    build_circle_fragment_shader,
    build_circle_vertex_shader,
    build_magnifier_vertex_shader,
    build_magnifier_fragment_shader,
)
from .textures import (
    clear_magnifier_gpu,
    update_letterbox_geometry,
    upload_pil_images,
    upload_source_pil_image,
)

@dataclass(slots=True)
class GLViewportContext:
    width: int
    height: int
    zoom_level: float
    pan_offset_x: float
    pan_offset_y: float
    is_horizontal: bool
    split_position: float
    render_scene: object

@dataclass(slots=True)
class GLTextureContext:
    stored_pil_images: list
    source_texture_ids: list[int]
    texture_ids: list[int]
    source_images_ready: bool
    diff_source_ready: bool
    diff_source_texture_id: int
    shader_letterbox_mode: bool
    content_rect_px: tuple[int, int, int, int] | None
    clip_overlays_to_content_rect: bool
    images_uploaded: list[bool]

@dataclass(slots=True)
class GLMagnifierContext:
    capture_center: object
    capture_radius: float
    magnifier_centers: list
    magnifier_radius: float
    magnifier_border_width: float
    mag_quads: list
    mag_gpu_active: bool
    mag_gpu_slots: list
    mag_gpu_channel_mode: int
    mag_gpu_diff_mode: int
    mag_gpu_diff_threshold: float
    mag_gpu_interp_mode: int
    mag_combined_params: list
    magnifier_border_color: object

@dataclass(slots=True)
class GLOverlayContext:
    show_guides: bool
    guides_thickness: int
    laser_color: object
    capture_color: object
    divider_color: object
    divider_thickness: int
    show_divider: bool

@dataclass(slots=True)
class GLRenderRuntimeContext:
    viewport: GLViewportContext
    textures: GLTextureContext
    magnifier: GLMagnifierContext
    overlays: GLOverlayContext

    def __getattr__(self, name):
        for section in (self.viewport, self.textures, self.magnifier, self.overlays):
            if hasattr(section, name):
                return getattr(section, name)
        raise AttributeError(name)

def build_render_runtime_context(widget) -> GLRenderRuntimeContext:
    state = widget.runtime_state
    store = getattr(state, "_store", None)
    viewport = getattr(store, "viewport", None) if store is not None else None
    view_state = getattr(viewport, "view_state", None) if viewport is not None else None
    return GLRenderRuntimeContext(
        viewport=GLViewportContext(
            width=widget.width(),
            height=widget.height(),
            zoom_level=float(getattr(widget, "zoom_level", 1.0) or 1.0),
            pan_offset_x=float(getattr(widget, "pan_offset_x", 0.0) or 0.0),
            pan_offset_y=float(getattr(widget, "pan_offset_y", 0.0) or 0.0),
            is_horizontal=bool(
                getattr(view_state, "is_horizontal", getattr(widget, "is_horizontal", False))
            ),
            split_position=float(
                getattr(view_state, "split_position", getattr(widget, "split_position", 0.5))
                or 0.5
            ),
            render_scene=state._render_scene,
        ),
        textures=GLTextureContext(
            stored_pil_images=list(state._stored_pil_images),
            source_texture_ids=list(getattr(widget, "_source_texture_ids", [0, 0])),
            texture_ids=list(getattr(widget, "texture_ids", [0, 0])),
            source_images_ready=bool(state._source_images_ready),
            diff_source_ready=bool(state._diff_source_ready),
            diff_source_texture_id=int(getattr(widget, "_diff_source_texture_id", 0) or 0),
            shader_letterbox_mode=bool(state._shader_letterbox_mode),
            content_rect_px=state._content_rect_px,
            clip_overlays_to_content_rect=bool(state._clip_overlays_to_content_rect),
            images_uploaded=list(state._images_uploaded),
        ),
        magnifier=GLMagnifierContext(
            capture_center=state._capture_center,
            capture_radius=float(state._capture_radius or 0.0),
            magnifier_centers=list(state._magnifier_centers),
            magnifier_radius=float(state._magnifier_radius or 0.0),
            magnifier_border_width=float(state._magnifier_border_width or 2.0),
            mag_quads=list(state._mag_quads),
            mag_gpu_active=bool(state._mag_gpu_active),
            mag_gpu_slots=list(state._mag_gpu_slots),
            mag_gpu_channel_mode=int(state._mag_gpu_channel_mode or 0),
            mag_gpu_diff_mode=int(state._mag_gpu_diff_mode or 0),
            mag_gpu_diff_threshold=float(state._mag_gpu_diff_threshold or (20.0 / 255.0)),
            mag_gpu_interp_mode=(
                int(state._mag_gpu_interp_mode)
                if state._mag_gpu_interp_mode is not None
                else 1
            ),
            mag_combined_params=list(state._mag_combined_params),
            magnifier_border_color=state._magnifier_border_color,
        ),
        overlays=GLOverlayContext(
            show_guides=bool(state._show_guides),
            guides_thickness=int(state._guides_thickness or 0),
            laser_color=state._laser_color,
            capture_color=state._capture_color,
            divider_color=state._divider_color,
            divider_thickness=int(state._divider_thickness or 0),
            show_divider=bool(state._show_divider),
        ),
    )

def initialize_gl_resources(widget):
    state = widget.runtime_state

    ctx = widget.context()
    if ctx and ctx.isValid():
        fmt = ctx.format()
        is_gles = bool(ctx.isOpenGLES())
        logger.warning(
            "GL context created: version=%d.%d profile=%s gles=%s renderer=%s vendor=%s",
            fmt.majorVersion(), fmt.minorVersion(), fmt.profile(),
            is_gles, gl.glGetString(gl.GL_RENDERER), gl.glGetString(gl.GL_VENDOR),
        )
    else:
        logger.error(
            "initializeGL called without a valid context: ctx=%s valid=%s",
            ctx,
            ctx.isValid() if ctx is not None else False,
        )
        return

    is_gles = bool(ctx.isOpenGLES())

    widget.shader_program = QOpenGLShaderProgram()
    ok_vert = widget.shader_program.addShaderFromSourceCode(
        QOpenGLShader.ShaderTypeBit.Vertex, build_base_vertex_shader(is_gles)
    )
    ok_frag = widget.shader_program.addShaderFromSourceCode(
        QOpenGLShader.ShaderTypeBit.Fragment, build_base_fragment_shader(is_gles)
    )
    linked = widget.shader_program.link()
    if not (ok_vert and ok_frag and linked):
        logger.error("Base shader compile/link failed: %s", widget.shader_program.log())

    widget.vao = QOpenGLVertexArrayObject()
    widget.vao.create()
    widget.vao.bind()

    widget.vbo = QOpenGLBuffer()
    widget.vbo.create()
    widget.vbo.bind()
    widget.vbo.allocate(widget._quad_vertices.tobytes(), widget._quad_vertices.nbytes)

    widget.shader_program.enableAttributeArray(0)
    widget.shader_program.setAttributeBuffer(0, gl.GL_FLOAT, 0, 2, 4 * 4)
    widget.shader_program.enableAttributeArray(1)
    widget.shader_program.setAttributeBuffer(1, gl.GL_FLOAT, 2 * 4, 2, 4 * 4)

    widget.vbo.release()
    widget.vao.release()

    widget.texture_ids = list(gl.glGenTextures(2))
    widget._source_texture_ids = list(gl.glGenTextures(2))
    widget._diff_source_texture_id = int(gl.glGenTextures(1))

    for tex_id in widget.texture_ids + widget._source_texture_ids + [widget._diff_source_texture_id]:
        _configure_texture_parameters(tex_id)

    widget._mag_shader_cache = {}

    widget._mag_tex_ids = [int(t) for t in list(gl.glGenTextures(3))]
    widget._mag_combined_tex_ids = [int(t) for t in list(gl.glGenTextures(3))]
    widget._mag_tex_id = widget._mag_tex_ids[0]
    for texture_id in widget._mag_tex_ids + widget._mag_combined_tex_ids:
        _configure_texture_parameters(texture_id)

    widget._circle_mask_tex_id = int(gl.glGenTextures(1))
    _configure_texture_parameters(widget._circle_mask_tex_id)
    _load_circle_mask_assets(widget, state)

    widget._circle_shader = QOpenGLShaderProgram()
    ok_vert2 = widget._circle_shader.addShaderFromSourceCode(
        QOpenGLShader.ShaderTypeBit.Vertex, build_circle_vertex_shader(is_gles)
    )
    ok_frag2 = widget._circle_shader.addShaderFromSourceCode(
        QOpenGLShader.ShaderTypeBit.Fragment, build_circle_fragment_shader(is_gles)
    )
    linked2 = widget._circle_shader.link()
    if not (ok_vert2 and ok_frag2 and linked2):
        logger.error("Circle shader compile/link failed: %s", widget._circle_shader.log())

    widget._guides_tex_id = int(gl.glGenTextures(1))
    _configure_texture_parameters(widget._guides_tex_id)

    widget._ui_overlay_tex_id = int(gl.glGenTextures(1))
    _configure_texture_parameters(widget._ui_overlay_tex_id)

def get_magnifier_shader_program(widget, key: MagnifierShaderVariantKey) -> QOpenGLShaderProgram:
    cache = getattr(widget, "_mag_shader_cache", None)
    if cache is None:
        cache = {}
        widget._mag_shader_cache = cache

    program = cache.get(key)
    if program is not None and program.isLinked():
        return program

    program = QOpenGLShaderProgram()
    context = widget.context()
    is_gles = bool(context.isOpenGLES()) if context is not None and context.isValid() else False
    if not program.addShaderFromSourceCode(
        QOpenGLShader.ShaderTypeBit.Vertex, build_magnifier_vertex_shader(is_gles)
    ):
        raise RuntimeError(program.log())
    if not program.addShaderFromSourceCode(
        QOpenGLShader.ShaderTypeBit.Fragment, build_magnifier_fragment_shader(key, is_gles=is_gles)
    ):
        raise RuntimeError(program.log())
    if not program.link():
        raise RuntimeError(program.log())
    cache[key] = program
    return program

def resize_gl(widget, w: int, h: int):
    state = widget.runtime_state
    dpr = widget.devicePixelRatioF()
    logger.warning(
        "resizeGL: w=%d h=%d | widget.width=%d widget.height=%d | dpr=%.2f",
        w, h, widget.width(), widget.height(), dpr,
    )
    gl.glViewport(0, 0, w, h)
    widget._update_paste_overlay_rects()
    clear_magnifier_gpu(widget)
    if getattr(state._render_scene, "render_magnifiers", False):
        QTimer.singleShot(0, widget._emit_viewport_state_change)
    img1, img2 = state._stored_pil_images
    if state._shader_letterbox_mode and img1 is not None:
        update_letterbox_geometry(widget, img1, slot_index=0)
    elif img1 is not None:
        upload_pil_images(
            widget,
            img1,
            img2,
            source_image1=None,
            source_image2=None,
            source_key=None,
            shader_letterbox=False,
        )
        return
    if state._shader_letterbox_mode and img2 is not None:
        update_letterbox_geometry(widget, img2, slot_index=1)
    elif img2 is not None:
        state._letterbox_params[1] = (0.0, 0.0, 1.0, 1.0)
    widget.update()

def request_update(widget):
    state = widget.runtime_state
    if state._update_batch_depth > 0:
        state._update_pending = True
        return
    widget.update()

def emit_viewport_state_change(widget):
    store = widget.runtime_state._store
    if store is not None and hasattr(store, "emit_state_change"):
        store.emit_viewport_change("geometry")

def schedule_source_preload(widget):
    state = widget.runtime_state
    if state._source_preload_scheduled:
        return
    state._source_preload_scheduled = True
    QTimer.singleShot(0, lambda: preload_source_textures(widget))

def preload_source_textures(widget):
    state = widget.runtime_state
    state._source_preload_scheduled = False
    img1, img2 = state._source_pil_images
    if not img1 and not img2:
        state._source_images_ready = False
        return

    try:
        if img1 is not None:
            upload_source_pil_image(widget, img1, 0)
        if img2 is not None:
            upload_source_pil_image(widget, img2, 1)

        gl.glFinish()
        state._source_images_ready = True
        if (
            state._store is not None
            and hasattr(state._store, "emit_state_change")
            and getattr(state._render_scene, "render_magnifiers", False)
        ):
            state._store.emit_viewport_change("geometry")
    except Exception:
        state._source_images_ready = False
    request_update(widget)

def begin_update_batch(widget):
    widget.runtime_state._update_batch_depth += 1

def end_update_batch(widget):
    state = widget.runtime_state
    if state._update_batch_depth <= 0:
        state._update_batch_depth = 0
        return
    state._update_batch_depth -= 1
    if state._update_batch_depth == 0 and state._update_pending:
        state._update_pending = False
        widget.update()

def _configure_texture_parameters(texture_id: int):
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)

def _load_circle_mask_assets(widget, state):
    try:
        from PIL import Image as _PilImage
        from PyQt6.QtGui import QImage as _QImage

        from utils.resource_loader import resource_path

        mask_img_raw = _PilImage.open(resource_path("resources/assets/circle_mask.png"))
        if "A" in mask_img_raw.getbands():
            mask_img = mask_img_raw.getchannel("A")
        else:
            from PIL import ImageOps as _ImageOps

            mask_img = _ImageOps.invert(mask_img_raw.convert("L"))
        mask_w, mask_h = mask_img.size
        mask_raw = mask_img.tobytes("raw", "L")
        gl.glTexImage2D(
            gl.GL_TEXTURE_2D,
            0,
            gl.GL_R8,
            mask_w,
            mask_h,
            0,
            gl.GL_RED,
            gl.GL_UNSIGNED_BYTE,
            mask_raw,
        )
        mask_rgba = mask_img_raw.convert("RGBA")
        state._circle_mask_overlay_image = _QImage(
            mask_rgba.tobytes("raw", "RGBA"),
            mask_rgba.width,
            mask_rgba.height,
            _QImage.Format.Format_RGBA8888,
        ).copy()
        mask_shadow_rgba = _PilImage.new("RGBA", mask_img.size, (0, 0, 0, 0))
        mask_shadow_rgba.putalpha(mask_img)
        state._circle_mask_shadow_image = _QImage(
            mask_shadow_rgba.tobytes("raw", "RGBA"),
            mask_shadow_rgba.width,
            mask_shadow_rgba.height,
            _QImage.Format.Format_RGBA8888,
        ).copy()
        state._circle_mask_shadow_cache.clear()
    except Exception:
        state._circle_mask_overlay_image = None
        state._circle_mask_shadow_image = None
