import logging
import time
from dataclasses import replace as _dc_replace

from shared.rendering.tile_debug import log_tile_event, tile_dump_enabled

_log = logging.getLogger("ImproveImgSLI.magnifier.scene_update")

from tabs.image_compare.canvas.features.magnifier.geometry.layout_plan import build_magnifier_layout
from tabs.image_compare.canvas.features.magnifier.render.plan_overlay import apply_magnifier_plan_overlay
from tabs.image_compare.canvas.features.magnifier.state.store import active_or_default_divider_thickness
from ui.canvas_infra.scene.apply import apply_scene_to_canvas
from ui.canvas_infra.scene.builder import build_canvas_scene
from ui.canvas_infra.scene.pass_contract import SceneVisibility
from ui.canvas_presentation.plan import resolve_plan_logical_image_rect
from tabs.image_compare.canvas.helpers import reset_canvas_overlays

from tabs.image_compare.canvas.features.magnifier.workers.common import (
    get_effective_main_interpolation_method,
    get_live_image_label,
    is_effective_magnifier_interactive,
)
from tabs.image_compare.canvas.features.magnifier.workers.diff_cache import ensure_cached_diff_image


def _build_and_apply_scene_snapshot(presenter, image_label, geometry):
    label_width, label_height = presenter.get_current_label_dimensions()
    scene = build_canvas_scene(
        presenter.store,
        image_label=image_label,
        label_width=label_width,
        label_height=label_height,
    )
    runtime_state = getattr(image_label, "runtime_state", None)
    if runtime_state is not None:
        runtime_state._canvas_scene_graph = scene
    apply_scene_to_canvas(
        scene,
        image_label,
        geometry,
        session_type="image_compare",
        use_quick_overlay=False,
        scene_visibility=SceneVisibility.INTERACTIVE,
    )
    return scene


def _resolve_magnifier_interpolation_method(vp, *, effective_interactive: bool) -> str:
    if effective_interactive:
        return str(
            getattr(
                vp.render_config,
                "interactive_movement_interpolation_method",
                "BILINEAR",
            )
            or "BILINEAR"
        )
    return str(get_effective_main_interpolation_method(vp) or "BILINEAR")


