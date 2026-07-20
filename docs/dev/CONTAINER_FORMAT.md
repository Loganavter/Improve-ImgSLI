# `.imgsli` Container Format

The `.imgsli` file format is used to snapshot and restore the entire Improve-ImgSLI workspace, allowing users to save portable "projects" containing both their session state and embedded media files.

The container logic lives in `src/services/io/project_io.py` and `src/services/io/project_package.py`.

## Version 2 Portable Packages

A modern `.imgsli` file (version 2) is a **ZIP archive** with the following internal layout:

```text
project.json
preview.png (optional, active canvas thumbnail)
media/<asset_id>/<original_basename>
```

- **`project.json`**: The serialized state of all active workspace sessions.
- **`preview.png`**: A snapshot of the active canvas at the time of saving, used for OS-level thumbnails or quick previews.
- **`media/`**: Byte-copied (not re-encoded) images used within the project. The `<asset_id>` is the first 16 hexadecimal characters of the file's SHA-256 digest.

*(Note: Legacy plain JSON v1 `.imgsli` files containing only local path references, without embedded media, remain loadable for backward compatibility.)*

## How Saving Works

1. **Snapshotting State**:
   On the UI thread, `build_project_data` reads from the Redux-like `Store` and asks the `TabRegistry` to serialize each active session via its tab's `serialize_session` hook.
2. **Rewriting Paths**:
   Original absolute paths in the session data (like `image1_path`, `image_list1`, etc.) are mapped to their new ZIP-relative `media/<asset_id>/<name>` locations.
3. **Packaging**:
   Off the UI thread, `package_project_data` computes SHA-256 hashes for all media files to deduplicate them, copies them into a temporary ZIP file alongside the rewritten `project.json` and `preview.png`, and atomically replaces the destination `.imgsli` file.

## How Loading Works

1. **Extraction (Cache)**:
   When opening an `.imgsli` file, `prepare_project_file_for_load` extracts the `media/` folder contents into a stable per-project cache directory (e.g., `~/.cache/ImproveImgSLI/projects/<key>/`).
2. **Rewriting Paths to Cache**:
   The paths in `project.json` are rewritten again—this time from the `media/...` format into the absolute paths pointing to the extracted cache directory.
3. **Rehydrating Workspace**:
   Back on the UI thread, `load_project_data` handles restoring the workspace by dispatching actions to create sessions and invoking `deserialize_session` and `rehydrate_session` for each tab's state. By default, opening a project replaces the current workspace sessions.
