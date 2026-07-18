# Known bugs / Qt quirks

Confirmed, root-caused platform/framework quirks worth remembering so we
don't re-diagnose them from scratch. Bugs with a long investigation trail
get their own doc, linked from here; this file is the index plus anything
too small to deserve a standalone doc.

## PySide: app `eventFilter` + non-`QObject` watched (QRhi) — fixed (2026-07-18)

**Status:** fixed in `sli-ui-toolkit` tooltip interceptors.

Opening Video Editor (or any dialog while an RHI canvas is alive) could
raise `TypeError: QObject.eventFilter(QRhi, QEvent)` and then
`SystemError: QWidget returned NULL`. The app-level `PathTooltip`
interceptor is installed on `QApplication` and receives events for
non-`QObject` targets (notably `QRhi`). Calling `super().eventFilter`
with those arguments is rejected by PySide and corrupts further widget
construction.

**Fix:** if `watched` is not a `QObject`, return `False` without calling
`QObject.eventFilter`. Same for the per-widget interceptor.

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
- `src/tabs/session_picker/recent/shelf_chrome.py` (`OpaqueFillHost`) —
  recent-projects content well under translucent CSD. Palette autofill
  plus destroy/rebuild card grids punched see-through holes; the host
  paints explicitly and cards update in place by path identity.

