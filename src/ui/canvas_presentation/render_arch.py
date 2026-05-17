from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from PyQt6.QtGui import QColor

from ui.widgets.gl_canvas.render_metrics import resolve_font_px, resolve_view_px
from ui.widgets.gl_canvas.style_tokens import (
    CanvasStyleTokens,
    DEFAULT_CANVAS_STYLE_TOKENS,
)

RenderIntentKind = Literal["interactive", "preview", "export", "thumbnail"]

@dataclass(frozen=True, slots=True)
class SceneFrame:
    """
    Transitional semantic scene contract.

    The current pipeline still carries `GLRenderScene` and feature overrides, but
    new refactors should target this contract instead of adding more target-local
    values to feature configs.
    """

    feature_payloads: dict[str, object] = field(default_factory=dict)
    blank_white: bool = False
    single_image_preview: int = 0
    clip_overlays_to_image_bounds: bool = False
    is_horizontal: bool = False
    split_position_visual: float = 0.5
    divider_clip_rect: tuple[int, int, int, int] | None = None
    divider_visible: bool = False
    divider_color: QColor | None = None
    divider_thickness: int = 2
    channel_mode_int: int = 0
    diff_mode_active: bool = False
    diff_mode_int: int = 0
    zoom_interpolation_method: str = "BILINEAR"
    render_magnifiers: bool = True
    content_rect_px: tuple[int, int, int, int] | None = None
    split_override: float | None = None
    capture_circles: tuple["SceneCaptureCircle", ...] = ()
    guide_sets: tuple["SceneGuideSet", ...] = ()
    filename_overlay: object | None = None

@dataclass(frozen=True, slots=True)
class RenderIntent:
    kind: RenderIntentKind
    output_width: int
    output_height: int
    output_scale: float
    zoom_level: float
    clip_overlays_to_content: bool
    preserve_zoom: bool = False

@dataclass(frozen=True, slots=True)
class FilenameOverlayStyle:
    font_pixel_size: int
    text_alpha: float
    label_safe_gap_px: float
    label_padding_x_px: float
    label_padding_y_px: float
    glyph_overscan_px: float
    label_corner_radius_px: float
    text_inset_px: float

@dataclass(frozen=True, slots=True)
class ResolvedCanvasStyle:
    filename_overlay: FilenameOverlayStyle
    capture_ring_stroke_px: float
    guides_stroke_px_per_unit: float
    occluded_arc_stroke_px: float
    hidden_selection_stroke_px: float

@dataclass(frozen=True, slots=True)
class SceneCaptureCircle:
    center: object
    radius: float
    color: QColor

@dataclass(frozen=True, slots=True)
class SceneGuideSet:
    source_center: object
    source_radius: float
    target_centers: tuple[object, ...]
    target_radii: tuple[float, ...]
    color: QColor

@dataclass(frozen=True, slots=True)
class CaptureRingPrimitive:
    center_px: tuple[float, float]
    radius_px: float
    line_width_px: float
    color: QColor
    clip_to_content: bool

@dataclass(frozen=True, slots=True)
class GuideLinePrimitive:
    start_px: tuple[float, float]
    end_px: tuple[float, float]
    start_radius_px: float
    end_radius_px: float
    line_width_px: float
    color: QColor
    clip_to_content: bool

@dataclass(frozen=True, slots=True)
class FilenameOverlayPrimitive:
    config: object
    content_rect_px: tuple[int, int, int, int]
    split_override: float | None
    divider_thickness_px: float
    name1: str
    name2: str

@dataclass(frozen=True, slots=True)
class DividerPrimitive:
    position_px: float
    thickness_px: float
    is_horizontal: bool
    color: QColor
    clip_rect_px: tuple[int, int, int, int] | None

@dataclass(frozen=True, slots=True)
class MagnifierPrimitive:
    render_enabled: bool
    clip_to_content: bool
    border_color: object
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
    hidden_magnifier_circles: tuple[object, ...]

@dataclass(frozen=True, slots=True)
class BaseImagePrimitive:
    split_position: float
    is_horizontal: bool
    zoom: float
    pan_offset_x: float
    pan_offset_y: float
    diff_mode_int: int
    channel_mode_int: int
    use_hires: bool
    letterbox1: tuple[float, float, float, float]
    letterbox2: tuple[float, float, float, float]

