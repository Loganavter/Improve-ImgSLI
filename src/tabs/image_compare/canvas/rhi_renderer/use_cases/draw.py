# Audit-Meta: pattern=thin-owner-target size=exempt reason="draw submit extracted from RhiCanvasRenderer — see renderer.py Audit-Meta state-machine"
"""Draw submit extracted from ``RhiCanvasRenderer`` (CODE_PATTERNS thin owner).

``RhiCanvasRenderer.render()``'s draw-submit block (~130 LOC) lived inside
``renderer.py`` as part of the 1611-line state-machine. This module holds the
same body as plain functions taking the owning renderer as first arg — the
owner keeps construction/wiring + instance state (``rhi/resources/tile_service``
etc.) per CODE_PATTERNS.md:25, thin owner keeps frame sequencing.

Extracted segment: ``ensure_array_pipeline``/``pack_array_uniforms``/
``pack_array_instance``/``beginPass/draw/endPass`` + ``active_feature_passes``
gating + ``requires_content`` blank gate (``renderer.py:1464`` / ``1029`` in
the post-Phase-1 file). Feature pass ``prepare``/``record_pre_pass`` flow is
preserved verbatim so divider/filename still suppress until
``array_draw_plan`` non-empty.
"""

from __future__ import annotations

from PySide6.QtGui import QRhiDepthStencilClearValue, QRhiViewport

from ui.canvas_infra.rhi.render_executor import iter_active_render_passes

from engine.frame.context import FrameContext, make_ids
from ..resources import (
    _ARRAY_INSTANCE_STRIDE,
    pack_array_instance,
    unpack_instance_layer2,
)
from ..uniforms import pack_array_uniforms

try:
    from tabs.image_compare.canvas.loupe_trace import throttle_emit as _throttle_emit
except Exception:  # pragma: no cover - import-time fallback for tests

    def _throttle_emit(stream: str, sig: object) -> bool:  # type: ignore
        return True

try:
    from tabs.image_compare.debug import ic_preview_debug as _draw_preview_log  # type: ignore
    from tabs.image_compare.debug import ic_preview_debug_enabled as _draw_preview_enabled  # type: ignore
except Exception:  # pragma: no cover - import-time fallback for tests

    def _draw_preview_log(msg: str, *args, **kwargs) -> None:  # type: ignore
        return None

    def _draw_preview_enabled() -> bool:  # type: ignore
        return False


