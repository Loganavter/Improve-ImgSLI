# Improve ImgSLI 10.0.0 — release notes draft

Draft for the GitHub release body and AppStream/Flatpak changelog.
Style mirrors [v9.0.0](https://github.com/Loganavter/Improve-ImgSLI/releases/tag/v9.0.0).
Edit freely before shipping; then copy into the GitHub release and shorten for `metainfo.xml`.

---

# Improve ImgSLI 10.0.0

From 9.0.0 to 10.0.0 the application stopped being a single-purpose comparison window and became a small workspace platform. Image Compare is no longer wired into the core as “the app itself”: it lives behind a tab contract, shares the shell with Multi Compare, and starts from a session picker. Under the hood the renderer moved to QRhi, full-resolution pixels spill into a tiled store, and the UI toolkit finally lives outside the tree.

The visible feature list is still focused — workspaces, navigation, large images, Find Action, help, and project files — but the foundation underneath them is what this release is about.

## Highlights

- Session picker and a real multi-workspace shell: Image Compare and Multi Compare as separate tabs.
- QRhi-based canvas path (Vulkan/Metal-capable backends via Qt) instead of the old OpenGL-only assumption.
- Custom window chrome (CSD) for reliable decoration behavior on modern Wayland compositors.
- Tiled full-resolution storage (`TiledPixelStore`) for Image Compare and Multi Compare — the old hard ~16k load/live ceiling is gone for normal work.
- Find Action palette (`Ctrl+Shift+P`) with pulse-into-view for toolbar and settings controls.
- Hierarchical in-app Help (host + per-tab topics, figures, About).
- Portable project packages (`.imgsli`) with Open / Save / Save As.
- External `sli-ui-toolkit`, PySide6, and GPL-3.0-or-later licensing.

## Workspaces and session picker

The app opens on a “Create a workspace” screen. Pick Image Compare or Multi Compare, then work in Firefox-style tabs instead of a single fixed layout.

- Recent projects shelf on the session picker for jumping back into saved work.
- Tab bar and host chrome own session lifecycle; comparison logic stays inside each tab.
- Switching sessions is an application-level transition, not a pile of hidden mode flags.

Multi Compare is a first-class grid workspace for several sources at once, not a bolted-on mode of Image Compare.

## Rendering and large images

- Live canvas rendering continues on the QRhi path so the same model can target modern GPU backends without staying locked to legacy OpenGL.
- Full-resolution pixels for both comparison tabs use memmap-backed tiled storage. Decode still materializes a full frame once (very large files remain a RAM concern), but spill no longer keeps a second full `HxWx4` copy in memory.
- GPU residency and export tiling follow the same host store, so live view and still-image export stay on one pixel model.
- Still-image export above the tested 16384 px edge is allowed with a warning instead of silently clamping the composition plane.

Live preview, export preview, final still export, and video snapshots remain on the shared rendering contracts from 9.x — 10.0.0 extends that story to tiled storage and the Multi Compare path.

## Find Action, Help, and shell UX

- Find Action (`Ctrl+Shift+P`) searches commands across the host and the active tab, with grouping and “pulse” so you can see where a control lives.
- Help is a hierarchical hub: About, UI/platform topics, and workspace topics contributed by each tab, with illustrated scenario pages.
- Context menus on the canvas for common comparison actions.
- Dialog and settings chrome aligned with the external toolkit (CSD, geometry recipes, no QSS styling of toolkit controls).

## Video editor

- Preview vs export quality stays independent; timeline and keyframe pipelines keep getting tighter with the live canvas.
- Magnifier keyframing covers capture position and lens offset as separate tracks (new recordings pick up Offset tracks).
- Standard export tab layout and quality/CRF controls cleaned up for clearer encoding setup.

The video editor remains a recording → timeline → export workflow; broader editing UI is still expected to grow later.

## Packaging, toolkit, and license

- Consumes external `sli-ui-toolkit` (PySide6) instead of an in-tree widget dump.
- Flatpak / AUR / Windows metadata updated for 10.0.0, including refreshed store screenshots.
- Project license is GPL-3.0-or-later (temporary strategic choice while sustainability options are evaluated; see `DEVELOPMENT_HISTORY.md`).
- Third-party notices and Windows license bundling documented for Qt/FFmpeg redistribution.

## Known limitations

- Extremely large sources can still pressure RAM at decode time: a full frame is decoded once before spill into tiles.
- Still-image export above 16384 px on an edge is supported but marked untested in the UI.
- Undo/redo across session history and some Multi Compare state-binding cleanups remain on the engineering backlog (`docs/dev/TODO.md`).

## For packagers

- AppStream screenshots: `https://raw.githubusercontent.com/Loganavter/media_archive/2.0.0/Improve_ImgSLI/screenshots/screenshot_{1..5}.jpg`
- Metainfo release block: shorten the Highlights + one short paragraph; keep captions in English.
