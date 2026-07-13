# Known bugs / Qt quirks

Confirmed, root-caused platform/framework quirks worth remembering so we
don't re-diagnose them from scratch. Bugs with a long investigation trail
get their own doc, linked from here; this file is the index plus anything
too small to deserve a standalone doc.

## Qt: `setPalette()` + `setAutoFillBackground(True)` unreliable for bare leaf `QWidget`s

**Status:** root-caused and fixed at every known call site; mechanism
inside Qt is still not understood.

Repainting a widget's background via the "implicit" Qt path —
`pal = self.palette(); pal.setColor(role, color); self.setPalette(pal);
self.setAutoFillBackground(True)`, then relying on Qt's own
`QWidgetPrivate::paintBackground()` step before `paintEvent` — turned out
to be unreliable in this app for widgets with no children of their own.
Symptom: the widget's on-screen color visibly "warms up" — it takes 2-3
repeated `on_theme_changed()` triggers (theme toggled back and forth)
before it starts repainting correctly every time. A single theme switch
does not reliably repaint.

Confirmed via `QWidget.grab()` (an offscreen render independent of what's
actually presented on screen): the *pixmap itself*, not just the on-screen
presentation, contained stale pixels. That ruled out compositor/Wayland/
presentation-layer theories — the bug is in Qt's own repaint pipeline for
this app, not in how the frame gets displayed.

**Fix:** don't rely on the implicit path. Override `paintEvent()` and
paint the background explicitly:

```python
def paintEvent(self, event) -> None:
    painter = QPainter(self)
    painter.fillRect(self.rect(), self._bg_color)
    painter.end()

def on_theme_changed(self) -> None:
    self._bg_color = QColor(resolve_theme_color(self._theme_manager, "Window"))
    super().on_theme_changed()  # still calls self.update()
```

This repaints correctly on the very first theme switch, no warm-up.

**Why this wasn't caught by Qt itself / why it happens**: unknown. Initial
theory was "widgets with child widgets get their background flushed as a
side effect of their children's repaints, bare leaf widgets don't" — but
`ThemedBackgroundContainer` instances (which do have child widgets/layouts:
`selection_widget`, `save_buttons_widget`, etc.) were affected too, and
`SessionPickerWidget` (also with many children) apparently was not. So
"has children" isn't the deciding factor either. Root Qt-internal mechanism
still unknown — if we ever find it, replace this paragraph and reconsider
whether the explicit-`paintEvent` fix is still necessary everywhere or was
only masking a narrower issue.

**Confirmed fixed:**
- `src/tabs/multi_compare/ui/toolbar.py` (`MultiCompareToolbar`)
- `src/tabs/multi_compare/ui/footer.py` (`MultiCompareFooter`)
- `src/tabs/image_compare/widget.py` (`ImageCompareWidget`) — the tab's
  root widget. Fixed for consistency, but turned out **not** to be what
  the user was actually seeing broken (see below) — its own background is
  fully covered by children, so this fix alone was invisible in the UI.
- `src/ui/widgets/themed_container.py` (`ThemedBackgroundContainer`) —
  **this was the actual fix for the visible image_compare bug.** All of
  image_compare's toolbar-like bars (`selection_widget`, `checkbox_widget`,
  `footer_info_widget`, `edit_layout_widget`, `save_buttons_widget` — see
  `src/tabs/image_compare/ui/layout.py`) are built from this one shared
  class, so fixing it here fixed every bar at once. Lesson: when a symptom
  spans several visually-similar bars, look for the shared base class
  before patching each call site's containing widget individually.
- `src/tabs/session_picker/widget.py` (`SessionPickerWidget`) — symptom
  never reproduced here, but converted anyway as a precaution once the
  pattern was known to be unreliable elsewhere; no functional change
  expected, just removes a latent risk.