def rebuild_magnifier_overlay(presenter):
    vp = presenter.store.viewport
    geometry = vp.geometry_state
    image_label = get_live_image_label(presenter)
    if image_label is None:
        return
    if not hasattr(image_label, "set_feature_overlay_gpu_params"):
        return

    _debug_timing = tile_dump_enabled()
    _t_start = time.perf_counter() if _debug_timing else 0.0
    _checkpoints: list[tuple[str, float]] = []

    def _mark(label: str) -> None:
        if _debug_timing:
            _checkpoints.append((label, time.perf_counter() - _t_start))

    if hasattr(image_label, "begin_update_batch"):
        image_label.begin_update_batch()
    try:
        _build_and_apply_scene_snapshot(presenter, image_label, geometry)
        _mark("scene_snapshot")

        plan = getattr(image_label, "_active_render_plan", None)
        if plan is None:
            reset_canvas_overlays(image_label)
            return

        source_pil_images = getattr(image_label, "_source_pil_images", ())
        tex_img1 = source_pil_images[0] if len(source_pil_images) >= 1 else None
        tex_img2 = source_pil_images[1] if len(source_pil_images) >= 2 else None
        if tex_img1 is None or tex_img2 is None:
            # PipelineCache fallback
            try:
                store = presenter.store
                doc = store.get_session_state_slot("document")
                for slot, cur in ((1, tex_img1), (2, tex_img2)):
                    if cur is not None:
                        continue
                    path = doc.image1_path if slot == 1 else doc.image2_path
                    if not path:
                        continue
                    try:
                        _img_state = store.viewport.session_data.image_state
                        cand = _img_state.image1 if slot == 1 else _img_state.image2
                        if cand is not None and getattr(cand, "is_open", True):
                            try:
                                if hasattr(cand, "isNull") and cand.isNull():
                                    cand = None
                                elif hasattr(cand, "is_open") and not cand.is_open:
                                    cand = None
                            except Exception:
                                pass
                            if cand is not None:
                                if slot == 1:
                                    tex_img1 = cand
                                else:
                                    tex_img2 = cand
                                continue
                    except Exception:
                        pass
                    try:
                        ps = store.get_session_state_slot("pipeline")
                        if ps is not None:
                            import os

                            from tabs.image_compare.pipeline.cache import _pixel_key, _preview_key

                            for cache_dict, key_fn in ((ps.pixel, _pixel_key), (ps.preview, _preview_key)):
                                try:
                                    k = key_fn(path, None, None)
                                    v = cache_dict.get(k)
                                    if v is not None:
                                        if hasattr(v, "is_open") and not v.is_open:
                                            continue
                                        if hasattr(v, "isNull") and v.isNull():
                                            continue
                                        if slot == 1:
                                            tex_img1 = v
                                        else:
                                            tex_img2 = v
                                        break
                                except Exception:
                                    pass
                                if (tex_img1 if slot == 1 else tex_img2) is not None:
                                    break
                                try:
                                    norm = os.path.normpath(path)
                                    for kk, vv in cache_dict.items():
                                        if kk[0] == norm:
                                            if hasattr(vv, "is_open") and not vv.is_open:
                                                continue
                                            if hasattr(vv, "isNull") and vv.isNull():
                                                continue
                                            if slot == 1:
                                                tex_img1 = vv
                                            else:
                                                tex_img2 = vv
                                            break
                                except Exception:
                                    pass
                    except Exception:
                        pass
            except Exception:
                pass
        _mark("resolve_source_images")
        if not tex_img1 or not tex_img2:
            reset_canvas_overlays(image_label)
            return

        diff_mode_str = getattr(vp.view_state, "diff_mode", "off")
        cached_diff_image = (
            ensure_cached_diff_image(
                presenter,
                tex_img1,
                tex_img2,
                local_source1=tex_img1,
                local_source2=tex_img2,
            )
            if diff_mode_str == "ssim"
            else None
        )
        current_uploaded_diff = getattr(image_label, "_diff_source_pil_image", None)
        diff_image_for_magnifier = cached_diff_image or current_uploaded_diff
        if cached_diff_image is not None:
            image_label.upload_diff_source_pil_image(cached_diff_image)
        elif diff_mode_str != "ssim":
            image_label.upload_diff_source_pil_image(None)
        _mark("diff_cache")

        effective_interactive = is_effective_magnifier_interactive(vp)
        interpolation_method = _resolve_magnifier_interpolation_method(
            vp,
            effective_interactive=effective_interactive,
        )
        if diff_mode_str == "ssim":
            diff_mode_int = 4 if diff_image_for_magnifier is not None else 0
        else:
            diff_mode_int = {"highlight": 1, "grayscale": 2, "edges": 3}.get(
                diff_mode_str,
                0,
            )

        content_x, content_y, content_w, content_h = resolve_plan_logical_image_rect(
            plan
        )

        layout = build_magnifier_layout(
            vp,
            width=max(1, int(content_w)),
            height=max(1, int(content_h)),
            canvas_width=max(1, int(plan.canvas_w)),
            canvas_height=max(1, int(plan.canvas_h)),
            content_offset_x=float(content_x),
            content_offset_y=float(content_y),
            divider_thickness_px=int(
                active_or_default_divider_thickness(vp.view_state)
            ),
            interpolation_method=interpolation_method,
            diff_mode_override=diff_mode_int,
        )
        _mark("build_layout")
        if layout is None:
            image_label._active_render_plan = _dc_replace(plan, overlay_layout=None)
            reset_canvas_overlays(image_label)
            return

        updated_plan = _dc_replace(plan, overlay_layout=layout)
        image_label._active_render_plan = updated_plan
        apply_magnifier_plan_overlay(image_label, updated_plan)
        _mark("apply_plan_overlay")
    finally:
        if _debug_timing:
            total = time.perf_counter() - _t_start
            if total > 0.05:
                log_tile_event(
                    "magnifier.rebuild_overlay_timing",
                    total_s=total,
                    checkpoints={label: round(dt, 4) for label, dt in _checkpoints},
                )
        if hasattr(image_label, "end_update_batch"):
            image_label.end_update_batch()
        if hasattr(image_label, "_request_update"):
            image_label._request_update()
