"""Shared canvas helpers — direct import replacement for tab→tab registry calls.

Previously ``tabs.image_compare.plugins.video_editor.services.canvas_feature_gateway``
and ``tabs.image_compare.plugins.video_editor.services.video_export.bounds``
resolved their own tab's capabilities through ``TabRegistry.create_service``
(active-only string dispatch). That made intra-tab calls look like tab→tab
dependencies and forced the producer tab to be active.

This module exposes the same capabilities as importable functions built on
``ui.canvas_infra.scene.registry`` and
``tabs.image_compare.services.snapshot_render_plan_builder`` so consumers
inside ``src/tabs`` can do::

    from tabs._shared.canvas import execute_canvas_feature_alias

instead of::

    registry = TabRegistry(); registry.get_alias_command("canvas_feature_command_alias", ...)  # example was registry indirect

Host→tab path stays on ``TabRegistry.create_service`` /
``create_startup_service`` (``plugins.settings.canvas_feature_gateway``,
``ui/main_window/ui.py:123`` ``toast_anchor_widget``,
``services/io/project_preview.py:143`` ``capture_preview_image``,
``events/image_carry.py:316`` ``begin_pending_image_insert``) — this module
decouples only the tab→tab / intra-tab route. See
``docs/dev/tabs/capability-mechanisms.md:48`` and
``docs/dev/tabs/isolation.md:83``.

CODE_PATTERNS.md:114 — these are stateless helpers (widget-glue would be
use_cases functions; state-owning would be collaborator objects). No extra
state is introduced, so plain functions are correct. For pyramid/toast/
save-flow the shared modules are collaborator objects because they own
worker/toast lifecycle; that pattern does not apply here.
"""

from __future__ import annotations

from typing import Any


def _image_compare_registry():
    """Return ``CanvasFeatureRegistry`` for ``image_compare``.

    Uses the host-level canvas registry keyed by tab type
    (``ui.canvas_infra.scene.registry.get_canvas_registry``) rather than
    importing the tab's thin wrapper, to keep the shared module free of a
    hard ``tabs.image_compare`` import cycle at import time. Fallback to the
    wrapper if the generic accessor is unavailable.
    """
    try:
        from ui.canvas_infra.scene.registry import get_canvas_registry

        return get_canvas_registry("image_compare")
    except Exception:
        from tabs.image_compare.canvas.registry import registry as ic_registry  # type: ignore

        return ic_registry()


def get_canvas_feature_command_by_alias(alias: str):
    """Direct lookup of a canvas feature command by alias, no registry hop."""
    try:
        return _image_compare_registry().get_feature_command_by_alias(alias)
    except Exception:
        return None


def execute_canvas_feature_alias(
    alias: str, *args: Any, default=None, **kwargs: Any
) -> Any:
    """Execute alias from inside ``src/tabs`` without ``TabRegistry``.

    Mirrors ``tabs.image_compare.plugins.video_editor.services.canvas_feature_gateway``
    but without ``TabRegistry().create_service("canvas_feature_command_alias", ...)``.
    Host code (``plugins.settings.canvas_feature_gateway``) keeps its
    ``create_service`` path — this is the tab→tab replacement.
    """
    command = get_canvas_feature_command_by_alias(alias)
    if command is None:
        return default
    return command(*args, **kwargs)


def get_canvas_feature_command(feature_name: str, command_id: str):
    """Direct non-alias lookup (for completeness)."""
    try:
        return _image_compare_registry().get_feature_command(feature_name, command_id)
    except Exception:
        return None


def execute_canvas_feature_command(
    feature_name: str, command_id: str, *args: Any, **kwargs: Any
) -> Any:
    command = get_canvas_feature_command(feature_name, command_id)
    if command is None:
        return None
    return command(*args, **kwargs)


def calculate_global_canvas_bounds_direct(snapshots, image_loader, auto_crop: bool = False):
    """Direct ``global_canvas_bounds`` without ``TabRegistry.create_service``.

    Thin wrapper around
    ``tabs.image_compare.services.snapshot_render_plan_builder.calculate_global_canvas_bounds``
    so ``CanvasBoundsAnalyzer`` inside the same tab does not need a string
    dispatch. Host still resolves ``global_canvas_bounds`` via
    ``create_service`` (``service_factory.py:69``) — this is the intra-tab
    counterpart.
    """
    try:
        from tabs.image_compare.services.snapshot_render_plan_builder import (
            calculate_global_canvas_bounds,
        )

        return calculate_global_canvas_bounds(snapshots, image_loader, auto_crop)
    except Exception:
        return None


def create_snapshot_frame_renderer_direct(*args: Any, **kwargs: Any):
    """Direct ``snapshot_frame_renderer`` without ``create_startup_service``.

    Mirrors ``tabs.image_compare.service_factory`` ``snapshot_frame_renderer``
    branch but as an importable factory for tab-internal use. Host startup
    wiring (``ui`` composition) keeps ``create_startup_service``.
    """
    try:
        from tabs.image_compare.services.video_snapshot_rendering import (
            SnapshotFrameRenderer,
        )

        return SnapshotFrameRenderer(*args, **kwargs)
    except Exception:
        return None
