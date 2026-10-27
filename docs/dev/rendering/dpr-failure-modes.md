# DPR / orientation failure modes

Every mode below has shipped, cost a diagnosis cycle, and been merged as a fix.
That is why they are catalogued as **machine-checked** modes rather than as
advice: the gate is `tests/contracts/test_dpr_defect_catalog.py`, its exemptions
live in `tests/contracts/dpr_catalog_allowlist.py`, and each detector is proven
red on a snippet of the real broken code under
`tests/contracts/fixtures/dpr_bad_snippets/`.

The full version of this chapter, with the per-incident history, screenshots and
the cross-tab investigations, lives in the private knowledge base:
`../improve-imgsli-internal-docs/docs/dev/rendering/dpr-failure-modes.md`
(sibling checkout, not part of this repo). This page is the app-facing subset:
what to do, and which detector will catch you.

## The one measured fact everything rests on

`QPainter` **scales its commands by the `devicePixelRatio` of the device it
paints on**. For a `QPixmap`/`QImage` carrying DPR *d*, `combinedTransform`
already contains `scale(d)` and `worldTransform` is identity — the painter's
coordinates are **logical**. Two consequences:

* A raster must be **allocated in device px** (`round(logical * d)`) and
  **tagged** with `setDevicePixelRatio(d)`. Allocating logical px and tagging
  with *d* makes the painter treat the canvas as `size / d`, so the drawing
  lands in the top-left corner.
* A manual `painter.scale(d, d)` on a raster that is already tagged (or on a
  widget — `QPainter(self)`) is the **second** application of the same ratio.
  On an *untagged* raster it is the one legitimate application.

And: `QPixmap.width()/height()` are **device** pixels while widget geometry is
**logical**. "A number is a number" is exactly the reasoning behind every row
below.

## Mode -> form -> symptom -> answer -> detector

