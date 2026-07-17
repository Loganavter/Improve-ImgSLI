# Rendering Model

There is one renderer backend and two state-preparation paths:

- **Live authoring path** — the interactive canvas reads live `Store`/
  `ViewState`/feature state every frame. The only path a user's drag,
  toolbar click, or shortcut should ever mutate.
- **Snapshot replay path** — preview, image export, video preview/export,
  thumbnails build a frozen snapshot, turn it into a render plan, and feed
  that plan through the *same* passes. No parallel rendering logic for "what
  export looks like."

**Rule:** a fix that only works in export/preview/video code with no
live-canvas counterpart is the wrong fix. It will drift the first time the
live path changes underneath it.

The distinction between modes is an explicit `mode` value (`"interactive"` /
`"preview"` / `"export"`) passed into render-context construction. That's a
convenience for expressing `SceneVisibility` decisions (see
[render-pass-contract.md](render-pass-contract.md)) — it is not license to
sprinkle `if mode == "export"` branches inside a pass.

## Snapshot Renderer Notes

Preferred export/video direction:
- one snapshot-driven render-plan builder
- one QRhi/offscreen renderer backend
- multiple snapshot producers (`live store -> snapshot`, `timeline -> snapshot(t)`)

Image export preview/final and video preview/export differ by snapshot
source and target surface, not by feature-specific scene assembly.

Snapshot prepare must **not** bake letterbox or feature padding into image
pixels. Keep `TiledPixelStore` (or other unpadded sources) on the plan and
express pads via `CanvasGeometry` / `overlay_clip_rect` + shader letterbox,
matching the live canvas geometry model.
