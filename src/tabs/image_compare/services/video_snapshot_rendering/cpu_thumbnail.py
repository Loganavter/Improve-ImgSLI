"""CPU filmstrip-tile composer — the GPU-free path for snapshot thumbnails.

A strip tile costs 15-30 ms warm on the owner's machine (measured
2026-10-29). ~1 ms is this tab-side CPU work; the rest is one offscreen GPU
round-trip per tile (``update()`` + ``processEvents``, one pass,
``grabFramebuffer`` readback, driver sync). The same tile composed in PIL from
the already-resolved pyramid proxies measures ~2.2 ms for two panes at 160x90
including split, channel and divider (``test_thumbnail_cpu_composite.py``
prints it), so the strip prefers this path whenever the snapshot carries
nothing a composite cannot reproduce.

The contract is fail-open in both directions:

* :func:`thumbnail_needs_gpu` answers True for any snapshot state this module
  cannot reproduce (magnifier/guides overlays, filename overlay, diff modes,
  single-image preview) and for any doubt at all.
* :func:`compose_thumbnail_cpu` returns ``None`` — "ask the GPU path" — on a
  missing proxy, an unknown mode, or any exception.

The composite mirrors the render-plan semantics the shader uses
(``canvas/shaders/base_array.frag``): both sides cover the whole tile, the
split clips at ``split_position_visual`` of the tile (top/left = image 1),
channel modes zero the other channels, and the divider is drawn centred on the
boundary exactly when the export overlay would show it. Diff images are built
by the render plan from both sources and single-image preview is not carried
by a snapshot at all, so both stay on the GPU path rather than being guessed.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from tabs.image_compare.services.video_snapshot_rendering.geometry import (
    cover_crop_box,
)
from ui.canvas_infra.viewport.geometry import resolve_axis_position

#: Divider defaults, mirroring ``DividerWidgetState`` in
#: ``tabs/image_compare/canvas/features/divider/state/feature_state.py``.
#: Shared code must not import a canvas feature module (contract
#: ``tests/contracts/test_canvas_features_imports.py``), and the render plan's
#: lazy getter would create exactly this state when a snapshot carries none —
#: so a snapshot without a divider entry still paints the same line.
_DIVIDER_DEFAULT_THICKNESS = 3
_DIVIDER_DEFAULT_RGBA = (255, 255, 255, 255)

#: Same resampler the cover helper defaults to (``geometry.cover_source_to_content``).
_COVER_FILTER = Image.Resampling.LANCZOS

#: ``channel_view_mode`` → shader int, mirroring ``canvas/scene.py``.
_CHANNEL_MODE_BY_NAME = {"RGB": 0, "R": 1, "G": 2, "B": 3, "L": 4}


def _source_size(source):
    """``(w, h)`` of a PIL image or a tiled store, or ``None``."""
    size = getattr(source, "size", None)
    if isinstance(size, tuple) and len(size) == 2:
        try:
            return int(size[0]), int(size[1])
        except (TypeError, ValueError):
            return None
    try:
        return int(source.width), int(source.height)
    except Exception:
        return None


def _as_pil(source):
    """Cheap PIL view of a proxy source (never a full-res decode).

    ``TiledPixelStore.as_pil_rgba()`` is a zero-copy view over the memmap; the
    following resize/crop copies out of it, so the store may be closed after
    this call returns. ``None`` on any doubt (closed store, unknown type).
    """
    if isinstance(source, Image.Image):
        return source if source.mode == "RGBA" else source.convert("RGBA")
    as_pil_rgba = getattr(source, "as_pil_rgba", None)
    if callable(as_pil_rgba):
        try:
            view = as_pil_rgba()
        except Exception:
            return None
        if isinstance(view, Image.Image):
            return view if view.mode == "RGBA" else view.convert("RGBA")
    return None


def _cover_pil(source, content_size):
    """Cover-fit ``source`` to exactly ``content_size`` as a PIL RGBA image.

    Same box as :func:`...geometry.cover_source_to_content` (shared
    :func:`cover_crop_box`), without the per-call ``TiledPixelStore``
    allocation that made the store-based helper ~11 ms per side.
    """
    cw, ch = int(content_size[0]), int(content_size[1])
    size = _source_size(source)
    if size is None:
        return None
    box = cover_crop_box(size, content_size)
    if box is None:
        return None
    tw, th, left, top = box
    image = _as_pil(source)
    if image is None:
        return None
    if image.size != (tw, th):
        image = image.resize((tw, th), _COVER_FILTER)
    return image.crop((left, top, left + cw, top + ch))


def _apply_channel(image: Image.Image, mode: int) -> Image.Image:
    """Per-pane channel view, mirroring the shader's ``applyChannel``."""
    if mode == 0:
        return image
    r, g, b, a = image.split()
    blank = Image.new("L", image.size, 0)
    if mode == 1:
        return Image.merge("RGBA", (r, blank, blank, a))
    if mode == 2:
        return Image.merge("RGBA", (blank, g, blank, a))
    if mode == 3:
        return Image.merge("RGBA", (blank, blank, b, a))
    luma = Image.merge("RGB", (r, g, b)).convert("L")
    return Image.merge("RGBA", (luma, luma, luma, a))


