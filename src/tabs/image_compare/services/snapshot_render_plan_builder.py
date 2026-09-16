# Audit-Meta: pattern=state-machine size=exempt reason="export plan builder plus co-located parity-harness LOD/tile decision that must stay next to the builder it pins"
from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtGui import QColor

from core.store import Store

from tabs.image_compare.services.analysis.background_layers import (
    build_cached_diff_image,
)
from tabs.image_compare.state.document import DocumentModel
from plugins.export.services.gpu_export_layout import compute_export_stroke_scales
from tabs.image_compare.services.gpu_export_scene import (
    build_export_render_scene,
)
from tabs.image_compare.plugins.video_editor.services.video_export_models import GlobalCanvasBounds
from engine.cache.image_identity import image_uid
from engine.cache import (
    NormalizedBounds,
    TargetSurfaceSpec,
)
from engine.cache.lod import LevelKey, select_level
from engine.cache.tile_texture_service import TileTextureService
from tabs.image_compare.canvas.presentation.plan_builder import (
    build_canvas_plan,
    compute_canvas_plan,
)
from ui.canvas_infra.scene.layout_requirements import resolve_feature_virtual_layout
from tabs.image_compare.canvas.registry import registry


def build_divider_export_overlay(
    store,
    *,
    scale_x: float,
    scale_y: float,
    content_offset_x: float,
    content_offset_y: float,
    content_width: float,
    content_height: float,
) -> dict:
    command = registry().get_feature_command_by_alias("splitter.export_overlay")
    if command is None:
        return {
            "visible": False,
            "split_pos": 0,
            "is_horizontal": False,
            "color": QColor(),
            "thickness": 0,
        }
    result = command(
        store,
        scale_x=scale_x,
        scale_y=scale_y,
        content_offset_x=content_offset_x,
        content_offset_y=content_offset_y,
        content_width=content_width,
        content_height=content_height,
    )
    return result


def query_guides_state(view):
    command = registry().get_feature_command_by_alias("guides.widget_state")
    if command is not None:
        return command(view)
    return type(
        "_FallbackGuidesState",
        (),
        {
            "enabled": False,
            "thickness": 1,
            "color": type("C", (), {"r": 255, "g": 255, "b": 255, "a": 255})(),
        },
    )()


def query_active_magnifier_divider_thickness(store) -> int:
    command = registry().get_feature_command_by_alias("overlay.active_divider_thickness")
    return int(command(store) if command is not None else 0)


    command = registry().get_feature_command_by_alias("overlay.active_divider_thickness")
    return int(command(store) if command is not None else 0)


def calculate_still_snapshot_bounds(snap, image1, image2) -> GlobalCanvasBounds:
    base_w = max(
        1,
        int(getattr(image1, "width", 0) or 0),
        int(getattr(image2, "width", 0) or 0),
    )
    base_h = max(
        1,
        int(getattr(image1, "height", 0) or 0),
        int(getattr(image2, "height", 0) or 0),
    )

    temp_store = Store()
    # See the matching comment in video_snapshot_rendering/store_rebuild.py's
    # `_rebuild_snapshot_store`: `resolve_feature_virtual_layout` below needs
    # an "image_compare" session active, not the default "session_picker".
    temp_store.create_workspace_session(session_type="image_compare", activate=True)
    temp_store.set_session_state_slot("document", DocumentModel())
    temp_store.viewport = snap.viewport_state.clone()
    temp_store.settings = snap.settings_state.freeze_for_export()
    temp_store.viewport.session_data.image_state.image1 = image1
    temp_store.viewport.session_data.image_state.image2 = image2
    temp_store.viewport.geometry_state.pixmap_width = base_w
    temp_store.viewport.geometry_state.pixmap_height = base_h

    layout = resolve_feature_virtual_layout(
        temp_store, drawing_width=base_w, drawing_height=base_h
    )
    if layout is not None:
        pad_left, pad_right, pad_top, pad_bottom = layout.resolve_padding_pixels(
            base_width=base_w,
            base_height=base_h,
        )
        canvas_bounds = layout.canvas_bounds
    else:
        pad_left, pad_right, pad_top, pad_bottom = (0, 0, 0, 0)
        canvas_bounds = NormalizedBounds.unit()

    return GlobalCanvasBounds(
        pad_left=pad_left,
        pad_right=pad_right,
        pad_top=pad_top,
        pad_bottom=pad_bottom,
        base_width=base_w,
        base_height=base_h,
        canvas_x_min=float(canvas_bounds.x_min),
        canvas_x_max=float(canvas_bounds.x_max),
        canvas_y_min=float(canvas_bounds.y_min),
        canvas_y_max=float(canvas_bounds.y_max),
    )