@dataclass(frozen=True, slots=True)
class RenderList:
    base_image: BaseImagePrimitive | None = None
    divider: DividerPrimitive | None = None
    magnifier: MagnifierPrimitive | None = None
    capture_rings: tuple[CaptureRingPrimitive, ...] = ()
    guide_lines: tuple[GuideLinePrimitive, ...] = ()
    filename_overlays: tuple[FilenameOverlayPrimitive, ...] = ()

def build_render_intent(
    *,
    kind: RenderIntentKind,
    output_width: int,
    output_height: int,
    output_scale: float,
    zoom_level: float,
    clip_overlays_to_content: bool,
    preserve_zoom: bool = False,
) -> RenderIntent:
    return RenderIntent(
        kind=kind,
        output_width=max(0, int(output_width)),
        output_height=max(0, int(output_height)),
        output_scale=max(0.0, float(output_scale)),
        zoom_level=max(0.0, float(zoom_level)),
        clip_overlays_to_content=bool(clip_overlays_to_content),
        preserve_zoom=bool(preserve_zoom),
    )

def resolve_canvas_style(
    scene_frame: SceneFrame,
    render_metrics,
    tokens: CanvasStyleTokens = DEFAULT_CANVAS_STYLE_TOKENS,
) -> ResolvedCanvasStyle:
    filename_cfg = scene_frame.filename_overlay
    font_size_percent = getattr(filename_cfg, "font_size_percent", 100)
    if font_size_percent is None:
        font_size_percent = 100
    text_alpha_percent = getattr(filename_cfg, "text_alpha_percent", 100)
    if text_alpha_percent is None:
        text_alpha_percent = 100

    base_font_px = float(
        getattr(filename_cfg, "font_base_pixel_size", tokens.filename_font_base_du)
        or tokens.filename_font_base_du
    )
    font_scale = int(font_size_percent) / 100.0
    text_alpha = max(
        0.0,
        min(1.0, float(int(text_alpha_percent)) / 100.0),
    )

    return ResolvedCanvasStyle(
        filename_overlay=FilenameOverlayStyle(
            font_pixel_size=resolve_font_px(base_font_px * font_scale, render_metrics),
            text_alpha=text_alpha,
            label_safe_gap_px=resolve_view_px(tokens.filename_label_safe_gap_du, render_metrics),
            label_padding_x_px=resolve_view_px(tokens.filename_label_padding_x_du, render_metrics),
            label_padding_y_px=resolve_view_px(tokens.filename_label_padding_y_du, render_metrics),
            glyph_overscan_px=resolve_view_px(tokens.filename_glyph_overscan_du, render_metrics),
            label_corner_radius_px=resolve_view_px(tokens.filename_label_corner_radius_du, render_metrics),
            text_inset_px=resolve_view_px(tokens.filename_text_inset_du, render_metrics),
        ),
        capture_ring_stroke_px=resolve_view_px(tokens.capture_ring_stroke_du, render_metrics),
        guides_stroke_px_per_unit=resolve_view_px(tokens.guides_stroke_du, render_metrics),
        occluded_arc_stroke_px=resolve_view_px(tokens.occluded_arc_stroke_du, render_metrics),
        hidden_selection_stroke_px=resolve_view_px(tokens.hidden_selection_stroke_du, render_metrics),
    )