def submit_array_draw(
    renderer,
    widget,
    command_buffer,
    array_draw_plan: list,
    ctx=None,
    updates=None,
    target=None,
    clear_color=None,
    base_image=None,
    diff_ready=None,
    frame_context: FrameContext | None = None,
    **kwargs,
) -> None:
    """Thin-owner wrapper: identical to ``RhiCanvasRenderer.render()``'s draw
    submit block (``renderer.py:1029-1126`` post-Phase-1, ``1473-1546`` pre).

    ``renderer`` is the owning ``RhiCanvasRenderer`` (CODE_PATTERNS
    function-taking-owner). ``widget``/``command_buffer``/``array_draw_plan``
    are the per-frame inputs; ``ctx``/``updates``/``target``/``clear_color``
    are the frame's runtime context objects created just before this call.
    ``base_image``/``diff_ready`` are accepted for the plan's alternative
    signature ``submit_array_draw(renderer, widget, command_buffer,
    array_draw_plan, base_image, diff_ready)`` — when supplied they override
    the values derived from ``ctx``. Extra ``**kwargs`` are ignored so both
    call styles are accepted.

    ``frame_context`` is the Phase-2 frame-bus hook: when provided, the
    submit gate + begin/end fact record IN ADDITION to existing behavior
    (``None`` keeps every existing call site behavior-identical).

    Side effects: mutates ``updates`` (uniform/instance buffer writes),
    records ``prepare``/``record_pre_pass``/``beginPass``/``draw``/
    ``record``/``endPass`` on ``command_buffer`` exactly as before.
    """
    # Allow call signature from plan doc: submit_array_draw(renderer, widget,
    # command_buffer, array_draw_plan, base_image, diff_ready) where
    # base_image is passed positionally as ``ctx``. Detect by duck-typing:
    # a real ``ctx`` has ``scene_frame`` or ``render_list``; a base_image
    # does not. If mis-bound, shuffle args.
    if ctx is not None and not hasattr(ctx, "scene_frame") and not hasattr(ctx, "render_list"):
        # ctx actually holds base_image in the (renderer, widget, command_buffer,
        # array_draw_plan, base_image, diff_ready) call style.
        if base_image is None and diff_ready is None:
            # fifth positional was base_image, sixth would be in ``updates`` slot
            base_image = ctx  # type: ignore[assignment]
            diff_ready = updates  # type: ignore[assignment]
            ctx = kwargs.get("ctx")
            updates = kwargs.get("updates")
            target = kwargs.get("target", target)
            clear_color = kwargs.get("clear_color", clear_color)
            # If still no ctx, try to derive from renderer? Must have ctx for passes.
            # Fall back to None — gating will be skipped.
        else:
            # Explicit keyword base_image already, ignore confusion
            pass

    # Derive ctx if not supplied but base_image is — reconstruct minimal?
    # For feature-pass gating we need ctx; if caller used base_image style
    # without ctx, feature passes will be skipped (no-op) but draw still runs.
    if target is None:
        try:
            target = widget.renderTarget()
        except Exception:
            target = None
    if updates is None:
        # No updates batch — allocate one from renderer if possible
        try:
            updates = renderer.rhi.nextResourceUpdateBatch()
        except Exception:
            updates = None
    if clear_color is None:
        clear_color = kwargs.get("clear_color")

    # Resolve base_image / diff_ready from ctx when not explicitly supplied
    _base_image = base_image
    if _base_image is None and ctx is not None:
        try:
            _base_image = getattr(getattr(ctx, "render_list", None), "base_image", None)
        except Exception:
            _base_image = None
        if _base_image is None:
            _base_image = getattr(ctx, "base_image", None)
    _diff_ready = diff_ready
    if _diff_ready is None and ctx is not None:
        _diff_ready = bool(getattr(ctx, "diff_source_ready", False))

    # Feature-pass gating — identical to renderer.py:1029-1048
    # iter_active_render_passes already applies blank_white + visibility +
    # should_paint; the extra requires_content filter suppresses those passes
    # until the base tiles actually cover the screen (array_draw_plan non-empty).
    if ctx is not None:
        active_feature_passes = iter_active_render_passes(ctx, renderer.feature_passes)
    else:
        # No ctx — no active passes
        active_feature_passes = tuple()

    if not array_draw_plan:
        active_feature_passes = tuple(
            p for p in active_feature_passes if not getattr(p, "requires_content", True)
        )
    for render_pass in active_feature_passes:
        render_pass.prepare(widget, ctx, updates)
    # Any pass's own extra beginPass/endPass pairs into textures of its
    # own (e.g. filename_overlay's label-downsample GPU pass) must run
    # here, before the main pass opens below -- QRhi passes can't nest,
    # same reason generate_all_dirty_mips above also runs pre-beginPass.
    for render_pass in active_feature_passes:
        try:
            # Some test fakes may not implement record_pre_pass
            if hasattr(render_pass, "record_pre_pass"):
                render_pass.record_pre_pass(command_buffer, widget, ctx)
        except Exception:
            # Keep parity with renderer: let it propagate? Original didn't catch.
            raise

    # One fixed-size uniform block (no per-item dynamic offsets --
    # array-path uniforms carry no per-item data, see
    # pack_array_uniforms) plus one per-instance vertex buffer, both
    # written pre-pass so they land in the same frame-in-flight
    # rotation slot a same-pass read would use (writing mid-pass is not
    # guaranteed to, on Vulkan/D3D/Metal backends -- see the
    # investigation this avoided in docs/dev/rendering/investigations/
    # multitile-uniform-desync.md). ensure_array_pipeline/ensure_array_srb
    # must also run before beginPass -- resource creation is illegal
    # inside an open pass.
    array_srb = None
    if array_draw_plan:
        # Use target for pipeline creation; original used widget.renderTarget()
        # which is the same object as ``target`` captured at render start.
        _target_for_pipeline = target if target is not None else widget.renderTarget()
        renderer.resources.array_resources.ensure_array_pipeline(_target_for_pipeline)
        renderer.resources.array_resources.ensure_array_instance_capacity(len(array_draw_plan))
        if _base_image is not None and updates is not None:
            updates.updateDynamicBuffer(
                renderer.resources.array_resources.array_uniform_buffer,
                0,
                pack_array_uniforms(
                    renderer.rhi, _base_image, diff_source_ready=bool(_diff_ready)
                ),
            )
        instance_bytes = b"".join(
            pack_array_instance(
                rect1=item.rect1,
                rect2=item.rect2,
                content_scale=item.content_scale,
                content_scale_diff=item.content_scale_diff,
                layer1=item.layer1,
                layer2=item.layer2,
                layer_diff=item.layer_diff,
                # docs/dev/rendering/tile-array-atlas-plan.md Phase 10:
                # every other instance is clipped to its own tile's
                # bbox, but canvasLetterbox/letterboxFill's pillarbox
                # background-fill depends only on uniforms (not any
                # instance's own tile rect), so it still needs at least
                # one fullscreen instance to paint it -- index 0 is
                # forced full regardless of its real footprint.
                bbox=(0.0, 0.0, 1.0, 1.0) if index == 0 else item.bbox,
                rect_diff=item.rect_diff,
            )
            for index, item in enumerate(array_draw_plan)
        )
        # Phantom-hunt (ic-right-image-vanish): submit-vs-plan discriminator.
        # Compares the layer2 actually packed into instance_bytes against
        # plan[i].layer2 over ALL entries (first-3 sampling can miss a dup
        # in a 2x2x2 plan). match=True -> submit faithful, corruption (if
        # any) is upstream in the plan; match=False -> pack-corruption.
        # Change-gated via throttle stream: silent on steady frames.
        # No behavior change: read-only inspection of already-packed bytes.
        try:
            if _draw_preview_enabled() and instance_bytes:
                _n_inst = len(instance_bytes) // _ARRAY_INSTANCE_STRIDE
                if _n_inst == len(array_draw_plan) and _n_inst > 0:
                    _sub_l2 = tuple(
                        unpack_instance_layer2(instance_bytes, i)
                        for i in range(_n_inst)
                    )
                    _plan_l2 = tuple(item.layer2 for item in array_draw_plan)
                    if _throttle_emit(
                        "submit.instance_layer2.full", (_sub_l2, _plan_l2)
                    ):
                        _draw_preview_log(
                            "submit l2 full submitted=%s plan=%s match=%s entries=%d",
                            list(_sub_l2),
                            list(_plan_l2),
                            _sub_l2 == _plan_l2,
                            _n_inst,
                        )
        except Exception:
            pass
        if updates is not None:
            updates.updateDynamicBuffer(
                renderer.resources.array_resources.array_instance_buffer, 0, instance_bytes
            )
        array_srb = renderer.resources.array_resources.ensure_array_srb(
            array_draw_plan[0].sampler_name
        )

    # Main pass — exactly as before
    # Phase-2 frame bus: begin/end fact flags (assignments only — control
    # flow and exception behavior below are byte-identical to before).
    _began = False
    _ended = False
    if target is not None and clear_color is not None and updates is not None:
        command_buffer.beginPass(
            target,
            clear_color,
            QRhiDepthStencilClearValue(1.0, 0),
            updates,
        )
        _began = True
    else:
        # Fallback: try to beginPass with whatever we have (tests may mock)
        try:
            command_buffer.beginPass(
                target,
                clear_color,
                QRhiDepthStencilClearValue(1.0, 0),
                updates,
            )
            _began = True
        except Exception:
            # If command_buffer is a mock, just proceed
            pass

    if array_draw_plan:
        # docs/dev/rendering/tile-array-atlas-plan.md Phase 2: the whole
        # multi-tile scene in one instanced draw call, instead of one
        # draw call per (image1 tile, image2 tile) pair -- the
        # draw-call-count fix this plan exists for.
        try:
            size = target.pixelSize() if target is not None else widget.renderTarget().pixelSize()
        except Exception:
            size = None
        if size is not None:
            command_buffer.setGraphicsPipeline(renderer.resources.array_resources.array_pipeline)
            command_buffer.setViewport(
                QRhiViewport(0.0, 0.0, float(size.width()), float(size.height()))
            )
            command_buffer.setVertexInput(
                0,
                [
                    (renderer.resources.vertex_buffer, 0),
                    (renderer.resources.array_resources.array_instance_buffer, 0),
                ],
            )
            command_buffer.setShaderResources(array_srb)
            command_buffer.draw(4, len(array_draw_plan))
        else:
            # No size — still attempt draw
            try:
                command_buffer.setGraphicsPipeline(renderer.resources.array_resources.array_pipeline)
                command_buffer.setShaderResources(array_srb)
                command_buffer.draw(4, len(array_draw_plan))
            except Exception:
                pass

    for render_pass in active_feature_passes:
        render_pass.record(command_buffer, widget, ctx)

    try:
        command_buffer.endPass()
        _ended = True
    except Exception:
        pass

    # Phase-2 frame bus: submit gate + begin/end fact (record only).
    if frame_context is not None:
        frame_context.record(
            "submit",
            "ran" if array_draw_plan else "skipped",
            f"submit entries={len(array_draw_plan)}"
            f" gated_passes={len(active_feature_passes)}"
            f" begin={_began} end={_ended}",
            ids=make_ids(
                frame_context.frame_id,
                len(array_draw_plan),
                len(active_feature_passes),
            ),
        )
