## Image Properties

Inspect file metadata and in-app context for one loaded image without leaving the session.

### Open the dialog {#open}

Right-click a row in a {{tr:workspace.session_types.image_compare}} list, or a {{tr:workspace.session_types.multi_compare}} slot, and choose {{tr:image_properties.title}}. The dialog is read-only except for {{tr:image_properties.copy_all}}, which copies every visible row to the clipboard.

:::figure{side=right width=280}
![Image Properties dialog](ui/placeholder.png)
{{tr:image_properties.title}} (placeholder).
:::

### Sections {#sections}

Rows are grouped into:

- {{tr:image_properties.section_file}} — name, path, size on disk, format, modified time
- {{tr:image_properties.section_image}} — pixel size, aspect, orientation, channels, color mode / profile when available
- {{tr:image_properties.section_app}} — how the app places this image in the current session (see below)
- {{tr:image_properties.section_metadata}} — camera / EXIF-style fields when the file provides them

Missing values stay blank; a read error on the file is shown as {{tr:image_properties.read_error}}.

### In-app context {#in-app}

{{tr:image_properties.section_app}} depends on the session type. A {{tr:workspace.session_types.image_compare}} session may show {{tr:image_properties.side}} (left / right) and {{tr:image_properties.rating}}. {{tr:workspace.session_types.multi_compare}} may show {{tr:image_properties.position}} or {{tr:image_properties.slot}} for the cell. Those rows describe session state, not the file on disk.

### Close {#close}

{{tr:image_properties.close}} dismisses the dialog. Closing does not change lists, ratings, or the canvas.
