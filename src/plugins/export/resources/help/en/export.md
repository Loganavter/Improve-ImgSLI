## Export

Still-image export of the current canvas.

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
- **Fill** — {{tr:export.fill_background}} paints the area around an image that is placed smaller than the frame. On an image that fills the frame, the option switches off.

### Metadata and favorites {#metadata-and-favorites}

- **Metadata** — {{tr:export.include_metadata}} stays on unless switched off; the comment field hides with it. {{tr:export.remember_by_default}} keeps the comment text for the next export.
- **Favorites** — {{tr:misc.set_as_favorite}} pins the current directory; {{tr:tooltip.use_favorite}} recalls it.
- **Labels** — when {{tr:image_compare.action.file_names}} is on, names render into the still.

### Quick save {#quick-save}

- **`Ctrl+S`** — {{tr:image_compare.action.quick_save}} reuses the last export settings without opening the dialog.
- **Tray** — the tray icon menu reopens the last saved file and folder.

### Recording and video {#video-editor}

Recording controls and video or GIF encoding are in the [Video Editor](help://video); this page covers still images only.
