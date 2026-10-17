# Screenshots

Capturing real product surfaces as PNGs — for Help figures and quick visual
verification. **Tool:** `src/devtools/capture_surface.py`
(devtool only; it imports no app runtime code and changes no product code).

```bash
Xvfb :91 -screen 0 1400x1000x24 &
DISPLAY=:91 LIBGL_ALWAYS_SOFTWARE=1 \
    python src/devtools/capture_surface.py gallery-populated --out /tmp/shots
python src/devtools/capture_surface.py --list          # no display required
```

CLI: `<surface>`, `--out DIR` (default `/tmp/opencode/capture-surface`),
`--width W`, `--height H`, `--theme dark|light`, `--lang en`, `--list`.

## Why each step is not optional

- **Private Xvfb, never `:0`.** `QT_QPA_PLATFORM=offscreen` makes the toolkit
  painter pipeline render **black** — every grab is a black rectangle. A real
  (software) X server rasterizes the widget, but it must be a *private*
  display so the user's running app is untouched. The script reads `DISPLAY`
  from the environment and refuses to run without it
  (`src/devtools/capture_surface.py:362`); it never defaults to `:0`.
  `LIBGL_ALWAYS_SOFTWARE=1` avoids fighting for the GPU.
- **Theme is mandatory.** Without `ThemeManager.register_palettes(...)` +
  `set_theme(...)` the painter pipeline has no tokens and paints unstyled /
  black surfaces (`src/devtools/capture_surface.py:375`).
- **i18n is mandatory.** Without `emit_language_changed(...)` after registering
  the per-tab / per-plugin i18n roots, widget labels show **raw keys**
  (`help.topic.foo`) instead of text. The `I18N_ROOTS` list mirrors the app's
  own bootstrap; keep it in sync when a new package adds `resources/i18n`.
- **Pump before grab.** Widgets size and style themselves across posted events
  (show → layout → theme polish). `QTimer.singleShot` + a nested `QEventLoop`
  then `processEvents()` lets Qt settle; grabbing immediately captures a
  half-laid-out frame (`CaptureSession.pump` in the script).

## Surfaces

| Name | Shot |
|---|---|
| `settings` | Settings dialog, General section |
| `settings-keyboard` | Settings dialog, Keyboard shortcuts section |
| `gallery` | Image Gallery, empty (drop-zone) state |
| `gallery-populated` | Image Gallery grid, six generated demo images |
| `multi` / `multi-populated` | Multi Compare — **chrome only** (see limitation) |
| `session-picker` | Session Picker with three demo session types |
| `onboarding` | First-run onboarding overlay |

## Construct a surface (validated patterns)

Deep-import the widget in the builder and hand it to `CaptureSession.grab`.
These are the proven constructions:

- **Settings dialog** — `SettingsDialog(**SETTINGS_KWARGS)`; the kwargs mirror
  `tests/plugins/test_settings_dialog_sync.py:22`. Call
  `dialog.select_section("builtin.keyboard")` for the keyboard shot
  (`_settings` in the script).
- **Image Gallery** — `ImageGalleryWidget(None, context=TabContext())`
  (`src/tabs/image_gallery/widget.py:70`), then `widget.rebuild_grid(items)`
  (`:1663`). Build `GalleryItem(path=…, mtime_ns=…)`
  (`src/tabs/image_gallery/models.py:199`), set `.thumbnail = QPixmap(p).scaled(320, 240)`
  and `.thumbnail_status = ThumbnailStatus.LOADED` so cells aren't empty.
- **Session Picker** — `SessionPickerWidget(context=ctx)`
  (`src/tabs/session_picker/widget.py:114`). There is no host window, so pass
  a tiny stand-in context that answers `list_session_blueprints` /
  `get_tab_icon` and delegates `_tr` to `resources.translations.tr` — see
  `_FakeSessionContext` (`src/devtools/capture_surface.py:296`).
  Blueprints come from `SessionBlueprint` (`src/core/session_blueprints.py:18`).
- **Onboarding overlay** — `OnboardingOverlay(None, SimpleNamespace(settings=SimpleNamespace(current_language="en")))`
  (`src/plugins/onboarding/overlay.py:52`).
- **Populate content** — `CaptureSession.make_samples()` generates six gradient
  demo images so grids are not empty.

## Put a shot into a Help package

Copy the PNG into the **owning** package's `assets/` — host
`src/resources/help/assets/` for platform/UI topics, a tab's
`src/tabs/<tab>/resources/help/assets/` for that tab's topics — then reference
it body-relative (see [HELP_SYSTEM.md](HELP_SYSTEM.md) §Figure paths):

```markdown
:::figure{side=block width=100%}
![Gallery grid view](../assets/overview_grid.png)
**Grid** view: the toolbar, then the cards.
:::
```

Use final filenames (shipping a shot = overwrite the file; no markdown edit).
Paths must not escape the package's `resources/help/` dir
(`tests/plugins/test_help_bodies.py`).

## Known limitation: the live QRhi/GL canvas

The **Multi Compare grid canvas is not capturable headlessly**: the QRhi/GL
swapchain is not part of `QWidget.grab()`. On a real X display QRhi init
*hard-exits* the process; under the offscreen platform it renders the canvas
**blank** (and logs `renderFailed`). The `multi*` surfaces are therefore
marked `isolated` and run in an offscreen child
(`src/devtools/capture_surface.py:436`) so a crash can't
take the tool down — you get the chrome (toolbar + footer) with a blank
canvas. For a real canvas shot, capture the **running app manually**
(screenshot tool / `grim`).

**Exception — the live path.** A capture taken from a *running* app
(MCP `capture_surface` with a live instance, or the app-side
`capture_live`) composites each visible `QRhiWidget`'s own last frame(`QRhiWidget.grabFramebuffer`) on top of the window raster, at the widget's
geometry — so the canvas does show its content. Canvases are looked up from
the target's top-level window (the Quick Look canvas rides an in-window
overlay parented to the window, not to the tab page) and only those landing
on the grab are painted; a hidden canvas, one that has not rendered yet, or
one that cannot hand its frame over is skipped, and the capture reports how
many layers were composited (`rhi_layers`). The isolated devtool surfaces
above are unaffected — they are separate processes with no live frame to
read.

**Window bigger than the display: no black bands.** A window that does not
fit the screen has **no pixels** outside it, and an X grab returns black
there — which reads as "the toolbar/footer is broken" (exactly how it was
read once, 2026-10-17). Two guards, in order:

1. the app now fits its startup geometry into the available screen
   (`utils/geometry.py::fit_into`), so a rectangle saved on a bigger display
   is clamped instead of restored blindly;
2. if a target still is not fully on screen, the live capture takes the Qt
   raster grab first (`QWidget.grab` renders the widget tree with no X
   involvement, so nothing is missing) and only a contentless raster falls
   back to the X grab, clipped to its visible part.

Keep a private Xvfb at least as large as the window anyway: composing both
guards is not as good as "it simply fits".