def _state_value(states, key):
    try:
        return states.get(key)
    except Exception:
        return None


def _divider_state(states):
    """``(visible, thickness, rgba)`` of the divider, canvas defaults filled in.

    The render plan lazily creates ``DividerWidgetState()`` (visible, white,
    3 px) when a view state carries no ``divider`` entry, so a snapshot
    without one still renders a divider through the GPU path — the composite
    must draw the same line instead of a seam. Values are read from the state
    object; the composer never mutates the shared view state the way the
    canvas lazy getter does.
    """
    state = _state_value(states, "divider")
    if state is None:
        return True, _DIVIDER_DEFAULT_THICKNESS, _DIVIDER_DEFAULT_RGBA
    color = getattr(state, "color", None)
    if color is None:
        rgba = _DIVIDER_DEFAULT_RGBA
    else:
        rgba = (
            int(getattr(color, "r", 255)),
            int(getattr(color, "g", 255)),
            int(getattr(color, "b", 255)),
            int(getattr(color, "a", 255)),
        )
    return (
        bool(getattr(state, "visible", True)),
        int(getattr(state, "thickness", _DIVIDER_DEFAULT_THICKNESS) or 0),
        rgba,
    )


def _feature_would_paint(states) -> bool:
    """True when a canvas feature state would add pixels the composite misses.

    ``magnifier``/``guides`` carry their enabled flag in the snapshot; an
    unknown feature state counts as painting when it says ``enabled`` (fail
    open), so a future overlay cannot silently lose its tile. Two documented
    exceptions: ``divider`` is reproduced here, and ``capture`` alone paints
    nothing (``CaptureRingPass.should_paint`` needs magnifier-instance rings
    that live in widget runtime state, never in a recorded snapshot) — the
    live canvas lazily creates the capture state with ``visible=True``, so
    gating on it would disable the CPU path for every snapshot.
    """
    for key, state in states.items():
        if key in ("divider", "capture"):
            continue
        if key == "magnifier":
            # Only the feature flag decides whether the loupe paints:
            # MagnifierWidgetState.enabled defaults to False while the live
            # canvas still carries a default instance model, so gating on
            # ``models`` disabled the CPU path for every real recording
            # (verified live 2026-10-29: a default session shows no loupe in
            # the canvas capture, yet the state holds one model).
            if bool(getattr(state, "enabled", False)):
                return True
            continue
        if bool(getattr(state, "enabled", False)):
            return True
    return False


