# Screenshots

Capturing real product surfaces as PNGs — for Help figures and quick visual
verification. **Tool:** `src/devtools/capture_surface.py`
(devtool only; it imports no app runtime code and changes no product code).
The Help-figure set on top of it is produced by `src/devtools/help_figures.py`
(§[Help-figure generator](#help-figure-generator-recipes-drift-check)).

**One command for the whole covered set:** `src/devtools/help_figures_suite.py`
runs the devtool stage and then the live stage over both manifests, prints one
summary row per stage and fails fast (a red stage stops the run; its exit code
and output tail are reported, and nothing from a failed cell is installed).

```bash
python src/devtools/help_figures_suite.py              # devtool --all --jobs 4, then live --all
python src/devtools/help_figures_suite.py --check      # devtool drift gate; live prints 'unverified' (no baseline yet)
python src/devtools/help_figures_suite.py --dry-run    # print both commands, needs no DISPLAY
python src/devtools/help_figures_suite.py --only devtool --jobs 2   # one stage, N devtool workers
```

Measured 2026-10-21 on the 12-core host: **2 m 20 s** end to end (devtool 48
cells in 29.9 s, live 9 cells in 109.7 s) with the generated cells
byte-identical to the committed set. Those are dated numbers — the live set
has grown since, the help-asset tree holds 168 files (2026-10-22), and
`--check` is the authority for byte-identity, not this paragraph.

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
  (`_require_display` in `src/devtools/capture_surface.py`); it never defaults
  to `:0`.
  `LIBGL_ALWAYS_SOFTWARE=1` avoids fighting for the GPU.
- **Theme is mandatory.** Without `ThemeManager.register_palettes(...)` +
  `set_theme(...)` the painter pipeline has no tokens and paints unstyled /
  black surfaces (`_bootstrap_qt` in `src/devtools/capture_surface.py`).
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

- **Settings dialog** — `SettingsDialog(**SETTINGS_KWARGS)`; `SETTINGS_KWARGS`
  lives in `src/devtools/capture_surface.py` and mirrors the kwargs of
  `_dialog(**overrides)` in `tests/plugins/test_settings_dialog_sync.py`. Call
  `dialog.select_section("builtin.keyboard")` for the keyboard shot
  (`_settings` in the script).
- **Image Gallery** — `ImageGalleryWidget(None, context=TabContext())`
  (`src/tabs/image_gallery/widget.py`), then `widget.rebuild_grid(items)`.
  Build `GalleryItem(path=…, mtime_ns=…)`
  (`src/tabs/image_gallery/models.py`), set `.thumbnail = QPixmap(p).scaled(320, 240)`
  and `.thumbnail_status = ThumbnailStatus.LOADED` so cells aren't empty.
- **Session Picker** — `SessionPickerWidget(context=ctx)`
  (`src/tabs/session_picker/widget.py`). There is no host window, so pass
  a tiny stand-in context that answers `list_session_blueprints` /
  `get_tab_icon` and delegates `_tr` to `resources.translations.tr` — see
  `_FakeSessionContext` (`src/devtools/capture_surface.py`).
  Blueprints come from `SessionBlueprint` (`src/core/session_blueprints.py`).
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

## Help-figure generator (recipes, drift check)

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
python src/devtools/help_figures.py --compare                    # report generated vs pinned WxH (exit 1 on dims-differ)
python src/devtools/help_figures.py --all --locale ru --theme light  # restrict the matrix
python src/devtools/help_figures.py --all --write-manifest       # record baselines
```

- **Backend.** `--backend xvfb` (default) starts a private `Xvfb` on a free
  display number, waits for its socket and tears it down; `--backend native`
  uses the current `DISPLAY` and refuses to run without one. Neither ever
  defaults to `:0`.
- **Cells are independent, so they can run in parallel.** `--jobs N` (also with
  `--check` / `--compare`, which generate) captures `N` `(figure, locale, theme)`
  cells at a time in a `spawn` pool — each worker builds its own `QApplication`
  and reuses it across the cells it picks up. `--jobs 1` is the default and the
  old in-process path (one reused app, input order). `--jobs 0` / `--jobs auto`
  means `min(4, cpu_count)`; values above 8 are clamped. The parent never creates
  a `QApplication` before the pool (the display context only starts Xvfb and
  exports env). Results come back in `(figure, locale, theme)` order no matter
  which worker finished first, so `--write-manifest` and the drift table are
  byte-identical to a sequential run; a failing cell aborts the pool and names
  its `figure [locale/theme]`, and no manifest is written from a partial run.
  Rough win: a cell is dominated by its settle pumps (~1.2 s), so a 40-cell
  `--check` is minutes sequentially and a small multiple of one cell at 4 jobs.
- **No asset writes.** Captures go to `--out` (a fresh temp dir by default).
  Nothing is written into `src/**/resources/help/assets/`: installing a shot is
  still the copy step above, so a routine run cannot churn a shipped figure.
- **Recipe source.** `--manifest <path>` points the run at a different recipe
  file (default `src/devtools/help_figures.json`); `--locale` / `--theme` are
  repeatable and restrict the matrix actually captured.
- **Drift.** `--check` regenerates every selected figure+locale+theme pair and
  compares `sha256` against the manifest, printing a table. `ok` = identical,
  `drift` = different hash (exit code 1), `unbaselined` = the entry has no
  recorded hash yet (reported, not drift, so a fresh recipe exits 0).
  `uncovered` recipe entries are listed after the table and are never generated.
- **Baselines.** `--write-manifest` records `sha256`, byte size, dimensions and
  the applied pins for what it generated. Recording needs a real display, so a
  fresh recipe stays `unbaselined` until someone runs `--all --write-manifest`
  on a private Xvfb.
- **Variants are declared per figure, and installed per cell — in both
  pipelines.** A figure's `locales` x `themes` is the matrix: more than one
  pair makes every capture install under `assets/<locale>/<theme>/<name>` (a
  single-variant figure keeps today's flat destination). The recipe path
  (`help_figures.install_destination`) always did this; the live path
  (`help_live.install_target`) used to write every cell to the flat
  destination, so a declared live matrix shipped exactly one variant. Measured
  2026-10-22: **19 figures carry a matrix — 140 installed cells, ~7.3 MB**, still
  below the 15 MB bundle-in-the-binary gate. `empty_state.png` joined the matrix
  in #507, after the earlier "five figures, 40 files" line was written, and the
  live matrices landed in the variant wave (13 live figures: 11 at
  `en|pt_BR|ru|zh` x `dark|light`, `long_press`/`mc-layouts` at
  `en` x `dark|light`).
  One literal markdown reference then resolves
  through `resolve_help_asset`: `locale+theme -> locale -> theme -> base`. A
  **declared** cell that is missing is a content bug and returns `None` (the
  placeholder path), never the base; a locale with no declared matrix keeps the
  base image. The declarations the resolver consults are the **union of both
  manifests** (recipe + live), so a missing live cell fails closed exactly like
  a recipe one — measured live on 2026-10-22: an app run from a checkout
  without the cells rendered the English/dark base image inside a Russian
  light-theme page, with no signal at all.
  `help-paste-overlay` is the one measured exception still on its single cell:
  the direction picker is a `TopLevelInWindowOverlay` and has no top-level
  window for the `window` crop selector, so all 8 captures fail. zh is
  reproducible because the app and the captures both pin the
  bundled **Noto Sans SC** (SIL OFL 1.1) as the CJK fallback: the system
  fallback is not deterministic, and a runner without a CJK font renders tofu.
  Both bundled fonts ship their OFL texts next to the files
  (`LICENSE-SourceSans3.txt`, `LICENSE-NotoSansSC.txt`).
- **A variant matrix is justified by what is in the frame, not by figure
  count.** Every figure declares `variant_need`, and the value is what its
  frame needs: `locale+theme` (the frame contains UI chrome — labels, buttons,
  panel titles, dialog fields), `theme` (theme-coloured chrome but no
  translatable text — a plain button row, an overlay) or `none` (canvas/image
  pixels only — a lens over a photo with no chrome in the crop). The asset
  itself is the evidence, not the recipe name, so each declaration carries a
  one-clause justification in the figure's `note`. Both manifest readers
  validate the vocabulary (`ManifestError` on an unknown value), and
  `tests/devtools/test_help_figure_variant_matrix.py` enforces it against the
  declared matrix: `none` declares exactly one cell, `theme` declares `en`
  locales only, and a declared `locale+theme` matrix is the full 4 locales x
  2 themes. A figure may declare one `en`/`dark` cell while its need is larger
  — that is recorded debt, and the full shape is required the moment a second
  cell is declared, in the same change as the capture: declaring cells that are
  not on disk fails closed to the placeholder.
- **Idle blank is not a bug; drag-hover is a state.** The gallery's S0 repose
  is deliberately blank — the dashed drop zone + "Pick a folder…" prompt appear
  only while a drag hovers (`dragEnter`). The `gallery` surface drives that
  state with a synthetic `QDragEnterEvent` carrying a demo folder URL, so the
  empty-gallery figure shows what a user sees mid-drag and reads no store/user
  path. Do not "fix" the blank idle frame by showing the zone unconditionally.
- **User state never enters a frame.** A capture surface must be a product
  surface, not the maintainer's session. `session-picker`'s Recent shelf reads
  `services.io.recent_projects` from disk, so a raw grab embedded the user's
  real projects (private data in a shipped figure) and their changed
  thumbnails/mtimes made the sha256 gate flaky. The devtool now injects demo
  records with sample covers and a frozen relative label; nothing on the shelf
  comes from the store.
- **A JPEG destination is converted from the grab.** Captures are PNG; when the
  shipped asset is `.jpg` the generator converts the final frame (`quality=95`,
  `subsampling=0`, Pillow is pinned) so the installed bytes — and therefore the
  baseline — are the shipped format, not PNG bytes under a lying extension.
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

## Live figures (running app)

Some manual figures only exist in a **running** app: real QRhi canvases,
flyouts, session chrome, the Quick Look overlay. They are captured from a
private instance by `src/devtools/help_live.py`, with recipes in
`src/devtools/help_figures_live.json` (one entry per figure: capture target,
scenario steps, crop, destination).

```bash
python src/devtools/help_live.py --list
python src/devtools/help_live.py --figure help-toolbar
python src/devtools/help_live.py --all --out /tmp/live-shots
```

For the whole set (both stages, one summary) use
`src/devtools/help_figures_suite.py` above; `--figure`/`--all` here stay the
per-figure tools.

Rules (each exists because a live capture lied):

- **Isolate all four XDG dirs, not three.** `XDG_CONFIG_HOME` is where
  `QSettings` keeps theme/language/window geometry — a recon that isolated only
  DATA/CACHE/RUNTIME read the host's settings.
- **Seed the profile before boot** (`theme`, `language`, `ui_mode`, window
  size/position, `export_default_dir=/home/user/Pictures`) and sandbox `HOME`.
  `set_theme`/`set_language` answer "applied" but do not repaint/retranslate an
  open window, and a real home directory would print the maintainer's username
  into the export dialog.
- **A figure installs only after two consecutive captures are byte-identical**;
  `min_size` rejects a helper/warning window (measured: "Save Result" without a
  pair installed a 356x194 *load both slots* warning over the export figure).
- **Live figures are not in the sha256 drift gate.** CI gates the devtool
  surfaces (`help_figures.py --check`); a live capture carries no cross-host
  promise. Two independent boots are the review proof (measured identical for
  toolbar, tab strip, Multi Compare save dialog, gallery stats, Quick Look).
- **`@window` vs a tab name vs `@screen`.** A tab name captures that tab's
  widget (the tab strip/title bar live outside it); `@window` captures the whole
  active window — use it for chrome and dialogs. Toolkit flyouts are in-app
  `BaseFlyout` (`Qt.Widget`) children attached to the window's **overlay
  layer**, not native dialogs; the X `grabWindow` capture can still miss them
  (measured: the menu is in `ui_elements` while the window capture shows only
  the chrome behind it, and a tab capture never includes a window-level
  overlay). `@screen` grabs the X root (overlay included) and its pixels are
  1:1 with `screen_rect`, which is what `crop_element` uses. `wait_jobs` settles analysis;
  a fixed sleep is not a settle signal.
- **The render backend is per figure.** Image Compare canvas figures pin
  `rhi_backend=vulkan`: llvmpipe/OpenGL cannot create the IC canvas probe mip
  render target (`MipCascadeNotReady`, black canvas + the app's report dialog —
  measured), while Vulkan renders it headless on this driver. Chrome-only
  figures keep OpenGL. A host without a Vulkan ICD fails loudly, it does not
  silently ship a black canvas.
- **Transient flyouts capture fast.** A flyout can close before a normal
  two-capture settle; `stable_interval_s` (e.g. 0.15) keeps both captures inside
  its lifetime. Do not open a toolbar flyout with `ui_click` while a Vulkan IC
  canvas holds images: that kills the injected-input path (the figures open
  menus without images).

Current live set (14 figures, `python src/devtools/help_live.py --list` is the
authority): `help-toolbar`, `help-tab-strip`, `help-multi-save-dialog`,
`help-gallery-stats`, `help-gallery-quicklook`, `help-mc-layouts`,
`help-ic-magnifier`, `help-diff-modes`, `help-export-dialog`,
`help-image-properties`, `help-long-press`, `help-paste-overlay`,
`help-video-editor`, `help-video-export`. `help-paste-overlay` is declared but
its captures fail today (see the variant-matrix exception above). Still manual:
`magnifier_combined` (needs a lens state the control surface cannot compose),
`split_line` (a `ScrollValueButton` popup, not the compact/expanded composite
the figure teaches), plus Ask AI.

Two decisions on that manual pair (2026-10-21), recorded so neither is solved by
multiplying variants:

- `split_line` teaches a control that no longer exists — today's
  `ScrollValueButton` has a hover split and a value pill, not the
  compact/expanded composite in the prose. It is regenerated as a two-state
  figure or retired. If kept, its frame is chrome with text →
  `variant_need: locale+theme`.
- `magnifier_combined`'s "two halves become one" state must be proven reachable
  through a control verb (`set_setting`, or the lens settings read from
  `get_state`) before it is photographed; otherwise the figure is retired. A
  state that no verb can compose is not a variant question at all.

## Known limitation: the live QRhi/GL canvas

The **Multi Compare grid canvas is not capturable headlessly**: the QRhi/GL
swapchain is not part of `QWidget.grab()`. On a real X display QRhi init
*hard-exits* the process; under the offscreen platform it renders the canvas
**blank** (and logs `renderFailed`). The `multi*` surfaces are therefore
marked `isolated` and run in an offscreen child
(`_run_isolated` in `src/devtools/capture_surface.py`) so a crash can't
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
