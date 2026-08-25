# Investigation: W3 Untrusted-input hardening — craft .imgsli DoS/SIGBUS + zip-bomb + UNC + ffmpeg minors

Date: 2026-08-25 (wave2, follow-up sub-agent)
Scope: `docs/dev/investigations/cross-module-review-2026-08-25-wave2.md` §W3 (W3.1-W3.4 + minor), `docs/dev/TODO.md` P2 Untrusted-input hardening, `improve-imgsli-internal-docs/docs/dev/KNOWN_BUGS.md` #5-6
Threat: malicious `.imgsli`/image shared between users, desktop-calibrated (no code exec, crash/DoS/resource).

## Trigger / Symptom

- **W3.1 SIGBUS clamp bypass:** `project_io.py:295-327` `_register_pixel_cache` reads `pixel_cache[asset_id].width/height` with truthiness-only check, passes directly to `pixel_cache_registry.register` → `TiledPixelStore.from_embedded_cache` → `np.memmap(shape=(h,w,4))` without `MAX_SUPPORTED_IMAGE_DIMENSION` (65536) clamp and without `st_size >= w*h*4` check (`tiled_pixel_store.py:182-183`, `pixel_cache_registry.py:12`). Crafted project with `width=100000,height=100000` crashes app (SIGBUS on Linux, sparse file) on open; bypasses dimension bound entirely. Also `from_embedded_cache` at `tiled_pixel_store.py:687-700` missing same guard.
- **W3.2 unbounded decompression:** No per-member or cumulative caps anywhere in zip pipeline: `project_package.py:370-549` `read_project_json_from_zip` (`zf.read` unbounded), `extract_media`/`extract_pixel_cache` (`shutil.copyfileobj` unbounded), `project_preview.py:248-257` (`zf.read` preview), `build/linux/bin/improve-imgsli-thumbnailer:198-203` (`zf.read` preview). ~10 MB zip can expand to hundreds of GB; thumbnailer triggers on directory listing (Nautilus/GNOME).
- **W3.3 legacy v1 UNC:** `project_io.py:365-367` plain-JSON v1 loads `image1_path` etc. as absolute strings and later tabs open them. On Windows a UNC `\\host\share\a.png` triggers automatic SMB credential exchange on mere open, no prompt/warn.
- **W3.4 zip-slip `startswith`:** `project_package.py:400-403,441-444` guard `str(target).startswith(str(cache_dir.resolve()))` without separator → sibling-dir escape in principle (e.g. `cache_dir=/a/b/projects/abc`, member `media/../../projects/evil/...` could be considered inside via prefix). Must use `Path.is_relative_to`.
- **Minor `encoding.py:16-49`:** `os.path.join(os.getcwd(), "ffmpeg")` (CWD-relative, attacker plants `ffmpeg` in shared dir), `-`-leading output filename parsed as option (`cmd.append(output_path)`), `shlex.split` with default `posix=True` mangles Windows backslash paths.

Verified against source at branch `migrate/qrhi` plus stashed wave2 partial fix (project_package already had `_is_within_directory`/`_atomic_extract_member`).

## Root cause

- W3.1: untrusted dims treated as trusted; missing clamp and file-size validation before memmap. `project_io.py:324-327` only checked `if not width or not height: continue`.
- W3.2: zip extraction assumed trusted producer; used unbounded stdlib APIs without declared-size pre-checks or streaming caps.
- W3.3: v1 format predates embedded media; path strings persisted verbatim, no warning layer.
- W3.4: string-prefix check is not a path-boundary check.
- Minor: ffmpeg discovery copied naïve CWD fallback; output path appended without `--` sentinel; `shlex` default ignores Windows.

## False leads

- Considered capping `write_project_zip` as well — rejected: that path writes trusted local files, caps add no safety and could break legitimate large saves.
- Considered prompting dialog for UNC (GUI) in worker-safe `prepare_project_file_for_load` — rejected: function is documented worker-safe, cannot show UI off main thread; logging + warnings return is correct layer.
- Initial per-member limit as default arg `per_member_limit=ZIP_MAX_MEMBER_BYTES` read at definition time — changing module constant in tests did not affect default; fixed to `None` sentinel that reads current global.
- `media/../evil.txt` inside same hash dir is not an escape beyond `cache_dir` — old and new guard both allow it. True zip-slip requires `../../` beyond base; sibling-hash escape is already blocked by `is_relative_to`.

## Fix