| Mode | Form (what the code looks like) | Symptom on screen | Sanctioned answer | Detector id |
|---|---|---|---|---|
| Clip matrix literal | `stage_clip(updates, _IDENTITY_CLIP)`, `clip_matrix=(1,0,…)` (16 floats), `None`, an `IDENTITY*` constant | Canvas/preview **mirrored** on a backend whose clip space is y-down (Vulkan) while looking right on the author's host | Ask the one source: `ctx.clip_matrix`, or `engine/gpu/rt_y_orientation.composited_clip_correction(rhi)` / `composited_clip_matrix(rhi)`, or `framing.clip_matrix(...)` | `clip-matrix-literal` |
| Viewport from logical size | `QRhiViewport(0, 0, ctx.width, ctx.height)`; a device-*named* variable (`fb_w`) assigned from logical numbers | Content fills `1/DPR` of the target per axis — a quarter of the area at DPR=2, i.e. "gets smaller at a larger interface scale" | Derive the size from the framebuffer once: prefer `ctx.framebuffer_size`, else `renderTarget().pixelSize()`, else `logical * devicePixelRatioF()`. `drag_drop_overlay/framing.py::framebuffer_size` is the reference | `viewport-logical` |
| Double scale | `QPainter(pixmap)` (grab / widget / tagged raster) **plus** `x * dpr`, `painter.scale(dpr, dpr)` | Content painted at 2x offset and 2x size, cropped at the edge (`(200,100)-(600,300)` → `(400,200)-(1198,598)`) | Coordinates stay logical; the ratio belongs to the *buffer* size, in another function | `double-scale` |
| Logical raster, tagged | `QImage(widget.width(), widget.height())` + `setDevicePixelRatio(dpr)` | Content in the top-left corner, rest of the canvas empty; the whole raster shrinks by DPR | Allocate `round(logical * dpr)`, then tag with `dpr` | `raster-logical-tagged` |
| Ratio dropped on copy | `QPixmap(src.size())`, `QImage(src.width(), src.height(), …)` with no ratio copy | A DPR=2 source becomes a DPR=1 copy: drawn at half size, or its content in the corner of a blank fill | `out.setDevicePixelRatio(src.devicePixelRatio())` in the same function (`tabs/image_gallery/.../icons.py` is the reference) | `ratio-dropped-on-copy` |
| Ratio rounded | `int(dpr)`, `round(dpr)` (no `ndigits`), `setDevicePixelRatio(2)` | On 125 %/150 % hosts: slightly blurry (buffer too small) or slightly cropped (buffer too large); invisible on the 1x and 2x hosts everyone tests | Keep the ratio a `float` end to end; round the *product* (`round(logical * dpr)`), never the ratio | `ratio-rounded`, `ratio-hardcoded` |
| UV flip compensation | `1.0 - vUv.y` in a shader outside a gate, `.mirrored()`, `flip_y = True`, a local `diag(1,-1,1,1)` | Flipped/upside-down tiles below 1:1, or an alternated-parity band pattern (trilinear blending upright mip0 with flipped mip1) | Named cases in `engine/gpu/rt_y_orientation.py` (`widget_texture_needs_y_flip`, `sampled_rt_correction`, `composited_clip_correction`); a shader gates on a `flipY` uniform fed by them | `uv-flip-compensation` |
| Primary-screen grab | `app.primaryScreen().grabWindow(...)` | On a mixed-DPI desktop: black/other-window pixels, plus a false "fully visible" verdict from the wrong `availableGeometry` | Ask the **target's** screen: `target.windowHandle().screen()`, then `target.screen()`, primary only as a documented last resort | `primary-screen-grab` |
| Logical rect out of a device grab | `grab.copy(visible_logical)` | Capture shows the top-left `1/DPR²` of the window: 1280x700 returned for a 2560x1400 visible region | Scale the logical rect by the grab's own `devicePixelRatio()` before cropping (`core/control/capture._clip_to_visible`) | `geometry-device-copy` (behavioural) |
| Silent downsample | `grabFramebuffer()` → `.resize(logical_target)` | A HiDPI grab quietly loses half its resolution; exports go soft without any error | Resize only to a device-named target, or prove the resize is a supersample (the export canvas renders the same layout at device resolution) | `silent-downsample` |

Rules 10 and 11 are behaviourally proven in the same test module
(`test_geometry_device_copy_keeps_the_whole_visible_rect`,
`test_export_grab_downscale_preserves_content`); the others are static AST /
shader scans plus the fixture self-test.

## Three dispositions, and what each one means

A hit is never silently tolerated. It gets exactly one of these:

* **fix it** in the same change — the wave's own fixes (#751, #752, #755) did
  this, which is why they need no entry anywhere;
* **`DPR_ALLOWLIST`** (`tests/contracts/dpr_catalog_allowlist.py`) — the shape is
  legitimate *here*, and the reason carries the measurement that proves it
  ("`QIcon.pixmap(QSize)` returns ratio 1.0 even at `QT_SCALE_FACTOR=2`");
* **`KNOWN_DEFECTS`** (`test_dpr_defect_catalog.py`) — a real bug with a task id
  on it, declared openly. It stays visible in every run and self-expires: an
  entry that no longer matches a live hit fails the suite, so the fix must land
  together with the deletion.

A defect must never be laundered into the allowlist — an allowlist entry asserts
"legitimate", which is the opposite of what a known bug is.

Currently declared (`task-mc-tiled-export-dpr-2026-10-28`): the tiled export
composes in logical output px against a device-px framebuffer, so at DPR=2 the
exported PNG holds the composition in the top-left quarter and the device grab is
downsampled to the logical tile — `src/engine/gpu/export_tiling.py`
(`_render_single`, `_render_tile`), `src/tabs/multi_compare/services/gpu_export.py`
(`render_to_qimage`) and the plugin proxy
`src/plugins/export/services/gpu_export_proxy.py` (`_render_plan_frame_single`).

## What this gate deliberately does NOT catch

Name them so nobody trusts the gate beyond its reach:

* **A convention decided behind a helper.** The scan reads a function at a time,
  so `w = helper(ctx)` returning logical pixels is invisible unless the name
  lies (which `viewport-logical` does catch).
* **A logical size handed to a bitmap API that is not a viewport.**
  `setFixedColorBufferSize(rhi.size())` (a `pixelSize` argument fed a logical
  `size()`, fixed as the resize shield) and
  `build_render_context(framebuffer_size=<logical>)` in
  `src/tabs/multi_compare/scene/projection.py` are that shape — part of the
  declared export defect above, but the catalog has no mode for it yet. First
  candidate for a future mode.
* **Whether a legal-looking resize is a supersample or real resolution loss.**
  Only the behavioural test can tell, and it covers the export path only.
* **Anything on a real backend.** Every visual symptom above was measured on a
  real window; the gate is static. A mode that only manifests on Vulkan/D3D11
  still needs the live proof.

## How to add a mode

The order matters — numbers first, detector last:

1. **Find the numbers.** Measure on a real surface (a private Xvfb + the live
   control channel, see `../Improve-ImgSLI/docs/dev/MCP.md` and
   `RUNBOOK_LIVE_MCP_VERIFICATION.md`): what size was allocated, what the
   painter transformed it by, what the widget geometry was. A mode without a
   measured pair (device vs logical) is a guess.
2. **Find the real broken code.** `git show <commit>^:<path>` on the fix commit.
   Copy the snippet into `tests/contracts/fixtures/dpr_bad_snippets/` with a
   `# provenance: <path>:<line> @ <commit>` header and a `# rule: <id>` line.
   Snippets reconstructed from a documented incident (no reachable pre-fix
   commit) say `@ reconstructed` and the header explains what the body was
   rebuilt from. Add a **negative** fixture too (`# rule: none`): the legal shape
   the detector must stay silent on.
3. **Write the detector** in `tests/contracts/test_dpr_defect_catalog.py`, one
   function per rule, returning `(line, detail)` pairs; add the rule id to
   `RULE_IDS` and the mode to the table above. Prefer an AST fact over a string
   match — the first draft of every rule here was a substring alarm
   (`ratio` matched progress/aspect ratios, `1.0 - y * 2.0` matched the legal
   UV→NDC mapping).
4. **Run it over the tree** and over your `.probe/prefix/` copies of the
   pre-fix files (`git show <commit>^:<path>` into a scratch dir inside the
   repo, never committed). The pre-fix copy must be found **by rule id**; if it
   is not, the detector describes nothing that happened.
5. **Allowlist with the measured reason**, `(rel_path, function, rule_id) ->
   reason` in `tests/contracts/dpr_catalog_allowlist.py`. The reason must name
   the measurement that makes the shape correct there ("`QIcon.pixmap(QSize)`
   returns ratio 1.0 even at `QT_SCALE_FACTOR=2`"), not a vibe. Empty reasons and
   entries that stopped matching a hit fail the suite by design. If the shape is
   a **real bug** instead, declare it in `KNOWN_DEFECTS` with a task id — never
   in the allowlist.
6. **Update help/docs** if the mode changes user-visible behaviour.

## Contracts that own the neighbours

* `tests/contracts/test_rt_y_orientation.py` — nothing outside
  `engine/gpu/rt_y_orientation.py` may *call* the QRhi convention queries or
  build a Y-flip literal. This catalog's `uv-flip-compensation` covers the other
  half: an identity or an unconditional flip *standing in* for that call.
* `tests/contracts/test_text_paint_scale_scan.py` — the same ratchet shape for
  UI-scale text (a different multiplier; same "entered twice / never entered"
  bug family).
* `tests/devtools/test_capture_dpr_units.py` — the behavioural capture gate;
  `geometry-device-copy` here is its static/fixture-side companion.
* `docs/dev/rendering/coordinate-systems.md` — the space model (canvas-px,
  widget-px, framebuffer-px) these modes violate.