def build_scene_frame(
    *,
    render_scene,
    content_rect_px: tuple[int, int, int, int] | None,
    split_override: float | None,
    capture_circles: list | tuple | None,
    capture_center,
    capture_radius: float,
    capture_color,
    guide_sets: list | tuple | None,
    laser_color,
    show_guides: bool,
) -> SceneFrame:
    feature_overrides = getattr(render_scene, "feature_overrides", {}) or {}

    normalized_capture: list[SceneCaptureCircle] = []
    raw_capture = list(capture_circles or [])
    if not raw_capture and capture_center is not None and capture_radius > 0:
        raw_capture = [(capture_center, capture_radius, capture_color)]
    for item in raw_capture:
        if len(item) >= 3:
            center, radius, color = item[0], item[1], item[2]
        else:
            center, radius = item[0], item[1]
            color = capture_color
        if center is None or radius <= 0:
            continue
        normalized_capture.append(
            SceneCaptureCircle(center=center, radius=float(radius), color=QColor(color))
        )

    normalized_guides: list[SceneGuideSet] = []
    for guide_set in list(guide_sets or []):
        if len(guide_set) < 4:
            continue
        source_center = guide_set[0]
        source_radius = float(guide_set[1] or 0.0)
        target_centers = tuple(guide_set[2] or ())
        target_radii_raw = guide_set[3]
        line_color = QColor(guide_set[4]) if len(guide_set) >= 5 else QColor(laser_color)
        if isinstance(target_radii_raw, (tuple, list)):
            target_radii = tuple(float(v or 0.0) for v in target_radii_raw)
        else:
            target_radii = tuple(float(target_radii_raw or 0.0) for _ in target_centers)
        normalized_guides.append(
            SceneGuideSet(
                source_center=source_center,
                source_radius=source_radius,
                target_centers=target_centers,
                target_radii=target_radii,
                color=line_color,
            )
        )

    split_position_visual = getattr(render_scene, "split_position_visual", 0.5)
    if split_position_visual is None:
        split_position_visual = 0.5

    return SceneFrame(
        feature_payloads=dict(feature_overrides),
        blank_white=bool(getattr(render_scene, "blank_white", False)),
        single_image_preview=int(getattr(render_scene, "single_image_preview", 0) or 0),
        clip_overlays_to_image_bounds=bool(
            getattr(render_scene, "clip_overlays_to_image_bounds", False)
        ),
        is_horizontal=bool(getattr(render_scene, "is_horizontal", False)),
        split_position_visual=float(split_position_visual),
        divider_clip_rect=getattr(render_scene, "divider_clip_rect", None),
        divider_visible=bool(getattr(render_scene, "show_divider", False)),
        divider_color=QColor(getattr(render_scene, "divider_color", QColor(255, 255, 255, 255))),
        divider_thickness=int(getattr(render_scene, "divider_thickness", 2) or 2),
        channel_mode_int=int(getattr(render_scene, "channel_mode_int", 0) or 0),
        diff_mode_active=bool(getattr(render_scene, "diff_mode_active", False)),
        diff_mode_int=int(getattr(render_scene, "diff_mode_int", 0) or 0),
        zoom_interpolation_method=str(
            getattr(render_scene, "zoom_interpolation_method", "BILINEAR") or "BILINEAR"
        ),
        render_magnifiers=bool(feature_overrides.get("render_magnifiers", True)),
        content_rect_px=content_rect_px,
        split_override=split_override,
        capture_circles=tuple(normalized_capture),
        guide_sets=tuple(normalized_guides),
        filename_overlay=feature_overrides.get("filename_overlay"),
    )

def _point_xy(point) -> tuple[float, float]:
    x = getattr(point, "x", 0.0)
    y = getattr(point, "y", 0.0)
    return float(x() if callable(x) else x), float(y() if callable(y) else y)