def thumbnail_needs_gpu(snap) -> bool:
    """True when the snapshot carries state a CPU composite cannot reproduce.

    Pure function of the snapshot; any doubt (missing state, unreadable
    fields) answers True so the GPU path keeps today's tile.
    """
    try:
        viewport_state = getattr(snap, "viewport_state", None)
        view = getattr(viewport_state, "view_state", None)
        if view is None:
            return True
        if int(getattr(view, "showing_single_image_mode", 0) or 0) != 0:
            # Single-pane preview is widget-side in the live canvas (the same
            # picture is uploaded to both slots); a snapshot keeps both paths
            # and no split mapping, so guessing would drop a real pane.
            return True
        if str(getattr(view, "diff_mode", "off") or "off") != "off":
            # Diff images are built by the render plan from both sources;
            # the snapshot does not carry them.
            return True
        channel_name = str(getattr(view, "channel_view_mode", "RGB") or "RGB")
        if channel_name not in _CHANNEL_MODE_BY_NAME:
            return True
        if bool(getattr(view, "overlay_enabled", False)):
            return True
        render_config = getattr(viewport_state, "render_config", None)
        if bool(getattr(render_config, "include_file_names_in_saved", False)):
            return True
        states = getattr(view, "canvas_widget_state", None) or {}
        if not isinstance(states, dict):
            return True
        return _feature_would_paint(states)
    except Exception:
        return True


def _channel_mode(view):
    """Shader channel int, or ``None`` when the mode is unknown."""
    name = str(getattr(view, "channel_view_mode", "RGB") or "RGB")
    return _CHANNEL_MODE_BY_NAME.get(name)


def _draw_divider(tile, view, boundary, is_horizontal):
    """Centred divider line, matching ``splitter.export_overlay`` visibility."""
    states = getattr(view, "canvas_widget_state", None) or {}
    visible, thickness, rgba = _divider_state(states)
    if not visible or thickness <= 0:
        return tile
    if str(getattr(view, "diff_mode", "off") or "off") != "off":
        return tile
    w, h = tile.size
    axis_size = h if is_horizontal else w
    half = thickness // 2
    start = max(0, boundary - half)
    end = min(axis_size, start + thickness)
    if end <= start:
        return tile
    overlay = Image.new("RGBA", tile.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    if is_horizontal:
        draw.rectangle((0, start, w, end - 1), fill=rgba)
    else:
        draw.rectangle((start, 0, end - 1, h), fill=rgba)
    return Image.alpha_composite(tile, overlay)


def compose_thumbnail_cpu(
    snap, out_w, out_h, *, auto_crop=False, image1=None, image2=None
):
    """Compose one filmstrip tile on the CPU; ``None`` means "use the GPU".

    ``image1``/``image2`` are the already-resolved proxy stores (pyramid
    coarse level / decoded base — the P1 seam, never a fresh decode);
    ``auto_crop`` is already baked into them by the resolver and is accepted
    for call-site symmetry only.
    """
    del auto_crop
    if image1 is None or image2 is None:
        return None
    if thumbnail_needs_gpu(snap):
        return None
    try:
        view = snap.viewport_state.view_state
        width = max(1, int(out_w))
        height = max(1, int(out_h))
        cover1 = _cover_pil(image1, (width, height))
        cover2 = _cover_pil(image2, (width, height))
        if cover1 is None or cover2 is None:
            return None
        mode = _channel_mode(view)
        if mode is None:
            return None
        if mode:
            cover1 = _apply_channel(cover1, mode)
            cover2 = _apply_channel(cover2, mode)
        is_horizontal = bool(getattr(view, "is_horizontal", False))
        fraction = float(getattr(view, "split_position_visual", 0.5))
        axis_size = height if is_horizontal else width
        boundary = int(
            round(resolve_axis_position(0.0, float(axis_size), fraction))
        )
        boundary = max(0, min(axis_size, boundary))
        # Image 2 covers the whole tile, image 1 is clipped over it — the
        # shader's ``useFirst`` branch in sampler space.
        tile = Image.new("RGBA", (width, height), (0, 0, 0, 255))
        tile.paste(cover2, (0, 0))
        if boundary > 0:
            if is_horizontal:
                tile.paste(cover1.crop((0, 0, width, boundary)), (0, 0))
            else:
                tile.paste(cover1.crop((0, 0, boundary, height)), (0, 0))
        return _draw_divider(tile, view, boundary, is_horizontal)
    except Exception:
        return None