### W3.1 — clamp + st_size guard

- `src/services/io/project_io.py:295-360` — new helpers `_is_unc_path`, `_collect_legacy_path_warnings`; rewrite `_register_pixel_cache` (W3.1): int-cast with try/except, reject `<=0` or `> AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION` (`65536`), `Path(extracted_path).stat().st_size` vs `w*h*4`, log and skip on mismatch.
- `src/shared/image_processing/tiled_pixel_store.py:686-720` — `from_embedded_cache` now validates same bounds and `st_size` before `_reopen_readonly`, raises `ValueError/OSError` instead of SIGBUS.

### W3.2 — decompression caps

- `src/services/io/project_package.py:28-35` — new constants `ZIP_MAX_PROJECT_JSON_BYTES=16MiB`, `ZIP_MAX_PREVIEW_BYTES=32MiB`, `ZIP_MAX_MEMBER_BYTES=2GiB`, `ZIP_MAX_TOTAL_BYTES=4GiB`.
- `src/services/io/project_package.py:371-411` — new `_capped_copy(src,dst,limit,member)` and hardened `read_project_json_from_zip` (pre-check `info.file_size`, streaming capped copy).
- `src/services/io/project_package.py:429-460` — `_atomic_extract_member` now takes `per_member_limit=None` sentinel, pre-checks `info.file_size`, streams via `_capped_copy`.
- `src/services/io/project_package.py:499-598` — `extract_media` and `extract_pixel_cache` accumulate `cumulative` declared sizes and raise if `> ZIP_MAX_TOTAL_BYTES`; reuse path still via size-matched check; calls to `_atomic_extract_member` now capped.
- `src/services/io/project_preview.py:248-275` — `read_preview_image_bytes` now pre-checks `info.file_size` and streams via `_capped_copy` with `ZIP_MAX_PREVIEW_BYTES` (log and skip oversize).
- `build/linux/bin/improve-imgsli-thumbnailer:20-23,198-230` — add `_ZIP_MAX_PREVIEW_BYTES=32MiB`, capped `zf.open` loop instead of `zf.read`; handles `ValueError`.

### W3.3 — legacy v1 absolute/UNC warn

- `src/services/io/project_io.py:295-310,365-375` — `_is_unc_path` (`\\\\` / `//`), `_collect_legacy_path_warnings` iterates `iter_session_media_paths`, `prepare_project_file_for_load` (non-zip branch) logs and appends to `warnings` return. Tabs still receive paths but caller can surface warning; avoids silent SMB.

### W3.4 — zip-slip is_relative_to

- `src/services/io/project_package.py:414-427,526,581` — introduce `_is_within_directory(base,target)` using `target.resolve().is_relative_to(base.resolve())` (Py3.11) with `relative_to` fallback; used in both `extract_media` and `extract_pixel_cache`. Already present in stashed wave2 diff, verified both extract sites (was 400/441, now 526/581) use it; `_atomic_extract_member` no longer needs separate guard.

### Minor — encoding.py

- `src/tabs/image_compare/plugins/video_editor/services/video_export/encoding.py:3-8,14-33` — add `sys`, `Path` imports; replace CWD-relative `ffmpeg` fallback with candidates `Path(sys.executable).parent/{ffmpeg,ffmpeg.exe}` and `Path(__file__).parents[6]/{ffmpeg,ffmpeg.exe}` (app-dir, not CWD).
- `src/tabs/image_compare/plugins/video_editor/services/video_export/encoding.py:62-72,144-149` — `manual_args` parsed via `shlex.split(raw, posix=(os.name != "nt"))`; output path appended as `["--", out]` when `out.startswith("-")` else `out` (both manual and normal branches).

## Files changed

