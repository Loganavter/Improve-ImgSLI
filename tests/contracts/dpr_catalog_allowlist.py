"""Allowlist for ``test_dpr_defect_catalog.py`` — shrink-only, never rot.

Every entry is ``(rel_path, function_name, rule_id) -> reason``. An entry means
"This shape is LEGITIMATE here, and this is the measurement that proves it".

A real bug does **not** belong here — it goes into ``KNOWN_DEFECTS`` in
``test_dpr_defect_catalog.py`` with a task id, so it stays visible in every run
and expires when the fix lands. Mixing the two would turn the gate into a place
where defects go to be forgotten.

The gate has a separate test that fails when an entry:

* has an empty reason (it would hide the gate without saying why),
* names a file that no longer exists, or
* no longer matches a real hit (the code was fixed/renamed and the entry rotted
  into a blanket exemption for that function).

So the only two legal moves on this file are "add an entry with the measured
reason the shape is correct here" and "delete an entry the gate no longer
needs". Never widen an entry to cover a neighbouring function.

Rule ids and what each one means live in ``test_dpr_defect_catalog.py``'s module
docstring and in ``docs/dev/rendering/dpr-failure-modes.md``.

Shrunk so far: the three defects of the 2026-10-27/28 wave (#751 drop overlay,
#752 Quick Look clip correction, #755 capture) need **no** entry — the fixes
removed the shapes instead of hiding them.
"""

from __future__ import annotations

DPR_ALLOWLIST: dict[tuple[str, str, str], str] = {
    # --- silent-downsample ---------------------------------------------------
    ("src/engine/gpu/export_tiling.py", "_read_frame", "silent-downsample"): (
        "the resample branch is reachable ONLY with fit_framebuffer=False, i.e. "
        "image_compare's legacy logical-space surface, and resolve_export_framebuffer "
        "has already logged it as 'downscaling supersampled legacy logical-space "
        "surface'. A fitted surface (multi_compare) never reaches it: the same "
        "function raises ExportFramebufferMismatch instead, which is the #756 rule."
    ),
    (
        "src/plugins/export/services/gpu_export_proxy.py",
        "_render_plan_frame_single",
        "silent-downsample",
    ): (
        "image_compare's tiled export deliberately renders into a LOGICAL-space "
        "surface and therefore reads back a DPR-supersampled grab, then "
        "downscales it to the plan's widget size: supersampling is the contract "
        "there, not a units bug (#756 measured both paths and pinned this one as "
        "intentional, with engine/gpu/export_tiling.py logging the downscale). "
        "multi_compare is the side that had the units bug and it no longer "
        "downscales at all (export_surface_size + ExportFramebufferMismatch)."
    ),

    # --- clip-matrix-literal -------------------------------------------------
    ("src/devtools/canvas_scene/multi_compare.py", "_mc_transform", "clip-matrix-literal"): (
        "devtools scene dump builds a synthetic render context with an empty "
        "clip_matrix: it is the dump harness, not a pass, and the empty tuple is "
        "how it says 'no context matrix' -- the real passes fall back to "
        "engine/gpu/rt_y_orientation.composited_clip_correction"
    ),
    # --- viewport-logical ----------------------------------------------------
    ("src/engine/overlay/shell.py", "draw", "viewport-logical"): (
        "the overlay shell IS the GPU seam: draw(width=, height=) is documented "
        "as framebuffer px and every caller passes a device size "
        "(framing.framebuffer_size / ctx.framebuffer_size -- see grid_dividers, "
        "focus_dim, layer_labels). The shell owns no logical geometry, so there "
        "is nothing to derive a size from here"
    ),
    ("src/engine/overlay/textured.py", "draw", "viewport-logical"): (
        "same seam as engine/overlay/shell.py::draw: the textured shell draws "
        "its uploaded raster 1:1 and the caller owns the device-pixel size"
    ),
    ("src/engine/gpu/mip_cascade.py", "_render_orientation_probe", "viewport-logical"): (
        "the SAMPLED_RT self-calibration probe renders into its own FIXED "
        "_ORIENTATION_PROBE_PX scratch target, which is a device-pixel size by "
        "construction (a module constant, not a widget-derived logical size) -- "
        "there is no framebuffer to ask"
    ),
    # --- ratio-dropped-on-copy -----------------------------------------------
    ("src/plugins/help/icons.py", "_mask_pixmap", "ratio-dropped-on-copy"): (
        "measured: QIcon.pixmap(QSize) returns devicePixelRatio()==1.0 even at "
        "QT_SCALE_FACTOR=2 (Qt 6.11.2 pins 1.0 in the one-arg overload), so the "
        "source and the QPixmap(source.size()) copy agree. Latent, not live: the "
        "hardening is one line (mirror the gallery sibling's "
        "setDevicePixelRatio(...)) -- see FINDING in the wave's DONE.md"
    ),
    ("src/plugins/export/dialog.py", "_apply_preview_pixmap", "ratio-dropped-on-copy"): (
        "the preview source is either PIL-derived (QImage->QPixmap, ratio 1.0) "
        "or a caller pixmap whose scaled copy keeps its ratio (measured on "
        "6.11.2: QPixmap.scaled preserves devicePixelRatio) while this composed "
        "frame is 1.0. Latent, and it is a LABEL preview that Qt scales, not an "
        "exported raster -- see FINDING in the wave's DONE.md"
    ),
    ("src/ui/main_window/runtime.py", "_build_rhi_resize_shield_pixmap", "ratio-dropped-on-copy"): (
        "a SOLID-COLOUR resize shield, not a copy of pixels: rhi.size() is "
        "logical and that is what the widget paints the shield at, so a flat "
        "fill loses nothing when Qt upscales it. The pixel path above uses "
        "QPixmap.fromImage(grabFramebuffer()), which keeps the frame's ratio"
    ),
    # --- ratio-hardcoded -----------------------------------------------------
    ("tests/devtools/test_capture_dpr_units.py", "<test>", "ratio-hardcoded"): (
        "the literal 2.0 is the ratio THIS test planted two lines above "
        "(grab.setDevicePixelRatio(2.0)); comparing against devicePixelRatioF() "
        "there would make the assertion tautological. A literal is only "
        "acceptable when the fixture set it -- see the negative fixture "
        "legal_ratio_compare_own_input.py"
    ),
    # --- uv-flip-compensation ------------------------------------------------
    ("src/engine/gpu/shaders/glass_panel/glass_composite.frag", "<shader>", "uv-flip-compensation"): (
        "`clamp(1.0 - vUv.y, 0, 1)` here is the WEIGHT of a top glow (pow 8), "
        "not a raster flip: it is a cosmetic gradient parameter that happens to "
        "be written in UV space. No pixel is mirrored; the copy/readback row "
        "order is handled by WIDGET_TEXTURE in glass_blur.frag"
    ),
}
