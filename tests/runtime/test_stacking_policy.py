"""Tests for the central stacking policy (Phase 3)."""

from __future__ import annotations

import importlib
import os
import pkgutil
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QColor

from ui.canvas_infra.scene.stacking_policy import (
    CanvasStackHint,
    CanvasStackLayer,
    CanvasStackRole,
    resolve_gl_pass_order,
    resolve_scene_object_order,
)
from ui.canvas_infra.scene.pass_contract import (
    CanvasRenderPassBase,
    RenderPhase,
    SceneVisibility,
)
from ui.canvas_infra.scene.feature_contract import CanvasFeatureZOrder
from tabs.image_compare.canvas.render_arch import (
    SceneFrame,
    build_render_list,
    build_scene_frame,
    resolve_canvas_style,
)
from ui.widgets.canvas.render_metrics import RenderMetrics

class TestGLPassResolution:
    """Every CanvasStackRole must resolve to a valid (RenderPhase, int) pair."""

    @pytest.mark.parametrize("role", list(CanvasStackRole))
    def test_every_role_resolves(self, role: CanvasStackRole):
        phase, priority = resolve_gl_pass_order(role)
        assert isinstance(phase, RenderPhase)
        assert isinstance(priority, int)

    def test_underlay_before_annotation(self):
        p1, _ = resolve_gl_pass_order(CanvasStackRole.UNDERLAY_SPLIT)
        p2, _ = resolve_gl_pass_order(CanvasStackRole.IMAGE_OVERLAY_FRAME)
        assert p1 < p2

    def test_frame_before_content(self):
        phase_f, pri_f = resolve_gl_pass_order(CanvasStackRole.IMAGE_OVERLAY_FRAME)
        phase_c, pri_c = resolve_gl_pass_order(CanvasStackRole.IMAGE_OVERLAY_CONTENT)
        assert phase_f == phase_c
        assert pri_f < pri_c

    def test_annotation_before_hud(self):
        p1, _ = resolve_gl_pass_order(CanvasStackRole.IMAGE_OVERLAY_CONTENT)
        p2, _ = resolve_gl_pass_order(CanvasStackRole.HUD_LABEL)
        assert p1 < p2

    def test_hud_before_debug(self):
        p1, _ = resolve_gl_pass_order(CanvasStackRole.HUD_LABEL)
        p2, _ = resolve_gl_pass_order(CanvasStackRole.DEBUG_VIS)
        assert p1 < p2

    def test_guide_before_ring_before_content_in_same_phase(self):
        phase_g, pri_g = resolve_gl_pass_order(CanvasStackRole.ANNOTATION_GUIDE)
        phase_r, pri_r = resolve_gl_pass_order(CanvasStackRole.ANNOTATION_RING)
        phase_c, pri_c = resolve_gl_pass_order(CanvasStackRole.IMAGE_OVERLAY_CONTENT)
        assert phase_g == phase_r == phase_c
        assert pri_g < pri_r < pri_c

    def test_border_above_ring_and_content(self):
        phase_r, pri_r = resolve_gl_pass_order(CanvasStackRole.ANNOTATION_RING)
        phase_c, pri_c = resolve_gl_pass_order(CanvasStackRole.IMAGE_OVERLAY_CONTENT)
        phase_b, pri_b = resolve_gl_pass_order(CanvasStackRole.ANNOTATION_BORDER)
        assert phase_r < phase_b
        assert phase_c < phase_b

class TestSceneObjectResolution:
    """Every CanvasStackRole must resolve to a valid (CanvasStackLayer, int) pair."""

    @pytest.mark.parametrize("role", list(CanvasStackRole))
    def test_every_role_resolves(self, role: CanvasStackRole):
        layer, priority = resolve_scene_object_order(role)
        assert isinstance(layer, CanvasStackLayer)
        assert isinstance(priority, int)

    def test_underlay_before_object(self):
        l1, _ = resolve_scene_object_order(CanvasStackRole.UNDERLAY_SPLIT)
        l2, _ = resolve_scene_object_order(CanvasStackRole.IMAGE_OVERLAY_FRAME)
        assert l1 < l2

    def test_overlay_before_hud(self):
        l1, _ = resolve_scene_object_order(CanvasStackRole.IMAGE_OVERLAY_CONTENT)
        l2, _ = resolve_scene_object_order(CanvasStackRole.HUD_LABEL)
        assert l1 < l2