| File | Lines | Change |
|---|---|---|
| `src/services/io/project_package.py:28-35` | +7 | `ZIP_MAX_*` caps constants |
| `src/services/io/project_package.py:371-411` | +20 | `_capped_copy`, capped `read_project_json_from_zip` |
| `src/services/io/project_package.py:414-427` | +14 | `_is_within_directory` (is_relative_to) |
| `src/services/io/project_package.py:429-460` | ~20 | `_atomic_extract_member` capped, sentinel default |
| `src/services/io/project_package.py:499-552` | ~25 | `extract_media` cumulative cap |
| `src/services/io/project_package.py:555-598` | ~20 | `extract_pixel_cache` cumulative cap |
| `src/services/io/project_io.py:295-360` | ~70 | `_is_unc_path`, `_collect_legacy_path_warnings`, hardened `_register_pixel_cache` (clamp + st_size) |
| `src/services/io/project_io.py:365-375` | +5 | legacy v1 warnings in non-zip branch |
| `src/shared/image_processing/tiled_pixel_store.py:686-720` | ~20 | `from_embedded_cache` dims + st_size guard |
| `src/services/io/project_preview.py:248-275` | ~25 | capped `read_preview_image_bytes` |
| `build/linux/bin/improve-imgsli-thumbnailer:20-23` | +3 | `_ZIP_MAX_*` |
| `build/linux/bin/improve-imgsli-thumbnailer:198-230` | ~25 | capped `zf.open` loop |
| `src/tabs/image_compare/plugins/video_editor/services/video_export/encoding.py:3-8` | +3 | `sys`, `Path` imports |
| `src/tabs/image_compare/plugins/video_editor/services/video_export/encoding.py:14-33` | ~15 | CWD → app-dir ffmpeg fallback |
| `src/tabs/image_compare/plugins/video_editor/services/video_export/encoding.py:62-72` | ~7 | `shlex` posix=False on Windows, `--` sentinel |
| `src/tabs/image_compare/plugins/video_editor/services/video_export/encoding.py:144-149` | ~5 | normal-branch `--` sentinel |

## Testing

- **py_compile:** `python -m py_compile` on all touched files — `ok1..ok6`.
- **pytest focused:** `QT_QPA_PLATFORM=offscreen pytest -q -k "project_io or project_package or encoding or thumbnailer or preview"` — **117 passed, 2881 deselected** (4.06s).
- **pytest collect:** `--collect-only` — 2998 tests collected.
- **contracts:** `pytest -q tests/contracts` — 1474 passed, 3 failed (pre-existing: `test_oversized_files_have_audit_meta` — 3 files over 500 lines without Audit-Meta, unrelated to W3; `test_no_arrow_key_redirection` Up/Down remap in `scroll_value_button.py:191,490` — pre-existing).
- **Manual craft regressions (PYTHONPATH=src, QT_QPA_PLATFORM=offscreen):**
  - Craft `.imgsli` with `pixel_cache width=100000,height=100000` + 10-byte raw → registry empty, log `dims ... out of bounds` — **PASS W3.1 clamp**.
  - Same with valid dims 100x100 but 10-byte raw (expected 40000) → `Skipping pixel_cache ... file too small` — **PASS st_size guard**.
  - Valid dims 100x100 with 40000-byte raw → registry populated — **PASS positive**.
  - `TiledPixelStore.from_embedded_cache` with 10-byte file 10x10 → `ValueError Embedded cache file too small` — **PASS**.
  - `TiledPixelStore.from_embedded_cache` with 70000x70000 → `ValueError out of bounds` — **PASS**.
  - Legacy v1 JSON with `\\host\share\a.png` → `warnings=["UNC path ..."]` — **PASS W3.3**.
  - `ZIP_MAX_MEMBER_BYTES=10` with 20-byte media member → `ValueError Zip member ... too large` — **PASS W3.2 per-member**.
  - `ZIP_MAX_TOTAL_BYTES=30` with two 20-byte members → `ValueError Total extracted media exceeds cumulative limit` — **PASS cumulative**.
  - `project.json` 16MiB+1 → `ValueError project.json too large` — **PASS**.
  - `preview.png` 32MiB+1 → `read_preview_image_bytes` returns `None` — **PASS**.
  - `encoding.py` with `os.name="nt"`, `manual_args=r'-c:v libx264 -i "C:\path\to\file.mp4"'` + output `-out.mp4` → `cmd` contains `C:\path\to\file.mp4` preserved and `["--","-out.mp4"]` — **PASS shlex/--**.
  - Zip-slip `media/../evil.txt` stays inside hash dir (allowed, not escape); `../../../etc/passwd` style would be blocked by `is_relative_to` — verified.

All W3 items closed. No remaining open W3 subtasks.

## Remaining / Out of scope

- `purge_old_project_caches` and atomic extract already present in stashed diff — verified, no further change.
- GNOME thumbnailer runs without GUI; warning granularity is log-only, no desktop notification — acceptable per threat model (directory-listing trigger).
- Per-member cap 2GiB / total 4GiB may reject rare legitimate 30k×30k cache raw (3.6GiB+); documented as intentional DoS trade-off, adjustable via constants.
