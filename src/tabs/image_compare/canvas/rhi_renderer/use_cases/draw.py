# Audit-Meta: pattern=thin-owner-target size=exempt reason="draw submit extracted from RhiCanvasRenderer — see renderer.py Audit-Meta state-machine"
"""Draw submit extracted from ``RhiCanvasRenderer`` (CODE_PATTERNS thin owner).

``RhiCanvasRenderer.render()``'s draw-submit block (~130 LOC) lived inside
``renderer.py`` as part of the 1611-line state-machine. This module holds the
same body as plain functions taking the owning renderer as first arg — the
owner keeps construction/wiring + instance state (``rhi/resources/tile_service``
etc.) per CODE_PATTERNS.md:25, thin owner keeps frame sequencing.

Extracted segment: ``ensure_array_pipeline``/``pack_array_uniforms``/
``pack_array_instance``/``beginPass/draw/endPass`` + ``active_feature_passes``
gating + ``requires_content`` blank gate — formerly the tail of
``RhiCanvasRenderer.render``. Feature pass ``prepare``/``record_pre_pass`` flow is
preserved verbatim so divider/filename still suppress until
``array_draw_plan`` non-empty.
"""

from __future__ import annotations

from contextlib import nullcontext

from ui.canvas_infra.rhi.render_executor import iter_active_render_passes

from engine.frame.context import FrameContext, make_ids
from engine.gpu.array_draw import (
    ARRAY_INSTANCE_STRIDE as _ARRAY_INSTANCE_STRIDE,
    ArrayInstance,
    pack_array_instance,
    record_array_draw,
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


#: ``base_array.frag`` diff-mode index whose sampling is clamp-based, not
#: discard-gated: mode 4 (SSIM/diff-source) skips the ``inTile1``/``inTile2``
#: discard and clamps out-of-tile UVs instead. A fullscreen instance-0 then
#: samples ClampToEdge-smeared edge texels across the whole canvas instead
#: of being clipped to its own tile.
_SSIM_CLAMP_SAMPLING_MODE = 4


def resolve_instance_bbox(
    index: int,
    item_bbox: tuple[float, float, float, float],
    *,
    clamp_sampling: bool,
) -> tuple[float, float, float, float]:
    """Instance ``index``'s geometry clip: fullscreen for the fill instance.

    Index 0 is forced fullscreen so ``canvasLetterbox``/``letterboxFill``'s
    pillarbox background-fill (uniforms-only, no per-instance data) still
    paints — every other instance keeps its real footprint and relies on the
    fragment shader's per-pixel tileUV discard to clip down. The exception
    is clamp sampling (SSIM mode): with no discard to clip it, a fullscreen
    instance-0 would smear, so it keeps its real bbox there too (pillarbox
    fill in that mode falls back to the clear color — correct content wins
    over fill). Pure over inputs.
    """
    if index == 0 and not clamp_sampling:
        return (0.0, 0.0, 1.0, 1.0)
    return item_bbox


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
    submit block.

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

    # Feature-pass gating — identical to the pre-split ``RhiCanvasRenderer.render``
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

    # Build the logical per-instance draw data for the shared engine core.
    # ``bbox`` is resolved here -- index 0 is forced fullscreen so the
    # uniforms-only pillarbox fill still paints, except in SSIM clamp-
    # sampling mode (diff_mode 4 + diff source ready) where the frag has no
    # discard to clip a fullscreen instance back down; see
    # resolve_instance_bbox. The engine's record core only packs and records.
    _clamp_sampling = False
    if array_draw_plan:
        _diff_mode_int = 0
        if _base_image is not None:
            try:
                _diff_mode_int = int(getattr(_base_image, "diff_mode_int", 0) or 0)
            except (TypeError, ValueError):
                _diff_mode_int = 0
        _clamp_sampling = _diff_mode_int == _SSIM_CLAMP_SAMPLING_MODE and bool(_diff_ready)

    instances = [
        ArrayInstance(
            rect1=item.rect1,
            rect2=item.rect2,
            content_scale=item.content_scale,
            content_scale_diff=item.content_scale_diff,
            layer1=item.layer1,
            layer2=item.layer2,
            layer_diff=item.layer_diff,
            bbox=resolve_instance_bbox(
                index, item.bbox, clamp_sampling=_clamp_sampling
            ),
            rect_diff=item.rect_diff,
            sampler_name=item.sampler_name,
        )
        for index, item in enumerate(array_draw_plan)
    ]

    # One fixed-size uniform block (no per-item dynamic offsets -- array-path
    # uniforms carry no per-item data, see pack_array_uniforms). Written by
    # the engine core pre-pass so it lands in the same frame-in-flight
    # rotation slot a same-pass read would use (writing mid-pass is not
    # guaranteed to, on Vulkan/D3D/Metal backends -- see
    # docs/dev/rendering/investigations/multitile-uniform-desync.md).
    uniform_bytes = None
    if _base_image is not None:
        uniform_bytes = pack_array_uniforms(
            renderer.rhi, _base_image, diff_source_ready=bool(_diff_ready)
        )

    # Phantom-hunt (ic-right-image-vanish): submit-vs-plan discriminator.
    # Compares the layer2 actually packed into instance_bytes against
    # plan[i].layer2 over ALL entries (first-3 sampling can miss a dup in a
    # 2x2x2 plan). match=True -> submit faithful, corruption (if any) is
    # upstream in the plan; match=False -> pack-corruption. Change-gated via
    # throttle stream: silent on steady frames. No behavior change: packing
    # here is debug-only (the engine core packs for the real upload) and the
    # result is read-only inspection of those bytes.
    try:
        if _draw_preview_enabled() and instances:
            instance_bytes = b"".join(
                pack_array_instance(inst) for inst in instances
            )
            _n_inst = len(instance_bytes) // _ARRAY_INSTANCE_STRIDE
            if _n_inst == len(instances) and _n_inst > 0:
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

    # Feature-pass work runs through the engine record core's callbacks:
    # prepare/record_pre_pass before the pass opens (some passes run their
    # own beginPass/endPass pairs into textures of their own here -- QRhi
    # passes can't nest), feature record inside the open pass.
    def _pre_begin() -> None:
        for render_pass in active_feature_passes:
            render_pass.prepare(widget, ctx, updates)
        for render_pass in active_feature_passes:
            # Some test fakes may not implement record_pre_pass
            if hasattr(render_pass, "record_pre_pass"):
                render_pass.record_pre_pass(command_buffer, widget, ctx)

    def _in_pass() -> None:
        for render_pass in active_feature_passes:
            render_pass.record(command_buffer, widget, ctx)

    # Use target for pipeline creation; original used widget.renderTarget()
    # which is the same object as ``target`` captured at render start.
    _target_for_pipeline = target if target is not None else widget.renderTarget()

    # Main pass — exactly as before. Perf spans (Wave C): the submit hop of
    # the wheel-to-photon chain (span/record only). None-safe: callers
    # without a frame_context skip the span, not the draw.
    _submit_cm = (
        frame_context.span(
            "ic.submit",
            detail=lambda: {"entries": len(array_draw_plan)},
        )
        if frame_context is not None
        else nullcontext()
    )
    _began = True
    _ended = True
    with _submit_cm:
        record_array_draw(
            command_buffer,
            resources=renderer.resources.array_resources,
            vertex_buffer=renderer.resources.vertex_buffer,
            instances=instances,
            uniform_bytes=uniform_bytes,
            target=_target_for_pipeline,
            clear_color=clear_color,
            updates=updates,
            pre_begin=_pre_begin,
            in_pass=_in_pass,
        )

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
