STATUS: done

PR: "none"

TESTS:
1. `PYTHONPATH=$PWD/src QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 python3 src/devtools/bench_strip_batch.py --self-test -q` -> exit 0, "self-test: 0 failure(s)" (43 checks: viewport rects tile the atlas, uniform block == std140 size 192 and stride 256-aligned, instance stride == 100B packed size, layer2 round-trip, hash determinism / one-pixel sensitivity, DPR remap).
2. `... python3 src/devtools/bench_strip_batch.py --cpu-only` -> exit 0, N | plan_ms | pack_ms:
   17 | 163.1 | 0.35
   32 | 306.4 | 0.57
   64 | 618.7 | 1.02
3. `... python3 src/devtools/bench_strip_batch.py --frames 17` offscreen -> exit 2, "needs a display: QRhi did not start for a probe QRhiWidget (null rhi(); platform=offscreen)". No fabricated pass.
4. `PYTHONPATH=$PWD/src QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 python3 -m pytest src/tabs/image_compare/tests/video tests/contracts -q -p no:cacheprovider -o addopts=""` -> 3415 passed, 78 skipped, 1 xfailed, 1 warning in 174.97s (run twice, second time on the committed tree).
5. `python3 src/devtools/file_meta.py --check` -> "Registry OK" after `--write-registry` (registry entry added for the new file; the file is 1505 lines, so it carries `Audit-Meta: pattern=instrument`).
6. `python3 scripts/check_comment_citations.py` -> 0 findings for `src/devtools/bench_strip_batch.py` (baseline was 340 findings tree-wide, now 339 — the one in this file was fixed before commit).
7. GPU half was exercised on a private Xvfb (`Xvfb :77`, `LIBGL_ALWAYS_SOFTWARE=1`, llvmpipe): `DISPLAY=:77 ... python3 src/devtools/bench_strip_batch.py --frames 2|17|32|64` -> exit 1 (mismatch), numbers in SUMMARY. Exit 2 on the offscreen platform only.

INTERFACE:
`bench_strip_batch.py [--self-test] [--cpu-only] [--frames 17,32,64] [--tiles 160x90] [--reference-samples K] [-q]`
`plan_tile_grid(count, tile_w, tile_h, cols=None) -> (cols, rows, width, height)`
`tile_rects(count, tile_w, tile_h, cols) -> [(x, y, w, h)]`
`target_units(rects, grabbed_size) -> (scaled_rects, (sx, sy))`
`slice_tile_bytes(rgba, size, rect) -> bytes`
`hash_rgba(data) -> str`
`diff_stats(reference, candidate, size) -> (differing_px, first_xy)`
`pad_uniform_block(block, stride=256) -> bytes`
`uniform_offset(index, stride=256) -> int`
`pack_tile_uniforms(rhi, tile) -> bytes` (production `pack_array_uniforms`)
`pack_tile_instance(tile, layer1, layer2) -> bytes` (production `pack_array_instance`)
`build_tiles(count, tile_w, tile_h, image1_path, image2_path, verbose=...) -> (tiles, plan_ms)`
`pack_tiles(tiles, rhi=None) -> pack_ms`
`render_reference_tiles(tiles, sample_count) -> ([(hash, debug, raw_bytes)], ms)`
`run_batch_pass(tiles, cols) -> (hashes, tile_bytes, timings)`
`preflight_rhi() -> None` (raises `_NoDisplayError`)

SELF-REVIEW:
- Re-read the whole file before commit; removed a strip-overlays experiment (`--base-only`) that changed the reference scene more than the overlay payloads and produced misleading numbers.
- Re-ran the four acceptance commands on the committed tree (suite twice: once before the DPR fixes, once after, both green).
- Re-read the two contract failures my file caused (`tests/contracts/test_dpr_defect_catalog.py::test_no_known_dpr_failure_mode_in_the_tree`, `tests/contracts/test_file_size_policy.py::test_oversized_files_have_audit_meta`) and fixed the code, not the tests: viewport/scissor now derive from `target.pixelSize()` (`*_fb` names the detector sanctions), the readback refuses a device-pixel-to-logical resample (`_PreconditionError`, exit 1 with "run with QT_SCALE_FACTOR=1"), and the file carries the Audit-Meta marker + registry entry.
- Re-ran the GPU path on :77 after each change; the layer-assignment failure described in SUMMARY was reproduced three times (N=4, 8, 17) and is not flaky.