See also [THEMING.md](THEMING.md#known-qt-quirk-dont-repaint-backgrounds-via-setpalette--setautofillbackground)
and the `ThemedWidget` mixin that now owns theme repaint for most chrome
widgets.

## Qt: light-gray fringe on rounded window corners over dark backgrounds (unresolved)

**Status:** not root-caused. One fix attempt applied, did not resolve it.

`MainWindow` (`src/ui/main_window/window.py`) is `WA_TranslucentBackground`
with custom-drawn rounded corners: `paintEvent()` fills a rounded
`QPainterPath` with `self._window_bg_color`, and `_apply_rounded_mask()`
deliberately calls `clearMask()` instead of a `QBitmap` mask (a 1-bit mask
has no antialiasing and chops the rounded edge into a staircase — see the
comment at `window.py:174-179`).

Symptom: when something dark is behind the window (dark wallpaper, another
dark window), the corner/edge pixels of the rounded window show up as
light gray instead of blending transparently — as if alpha isn't being
composited correctly right at the antialiased edge.

**Tried:** explicitly clearing the paint rect to `Qt.GlobalColor.transparent`
via `CompositionMode_Source` before drawing the rounded-rect brush in
`SourceOver` mode (theory: leftover non-transparent pixels in the backing
store were blending with the AA edge). This did **not** fix the symptom in
practice, so stale backing-store content is not the (whole) mechanism.

**Not yet tried / suspected**: the fringe may originate below the
`QPainter`/backing-store level — e.g. in how the windowing
system/compositor (X11/Wayland) or Qt's own platform integration
composites a translucent top-level surface's edge pixels, or in the QRhi
swapchain/surface format not actually carrying alpha the way a plain
`QWidget` backing store does. Needs investigation with a compositor-level
inspection (e.g. screenshot the raw surface alpha channel, or test under a
different platform plugin) rather than more `QPainter` composition-mode
tweaking.

## multi_compare: no host-memory bounding for large slot images, and export resolution hard-capped by real GPU texture limit

**Status:** confirmed via code inspection (2026-07-13), not fixed — tracked
as a TODO item, not a live incident.

`multi_compare` never got the large-image hardening that `image_compare`
has (see [tile-rendering-system.md](rendering/tile-rendering-system.md#host-side-memory-bounding)
and [TODO.md](TODO.md) "Bring multi_compare up to image_compare's
host-memory bounding"). Two separate, confirmed gaps:

**1. Loading a slot never wraps large images as lazy/memmap.**
`tabs/multi_compare/controller.py`'s `_read_image()` does
`Image.open(path).convert("RGB")` → `np.array(..., dtype=np.uint8)`
unconditionally — no size check, no `LazyPixelSource` wrap, no downscale.
`grep` for `LazyPixelSource`/`maybe_wrap_for_lazy_storage`/
`_texture_upload_cache` under `src/tabs/multi_compare/` returns nothing.
GPU-side tile eviction exists (`TileTextureService.evict_over_budget`,
`SLOT_TILE_CACHE_BUDGET_BYTES` in `scene/resources.py`) but there is no
equivalent host-side QImage cache budget. A single large image (e.g.
16000×16000px, ~768MB as an RGB numpy array) will load fine on its own on a
typical machine, but nothing ever evicts it, and there's no cap as more/
larger slots accumulate — the same unbounded-host-RAM shape of bug that
`LARGE_IMAGE_MEMORY_REFACTOR`'s Phase 2/3 fixed for `image_compare`, just
never ported here.

**2. Export resolution is genuinely capped by the real GPU max texture size — image_compare's isn't.**
`image_compare`'s exporter (`plugins/export/services/gpu_export_proxy.py`)
tiles the *output framebuffer* itself when the requested canvas exceeds
`min(_EXPORT_TILE_MAX_EXTENT=4096, query_max_texture_size(rhi))`
(`_render_plan_frame_tiled`): each tile is rendered and grabbed separately
via `grabFramebuffer()` and stitched into one PIL image on the CPU side, so
the final exported resolution is bounded only by host RAM/time, not by any
GPU texture/framebuffer size limit.

`multi_compare`'s exporter (`services/gpu_export.py`) does not do this — it
resizes the offscreen widget directly to the *entire* requested
`output_w`/`output_h` and does a single `grabFramebuffer()` call, with no
tiling and no call to `query_max_texture_size` at all. Requesting an export
resolution above the backend's real max texture/framebuffer size has no
graceful fallback — the swapchain/framebuffer just can't be created at that
size (silent failure or garbage frame, not a caught/reported error).

**Fix (not yet done):** port `image_compare`'s tiled-framebuffer export
pattern into `multi_compare/services/gpu_export.py`, and wire
`maybe_wrap_for_lazy_storage`/`close_if_lazy` (or a generalized host-cache
LRU, see the TODO item) into `multi_compare/controller.py`'s `_read_image`/
slot-load path.

## Qt/SVG: thin diagonal strokes render jagged and asymmetric at small icon sizes

**Status:** root-caused and fixed for the title-bar icons.

The window-control icons (`resources/assets/icons/{light,dark}/window_close.svg`
etc., consumed via `sli_ui_toolkit`'s `normalized_icon_pixmap()` → `QIcon.pixmap()`)
were originally authored at `viewBox="0 0 16 16"` with `stroke-width="1"`.
The close icon's diagonal (45°) lines looked visibly jagged/staircased and
asymmetric between the two crossing strokes — worse than the equivalent
`resources/assets/icons/*/close.svg` (used elsewhere in the app), which
looked crisp at the same on-screen size.

**Root cause:** a stroke drawn at a 45° angle has its *perpendicular*
rendered width reduced by a factor of `1/√2 (~0.71)` relative to its
nominal `stroke-width`. A nominal `1px` diagonal stroke therefore rasterizes
at effectively `~0.7px` — thin enough that anti-aliasing coverage splits
unevenly across the pixel grid, producing visible stepping and a
left/right (or up/down) brightness asymmetry between the two crossing
diagonal lines, even though the SVG source is geometrically symmetric.
`close.svg` happened to dodge this because it uses `viewBox="0 0 24 24"`
with `stroke-width="2"`, which after being scaled down to the ~16px
render target lands at an effective width of `~1.33px` — enough for even
antialiased coverage.

Things that did **not** fix it (ruled out along the way):
- Changing the icon color (gray → pure black/white).
- Re-centering the geometry / shrinking the margins.
- Snapping the `viewBox` to exactly match the render target size (`16`)
  so the render scale is 1:1 — this actually made it *worse* by removing
  the incidental upscaling that `close.svg` benefits from.

**Fix:** bump `stroke-width` on the diagonal-line icons (and, for
consistency, the other window-control icons) from `1` to `1.33` — matching
`close.svg`'s effective post-scale width. Rule of thumb going forward: any
icon with a 45°-diagonal stroke needs a nominal stroke-width around
`1.3–1.4×` what a horizontal/vertical stroke of the same visual weight
would use, especially at small render sizes (~16px) where there's little
margin for anti-aliasing to smooth over.

В том же стиле это можно оформить так. Основано на текущем документе .

## Startup: first launch takes 2–3 minutes on some low-end systems (unresolved)

**Status:** confirmed by user reports, not root-caused.

On some weaker machines the very first application launch after starting
the process can take **2–3 minutes** before the UI becomes usable.
Subsequent launches complete in a few seconds as expected.

The delay appears to affect only the initial startup path. Once the
application has finished launching, closing and reopening it does not
reproduce the issue until the next "cold" start.

**Current understanding:** unknown. No convincing hypothesis yet. The
bottleneck has not been isolated to a particular subsystem (Qt
initialization, plugin loading, GPU initialization, shader compilation,
filesystem scanning, configuration migration, etc.).

**TODO:** profile a cold startup on affected hardware and instrument the
startup sequence with timestamps around major initialization stages to
identify where the time is actually being spent before attempting any
optimization.

## Custom decorations: decoration list refresh does not update decoration icons

**Status:** confirmed, not investigated.

Refreshing the list of custom decorations correctly updates the available
decoration entries, but the preview icons associated with those
decorations remain stale. Newly added or modified icons are not reflected
in the UI.

The icons only update after a full application restart.

This suggests that the underlying decoration data is refreshed correctly,
while the corresponding icon cache/model/view is not invalidated or
reloaded.

**Fix:** unknown. The decoration icon cache (or the model supplying the
icons) likely needs to be explicitly invalidated when custom decorations
are refreshed.

## Video editor: preview overlaps the right-side controls in narrow windows

**Status:** confirmed, not investigated.

When the video editor window becomes too narrow, the preview area expands
into the space reserved for the right-hand control panel instead of
respecting the available layout width.

As a result, the preview renders underneath the controls, making both the
preview and the control panel partially unusable.

The layout does not appear to enforce an appropriate minimum width or
reallocate space once the available horizontal size falls below the
required threshold.

**Fix:** unknown. The layout should either enforce a minimum window width,
allow the preview to shrink appropriately, or switch to an alternative
layout once the available horizontal space becomes insufficient.