def calculate_global_canvas_bounds(
    snapshots,
    image_loader,
    auto_crop: bool = False,
) -> GlobalCanvasBounds | None:
    if not snapshots:
        return None

    max_pad_left = 0
    max_pad_right = 0
    max_pad_top = 0
    max_pad_bottom = 0
    base_w, base_h = 0, 0
    canvas_bounds = NormalizedBounds.unit()
    have_explicit_layout = False

    for snap in snapshots:
        img1 = image_loader(snap.image1_path, auto_crop)
        if img1:
            w, h = img1.size
            base_w = max(base_w, w)
            base_h = max(base_h, h)

        img2 = image_loader(snap.image2_path, auto_crop)
        if img2:
            w, h = img2.size
            base_w = max(base_w, w)
            base_h = max(base_h, h)

    if base_w == 0 or base_h == 0:
        return None

    build_requirements = registry().get_feature_commands_by_id(
        "render.layout_requirement"
    )
    if not build_requirements:
        return GlobalCanvasBounds(
            pad_left=0,
            pad_right=0,
            pad_top=0,
            pad_bottom=0,
            base_width=base_w,
            base_height=base_h,
        )

    for snap in snapshots:
        img1 = image_loader(snap.image1_path, auto_crop)
        img2 = image_loader(snap.image2_path, auto_crop)
        if not img1 or not img2:
            continue

        temp_store = Store()
        # See the matching comment in calculate_still_snapshot_bounds above.
        temp_store.create_workspace_session(session_type="image_compare", activate=True)
        temp_store.set_session_state_slot("document", DocumentModel())
        temp_store.viewport = snap.viewport_state.clone()
        temp_store.settings = snap.settings_state.freeze_for_export()
        temp_store.viewport.session_data.image_state.image1 = img1
        temp_store.viewport.session_data.image_state.image2 = img2
        temp_store.viewport.geometry_state.pixmap_width = base_w
        temp_store.viewport.geometry_state.pixmap_height = base_h

        layout = resolve_feature_virtual_layout(
            temp_store, drawing_width=base_w, drawing_height=base_h
        )
        if layout is not None and layout.canvas_bounds != layout.content_bounds:
            pad_left, pad_right, pad_top, pad_bottom = layout.resolve_padding_pixels(
                base_width=base_w,
                base_height=base_h,
            )
            resolved_canvas_bounds = layout.canvas_bounds
        else:
            pad_left, pad_right, pad_top, pad_bottom = (0, 0, 0, 0)
            resolved_canvas_bounds = None
        max_pad_left = max(max_pad_left, pad_left)
        max_pad_right = max(max_pad_right, pad_right)
        max_pad_top = max(max_pad_top, pad_top)
        max_pad_bottom = max(max_pad_bottom, pad_bottom)
        if resolved_canvas_bounds is not None:
            canvas_bounds = canvas_bounds.union(resolved_canvas_bounds)
            have_explicit_layout = True

    final_canvas_bounds = canvas_bounds if have_explicit_layout else NormalizedBounds.unit()
    return GlobalCanvasBounds(
        pad_left=max_pad_left,
        pad_right=max_pad_right,
        pad_top=max_pad_top,
        pad_bottom=max_pad_bottom,
        base_width=base_w,
        base_height=base_h,
        canvas_x_min=float(final_canvas_bounds.x_min),
        canvas_x_max=float(final_canvas_bounds.x_max),
        canvas_y_min=float(final_canvas_bounds.y_min),
        canvas_y_max=float(final_canvas_bounds.y_max),
    )