SUMMARY:
- New devtool `src/devtools/bench_strip_batch.py` (no product file touched, never imported by app code): builds N real frame plans with `SnapshotFrameRenderer.prepare_canvas_frame_from_images` from two generated 3000x2000 sources (per-frame shifted tile-sized proxies, the strip's own proxy shape), renders one reference tile set through the current per-tile route (`GpuExportService.render_plan`, the GPU step `render_snapshot_thumbnail_to_pil` ends in), renders the N plans into ONE target with one beginPass/endPass (one viewport + one scissor + per-tile uniform block and texture-array layer pair per tile, production `base_array` shaders/pipeline via the tab's `ArrayResources`), reads the target back once and slices/hashes each tile.
- CPU numbers (offscreen, reproducible): plan_ms 163/306/619 for 17/32/64; uniform+instance packing 0.35/0.57/1.02 ms — packing is ~3 orders of magnitude cheaper than planning, so per-tile uniforms are not the cost of a batched strip.
- GPU numbers (llvmpipe on a private Xvfb, software rendering, so absolute values are pessimistic): pass_ms 0.17 (2 tiles) / 0.34 (17) / 0.50 (32) / 0.88 (64); one atlas readback 0.17-8.42 ms. The one-pass structure is cheap; the readback, not the pass, is what scales with N.
- Exactness, measured: with 2 tiles the atlas is 14040/14400 px byte-identical to the per-tile reference; the 360 px delta is exactly the divider overlay band (first differing px at x=78) — the batch draws the base-image pass only.
- Exactness, NOT proven: above 2 tiles the bench's own layer assignment breaks — uploads into array layers >= 2 do not land, so later frames alias layers 0/1 (tile 0 shows another frame) and the never-written tiles read back fully transparent (N=17: tiles 2,3,4). Content, viewport and scissor are ruled out (identical instance/uniform path is pixel-exact at N=2, blank rects are inside the target). The unruled-out suspect is the bench-local `layer = index * 2` mapping: production assigns layers via `TileTextureService`/`upload_tile_to_array` including residency and capacity shrink (`remembered_capacity`). So phase 0 gives "the pass is cheap and the base draw is bit-exact; N plans in one pass is blocked by the layer/upload path, not by the draw or the uniforms".
- Risks for the batch, as measured or identified: (1) per-tile texture-array layers — the real bottleneck, needs the production upload path re-tested; (2) overlay passes (divider/guides/capture/filename) are per-frame draws today and would need per-tile invocation inside the same pass — the 360 px divider delta shows they are not covered; (3) texture variability: the batch must upload exactly the plan's own pixels (uploading the pre-plan proxies made 100% of pixels differ by resample rounding — the bench now uploads `plan.image1/2`, which are `TiledPixelStore`s materialized through `read_array`); (4) the atlas target size grows as cols*tiles, and 64 tiles at 160x90 is 8x8 = 1280x720, still one texture.

LIVE-PROOF WANTED:
1. On a lease (real display or Xvfb on the real GPU, not llvmpipe):
   `cd <clone> && PYTHONPATH=$PWD/src QT_SCALE_FACTOR=1 python3 src/devtools/bench_strip_batch.py`
   Expected today: exit 1, table with N=17/32/64, `exact_matches` 0/N except possibly at small N, and the "tiles read back fully transparent" line. What proves the assumption: `exact_matches/N == N/N` for all three rows AND `pass_ms` at N=17 <= 20 ms. Anything else refutes or defers it.
2. Cheapest decisive next step (N=2 control, proves the harness itself is exact):
   `... python3 src/devtools/bench_strip_batch.py --frames 2`
   Expected: `tile 0: 14040/14400 px byte-identical` and a 360 px delta at x=78 (overlay band). If this does not reproduce on the lease, the bench's reference/batch contract is broken there too, and the N>2 numbers cannot be read.
3. The layer/upload failure needs the production layer assignment: re-drive the batch's texture upload through `TileTextureService.mark_resident` + `TileTextureService.slot_for` + `ArrayResources.upload_tile_to_array` (instead of `layer = index * 2`) and re-run 1; that is the experiment that decides "one pass for N plans".
