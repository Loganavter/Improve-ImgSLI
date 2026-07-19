# Investigation: Multi Compare transient UI “zoom nudge”

Symptom that started this write-up: after wheel-zooming Multi Compare until
the picture looked settled, opening the **first** RMB slot menu or toolbar
scroll-value flyout made the image jump further in the **same direction** as
the last zoom — while the zoom **percent chip stayed unchanged**. Later
flyouts in the same view did not jump again. Image Compare on the same
session did **not** reproduce.

This page is the durable lesson. Short pointers also live in
[qrhi-gotchas.md](../qrhi-gotchas.md#display-lags-store),
[patterns.md](../patterns.md), and
[KNOWN_BUGS.md](../../KNOWN_BUGS.md).

## What it looked like vs what it was

| Looks like | Actually is |
|---|---|
| Extra zoom step on flyout open | One-shot **display catch-up** to an already-committed store zoom |
| Bug in Redux / letterbox / pan math | Store zoom/pan, letterbox `sr/ox/oy`, and GPU draw plan stay identical across the jump |
| Wrong redraw in `render()` | Glitch survives `setUpdatesEnabled(False)` with **no** app `present#` — outside the QRhi color buffer |
| IC and MC share the same trigger class | Same flyout/popup machinery; only MC + Vulkan + Wayland showed the catch-up |

**User-visible pattern (refined):**

1. Wheel-zoom on MC until the picture looks settled (do not touch).
2. Open **first** RMB menu or scroll-value cloud → image jumps in the zoom
   direction.
3. Zoom percent chip unchanged between those frames.
4. Subsequent flyouts: clean.

So the first transient only **restacks** the Vulkan subsurface and finally
shows a buffer the compositor was already holding (or had throttled while
Qt reported `ApplicationInactive`). It is not a second `set_zoom`.

## Probe facts (what stayed stable)

With `./launcher.sh run --debug` / tracer and careful store vs display
observation:

- Widget `glob`, size, DPR, Wayland attrs (`wa_*`) unchanged across the jump.
- Store `zoom` / `pan` unchanged (matches the percent chip).
- Present plan fingerprints (`rect_fb`, `tile0`, `L0_zoom`, clip) unchanged
  when a present did run.
- `pipeline_rebuilt` usually never fired on RMB.
- UV letterbox migration for MC base images (fullscreen quad + letterbox /
  slotRect UBO) did **not** remove the nudge — ruled out as the cause.

**Critical falsification:** freezing updates (`setUpdatesEnabled(False)`)
removed app presents entirely (no image *and* no overlay redraw) but the
nudge **still appeared**. Therefore do not chase “we drew the wrong zoom”
when the chip and store already agree.

## A/B: MC vs IC on the same flyout

| | Multi Compare | Image Compare |
|---|---|---|
| `app` during / after zoom | often `ApplicationInactive` | `ApplicationActive` |
| keyboard focus | often `none` (canvas may have held focus earlier) | tab shell (`ImageCompareWidget`) |
| canvas `has_focus` on flyout | historically flipped True→False | stayed False |
| backend / policy | Vulkan, `StrongFocus` | same Vulkan API in probe |

Geometry stacking attrs looked the same. The durable correlate was **false
`ApplicationInactive` while the user was still interacting with MC**, then a
transient restack that flushed the lagged display.

## Failed mitigations (do not reintroduce)

These were tried, caused worse side effects, or proved irrelevant:

- `menu_parent=MainWindow` + `popup` → one-frame clear wipe
- `setUpdatesEnabled(False)` around the menu → halo; nudge remains
- Pinning `fixedColorBufferSize` / color-buffer freeze for the popup
- Forcing flyout `in_window` only
- Vertex→UV letterbox alone (good architecture; not this bug)
- `ensure_pipeline` thrash on open
- Keyboard-focus parking alone (`ui.widgets.canvas.rhi_focus`) — clears
  QRhi `has_focus`, but MC could still sit in `ApplicationInactive` during
  wheel and the one-shot jump remained

Keep MC context menus on the same policy as IC: `popup`, parent = QRhi
canvas (not MainWindow).

## What helped (mitigations in tree)

1. **`ui.widgets.canvas.rhi_present_sync`** (primary):
   - On MC wheel / before RMB: `ensure_window_active_for_qrhi` if Qt reports
     Inactive while our window is visible.
   - After `set_zoom` / `set_pan` / `reset_view`: debounce (~100 ms)
     `schedule_compositor_sync` → activate + `QWindow.requestUpdate` +
     widget/`overlay` `update`, so catch-up happens on **gesture settle**
     instead of on the first flyout.

2. **`ui.widgets.canvas.rhi_focus`** (hygiene, insufficient alone):
   - Park keyboard focus off any `QRhiWidget` onto the nearest focusable
     ancestor (MC shell already forwards keys to the canvas).
   - Also clear QRhi focus before flyout / context-menu open.

Hooks live in MC `canvas/interaction.py`, `MultiCompareWidget._on_store_change`,
`ui/flyout_policy.py`, `ui/context_menu/manager.py`, and
`configure_rhi_widget`.

## Related but separate: MC grid dividers “dead”

During the same investigation window, MC dividers looked missing. That was
**not** the nudge:

- Cause was a weak / transparent default divider color (palette Mid / bad
  alpha), not missing geometry.
- Paint path moved from FB-sized overlay texture to GPU NDC quads
  (`GridDividersPass` + `projected_divider_rects`), with opaque white
  defaults aligned to IC (`DEFAULT_DIVIDER_COLOR_RGBA`,
  `ensure_visible_color`).

Do not conflate “divider invisible” with “zoom jumped.”

## Rules of thumb for future agents

1. **If the zoom chip did not move, do not “fix zoom” in the store first.**
   Diff store vs displayed frame; assume compositor / activation / stacking.
2. **`setUpdatesEnabled(False)` that still shows the glitch** means the bug
   is outside your color-buffer content — stop rewriting shaders for it.
3. **One-shot on first transient after a gesture** ⇒ lagged present flushed by
   restack; prefer settling the compositor after the gesture, not after UI.
4. **MC `ApplicationInactive` during wheel on Wayland+Vulkan** is a real
   signal even when the user is clearly using the app — compare IC on the
   same machine before inventing new letterbox math.
5. **Do not parent Qt.Popup menus to MainWindow** to “fix” stacking on this
   canvas — that caused a clear wipe; IC’s canvas-parent policy is the
   baseline.
6. Scissor / Y-flip surprises (wrong edge, correct height) are a *different*
   class of bug — see
   [qrhi-gotchas.md#offscreen-scissor-y-flip](../qrhi-gotchas.md#offscreen-scissor-y-flip).
   Same moral: numerically perfect CPU logs can still lie about what the user
   sees if the failure is in compositing / backend consumption.

## How to re-verify

```bash
./launcher.sh run --debug
```

1. MC: zoom in, wait ~0.2 s — optional self-catch-up from
   `rhi_present_sync`.
2. Open scroll-value cloud / RMB — should **not** jump; chip unchanged.
3. Optional A/B if it returns: `./launcher.sh run --rhi-backend opengl`.
4. Optional menu surface A/B: `IMGSLI_MC_RMB_SURFACE=in_window|popup`.

Modules: `src/ui/widgets/canvas/rhi_present_sync.py`,
`src/ui/widgets/canvas/rhi_focus.py`.

## See also

- [qrhi-gotchas.md](../qrhi-gotchas.md) — case catalog (this + scissors / autofill / …)
- [patterns.md](../patterns.md) — short do/don't rules
- [coordinate-systems.md](../coordinate-systems.md) — content vs display spaces
- [divider-zoom-pan-detach.md](divider-zoom-pan-detach.md) — real store /
  scissor geometry bugs (different symptom class)