class SnapshotRenderPlanBuilder:
    def __init__(self, store) -> None:
        self.store = store

    @staticmethod
    def _is_featureless_canvas_geometry(canvas_geometry) -> bool:
        if canvas_geometry is None:
            return True
        return (
            getattr(canvas_geometry, "virtual_layout", None) is None
            and int(getattr(canvas_geometry, "padding_left", 0) or 0) == 0
            and int(getattr(canvas_geometry, "padding_right", 0) or 0) == 0
            and int(getattr(canvas_geometry, "padding_top", 0) or 0) == 0
            and int(getattr(canvas_geometry, "padding_bottom", 0) or 0) == 0
            and int(getattr(canvas_geometry, "canvas_width", 0) or 0)
            == int(getattr(canvas_geometry, "image_width", 0) or 0)
            and int(getattr(canvas_geometry, "canvas_height", 0) or 0)
            == int(getattr(canvas_geometry, "image_height", 0) or 0)
        )

    def build_render_plan(
        self,
        image1,
        image2,
        *,
        source_image1=None,
        source_image2=None,
        source_key=None,
        display_cache_key=None,
        target_surface: TargetSurfaceSpec | None = None,
        canvas_fill_rgba=None,
        canvas_geometry=None,
        allow_feature_layout_fallback: bool = False,
        scene_images_cache: dict | None = None,
    ):
        if target_surface is not None and canvas_fill_rgba is None:
            canvas_fill_rgba = target_surface.fill_rgba
        if source_image1 is None:
            source_image1 = image1
        if source_image2 is None:
            source_image2 = image2

        diff_mode = str(
            getattr(self.store.viewport.view_state, "diff_mode", "off") or "off"
        )
        channel_mode = str(
            getattr(self.store.viewport.view_state, "channel_view_mode", "RGB") or "RGB"
        )

        computed_canvas_plan = compute_canvas_plan(
            self.store,
            image1.width,
            image1.height,
        )
        canvas_plan = (
            computed_canvas_plan
            if allow_feature_layout_fallback
            and self._is_featureless_canvas_geometry(canvas_geometry)
            else canvas_geometry
        )
        if canvas_plan is None:
            canvas_plan = (
                computed_canvas_plan
                if allow_feature_layout_fallback
                else compute_canvas_plan(
                    self.store,
                    image1.width,
                    image1.height,
                )
            )

        scene_cache_key = (
            image_uid(image1),
            image_uid(image2),
            image_uid(source_image1),
            image_uid(source_image2),
            canvas_plan.canvas_width,
            canvas_plan.canvas_height,
            canvas_plan.padding_left,
            canvas_plan.padding_top,
            diff_mode,
            channel_mode,
            canvas_fill_rgba,
        )
        if (
            scene_images_cache is not None
            and scene_images_cache.get("key") == scene_cache_key
        ):
            scene_images = scene_images_cache["value"]
            cached_diff_image = scene_images.get("raw_diff")
        else:
            cached_diff_image = None
            if diff_mode in {"highlight", "grayscale", "edges", "ssim"}:
                cached_diff_image = build_cached_diff_image(
                    image1,
                    image2,
                    diff_mode,
                    channel_mode,
                )
            scene_images = self._prepare_canvas_scene_images(
                canvas_plan=canvas_plan,
                image1=image1,
                image2=image2,
                source_image1=source_image1,
                source_image2=source_image2,
                cached_diff_image=cached_diff_image,
                canvas_fill_rgba=canvas_fill_rgba,
            )
            if scene_images_cache is not None:
                scene_images_cache["key"] = scene_cache_key
                scene_images_cache["value"] = scene_images
        from core.state_management.actions import SetCachedDiffImageAction
        try:
            d = getattr(self.store, "get_dispatcher", lambda: None)()
            if d is not None:
                d.dispatch(SetCachedDiffImageAction(image=cached_diff_image), scope="viewport")
            else:
                setattr(self.store.viewport.session_data.render_cache, "cached_diff_image", cached_diff_image)
        except Exception:
            try: setattr(self.store.viewport.session_data.render_cache, "cached_diff_image", cached_diff_image)
            except Exception: pass

        viewport_state = {
            "pixmap_width": getattr(
                self.store.viewport.geometry_state, "pixmap_width", 0
            ),
            "pixmap_height": getattr(
                self.store.viewport.geometry_state, "pixmap_height", 0
            ),
        }
        scale_x, scale_y, _scale_ref = compute_export_stroke_scales(
            viewport_state,
            image1.width,
            image1.height,
        )
        vp = self.store.viewport
        view = vp.view_state
        guides_state = query_guides_state(view)
        divider_overlay = build_divider_export_overlay(
            self.store,
            scale_x=scale_x,
            scale_y=scale_y,
            content_offset_x=canvas_plan.padding_left,
            content_offset_y=canvas_plan.padding_top,
            content_width=canvas_plan.image_width,
            content_height=canvas_plan.image_height,
        )
        divider_thickness_export = int(divider_overlay.get("thickness", 0))
        guides_thickness_export = int(guides_state.thickness)
        magnifier_divider_thickness_export = query_active_magnifier_divider_thickness(
            self.store
        )
        render_scene = build_export_render_scene(
            self.store,
            divider_thickness_export,
            virtual_layout=canvas_plan.virtual_layout,
            image_w=canvas_plan.image_width,
            image_h=canvas_plan.image_height,
        )
        if getattr(render_scene, "overlay_clip_rect", None) is None:
            pad_l = int(canvas_plan.padding_left)
            pad_t = int(canvas_plan.padding_top)
            img_w = int(canvas_plan.image_width)
            img_h = int(canvas_plan.image_height)
            canv_w = int(canvas_plan.canvas_width)
            canv_h = int(canvas_plan.canvas_height)
            if pad_l or pad_t or img_w != canv_w or img_h != canv_h:
                render_scene = replace(
                    render_scene,
                    overlay_clip_rect=(pad_l, pad_t, img_w, img_h),
                )
        base_image1 = scene_images["bg1"]
        base_image2 = scene_images["bg2"]
        if scene_images["diff"] is not None:
            base_image1 = scene_images["diff"]
            base_image2 = scene_images["diff"]
            display_cache_key = (
                "diff_base",
                display_cache_key,
                diff_mode,
                channel_mode,
                scene_cache_key,
            )
            render_scene = replace(
                render_scene,
                diff_mode_active=False,
                diff_mode_int=0,
                channel_mode_int=0,
            )

        plan = build_canvas_plan(
            self.store,
            base_image1,
            base_image2,
            source_image1=scene_images["src1"],
            source_image2=scene_images["src2"],
            source_key=source_key or (),
            display_cache_key=display_cache_key,
            target_size=(canvas_plan.canvas_width, canvas_plan.canvas_height),
            content_size=(canvas_plan.image_width, canvas_plan.image_height),
            pad_left=canvas_plan.padding_left,
            pad_top=canvas_plan.padding_top,
            render_scene=render_scene,
            divider_thickness_px=magnifier_divider_thickness_export,
            guides_thickness=guides_thickness_export,
            output_scale=(
                float(target_surface.output_scale)
                if target_surface is not None
                else 1.0
            ),
            fill_color=canvas_fill_rgba,
            preserve_zoom=(
                bool(target_surface.preserve_zoom)
                if target_surface is not None
                else False
            ),
            image_is_padded_composite=False,
            geometry_letterbox=True,
        )
        return plan

    def _prepare_canvas_scene_images(
        self,
        *,
        canvas_plan,
        image1,
        image2,
        source_image1,
        source_image2,
        cached_diff_image,
        canvas_fill_rgba=None,
    ):
        """Keep scene images unpadded; pads live in ``canvas_plan`` + fill.

        GPU export applies ``shader_letterbox=True`` and clears with
        ``fill_rgba``; baking pad into PIL would force a whole-image
        materialize of ``TiledPixelStore`` sources.
        """
        aligned_source1 = source_image1
        aligned_source2 = source_image2
        export_size = (
            getattr(image1, "size", None),
            getattr(image2, "size", None),
        )
        source_size = (
            getattr(aligned_source1, "size", None),
            getattr(aligned_source2, "size", None),
        )
        if source_size != export_size:
            aligned_source1 = image1
            aligned_source2 = image2

        return {
            "bg1": image1,
            "bg2": image2,
            "src1": aligned_source1,
            "src2": aligned_source2,
            "diff": cached_diff_image,
            "raw_diff": cached_diff_image,
        }