def build_render_list(
    scene_frame: SceneFrame,
    *,
    base_image: BaseImagePrimitive | None,
    magnifier_render_enabled: bool = False,
    magnifier_clip_to_content: bool = False,
    magnifier_border_color=None,
    magnifier_border_width: float = 2.0,
    magnifier_quads: list | tuple | None = None,
    magnifier_gpu_active: bool = False,
    magnifier_gpu_slots: list | tuple | None = None,
    magnifier_gpu_channel_mode: int = 0,
    magnifier_gpu_diff_mode: int = 0,
    magnifier_gpu_diff_threshold: float = 20.0 / 255.0,
    magnifier_gpu_interp_mode: int = 1,
    magnifier_combined_params: list | tuple | None = None,
    occluded_capture_arcs: list | tuple | None = None,
    hidden_capture_circles: list | tuple | None = None,
    hidden_magnifier_circles: list | tuple | None = None,
    divider_position_px: float,
    divider_clip_rect_px: tuple[int, int, int, int] | None,
    divider_thickness_px: float,
    guides_thickness_px: float,
    capture_line_width_px: float,
    zoom_level: float,
    widget_px_to_screen,
) -> RenderList:
    clip_to_content = bool(scene_frame.clip_overlays_to_image_bounds)
    zoom = max(0.0, float(zoom_level))
    divider = None
    if (
        bool(scene_frame.divider_visible)
        and float(divider_thickness_px) > 0.0
        and scene_frame.divider_color is not None
    ):
        divider = DividerPrimitive(
            position_px=float(divider_position_px),
            thickness_px=max(1.0, float(divider_thickness_px)),
            is_horizontal=bool(scene_frame.is_horizontal),
            color=QColor(scene_frame.divider_color),
            clip_rect_px=divider_clip_rect_px,
        )

    capture_rings = tuple(
        CaptureRingPrimitive(
            center_px=widget_px_to_screen(*_point_xy(circle.center)),
            radius_px=max(0.0, float(circle.radius) * zoom),
            line_width_px=max(1.0, float(capture_line_width_px)),
            color=QColor(circle.color),
            clip_to_content=clip_to_content,
        )
        for circle in scene_frame.capture_circles
    )

    guide_lines: list[GuideLinePrimitive] = []
    for guide_set in scene_frame.guide_sets:
        end_px = widget_px_to_screen(*_point_xy(guide_set.source_center))
        end_radius_px = max(0.0, guide_set.source_radius * zoom)
        target_radii = guide_set.target_radii
        for index, target_center in enumerate(guide_set.target_centers):
            start_px = widget_px_to_screen(*_point_xy(target_center))
            target_radius = (
                target_radii[index]
                if index < len(target_radii)
                else (target_radii[-1] if target_radii else 0.0)
            )
            guide_lines.append(
                GuideLinePrimitive(
                    start_px=start_px,
                    end_px=end_px,
                    start_radius_px=max(0.0, float(target_radius) * zoom),
                    end_radius_px=end_radius_px,
                    line_width_px=max(1.0, float(guides_thickness_px)),
                    color=QColor(guide_set.color),
                    clip_to_content=clip_to_content,
                )
            )

    magnifier = None
    normalized_quads = tuple(magnifier_quads or ())
    if normalized_quads:
        magnifier = MagnifierPrimitive(
            render_enabled=bool(magnifier_render_enabled),
            clip_to_content=bool(magnifier_clip_to_content),
            border_color=magnifier_border_color,
            border_width=float(magnifier_border_width),
            quads=normalized_quads,
            gpu_active=bool(magnifier_gpu_active),
            gpu_slots=tuple(magnifier_gpu_slots or ()),
            gpu_channel_mode=int(magnifier_gpu_channel_mode or 0),
            gpu_diff_mode=int(magnifier_gpu_diff_mode or 0),
            gpu_diff_threshold=float(magnifier_gpu_diff_threshold or 0.0),
            gpu_interp_mode=(
                int(magnifier_gpu_interp_mode)
                if magnifier_gpu_interp_mode is not None
                else 1
            ),
            combined_params=tuple(magnifier_combined_params or ()),
            occluded_capture_arcs=tuple(occluded_capture_arcs or ()),
            hidden_capture_circles=tuple(hidden_capture_circles or ()),
            hidden_magnifier_circles=tuple(hidden_magnifier_circles or ()),
        )

    filename_overlays: tuple[FilenameOverlayPrimitive, ...] = ()
    filename_cfg = scene_frame.filename_overlay
    _fn_enabled = bool(getattr(filename_cfg, "enabled", False))
    _fn_force = bool(scene_frame.single_image_preview)
    if (
        filename_cfg is not None
        and (_fn_enabled or _fn_force)
        and scene_frame.content_rect_px is not None
    ):
        name1 = str(getattr(filename_cfg, "name1", "") or "")
        name2 = str(getattr(filename_cfg, "name2", "") or "")
        if name1 or name2:
            filename_overlays = (
                FilenameOverlayPrimitive(
                    config=filename_cfg,
                    content_rect_px=scene_frame.content_rect_px,
                    split_override=scene_frame.split_override,
                    divider_thickness_px=max(0.0, float(divider_thickness_px)),
                    name1=name1,
                    name2=name2,
                ),
            )

    return RenderList(
        base_image=base_image,
        divider=divider,
        magnifier=magnifier,
        capture_rings=capture_rings,
        guide_lines=tuple(guide_lines),
        filename_overlays=filename_overlays,
    )
