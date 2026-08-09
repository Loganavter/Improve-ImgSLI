# `.imgsli` Container Format — Legacy Versions

Superseded formats for the `.imgsli` container. Current format lives in
[docs/dev/CONTAINER_FORMAT.md](../dev/CONTAINER_FORMAT.md); this doc exists
because both formats below are still readable today, so it's worth knowing
what they look like when one turns up on a user's disk.

`_validate_project_container` (`src/services/io/project_io.py`) accepts any
`version <= PROJECT_VERSION` and both `format` ids in
`_LEGACY_PROJECT_FORMATS` (`"imgsli"`, `"imgsli-project"`) — new saves never
write these anymore, but nothing was ever migrated on load, so old files
keep opening indefinitely.

## Version 2 — ZIP without pixel cache

Same ZIP layout as v3 minus `cache/` and the `"pixel_cache"` catalog key:

```text
project.json
preview.png (optional)
media/<asset_id>/<original_basename>
```

Loads through the exact same `prepare_project_file_for_load` path as v3 —
`data.get("pixel_cache")` is simply absent, so `_register_pixel_cache`
no-ops and every image re-decodes from `media/` on open, same as before the
pixel-cache feature existed.

## Version 1 — plain JSON, no embedded media

The original format, predating the ZIP/media-embedding rework. A single
JSON file (not a ZIP) at the `.imgsli` (or legacy `.imgsli-project`) path:

```json
{
  "format": "imgsli-project",
  "version": 1,
  "active_session_index": 0,
  "sessions": [
    {"session_type": "image_compare", "title": "...", "data": {"...": "..."}}
  ]
}
```

- No `media`/`preview.png`/`pixel_cache` — session `data` blobs hold **local
  filesystem paths directly** (`image1_path`, `image_list1[].path`, …), not
  portable ZIP members. Opening a v1 project on a machine that no longer has
  those source files at those paths fails to load the images (the project
  metadata itself still loads fine).
- `is_zip_project` returns `False` for these files, so
  `prepare_project_file_for_load` takes the plain-`json.loads` branch
  instead of the ZIP-extraction branch — no `cache_dir`, no path rewriting,
  no `pixel_cache` registration.
- `package_project_data`/`save_project_file` (current code) only ever
  produce ZIP output — there is no supported way to *write* a new v1 file;
  it is read-only legacy support.
