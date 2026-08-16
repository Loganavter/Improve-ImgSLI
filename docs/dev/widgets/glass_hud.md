# GlassHUD / InfoHUD / ZoomIndicator

Pinned frosted-glass corner chips over the canvas. `GlassHUD` is the shared
`BaseFlyout` base (registers a `GlassPanelSpec` with the canvas's
`GlassPanelRegistry`, owns the text-mask alpha rasterization and the glass
sprite display); `InfoHUD` and `ZoomIndicator` are the two concrete chips.

Sources: `src/ui/widgets/glass_hud/{hud,info,zoom}.py`,
`src/ui/widgets/glass_hud/{target_watch,text_mask}.py`,
`src/ui/widgets/glass_hud/shaders/`

## GlassHUD

| Param | Meaning |
|---|---|
| `parent` / `anchor` | flyout host / anchored widget |
| `flyout_group` | `info_hud` or `zoom_indicator` (see `ui/flyout_policy.py`) |

`target_watch` / `text_mask` (use_cases modules per CODE_PATTERNS) own the
anchor-tracking and glyph-mask rasterization (supersampled, throttled).

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