See also [THEMING.md](THEMING.md#known-qt-quirk-dont-repaint-backgrounds-via-setpalette--setautofillbackground)
and the `ThemedWidget` mixin that now owns theme repaint for most chrome
widgets.

## Qt: CSD corner rounding / clipping

**Status:** paint-path + child masks (2026-07-15).

Opaque children (especially `CustomTitleBar.fillsRect` and full-bleed content)
were painting square pixels into the translucent corner regions. Top-level
`setMask` is often input-only on Wayland, so rounding relied on alpha:

- window body: `paint_rounded_window_background` (4 corners)
- title bar: `paint_top_rounded_background` (transparent outside top arcs)
- content hosts: `apply_bottom_rounded_mask` on `_startup_stack` / cover
- QSS for `#CustomTitleBar` is transparent (no square stylesheet fill)

Slight staircasing from 1-bit child masks is expected at low DPI.

Nested `OverlayScrollArea` viewport masks (default radius 8) on full-bleed
pages like Session Picker can leave black wedges in the bottom CSD corners
when content height changes in-place (e.g. recent shelf growing to a second
row). Those scrolls use `set_corner_radius(0)`; rounding stays on the window
paint path + host bottom masks.

## multi_compare: large slot images and tiled export — fixed (2026-07-15)

**Status:** fixed.

Multi Compare now loads slots via `TiledPixelStore.from_path` (memmap RGBA8,
same GEGL-style storage as image_compare). GPU residency crops per-tile from
the store (`crop_apron_tile` + `qimage_from_pixel_source`) instead of
keeping uncapped full QImages. Export uses shared `TiledFramebufferExporter`
when `output_w` or `output_h` exceeds `min(4096, query_max_texture_size(rhi))`.
Native composition canvas is uncapped; still-image export above
`AppConstants.EXPORT_TESTED_MAX_EDGE` (16384) shows an untested-resolution
warning instead of silently clamping.

See [tile-rendering-system.md](rendering/tile-rendering-system.md).

## QRhiWidget autofill fights Multi Compare zoom/pan presentation — fixed (2026-07-17)

**Status:** fixed.

Multi Compare zoom-reset (and zoom-then-pan) could leave a visually stale
frame even though ``render()`` already drew the new ``zoom``/``pan``. Image
Compare had a related "bounce" when a CSD dropdown micro-resize accidentally
forced a redraw.

**Root cause:** ``MultiCompareCanvasWidget`` enabled
``setAutoFillBackground(True)`` on the ``QRhiWidget``. Image Compare's canvas
no-ops that API. Autofill + palette clear can fight RHI texture compositing.

**Fix:** no-op ``setAutoFillBackground`` (same as IC); clear color stays in
the RHI pass. ``request_view_update()`` still does an immediate ``update()``
plus a next-tick pass after zoom/pan/reset so overlay hide cannot swallow the
first request.

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
would use, especially at small render sizes (~16px) where there is little
margin for anti-aliasing to smooth over.

## Startup: first launch takes 2–3 minutes on some low-end systems (partially mitigated)

**Status:** confirmed by user reports; code-side mitigation landed 2026-07-15.
Environmental cold-cache effects (OS page cache, `.pyc`, antivirus, GPU shader
cache on first process start) may still dominate on low-end Windows hardware.

On some weaker machines the very first application launch after starting
the process can take **2–3 minutes** before the UI becomes usable.
Subsequent launches complete in a few seconds as expected.

The delay appears to affect only the initial startup path. Once the
application has finished launching, closing and reopening it does not
reproduce the issue until the next "cold" start.

**Code-side mitigation (2026-07-15):** staged plugin/tab discovery — bootstrap
tier (`comparison`, `settings`, `layout`, `session_picker`) loads before the
main window; deferred tier (`export`, `video_editor`, `help`, `image_properties`,
`multi_compare`) loads after `startupVisualReady`. See
[PLUGINS.md](PLUGINS.md) and [ARCHITECTURE.md](ARCHITECTURE.md).

**Profiling on affected hardware:**

- Set `IMGSLI_STARTUP_TRACE=1` — logs monotonic timestamps for bootstrap phases
  (`ctx.plugins.bootstrap`, `startup.visual_ready`, `ctx.plugins.deferred`, …).
- Or run `python -X importtime src/__main__.py` and inspect the slowest imports.

**Still open:** confirm remaining delay on Win 2C/8GB after staged discovery;
further wins may require OS-level caching rather than app changes.

## Video editor: preview overlaps the right-side controls in narrow windows

**Status:** fixed (2026-07-15).

When the video editor window became too narrow, the preview area expanded
into the space reserved for the right-hand control panel instead of
respecting the available layout width.

**Root cause:** the top row used a plain ``QHBoxLayout`` with
``preview_label.setMinimumSize(480, 270)`` plus a settings panel at
``setFixedWidth(350…650)``, while the dialog itself allowed
``setMinimumSize(820, …)``. Below ~870px the layout could not satisfy
both minimums and the preview pane overlapped the settings panel.

**Fix:** use a plain top-row ``QHBoxLayout`` (preview stretch + fixed-width
settings panel), lower the preview minimum to 240×135, and derive both the
settings width and dialog minimum width from measured export controls via
``layout_geometry.apply_top_row_geometry`` (built on shared
``shared_toolkit.ui.layout_sizing`` helpers). Recompute after theme and
language changes.

## Video editor: magnifier is clipped during uncrop mode

**Status:** fixed (2026-07-15).

When using the uncrop tool, the magnifier overlay becomes partially
clipped instead of rendering in its entirety.

**Root cause:** the video preview path called
``apply_canvas_render_plan(..., clip_overlays_to_image_bounds=True)``
unconditionally. In fit-content / uncrop mode the render plan is a
padded composite (`image_is_padded_composite=True`); overlay clipping
uses ``_inner_content_rect_px`` (the unpadded image region), so any
magnifier geometry that extends into the padding area was scissored away.
GPU export already used ``clip_overlays_to_image_bounds=False``
(``gpu_export_scene.py``), so preview and export disagreed only in uncrop
mode.

**Fix:** pass ``clip_overlays_to_image_bounds=not fit_content_mode`` from
``PreviewCoordinator._apply_preview_scene`` — crop mode still clips to
the export frame; uncrop mode matches export and allows the magnifier to
render across the full padded canvas.


## Video editor: divider detaches / wrong size in uncrop mode

**Status:** fixed (2026-07-18).

With uncrop (fit-content) enabled, the white split line floated off the
image pair and grew into the pad fill — position and length no longer
matched the base-image seam.

**Root cause:** ``_refresh_live_content_rect`` gated on ``state._store``,
but video preview binds the store on ``canvas._store`` and
``set_pil_layers`` clears ``state._store``. The refresh was skipped, so
``_content_rect_px`` stayed as the raw-image letterbox while
``_compute_inner_content_rect`` scaled ``overlay_clip_rect`` against that
wrong base. DividerPass then clipped/positioned against a rect that did
not match ``_letterbox_params``.

**Fix:** always refresh content rect for ``geometry_letterbox`` /
padded-composite plans (no store gate); rebind ``state._store`` after
texture upload in the plan applicator. On preview-pane resize, re-apply
``_apply_plan_letterbox_from_clip`` from ``apply_plan_runtime_overlays``
(raw-image ``update_common_letterbox_geometry`` otherwise overwrites the
nested uncrop letterbox), and emit ``windowResized`` from the
preview/timeline splitter so the cheap refit path runs.


## Video editor: background-color indicator always shows blue, color picker dialog needs cleanup

**Status:** fixed (2026-07-15).

The underline indicating the currently selected background color always
rendered as blue, regardless of the actual background color selected by the
user.

Additionally, the background-color picker dialog was visually inconsistent
and awkwardly constructed compared to the rest of the editor UI.

**Root cause (underline):** ``update_fit_fill_color_button`` guarded on
``hasattr(btn, "set_color")`` but called ``setUnderlineColor`` — toolkit
``Button`` exposes the latter, not the former, so the guard always failed
and the underline stayed at the default accent color.

**Root cause (picker):** the handler opened a blocking modal ``QColorDialog``
without ``polish_themed_dialog``, which clashed with the editor's custom
window chrome and theming pipeline.

**Fix:** call ``setUnderlineColor`` directly (same pattern as divider/guide
color buttons elsewhere). Open the picker through
``SettingsColorPickerCoordinator`` / ``SettingsPresenter.show_color_picker``
— the same path as image-compare toolbar color buttons, with alpha enabled
for fit-content fill.

## Custom CSD: error dialogs always use dark background and clip rounded corners incorrectly

**Status:** fixed (2026-07-15) via first-party ``AppMessageDialog``.

Error dialogs using the custom client-side decorations (CSD) always rendered
with a dark background regardless of the active application theme, and the
rounded-corner region looked clipped/broken. In light theme the body stayed
near-black while labels kept dark ``@dialog.text`` — unreadable contrast.

**Root cause:** ``QMessageBox`` was auto-decorated with monkey-patched
``paintEvent`` and transparent QSS hacks. That path is unreliable on some
platforms; the native ``QMessageBox`` panel could still paint over CSD.

**Fix:** app code now uses ``shared_toolkit/ui/message_dialog.AppMessageDialog``
(``ThemedDialog`` + toolkit ``Label``/``Button`` + explicit ``decorate_dialog``).
``QMessageBox`` remains only as a fallback for the auto-decorator on stray
third-party dialogs; new alerts must go through ``AppMessageDialog`` or
``MessageManager.show_non_modal_message``.

## Mutter (GNOME): session-picker create-cards look missing while the widget tree is fine

**Status:** compositor presentation quirk; not an app logic bug (2026-07-17).

**Symptom:** under GNOME Wayland (Mutter), a Session Picker create-card
(e.g. Multi Compare) can appear absent or stale on screen even though the
app already built it.

**What we checked:** with temporary `[session-picker-debug]` logging,
`SessionPickerWidget.refresh()` scanned `tabs/` via
`iter_tab_entry_points()`, created both `image_compare` and `multi_compare`
cards (`layout_count=2`), and deferred startup successfully ran
`sync_icons` with non-null icons for both. No missing blueprint / failed
create path in that run — the Qt widget tree had the buttons.

**Interpretation:** the frame Mutter presents can lag or drop updates for
widgets added/updated during early startup (bootstrap page show + deferred
icon sync shortly after). Do not “fix” this by repeatedly rebuilding
picker cards when logs already show they exist; confirm with a resize,
tab switch away/back, or restart before chasing app-side card discovery.

**App-side posture (kept):** cards are built once from the filesystem tab
scan so deferred plugins do not force a visible card rebuild; icons may
still update in place after deferred tab registration.
