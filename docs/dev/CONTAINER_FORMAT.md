# `.imgsli` Container Format

The `.imgsli` file format is used to snapshot and restore the entire Improve-ImgSLI workspace, allowing users to save portable "projects" containing both their session state and embedded media files.

The container logic lives in `src/services/io/project_io.py` and `src/services/io/project_package.py`.

## Version 3 Portable Packages

A modern `.imgsli` file (version 3) is a **ZIP archive** with the following internal layout:

```text
project.json
preview.png (optional, active canvas thumbnail)
media/<asset_id>/<original_basename>
cache/<asset_id>/pixels.raw (optional, decoded RGBA8 spill buffer)
```

- **`project.json`**: The serialized state of all active workspace sessions, plus a `"pixel_cache"` catalog (`{asset_id: {member, width, height, tile_size, bytes}}`, empty by default).
- **`preview.png`**: A snapshot of the active canvas at the time of saving, used for OS-level thumbnails or quick previews.
- **`media/`**: Byte-copied (not re-encoded) images used within the project. The `<asset_id>` is the first 16 hexadecimal characters of the file's SHA-256 digest.
- **`cache/`**: Optional, opt-in per save (see below). Raw RGBA8 pixel buffers (`ZIP_STORED`, uncompressed) that let a future reopen skip re-decoding a source image entirely. Shares its `asset_id` with the corresponding `media/` entry, so cache validity is structurally tied to the exact embedded bytes.

*(Note: Legacy plain JSON v1 and ZIP v2 `.imgsli` files remain loadable for backward compatibility — see [docs/legacy/container-format.md](../legacy/container-format.md).)*

## Optional Embedded Pixel Cache

Project save can optionally embed each live session's already-decoded `TiledPixelStore` spill buffer, skipping the (often dominant) re-decode cost on reopen for large images.

- **Opt-in**: `save_project_file(..., include_pixel_cache=True)` / `package_project_data(..., pixel_cache_sources=...)`. The real UI save flow (`ui.main_window.project_io.MainWindowProjectIo`) gates this behind `self.include_pixel_cache` (currently hard-coded `False` — landing spot for a future "small, no cache" vs. "bigger, with cache" UI checkbox).
- **Source discovery**: tabs implement `TabContract.collect_pixel_cache_sources` (default: none) to expose their live, open `TiledPixelStore` instances by absolute source path.
- **Race safety**: `project_io.collect_pixel_cache_sources(store, tab_registry)` must run on the UI thread, immediately after `build_project_data`. It opens each store's spill-file fd right there — on Linux, `os.remove()` never invalidates an already-open fd, so a worker thread streaming that fd into the ZIP always sees a consistent snapshot even if the live store is swapped/closed concurrently.
- **Load path**: `prepare_project_file_for_load` extracts `cache/` members and registers `{abs_media_path: (cache_path, width, height)}` in `shared.image_processing.pixel_cache_registry`. The handful of `TiledPixelStore.from_path` call sites (image_compare's `_session_controller.py`, multi_compare's `use_cases/loading.py`) check this registry first and use `TiledPixelStore.from_embedded_cache` instead of decoding when a hit is found. The cached buffer's dimensions already reflect whatever crop was applied at save time, so no auto-crop pass runs again.

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

## Legacy Formats

Superseded container versions (v2 ZIP without pixel cache, v1 plain JSON)
are documented in [docs/legacy/container-format.md](../legacy/container-format.md)
— both remain loadable today, they're just never written anymore.