# ---------------------------------------------------------------------------
# Parity-harness test support (task-engine-2d, bucket 2D).
#
# Pure snapshot LOD + tile decision used ONLY by
# src/tabs/image_compare/tests/render/test_live_export_parity.py to pin the
# live/export parity invariant: same snapshot in -> same level + same tiles
# out. ``SnapshotRenderPlanBuilder.build_render_plan`` never calls these
# (no production-logic change). Both the live canvas path
# (``rhi_renderer/draw_plan.py::resolve_lod_texture_keys`` +
# ``TileTextureService.visible_tiles``) and this helper decide through
# ``engine.cache.lod.select_level`` with identical inputs, and neither takes
# a ``mode`` argument -- so no ``if mode == "export"`` branch can sneak in
# on either side of the harness.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotLodTiles:
    """Export-path LOD + tile decision for one snapshot (test support)."""

    levels: tuple[int, int]
    tile_sets: tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]]


def snapshot_lod_tiles_for_sources(
    sources,
    *,
    canvas_size_px,
    zoom: float = 1.0,
    letterboxes=((0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0)),
    texture_keys=("source_0", "source_1"),
    image_space_rect=None,
    tile_service=None,
) -> SnapshotLodTiles:
    """Decide LOD levels + tile sets for one export snapshot (test support).

    ``sources`` is a ``(side0, side1)`` pair of pixel sources (``TiledPixelStore``
    or PIL); ``canvas_size_px`` is the snapshot surface in device pixels;
    ``zoom``/``letterboxes`` describe the snapshot's view exactly like the
    live path's ``base_image``. ``image_space_rect`` (``(left, top, right,
    bottom)`` in level-image pixels, or ``None`` for the whole snapshot)
    is fed unchanged to ``visible_tiles`` -- the harness passes the same
    rect to the live path, pinning "same snapshot -> same tiles".

    Level grids are registered into ``tile_service`` (a fresh
    ``TileTextureService`` when omitted) under the resolved keys -- bare
    base key for level 0, ``LevelKey(base, k)`` above -- mirroring what the
    live upload path registers before residency/draw-plan run.
    """
    from engine.store.pyramid_registry import pyramid_for
    from engine.store.tiled_pixel_store import TiledPixelStore

    canvas_w_px = float(canvas_size_px[0])
    canvas_h_px = float(canvas_size_px[1])
    zoom_f = float(zoom) or 1.0
    pyramids = [
        pyramid_for(source) if isinstance(source, TiledPixelStore) else None
        for source in sources
    ]
    # Shared-level clamp, mirroring
    # ``resolve_lod_texture_keys``: both sides' clamped level (and thus grid
    # dimensions) stay identical whenever they'd otherwise want the same
    # level; a side whose pyramid is missing/not yet built counts as 1
    # (base level only) so it can't outrun the slower side.
    effective_counts: list[int] = []
    for src, pyr in zip(sources, pyramids):
        if isinstance(src, TiledPixelStore):
            effective_counts.append(pyr.level_count if pyr is not None else 1)
    shared_level_count = min(effective_counts) if effective_counts else 0

    levels: list[int] = []
    keys: list[object] = []
    sizes: list[tuple[int, int]] = []
    for key, letterbox, source, pyramid in zip(
        texture_keys, letterboxes, sources, pyramids
    ):
        if not isinstance(source, TiledPixelStore) or pyramid is None:
            levels.append(0)
            keys.append(key)
            size = getattr(source, "size", (1, 1))
            sizes.append((int(size[0]), int(size[1])))
            continue
        src_w, src_h = source.size
        disp_w = canvas_w_px * float(letterbox[2] or 1.0) * zoom_f
        disp_h = canvas_h_px * float(letterbox[3] or 1.0) * zoom_f
        dest_scale = max(
            disp_w / float(max(1, src_w)), disp_h / float(max(1, src_h))
        )
        level = select_level(dest_scale, shared_level_count)
        levels.append(level)
        keys.append(key if level == 0 else LevelKey(key, level))
        level_size = pyramid.level(level).size if level else source.size
        sizes.append((int(level_size[0]), int(level_size[1])))

    service = tile_service if tile_service is not None else TileTextureService()
    tile_sets: list[tuple[tuple[int, int], ...]] = []
    for key, (width, height) in zip(keys, sizes):
        service.register_source(key, (width, height))
        rect = image_space_rect
        if rect is None:
            rect = (0.0, 0.0, float(width), float(height))
        tile_sets.append(tuple(sorted(service.visible_tiles(key, rect))))
    return SnapshotLodTiles(
        levels=(levels[0], levels[1]),
        tile_sets=(tile_sets[0], tile_sets[1]),
    )
