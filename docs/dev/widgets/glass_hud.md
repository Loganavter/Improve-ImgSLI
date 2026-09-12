# GlassHUD / InfoHUD / ZoomIndicator

Pinned frosted-glass corner chips over the canvas. `GlassHUD` is the shared
`BaseFlyout` base (registers a `GlassPanelSpec` with the canvas's
`GlassPanelRegistry` and owns the glass sprite display); `InfoHUD` and
`ZoomIndicator` are the two concrete chips. Their labels paint their own
glyphs in the normal theme color on top of the glass — there is no
GPU-recolored text mask (the dynamic text-vibrancy feature was removed; see
the private plan `glass-panel-soft-threshold-adaptive-tint-plan.md`).

Sources: `src/ui/widgets/glass_hud/{hud,info,zoom}.py`,
`src/ui/widgets/glass_hud/target_watch.py`,
`src/ui/widgets/glass_hud/shaders/`

## GlassHUD

| Param | Meaning |
|---|---|
| `parent` / `anchor` | flyout host / anchored widget |
| `flyout_group` | `info_hud` or `zoom_indicator` (see `ui/flyout_policy.py`) |

`target_watch` (a use_cases module per CODE_PATTERNS) owns the
anchor-tracking and backdrop re-registration.

## InfoHUD

Read-only info chip (PSNR/SSIM, dimensions) in a canvas corner;
`add_label(Label)` stacks readouts; re-lays itself out on
`font_changed`/`scale_changed`.

## ZoomIndicator

Zoom-percent chip with a reset button, pinned to the canvas corner; cold-
start double-deferred `_position()` workaround for first-show placement.

## Inspection

Families `GlassHUD` (state: `target`, `pinned`), `InfoHUD` (state:
`corner`, `target`), `ZoomIndicator` (state: `target`).

Used by: image_compare and multi_compare canvas layouts.
