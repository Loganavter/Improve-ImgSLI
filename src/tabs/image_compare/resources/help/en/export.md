## Export

Save what you see as a still image. Recording and the video editor have their own topic: [Video Editor](help://video).

### Save a still {#saving-an-image}

{{tr:image_compare.action.save}} (`Ctrl+Shift+S`) opens the export dialog.

- **Path** — output directory and file name.
- **Format** — PNG, JPEG, WEBP, BMP, TIFF, or JXL.
- **Preview** — live pane shows the composed result before you write the file.

:::figure{side=right width=280}
![Export dialog](ui/placeholder.png)
{{tr:image_compare.action.breadcrumb.toolbar}} → {{tr:image_compare.action.breadcrumb.export}} (placeholder).
:::

### Resolution and quality {#resolution-and-quality}

- **Size** — width and height when the source size is known; lock keeps aspect ratio.
- **Quality** — {{tr:label.quality}} for lossy formats.
- **PNG** — compression level and {{tr:export.optimize_png}}.
- **Fill** — transparent formats can enable {{tr:export.fill_background}} and pick a fill color.

### Metadata and favorites {#metadata-and-favorites}

- **Metadata** — {{tr:export.include_metadata}}; optional comment and {{tr:export.remember_by_default}}.
- **Favorites** — {{tr:misc.set_as_favorite}} / {{tr:tooltip.use_favorite}} after browsing a directory.
- **Labels** — when {{tr:image_compare.action.file_names}} is on, names can burn into the still.

### Quick save {#quick-save}

- **`Ctrl+S`** — {{tr:image_compare.action.quick_save}} with the last export settings.
- **`Ctrl+Shift+S`** — always opens the dialog.
- **Tray** — optional access to the last save under [Settings → General](help://settings#general).

### Recording and video {#video-editor}

To capture a session and encode video or GIF, see [Video Editor](help://video). Stills and video keep visual parity with the live canvas (including difference modes).
