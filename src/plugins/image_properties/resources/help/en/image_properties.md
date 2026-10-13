## Image Properties

File metadata and in-app context for one loaded image. The dialog floats above the session and changes nothing in it.

### Open the dialog {#open}

The {{tr:image_compare.action.context_properties}} entry in a list or slot context menu opens {{tr:image_properties.title}} for that image.

:::figure{side=block width=280}
![Image Properties dialog](../assets/platform/image_properties.png)
{{tr:image_properties.title}}.
:::

### Sections {#sections}

Rows are grouped into:

- {{tr:image_properties.section_file}} — name, path, size on disk, format, modified time
- {{tr:image_properties.section_image}} — pixel size, aspect, orientation, channels, color mode / profile when available
- {{tr:image_properties.section_app}} — how the app places this image in the current session (see below)
- {{tr:image_properties.section_metadata}} — camera / EXIF-style fields when the file provides them

Rows without values are omitted; a file read error appears as {{tr:image_properties.read_error}}.

### In-app context {#in-app}

{{tr:image_properties.section_app}} depends on the session type. An {{tr:workspace.session_types.image_compare}} entry carries {{tr:image_properties.side}} (left / right) and {{tr:image_properties.rating}}. A {{tr:workspace.session_types.multi_compare}} cell carries {{tr:image_properties.position}}. Those rows describe session state, not the file on disk.

### Close {#close}

{{tr:image_properties.close}} dismisses the dialog. {{tr:image_properties.copy_all}} copies every visible row to the clipboard; individual rows offer their own copy.
