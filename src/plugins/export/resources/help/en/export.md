## Export

Still-image export of the current canvas. Session capture and video encoding belong to a separate topic: [Video Editor](help://video).

### Save a still {#saving-an-image}

{{tr:image_compare.action.save}} (toolbar or {{tr:menu.find_action}}) opens the export dialog.

- **Path** — output directory and file name.
- **Format** — PNG, JPEG, WEBP, BMP, TIFF, or JXL.
- **Preview** — a live pane shows the composed result before writing.

:::figure{side=block width=630}
![Export dialog]({{img:workspace.image_compare.export.dialog}})
{{tr:image_compare.action.breadcrumb.toolbar}} → {{tr:image_compare.action.breadcrumb.export}}.
:::

### Resolution and quality {#resolution-and-quality}

- **Size** — width and height fields with an aspect-ratio lock.
- **Quality** — {{tr:label.quality}} appears for lossy formats only.
- **PNG** — compression level and {{tr:export.optimize_png}}.
- **Fill** — {{tr:export.fill_background}} paints padded areas when the virtual canvas extends past `0..1`. On a unit canvas the option switches off.

### Metadata and favorites {#metadata-and-favorites}

- **Metadata** — {{tr:export.include_metadata}} stays on unless switched off; the comment field hides with it. {{tr:export.remember_by_default}} keeps the comment text for the next export.
- **Favorites** — {{tr:misc.set_as_favorite}} pins the current directory; {{tr:tooltip.use_favorite}} recalls it.
- **Labels** — when {{tr:image_compare.action.file_names}} is on, names render into the still as session state, not file data.

### Quick save {#quick-save}

- **`Ctrl+S`** — {{tr:image_compare.action.quick_save}} reuses the last export settings without opening the dialog.
- **Tray** — the tray icon menu reopens the last saved file and folder.

### Recording and video {#video-editor}

Recording controls and video/GIF encoding belong to the [Video Editor](help://video).
