# QRhi / canvas gotchas (case catalog)

Detailed write-ups of rendering surprises where **logs looked correct** or
the wrong subsystem got blamed. For the short rule list, see
[patterns.md](patterns.md). Full multi-page investigations live under
[investigations/](investigations/).

How to use this page: match the **symptom**, read the case, follow the link
if you need the full timeline / failed mitigations.

---

## Index

| Symptom (short) | Case |
|---|---|
| Scissor-clipped pass correct height, wrong edge; base image fine | [#offscreen-scissor-y-flip](#offscreen-scissor-y-flip) |
| Divider floats in letterbox; magnifier OK; spit “weird” | [#divider-detaches-under-zoom-pan](#divider-detaches-under-zoom-pan) |
| First flyout after zoom “zooms again”; percent chip unchanged | [#display-lags-store](#display-lags-store) |
| Zoom/pan looks stale / fights the new frame | [#qrhiwidget-autofill](#qrhiwidget-autofill) |
| Dividers / underlines “missing” but geometry exists | [#invisible-chrome-vs-missing-geometry](#invisible-chrome-vs-missing-geometry) |
| App `eventFilter` blows up on non-`QObject` (e.g. `QRhi`) | [#eventfilter-non-qobject](#eventfilter-non-qobject) |
| Vulkan chosen but broken; no fallback | [#vulkan-startup-fallback](#vulkan-startup-fallback) |
| First canvas frame blank / see-through on Windows D3D | [#windows-d3d-empty-first-qrhi-frame--see-through-shell](#windows-d3d-empty-first-qrhi-frame--see-through-shell) |

Shared moral across several cases: **numerically perfect CPU/GPU plan logs
do not prove the user sees that frame.** Failure can be scissor consumption,
compositor stacking, autofill fighting the backing store, or transparent
chrome.

---

## Offscreen scissor Y-flip

**Symptom:** A scissor-clipped pass (in practice `DividerPass`) has the
*correct height* but the *wrong vertical offset* — looks anchored to the
wrong edge. Base image (vertex/UV geometry, no scissor) looks fine. Easy to
misdiagnose as `content_rect_px` / spit math.

**Cause:** `resolve_rhi_scissor()` used to flip Y only when
`rhi.isYUpInFramebuffer()` is true. That matches a **visible** `QRhiWidget`,
whose backing texture is composited into the top-level window and absorbs
the backend Y convention. A widget created with
`Qt.WidgetAttribute.WA_DontShowOnScreen` solely for `grabFramebuffer()`
(GPU export/preview canvas) **never** runs that compositing step, so the raw
scissor Y must be flipped even when `isYUpInFramebuffer()` is `false` for
the same backend.

Wrong offset magnitude is typically
`framebuffer_height - 2*content_y - content_height`.

**Fix:** flip when `y_up OR widget.testAttribute(WA_DontShowOnScreen)`.
Always prefer `resolve_rhi_scissor` over hand-built `QRhiScissor` /
`QRhiViewport`.

**Code:** `tabs/image_compare/canvas/rhi_feature_common.py` —
`resolve_rhi_scissor`. Consumers: export GPU canvas in
`plugins/export/services/gpu_export_proxy.py`.

**Rule:** [patterns.md](patterns.md) → scissors / coordinates.

---

## Divider detaches under zoom/pan

**Symptom:** At zoom-out with pan, the image half-boundary stays on the
picture, but the white/colored divider line floats in the fit-zoom letterbox
band. Magnifier stays locked to the image — “magnifier OK” is a red herring
for the *line*, a correct clue for *content-space spit*.

**Cause (stacked):**

1. Store spit always camera-owned (including `zoom <= 1`).
2. Image halves compared screen `vTexCoord` spit; magnifier used content spit.
3. Divider paint used fullscreen draw + QRhi **content** scissor on
   fit-zoom `content_rect_px` (live magnifier often skips that scissor).

**Fix / dual-mode:** content spit at `zoom <= 1`; camera rewrite (clamped to
`[0,1]`) only when `zoom > 1`. Halves in letterboxed image UV. Divider from
view-transformed letterbox + fragment clip, not fit-zoom content scissor.

**Full write-up:**
[investigations/divider-zoom-pan-detach.md](investigations/divider-zoom-pan-detach.md)

**Rule:** [patterns.md](patterns.md) → zoom / spit / overlays.

---

## Display lags store (MC transient “zoom nudge”)

**Symptom:** Wheel-zoom Multi Compare until the picture looks settled. Zoom
**percent chip already shows the final store value.** Open the **first** RMB
slot menu or toolbar scroll-value flyout → image jumps further in the **same
direction** as the last zoom. Chip unchanged. Later flyouts clean. Image
Compare does not reproduce on the same session.

**Cause:** One-shot **display catch-up** on Wayland + Vulkan: Qt often
reports `ApplicationInactive` during MC wheel while the user is still
interacting; the compositor throttles / lags the `QRhiWidget` subsurface.
The first transient restacks it and finally shows the buffer that already
matched the store. Not a second Redux zoom.

**Critical falsification:** `setUpdatesEnabled(False)` removes app presents
entirely; the jump **still** appears → outside the QRhi color-buffer content.

**Failed mitigations (do not reintroduce):** MainWindow as menu parent
(clear wipe); update freeze (halo); color-buffer freeze; force `in_window`;
UV letterbox alone; focus-parking alone.

**Mitigations in tree:** `ui.widgets.canvas.rhi_present_sync` (re-activate +
debounced compositor flush after zoom/pan); `rhi_focus` (hygiene).

**Probes:** `./launcher.sh run --debug` + tracer; optional A/B
`--rhi-backend opengl`. Menu surface A/B:
`IMGSLI_MC_RMB_SURFACE=in_window|popup`.

**Full write-up:**
[investigations/mc-transient-zoom-nudge.md](investigations/mc-transient-zoom-nudge.md)

**Status note:** [KNOWN_BUGS.md](../KNOWN_BUGS.md) (mitigated).

**Rule:** [patterns.md](patterns.md) → QRhiWidget / compositor.

---

## QRhiWidget autofill

**Symptom:** Multi Compare zoom-reset (and zoom-then-pan) leaves a visually
stale frame even though `render()` already drew the new zoom/pan. Related
“bounce” when a CSD dropdown micro-resize forced a redraw on Image Compare.

**Cause:** `setAutoFillBackground(True)` on the `QRhiWidget` — autofill +
palette clear fight RHI texture compositing.

**Fix:** no-op `setAutoFillBackground` (same as Image Compare). Clear color
stays in the RHI pass. MC also does immediate `update()` + next-tick
`request_view_update` after zoom/pan/reset so overlay hide cannot swallow
the first request.

**Status note:** [KNOWN_BUGS.md](../KNOWN_BUGS.md) (fixed 2026-07-17).

---

## Invisible chrome vs missing geometry

**Symptom:** Multi Compare grid dividers look “dead” / missing after GPU
work — easy to blame projection or pass registration.

**Cause (this instance):** fallback/default color weak or transparent
(palette Mid / bad alpha), not missing quads. Geometry was fine.

**Fix:** opaque defaults (`DEFAULT_DIVIDER_COLOR_RGBA` white like IC);
`ensure_visible_color` / `ensure_visible_qcolor` on chrome paths. Dividers
drawn as GPU NDC quads (`GridDividersPass`) rather than an FB-sized overlay
texture.

**Do not conflate** with [#display-lags-store](#display-lags-store) — same
investigation window, different bug.

---

## eventFilter + non-QObject (QRhi)

**Symptom:** `TypeError: QObject.eventFilter(QRhi, QEvent)` (or similar)
when an application/event filter is installed broadly.

**Cause:** Watching or receiving events for non-`QObject` targets (notably
`QRhi`). Calling `super().eventFilter` on those paths blows up.

**Fix:** Guard non-`QObject` targets before `super().eventFilter`.

**Status note:** [KNOWN_BUGS.md](../KNOWN_BUGS.md) (fixed 2026-07-18).

---

## Vulkan startup fallback

**Symptom:** Selecting Vulkan (or a broken Vulkan runtime) leaves the app
without a usable canvas; no automatic fallback.

**Fix:** probe / reject Vulkan for the process, persist platform fallback,
user-visible notice. Widgets must not `setApi(Vulkan)` after rejection.

**Status note:** [KNOWN_BUGS.md](../KNOWN_BUGS.md) (fixed 2026-07-19).
Code: `ui.widgets.canvas.rhi_backend`.

## Windows OpenGL / missing GLSL 330 in .qsb

**Symptom:**
`No GLSL shader code found (versions tried: 130, 120)` then
`Failed to create canvas graphics pipeline`.

**Cause:** baked shaders only include GLSL 330 / 300 es; a legacy Windows
OpenGL context cannot use them (sources are `#version 440`).

**Fix:** Windows Auto → explicit D3D11 (FL 11_0 probe); probe explicit
OpenGL for 3.3+, D3D12 / Metal similarly. If every candidate fails (e.g.
Windows with only D3D9), resolve to QRhi **Null** and show an unsupported
dialog with driver-update guidance + GitHub issues link.
Code: `ui.widgets.canvas.rhi_backend`. Workaround: `--rhi-backend d3d11`.

## Windows D3D empty first QRhi frame / see-through shell

**Symptom:** first presented canvas frame is blank **or punches through** the
CSD window on Windows (D3D11/12); Linux OpenGL/Vulkan usually fine.

**Cause (stacked):**

1. Image Compare used to fire startup first-frame signals on a no-op render
   (no target / no pass).
2. Live `QRhiWidget` sits under a `WA_TranslucentBackground` CSD shell.
   Clear / theme colors that keep alpha &lt; 255 (or an uninitialized D3D
   swapchain buffer) composite as a desktop hole — same class of failure as
   “logs correct, display lags” / FBO α≠1
   ([render-pass-contract.md](render-pass-contract.md),
   [#display-lags-store](#display-lags-store)).
3. Multi Compare already forced opaque clear and double-`update()`; IC did
   not.

**Fix:** gate signals on completed `beginPass`/`endPass`; force opaque live
clear (match MC); on Windows require **two** successful presents before
`firstVisualFrameReady`; settle with `flush_qrhi_compositor` (and on
`showEvent`) so DWM restacks a real opaque buffer.

**Code:** `tabs.image_compare.canvas.widget`, `rhi_render`,
`rhi_present_sync`, `themed_surface.apply_qrhi_theme_background`.

**Status note:** still seen under WinBoat after mitigations; bare-metal
Windows retest pending — [KNOWN_BUGS.md](../KNOWN_BUGS.md).

---

## Adding a new caseс

1. Write the full investigation under `investigations/<slug>.md` if the
   timeline / failed mitigations matter.
2. Add a short symptom→cause→fix→link section **here**.
3. Add one line to [patterns.md](patterns.md) (pattern and/or anti-pattern)
   pointing at this anchor or the investigation.
4. Update [KNOWN_BUGS.md](../KNOWN_BUGS.md) if it is still an open product
   bug; link both ways.
5. List it in [index.md](index.md).