class TestCanvasFeatureZOrder:

    def test_stack_role_resolves_to_correct_layer(self):
        zo = CanvasFeatureZOrder(stack_role=CanvasStackRole.UNDERLAY_SPLIT)
        hint = zo.stack_hint()
        assert hint.layer == CanvasStackLayer.UNDERLAY

    def test_stack_role_resolves_priority(self):
        zo = CanvasFeatureZOrder(stack_role=CanvasStackRole.ANNOTATION_GUIDE)
        hint = zo.stack_hint()
        expected_layer, expected_pri = resolve_scene_object_order(CanvasStackRole.ANNOTATION_GUIDE)
        assert hint.layer == expected_layer
        assert hint.priority == expected_pri

    def test_explicit_override_beats_role(self):
        zo = CanvasFeatureZOrder(stack_role=CanvasStackRole.UNDERLAY_SPLIT)
        hint = zo.stack_hint(layer=CanvasStackLayer.OBJECT_ACTIVE, priority=99)
        assert hint.layer == CanvasStackLayer.OBJECT_ACTIVE
        assert hint.priority == 99

class TestZeroValuePreservation:

    def test_text_alpha_zero_is_preserved(self):
        style = resolve_canvas_style(
            SceneFrame(
                feature_payloads={
                    "filename_overlay": SimpleNamespace(
                        font_base_pixel_size=18.0,
                        font_size_percent=120,
                        text_alpha_percent=0,
                    )
                }
            ),
            RenderMetrics(
                canvas_to_view=1.0,
                view_to_screen=1.0,
                output_scale=1.0,
                content_width=1920.0,
                content_height=1080.0,
                mode="interactive",
            ),
        )
        assert style.filename_overlay.text_alpha == 0.05

    def test_scene_frame_preserves_zero_split_position(self):
        scene = SimpleNamespace(
            split_position_visual=0.0,
            blank_white=False,
            single_image_preview=False,
            clip_overlays_to_image_bounds=False,
            is_horizontal=False,
            divider_clip_rect=None,
            show_divider=False,
            divider_color=QColor(255, 255, 255, 255),
            channel_mode_int=0,
            diff_mode_active=False,
            diff_mode_int=0,
            zoom_interpolation_method="BILINEAR",
        )
        frame = build_scene_frame(
            render_scene=scene,
            content_rect_px=None,
            image_rect_px=None,
            split_override=None,
        )
        assert frame.split_position_visual == 0.0

class TestMagnifierInterpMode:

    def test_build_render_list_preserves_base_image(self):
        base_image = SimpleNamespace(use_hires=False, split_position=0.5)
        render_list = build_render_list(
            SceneFrame(),
            base_image=base_image,
        )

        assert render_list.base_image is base_image

    def test_explicit_scene_layer_priority_override(self):
        zo = CanvasFeatureZOrder(layer=CanvasStackLayer.HUD, priority=42)
        hint = zo.stack_hint()
        assert hint.layer == CanvasStackLayer.HUD
        assert hint.priority == 42

    def test_flags_preserved(self):
        zo = CanvasFeatureZOrder(
            stack_role=CanvasStackRole.ANNOTATION_RING,
            always_on_top=True,
            active_bias=True,
            selectable_when_hidden=True,
        )
        hint = zo.stack_hint()
        assert hint.always_on_top is True
        assert hint.active_bias is True
        assert hint.selectable_when_hidden is True

class TestCanvasRenderPassBase:

    def test_stack_role_resolution(self):
        p = CanvasRenderPassBase()
        p.stack_role = CanvasStackRole.HUD_LABEL
        phase, pri = p.resolved_layer_and_priority()
        expected_phase, expected_pri = resolve_gl_pass_order(CanvasStackRole.HUD_LABEL)
        assert phase == expected_phase
        assert pri == expected_pri

    def test_stack_role_is_required(self):
        p = CanvasRenderPassBase()
        with pytest.raises(ValueError, match="must declare stack_role"):
            p.resolved_layer_and_priority()

    def test_visibility_defaults_to_all(self):
        p = CanvasRenderPassBase()
        assert p.visibility == SceneVisibility.ALL

