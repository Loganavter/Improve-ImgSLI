# Screenshots

Capturing real product surfaces as PNGs — for Help figures and quick visual
verification. **Tool:** `src/devtools/capture_surface.py`
(devtool only; it imports no app runtime code and changes no product code).
The Help-figure set on top of it is produced by `src/devtools/help_figures.py`
(§[Help-figure generator](#help-figure-generator-recipes--drift-check)).

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
  (`src/devtools/capture_surface.py:407`); it never defaults to `:0`.
  `LIBGL_ALWAYS_SOFTWARE=1` avoids fighting for the GPU.
- **Theme is mandatory.** Without `ThemeManager.register_palettes(...)` +
  `set_theme(...)` the painter pipeline has no tokens and paints unstyled /
  black surfaces (`src/devtools/capture_surface.py:420`).
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
  `_FakeSessionContext` (`src/devtools/capture_surface.py:341`).
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

## Help-figure generator (recipes + drift check)

`src/devtools/help_figures.py` wraps `capture_surface` (imported, never copied)
with a committed recipe, `src/devtools/help_figures.json`: one entry per figure
— `id`, `surface` (a `capture_surface.SURFACES` key), optional
`crop: [x, y, w, h]`, optional `size: [w, h]`, `locales`, `themes`, `destination`
(the existing asset path inside the owning package's `assets/`), `covered`,
`reason` and a `note`. `schema_version` pins the shape. Only figures with
`covered: true` are generated; an `uncovered` entry names the shipped figure it
would replace (or `null`) and carries `new-surface` / `hand-composed` as the
reason it cannot be reproduced from these surfaces yet. The entry set is derived
from the shipped asset inventory, not invented. The committed file carries no
timestamps and is written canonically (sorted keys, sorted figures/captures,
`\n` newlines), so a no-op run is byte-identical.

```bash
env -u DISPLAY python src/devtools/help_figures.py --list        # no X needed
python src/devtools/help_figures.py --all --out /tmp/help-shots  # starts a private Xvfb
python src/devtools/help_figures.py --figure help-gallery-populated --theme light
python src/devtools/help_figures.py --check                      # exit 1 on drift
python src/devtools/help_figures.py --all --write-manifest       # record baselines
```

- **Backend.** `--backend xvfb` (default) starts a private `Xvfb` on a free
  display number, waits for its socket and tears it down; `--backend native`
  uses the current `DISPLAY` and refuses to run without one. Neither ever
  defaults to `:0`.
- **No asset writes.** Captures go to `--out` (a fresh temp dir by default).
  Nothing is written into `src/**/resources/help/assets/`: installing a shot is
  still the copy step above, so a routine run cannot churn a shipped figure.
- **Drift.** `--check` regenerates every selected figure+locale+theme pair and
  compares `sha256` against the manifest, printing a table. `ok` = identical,
  `drift` = different hash (exit code 1), `unbaselined` = the entry has no
  recorded hash yet (reported, not drift, so a fresh recipe exits 0).
  `uncovered` recipe entries are listed after the table and are never generated.
- **Baselines.** `--write-manifest` records `sha256`, byte size, dimensions and
  the applied pins for what it generated. Recording needs a real display, so a
  fresh recipe stays `unbaselined` until someone runs `--all --write-manifest`
  on a private Xvfb.
- **Pins are recorded, not assumed.** `locale` and `theme` go through
  `capture_surface`'s CLI (`emit_language_changed`, `ThemeManager.set_theme`).
  `font` and `ui_scale` are forced for every capture by the canonical
  bootstrap: the app's bundled **Source Sans 3** is loaded and proven applied
  (the run fails loudly if it is not), `QT_SCALE_FACTOR=1` and
  `QT_FONT_DPI=96` are set before `QApplication`, `QT_QPA_PLATFORM=xcb` is forced
  for the Xvfb backend, and the private Xvfb starts with `-dpi 96` — so a
  baseline hash does not depend on the host's fontconfig or DPI. (`96` is Qt's
  baseline and the toolkit scales px by `logicalDpi / 96`: an Xvfb left at its
  default 100 DPI misses every size pin by +42/+32 px.) They are recorded as **applied**, not as caveats. Surfaces that
  hardcode their own language or theme (`SETTINGS_KWARGS`, the onboarding store)
  list `locale:constructor-pins-en` / `theme:constructor-pins-dark` under
  `pins_unavailable`, so a non-default filter is never claimed as applied.
- **Size pins are applied to the live window, twice.** `CaptureSession` sizes
  the top-level window, shows it, lets it settle, then applies the pin again
  before grabbing — a `resize` before `show` is only a request, and show paths
  do re-fit the window (the onboarding overlay returned 648 px for a 684 px
  request). A shell that resizes its *content* box and keeps its own frame
  margin (CSD dialogs: +16 px per axis) is measured live and corrected once;
  the correction is kept only when the grabbed frame really equals the pin.
  When a surface still refuses (fixed-size layout, min/max clamp), the run does
  **not** resample or silently ship a different size: `--all` prints a
  `pin_unavailable … pinned WxH, achieved WxH` line, the entry records
  `size:surface-ignores-pin:WxH` under `pins_unavailable`, and `--check`
  reports drift for a baselined figure whose frame isn't the pinned one. The
  `--all` run ends with a `figure / pinned / achieved / parity|differ` table.

## Known limitation: the live QRhi/GL canvas

The **Multi Compare grid canvas is not capturable headlessly**: the QRhi/GL
swapchain is not part of `QWidget.grab()`. On a real X display QRhi init
*hard-exits* the process; under the offscreen platform it renders the canvas
**blank** (and logs `renderFailed`). The `multi*` surfaces are therefore
marked `isolated` and run in an offscreen child
(`src/devtools/capture_surface.py:481`) so a crash can't
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
