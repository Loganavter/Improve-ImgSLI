# Investigation: divider detaches under zoom/pan

Symptom that started this write-up: at zoom ≈ 39% with pan, the **image
half-boundary** (seam inside the picture) stayed on the content, but the
**white/colored divider line** floated in the fit-zoom letterbox band — often
below / beside the zoomed image — while the magnifier stayed locked to the
picture on every axis.

This page is the durable lesson for future features. Short pointers also live
in [zoom-pan.md](../zoom-pan.md) and [coordinate-systems.md](../coordinate-systems.md).

## What was actually wrong (three stacked bugs)

### 1. Store spit was always camera-owned (including zoom ≤ 1)

`compute_zoom_split_position_for_view_transform` rewrote
`split_position_visual` on every pan/zoom so the **screen** spit stayed fixed.
At zoom-out that glued the line to the camera and could push values outside
content `[0, 1]` (reports of ~10).

**Rule (dual-mode):**

- `zoom <= 1`: leave store spit alone (content-anchored; line rides with image).
- `zoom > 1`: rewrite store spit (still clamped to `[0, 1]`) so the **screen**
  spit stays fixed while pan/zoom change — intentional “follow the camera”
  inspect/crop feel.

Never leave an unclamped camera rewrite in the store.
### 2. Image halves used screen spit; magnifier used content spit

`base.frag` compared `vTexCoord` (full-widget UV) to a **display** spit
uniform. Magnifier compared local `TexCoord` to content `internalSplit`.
That is why “magnifier is fine” was a red herring for the divider line, but
a correct clue for the **seam**: content-space spit is the robust model.

**Rule for image halves:** pass store `split_position_visual` into the base
shader and compare in **letterboxed image UV** (after unprojecting zoom/pan),
same idea as magnifier `internalSplit`. Do not bake pan/zoom into that
uniform.

### 3. Divider paint used fullscreen + QRhi content scissor

Even after spit math was fixed, the white line could still sit in the old
letterbox band:

- Position was `display_split * canvas_size` (axis only).
- Visibility was a **QRhi scissor** on `content_rect_px` (fit-zoom letterbox)
  or a Y-flipped transformed rect.
- Live magnifier often has `_clip_overlays_to_content_rect = False`, so it
  never hit that scissor path — another “magnifier OK, divider broken” trap.

**Rule for the white line:**

1. Map the fit-zoom letterbox through the camera with
   `map_content_rect_through_view` /
   `get_view_transformed_content_rect_widget_px`.
2. Place the line at `clip.origin + clip.size * spit` on the spit axis.
3. Clip in the **fragment shader** (`clipRectPx`), not with a live content
   `QRhiScissor`. Full-target scissor only.

`compute_zoom_display_split_position` remains useful as the shared
content→screen formula, but do **not** clamp it to `[0, 1]` (clamping pins
the line to the viewport edge while the image keeps moving). DividerPass
currently prefers the transformed-rect form above so position and clip share
one AABB.

## Coordinate cheat sheet

| Quantity | Space | Owner |
|---|---|---|
| `split_position_visual` | content `[0, 1]` along the comparison axis | Store; rewritten only when `zoom > 1` to hold screen spit fixed (clamped) |
| Base half choice | letterboxed image UV after camera unproject | `base.frag` + content spit uniform |
| Magnifier internal spit | local overlay UV | magnifier shaders / `internalSplit` |
| Fit-zoom letterbox | widget-px at zoom=1, pan=0 | `_inner_content_rect_px` / `_content_rect_px` |
| Visible image AABB after camera | widget-px | `map_content_rect_through_view` |
| White divider segment | widget-px inside that AABB | `DividerPass` + shader `clipRectPx` |

Camera inverse (same as `base.frag`):

```text
uv = (vTexCoord - 0.5) / zoom + 0.5 - pan
screen = (uv - 0.5 + pan) * zoom + 0.5
```

## UI naming trap

Toolbar icons: unchecked = vertical dividing line (`is_horizontal=False`,
spit on **X**); checked = horizontal line (`is_horizontal=True`, spit on **Y**).
Russian “вертикальный сплит” usually means the vertical **line**, not
top/bottom stacking. Confirm against icons before chasing an “X vs Y”
asymmetry in the wrong orientation branch.

## Anti-patterns for new features

- Rewriting semantic spit on pan/zoom when ``zoom <= 1`` (fit/zoom-out must
  stay content-anchored). Camera-anchored rewrite is intentional only for
  ``zoom > 1``, and must stay clamped to content ``[0, 1]``.
- Clamping a **display** mapping to `[0, 1]` when zoomed out — that pins the
  line to the viewport edge while the image keeps moving.
- Clipping a camera-moved overlay with the **fit-zoom** `content_rect_px`
  scissor (or trusting QRhi content scissor Y on the live widget without
  verifying against a known-good pass like magnifier).
- Treating “magnifier looks correct” as proof that DividerPass / base spit /
  scissor are correct — check whether that path uses the same clip and the
  same spit space.
- Diagnosing a floating **paint** segment as a store spit bug when the seam
  inside the image is already locked (or the reverse).

## Code map

| Piece | Location |
|---|---|
| Dual-mode store spit on view transform | `ui/canvas_infra/viewport/zoom.py` |
| Display spit formula (unclamped) | same |
| Letterbox → camera AABB | `ui/canvas_infra/viewport/geometry.py::map_content_rect_through_view` |
| Widget helper | `tabs/image_compare/canvas/render_config.py::get_view_transformed_content_rect_widget_px` |
| Content spit → base uniforms | `tabs/image_compare/canvas/render_context.py` |
| Half choice in UV | `tabs/image_compare/canvas/shaders/base.frag` |
| White line + shader clip | `tabs/image_compare/canvas/features/divider/` |

## Related

- [zoom-pan.md](../zoom-pan.md) — spit / pan invariants
- [coordinate-systems.md](../coordinate-systems.md) — content vs display spaces, scissor Y-flip notes
- [checklist.md](../checklist.md) — anti-patterns for review