class TestRenderExecutorOrdering:

    def test_passes_sorted_by_role(self):
        from ui.widgets.canvas.render_executor import iter_ordered_render_passes

        roles_in_expected_order = [
            CanvasStackRole.UNDERLAY_SPLIT,
            CanvasStackRole.ANNOTATION_GUIDE,
            CanvasStackRole.ANNOTATION_RING,
            CanvasStackRole.IMAGE_OVERLAY_FRAME,
            CanvasStackRole.IMAGE_OVERLAY_CONTENT,
            CanvasStackRole.ANNOTATION_BORDER,
            CanvasStackRole.HUD_LABEL,
            CanvasStackRole.DEBUG_VIS,
        ]
        passes = []
        for role in reversed(roles_in_expected_order):
            p = CanvasRenderPassBase()
            p.stack_role = role
            passes.append(p)

        ordered = iter_ordered_render_passes(passes)
        ordered_roles = [p.stack_role for p in ordered]
        assert ordered_roles == roles_in_expected_order

    def test_execute_render_passes_filters_by_scene_visibility(self):
        from ui.widgets.canvas.render_executor import execute_render_passes

        painted: list[str] = []

        class _Pass(CanvasRenderPassBase):
            def __init__(self, name: str, visibility: SceneVisibility):
                self.name = name
                self.visibility = visibility
                self.stack_role = CanvasStackRole.HUD_LABEL

            def should_paint(self, ctx) -> bool:
                return True

            def paint(self, widget, ctx) -> None:
                painted.append(self.name)

        ctx = SimpleNamespace(
            render_metrics=SimpleNamespace(mode="export"),
            scene_frame=SimpleNamespace(single_image_preview=0),
        )

        execute_render_passes(
            widget=None,
            ctx=ctx,
            passes=(
                _Pass("interactive", SceneVisibility.INTERACTIVE),
                _Pass("export", SceneVisibility.EXPORT),
                _Pass("all", SceneVisibility.ALL),
            ),
        )

        assert painted == ["export", "all"]

    def test_render_executor_no_longer_uses_hide_in_single_preview(self):
        render_executor_path = os.path.join(
            os.path.dirname(__file__),
            os.pardir,
            os.pardir,
            "src",
            "ui",
            "widgets",
            "canvas",
            "render_executor.py",
        )
        with open(render_executor_path, encoding="utf-8") as f:
            content = f.read()
        assert "hide_in_single_preview" not in content

class TestFeatureGLPassesUseStackRole:

    def test_all_discovered_passes_have_stack_role(self):
        import tabs.image_compare.canvas.features as features_pkg
        from ui.canvas_infra.scene.pass_registry import get_canvas_render_passes
        from ui.canvas_infra.scene.pass_registry import (
            register_canvas_render_pass_feature_package,
        )

        register_canvas_render_pass_feature_package(features_pkg)
        get_canvas_render_passes.cache_clear()
        passes = get_canvas_render_passes()
        assert len(passes) >= 5, f"Expected at least 5 render passes, got {len(passes)}"

        for p in passes:
            assert p.stack_role is not None, (
                f"{type(p).__name__} still uses raw layer/priority "
                f"instead of stack_role"
            )
            assert isinstance(p.stack_role, CanvasStackRole), (
                f"{type(p).__name__}.stack_role is {type(p.stack_role)}, "
                f"expected CanvasStackRole"
            )
            assert getattr(p.visibility, "name", None) in {
                "INTERACTIVE",
                "EXPORT",
                "PREVIEW",
                "ALL",
            }, (
                f"{type(p).__name__}.visibility is {type(p.visibility)}, "
                f"expected SceneVisibility-compatible flag"
            )

    def test_no_hardcoded_layer_priority_in_feature_passes(self):
        """Ensure no feature passes.py contains raw layer= or priority= on pass classes."""
        import re

        features_root = os.path.join(
            os.path.dirname(__file__),
            os.pardir,
            os.pardir,
            "src",
            "tabs",
            "image_compare",
            "canvas",
            "features",
        )
        pattern = re.compile(r"^\s+(layer|priority)\s*=\s*", re.MULTILINE)
        violations = []

        for entry in os.scandir(features_root):
            if not entry.is_dir():
                continue
            passes_path = os.path.join(entry.path, "passes.py")
            if not os.path.isfile(passes_path):
                continue
            with open(passes_path, encoding="utf-8") as f:
                content = f.read()
            matches = pattern.findall(content)
            if matches:
                violations.append(f"{entry.name}/passes.py: {matches}")

        assert not violations, (
            "Feature passes.py files still contain hardcoded layer/priority:\n"
            + "\n".join(violations)
        )

    def test_stack_policy_has_no_gl_order_collisions(self):
        """CANVAS_FEATURES.md: stack roles resolve to unambiguous GL pass ordering."""
        seen = {}
        for role in CanvasStackRole:
            order = resolve_gl_pass_order(role)
            assert order not in seen, f"{role} collides with {seen.get(order)} at {order}"
            seen[order] = role

    def test_image_overlay_content_renders_before_hud_label(self):
        """CANVAS_FEATURES.md: image annotations must stay below HUD labels."""
        content_order = resolve_gl_pass_order(CanvasStackRole.IMAGE_OVERLAY_CONTENT)
        hud_order = resolve_gl_pass_order(CanvasStackRole.HUD_LABEL)

        assert content_order < hud_order
