from __future__ import annotations

import logging
from dataclasses import dataclass

from OpenGL import GL as gl

logger = logging.getLogger("ImproveImgSLI")
from PyQt6.QtCore import QTimer
from PyQt6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
)

from .shader_sources.base import (
    build_base_fragment_shader,
    build_base_vertex_shader,
)
from .render_common import widget_px_to_screen_px
from .render_config import update_display_split_position
from ui.canvas_presentation.render_arch import (
    BaseImagePrimitive,
    RenderIntent,
    RenderList,
    ResolvedCanvasStyle,
    SceneFrame,
    build_render_list,
    build_render_intent,
    build_scene_frame,
    resolve_canvas_style,
)
from .render_metrics import RenderMetrics, resolve_screen_px
from ui.canvas_infra.scene.widget_registry import (
    apply_canvas_feature_live_runtime_overlays,
    has_canvas_feature_live_runtime_overlays,
)
from ui.canvas_infra.viewport.state import (
    get_pan_offset_x,
    get_pan_offset_y,
    get_zoom_level,
)
from .texture_parts.base_images import (
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
class GLFeatureOverlayContext:
    widget: object
    render_enabled: bool
    clip_to_content: bool
    border_color: object | None
    border_width: float
    quads: tuple[object, ...]
    gpu_active: bool
    gpu_slots: tuple[object, ...]
    gpu_channel_mode: int
    gpu_diff_mode: int
    gpu_diff_threshold: float
    gpu_interp_mode: int
    combined_params: tuple[object, ...]
    occluded_capture_arcs: tuple[object, ...]
    hidden_capture_circles: tuple[object, ...]
    hidden_overlay_circles: tuple[object, ...]

@dataclass(slots=True)
class GLMetricsContext:
    render_metrics: RenderMetrics
    render_intent: RenderIntent
    resolved_style: ResolvedCanvasStyle
    scene_frame: SceneFrame
    render_list: RenderList

@dataclass(slots=True)
class GLRenderRuntimeContext:
    viewport: GLViewportContext
    textures: GLTextureContext
    feature_overlay: GLFeatureOverlayContext
    metrics: GLMetricsContext

    def __getattr__(self, name):
        for section in (self.viewport, self.textures, self.feature_overlay, self.metrics):
            if hasattr(section, name):
                return getattr(section, name)
        raise AttributeError(name)

def build_render_runtime_context(widget) -> GLRenderRuntimeContext:
    state = widget.runtime_state
    store = getattr(state, "_store", None)
    viewport = getattr(store, "viewport", None) if store is not None else None
    view_state = getattr(viewport, "view_state", None) if viewport is not None else None
    plan = getattr(widget, "_active_render_plan", None)
    object_name = str(getattr(widget, "objectName", lambda: "")() or "")
    read_only = bool(getattr(state, "_read_only", False))
    mode = (
        "export"
        if object_name == "gpu_export_canvas"
        else "preview"
        if read_only or store is None
        else "interactive"
    )
    inner_rect = getattr(state, "_inner_content_rect_px", None)
    if inner_rect is not None:
        content_rect_px = (
            int(inner_rect[0]),
            int(inner_rect[1]),
            int(inner_rect[2]),
            int(inner_rect[3]),
        )
        split_override = getattr(state, "_inner_split_position", None)
    else:
        content_rect = state._content_rect_px or (0, 0, widget.width(), widget.height())
        content_rect_px = (
            int(content_rect[0]),
            int(content_rect[1]),
            int(content_rect[2]),
            int(content_rect[3]),
        )
        split_override = None
    render_metrics = RenderMetrics(
        canvas_to_view=float(getattr(state, "_content_sr", 1.0) or 1.0),
        view_to_screen=float(get_zoom_level(widget) or 1.0),
        output_scale=float(getattr(plan, "output_scale", 1.0) or 1.0),
        content_width=float(max(0, content_rect_px[2])),
        content_height=float(max(0, content_rect_px[3])),
        mode=mode,
    )
    render_intent = build_render_intent(
        kind=mode,
        output_width=widget.width(),
        output_height=widget.height(),
        output_scale=float(getattr(plan, "output_scale", 1.0) or 1.0),
        zoom_level=float(get_zoom_level(widget) or 1.0),
        clip_overlays_to_content=bool(getattr(state, "_clip_overlays_to_content_rect", False)),
        preserve_zoom=bool(getattr(plan, "preserve_zoom", False)),
    )

    render_scene = state._render_scene or {}
    static_fo = dict(getattr(render_scene, "feature_overrides", {}) or {})
    dynamic_fo = dict(getattr(state, "_dynamic_feature_overrides", {}) or {})
    feature_payloads = {**static_fo, **dynamic_fo}

    scene_frame = build_scene_frame(
        render_scene=render_scene,
        content_rect_px=content_rect_px,
        image_rect_px=content_rect_px,
        split_override=split_override,
        feature_payloads=feature_payloads,
    )
    resolved_style = resolve_canvas_style(scene_frame, render_metrics)
    display_split_position = update_display_split_position(
        widget,
        scene=scene_frame,
        zoom_level=float(get_zoom_level(widget) or 1.0),
        pan_offset_x=float(get_pan_offset_x(widget) or 0.0),
        pan_offset_y=float(get_pan_offset_y(widget) or 0.0),
        anchor_to_viewport=(mode == "interactive"),
    )
    diff_mode_active = bool(scene_frame.diff_mode_active)
    use_hires = bool(
        state._shader_letterbox_mode
        and not diff_mode_active
        and float(get_zoom_level(widget) or 1.0) > 1.0
        and state._source_images_ready
        and getattr(widget, "_source_texture_ids", [0, 0])[0]
        and getattr(widget, "_source_texture_ids", [0, 0])[1]
    )
    letterbox1 = (
        widget.get_letterbox_params(0)
        if state._shader_letterbox_mode and hasattr(widget, "get_letterbox_params")
        else (0.0, 0.0, 1.0, 1.0)
    )
    letterbox2 = (
        widget.get_letterbox_params(1)
        if state._shader_letterbox_mode and hasattr(widget, "get_letterbox_params")
        else (0.0, 0.0, 1.0, 1.0)
    )
    resolved_split_position = float(display_split_position) if display_split_position is not None else 0.5
    base_image = BaseImagePrimitive(
        split_position=resolved_split_position,
        is_horizontal=bool(scene_frame.is_horizontal),
        zoom=float(get_zoom_level(widget) or 1.0),
        pan_offset_x=float(get_pan_offset_x(widget) or 0.0),
        pan_offset_y=float(get_pan_offset_y(widget) or 0.0),
        diff_mode_int=int(scene_frame.diff_mode_int or 0),
        channel_mode_int=int(scene_frame.channel_mode_int or 0),
        use_hires=use_hires,
        letterbox1=tuple(float(v) for v in letterbox1),
        letterbox2=tuple(float(v) for v in letterbox2),
    )
    overlay_state = state._feature_overlay_gpu
    render_list = build_render_list(
        scene_frame,
        base_image=base_image,
    )
    return GLRenderRuntimeContext(
        viewport=GLViewportContext(
            width=widget.width(),
            height=widget.height(),
            zoom_level=get_zoom_level(widget),
            pan_offset_x=get_pan_offset_x(widget),
            pan_offset_y=get_pan_offset_y(widget),
            is_horizontal=bool(
                getattr(view_state, "is_horizontal", getattr(widget, "is_horizontal", False))
            ),
            split_position=float(
                getattr(view_state, "split_position", getattr(widget, "split_position", 0.5))
                or 0.5
            ),
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
        feature_overlay=GLFeatureOverlayContext(
            widget=widget,
            render_enabled=bool(getattr(overlay_state, "_quads", ())),
            clip_to_content=bool(getattr(state, "_clip_overlays_to_content_rect", False)),
            border_color=getattr(overlay_state, "_border_color", None),
            border_width=float(getattr(overlay_state, "_border_width", 2.0) or 2.0),
            quads=tuple(getattr(overlay_state, "_quads", ()) or ()),
            gpu_active=bool(getattr(overlay_state, "_gpu_active", False)),
            gpu_slots=tuple(getattr(overlay_state, "_gpu_slots", ()) or ()),
            gpu_channel_mode=int(getattr(overlay_state, "_gpu_channel_mode", 0) or 0),
            gpu_diff_mode=int(getattr(overlay_state, "_gpu_diff_mode", 0) or 0),
            gpu_diff_threshold=float(
                getattr(overlay_state, "_gpu_diff_threshold", 20.0 / 255.0) or 0.0
            ),
            gpu_interp_mode=(
                int(getattr(overlay_state, "_gpu_interp_mode"))
                if getattr(overlay_state, "_gpu_interp_mode", None) is not None
                else 1
            ),
            combined_params=tuple(getattr(overlay_state, "_combined_params", ()) or ()),
            occluded_capture_arcs=tuple(getattr(state, "_occluded_capture_arcs", ()) or ()),
            hidden_capture_circles=tuple(getattr(state, "_hidden_capture_circles", ()) or ()),
            hidden_overlay_circles=tuple(getattr(state, "_hidden_overlay_circles", ()) or ()),
        ),
        metrics=GLMetricsContext(
            render_metrics=render_metrics,
            render_intent=render_intent,
            resolved_style=resolved_style,
            scene_frame=scene_frame,
            render_list=render_list,
        ),
    )

def initialize_gl_resources(widget):
    state = widget.runtime_state

    ctx = widget.context()
    if ctx and ctx.isValid():
        pass
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
    for tex_id in widget.texture_ids + widget._source_texture_ids + [
        widget._diff_source_texture_id,
    ]:
        _configure_texture_parameters(tex_id)

    widget._feature_overlay_tex_ids = [int(t) for t in list(gl.glGenTextures(3))]
    widget._feature_overlay_aux_tex_ids = [int(t) for t in list(gl.glGenTextures(3))]
    widget._feature_overlay_tex_id = widget._feature_overlay_tex_ids[0]
    for texture_id in widget._feature_overlay_tex_ids + widget._feature_overlay_aux_tex_ids:
        _configure_texture_parameters(texture_id)

    widget._circle_mask_tex_id = int(gl.glGenTextures(1))
    _configure_texture_parameters(widget._circle_mask_tex_id)
    _load_circle_mask_assets(widget)

    _initialize_feature_gl_passes(widget)

def _initialize_feature_gl_passes(widget) -> None:
    """Discover and initialize all canvas feature GL render passes."""
    from ui.canvas_infra.scene.gl_pass_registry import get_canvas_gl_render_passes
    passes = [type(p)() for p in get_canvas_gl_render_passes()]
    widget._feature_gl_passes = passes
    for pass_ in passes:
        try:
            pass_.initialize(widget)
        except Exception:
            logger.exception("Failed to initialize GL pass %s", type(pass_).__name__)

def resize_gl(widget, w: int, h: int):
    state = widget.runtime_state
    letterbox_focus = None
    if state._shader_letterbox_mode and state._stored_pil_images[0] is not None:
        from ui.canvas_infra.viewport.focus import capture_letterbox_focus
        letterbox_focus = capture_letterbox_focus(widget)
    gl.glViewport(0, 0, w, h)
    widget._update_paste_overlay_rects()
    if has_canvas_feature_live_runtime_overlays():
        QTimer.singleShot(0, widget._emit_viewport_state_change)
    img1, img2 = state._stored_pil_images
    if state._shader_letterbox_mode and img1 is not None:
        update_letterbox_geometry(widget, img1, slot_index=0)
        from ui.canvas_infra.viewport.focus import restore_letterbox_focus
        restore_letterbox_focus(widget, letterbox_focus)
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
    state = widget.runtime_state
    store = state._store
    if store is None:
        store = getattr(widget, "_store", None)
    if store is not None and hasattr(store, "emit_state_change"):
        store.emit_viewport_change("geometry")

    plan = getattr(widget, "_active_render_plan", None)
    if not state._shader_letterbox_mode or (store is None and plan is None):
        return

    if plan is not None:

        from ui.canvas_presentation.plan_applicator import apply_plan_runtime_overlays
        apply_plan_runtime_overlays(widget, plan)

    if store is not None:

        from ui.canvas_presentation.plan_applicator import _sync_geometry_state
        _sync_geometry_state(widget, store)
        _live_plan = getattr(widget, "_active_render_plan", None)
        if _live_plan is None or _live_plan.overlay_layout is None:
            apply_canvas_feature_live_runtime_overlays(store, widget)

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
            and has_canvas_feature_live_runtime_overlays()
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

def _load_circle_mask_assets(widget):
    try:
        from PIL import Image as _PilImage
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
    except Exception:
        pass
