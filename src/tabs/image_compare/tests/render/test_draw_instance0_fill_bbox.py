"""P2 canvas parity: instance-0 fullscreen fill vs frag-discard coupling.

``submit_array_draw`` forces instance 0 to a fullscreen bbox so the
uniforms-only pillarbox fill still paints. That is safe exactly when the
fragment shader's per-pixel tileUV discard clips the instance back to its
own tile — SSIM clamp-sampling mode (diff_mode 4 + diff source ready)
skips that discard and clamps instead, so a fullscreen instance-0 would
smear ClampToEdge texels across the whole canvas. ``resolve_instance_bbox``
keeps the real bbox in that mode, fullscreen everywhere else.
"""

from __future__ import annotations

from tabs.image_compare.canvas.rhi_renderer.use_cases.draw import (
    resolve_instance_bbox,
)

REAL = (0.1, 0.2, 0.3, 0.4)
FULL = (0.0, 0.0, 1.0, 1.0)


def test_instance0_fullscreen_in_discard_gated_modes():
    assert resolve_instance_bbox(0, REAL, clamp_sampling=False) == FULL


def test_instance0_keeps_real_bbox_in_ssim_clamp_mode():
    assert resolve_instance_bbox(0, REAL, clamp_sampling=True) == REAL


def test_nonzero_instances_always_keep_real_bbox():
    assert resolve_instance_bbox(1, REAL, clamp_sampling=False) == REAL
    assert resolve_instance_bbox(3, REAL, clamp_sampling=True) == REAL
