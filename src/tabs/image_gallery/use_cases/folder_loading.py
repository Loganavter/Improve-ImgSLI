"""Folder loading for the Image Gallery controller.

Thin-owner helpers: plain functions taking the owner (``GalleryController``).
``open_folder`` scans a directory (or delegates a single-image pick to
``open_paths``), ``open_paths`` opens/append an explicit file list, and
``_on_pick_folder`` is the folder-dialog slot. The owner keeps the shared
primitives (``_next_folder_gen`` / ``_find_item`` / ``_analysis_fingerprint``)
and the folder-generation discipline — these functions only drive them through
``owner``.

The ``state.*`` mirror writes go through ``setattr``: a bare ``.state.X =``
outside ``controller.py`` is rejected by the gallery ownership guard
(``src/tabs/image_gallery/tests/contracts/test_gallery_ownership_guards.py``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from core.state_management.gallery_actions import (
    GalleryPathsAppended,
    GalleryPoolOpened,
    GalleryPoolReplaced,
)
from tabs.image_gallery.debug import gallery_debug as _dbg
from tabs.image_gallery.debug import gallery_dnd_debug as _dnd_log
from tabs.image_gallery.models import GalleryItem, GalleryState, TriageState
from tabs.image_gallery.services.folder_scanner import scan_folder

logger = logging.getLogger("ImproveImgSLI")


def open_folder(owner, folder: Path) -> None:
    import time

    t0 = time.perf_counter()
    folder = Path(folder)
    gen = owner._next_folder_gen()
    # P1: a folder switch invalidates the metric profile — the previous
    # folder's axis set must never leak into the new one. A fresh state carries
    # ``metric_profile=None`` anyway; this is the explicit invalidation point,
    # and the next mode/metrics settle derives the new folder's profile.
    clear = getattr(owner, "clear_metric_profile", None)
    if callable(clear):
        try:
            clear()
        except Exception:
            logger.debug("metric profile clear failed", exc_info=True)
    # Fresh world: stable ids restart (pins are path-keyed and stay
    # inert for the new pool).
    owner._series_next_id = 1
    _ = gen  # sync scan below replaces state immediately; gen guards workers
    _dnd_log("open_folder: ENTER %s is_file=%s is_dir=%s", folder, folder.is_file(), folder.is_dir())
    # If a single image file was passed (user dropped one image), don't scan its parent
    # — show just that image. Previously we scanned parent and fed entire folder (1037 items).
    if folder.is_file():
        _dnd_log("open_folder single file branch -> open_paths single %s", folder)
        # Delegate to open_paths so we don't set folder to parent
        try:
            owner.open_paths([folder])
            _dnd_log("open_folder: EXIT via open_paths (%.1f ms)", (time.perf_counter() - t0) * 1000)
            return
        except Exception:
            _dnd_log("open_folder single file fallback", exc_info=True)
            try:
                mtime = folder.stat().st_mtime_ns
            except Exception:
                mtime = 0
            items = [GalleryItem(path=folder, mtime_ns=mtime)]
            display_folder = folder.parent
            owner.state = GalleryState(folder=display_folder, items=items, triage_state=TriageState.RUNNING)
            _dbg("open_folder single file -> parent %s items=%d", display_folder, len(items))
            owner.widget.set_folder_label(display_folder)
            owner._hydrate_ai_cache(items)
            owner.widget.rebuild_grid(items)
            owner._emit_gallery(
                GalleryPoolOpened(
                    folder=str(display_folder),
                    entries=[(str(it.path), it.mtime_ns) for it in items],
                )
            )
            for item in items:
                owner._load_thumbnail(item)
            owner._start_triage(items)
            return
    _dnd_log("open_folder: scan_folder START %s", folder)
    items = scan_folder(folder)
    _dnd_log("open_folder: scan_folder DONE %s -> %d items (%.1f ms)", folder, len(items), (time.perf_counter() - t0) * 1000)
    _dnd_log("open_folder scanned %s -> %d items", folder, len(items))
    owner.state = GalleryState(folder=folder, items=items, triage_state=TriageState.RUNNING)
    _dnd_log("open_folder: set state + rebuild_grid START (%d items)", len(items))
    owner.widget.set_folder_label(folder)
    owner._hydrate_ai_cache(items)
    owner.widget.rebuild_grid(items)
    _dnd_log("open_folder: rebuild_grid DONE (%.1f ms total)", (time.perf_counter() - t0) * 1000)
    owner._emit_gallery(
        GalleryPoolOpened(
            folder=str(folder),
            entries=[(str(it.path), it.mtime_ns) for it in items],
        )
    )
    owner._begin_folder_schedule(items, gen)
    owner._start_triage(items)
    _dnd_log("open_folder: EXIT ok (%.1f ms)", (time.perf_counter() - t0) * 1000)


def open_paths(owner, paths: list[Path], *, replace: bool = False) -> None:
    """Open an explicit list of image paths (single/multiple drop).

    Fixes "скормить всю папку когда скинул одно изображение": previously
    a single image drop was converted to its parent folder and the whole
    folder was scanned (40 images). Now we build items only from the
    explicitly dropped paths.

    ``replace=False`` (default, file-drop style) APPENDS to the current
    pool — each FM file drop used to wipe the pool because ``uniq`` was
    built from the new drop only. ``replace=True`` restores the old
    wipe-and-replace (mixed folder+files drops where the dropped folder
    becomes the pool context).
    """
    import time

    t0 = time.perf_counter()
    _dnd_log("open_paths: ENTER %d paths %r replace=%s", len(paths), paths[:3], replace)
    if replace:
        # Folder switch cancels everything in flight from the previous folder.
        owner._next_folder_gen()
        # P1: replace = a new folder context — invalidate the previous
        # folder's metric profile (the next settle derives the new one).
        clear = getattr(owner, "clear_metric_profile", None)
        if callable(clear):
            try:
                clear()
            except Exception:
                logger.debug("metric profile clear failed", exc_info=True)
        old_items: list[GalleryItem] = []
    else:
        # Append: no folder switch — in-flight thumbnail/triage workers for
        # the old pool stay valid, so the generation is left untouched.
        old_items = list(owner.state.items)
    # Filter to images that exist
    from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS

    filtered: list[GalleryItem] = []
    for p in paths:
        pp = Path(p)
        if pp.is_file() and pp.suffix.lower() in ACCEPTED_IMAGE_EXTENSIONS:
            try:
                mtime = pp.stat().st_mtime_ns
            except Exception:
                mtime = 0
            filtered.append(GalleryItem(path=pp, mtime_ns=mtime))
        elif pp.is_dir():
            # If a directory was dropped among files, scan it
            filtered.extend(scan_folder(pp))
    # Deduplicate by path — seeded from the old pool when appending so
    # re-dropped files don't duplicate and already-loaded items are known.
    def _key(it: GalleryItem) -> str:
        try:
            return str(it.path.resolve()) if it.path.exists() else str(it.path)
        except Exception:
            return str(it.path)

    seen: set[str] = {_key(it) for it in old_items}
    uniq: list[GalleryItem] = []
    for it in filtered:
        s = _key(it)
        if s not in seen:
            seen.add(s)
            uniq.append(it)
    # Append: old pool first, truly-new drops at the end.
    merged: list[GalleryItem] = list(old_items) + uniq
    if not uniq and not replace:
        # Pure no-op (re-drop of known files): pool, label and folder are
        # already current — rebuilding would demolish headers for nothing.
        # Still ensure grouping: flat cards that never got triaged (e.g.
        # materialized by an external sync first) need their first pass;
        # a live series view needs nothing at all.
        try:
            gv = getattr(owner.widget, "_grid_view", None)
            grouped = bool(getattr(gv, "_series", None))
        except Exception:
            grouped = False
        if grouped or not merged:
            return
        owner._start_triage(merged, cover_grid=False)
        return
    # For explicit file drops, don't set folder to parent — keep it None
    # so we don't imply the whole parent folder was opened (fixes "установил путь на папку"
    # when user dropped a single image). Folder is only set when a directory
    # was explicitly dropped/scanned. For file lists, display_folder stays None
    # and the label shows the dropped files, not their parent.
    display_folder = None
    has_dir_input = any(Path(p).is_dir() for p in paths)
    if has_dir_input and uniq:
        # Directory was among dropped paths — use its path as folder
        for p in paths:
            if Path(p).is_dir():
                display_folder = Path(p)
                break
        if display_folder is None:
            try:
                display_folder = uniq[0].path.parent
            except Exception:
                display_folder = None
    # else: file-only drop — leave display_folder as None (no folder context),
    # unless appending into a folder-backed pool: then keep the folder so
    # folder actions (run-triage reopen, pick start_dir) keep working.
    if not has_dir_input and not replace and owner.state.folder is not None:
        display_folder = owner.state.folder
    # else: file-only drop — leave display_folder as None (no folder context)
    # S2: the fresh state wipes series/mode/source — snapshot the live
    # view first so the append-attach branch below can keep it.
    try:
        prev_series = list(owner.state.series or [])
    except Exception:
        prev_series = []
    try:
        prev_mode = owner.state.mode
    except Exception:
        prev_mode = None
    try:
        prev_source = owner.state.source_path
    except Exception:
        prev_source = None
    try:
        prev_triage = owner.state.triage_state
    except Exception:
        prev_triage = TriageState.IDLE
    owner.state = GalleryState(folder=display_folder, items=merged, triage_state=TriageState.RUNNING)
    _dnd_log(
        "open_paths -> folder %s items=%d (has_dir=%s replace=%s old=%d new=%d) (%.1f ms)",
        display_folder, len(merged), has_dir_input, replace,
        len(old_items), len(uniq), (time.perf_counter() - t0) * 1000,
    )
    if display_folder is not None:
        owner.widget.set_folder_label(display_folder)
    else:
        # For single/multi file drop, show what was actually dropped, not parent
        try:
            if len(uniq) == 1:
                owner.widget.set_folder_label(uniq[0].path)
            elif len(uniq) > 1:
                owner.widget.set_folder_label(Path(f"{len(uniq)} images dropped"))
            else:
                owner.widget.set_folder_label(Path(""))
        except Exception:
            pass
    owner._hydrate_ai_cache(merged)
    owner.widget.rebuild_grid(merged)
    # Mirror pool membership into the slot AFTER the local mirror + grid
    # are current, so the resulting 'gallery' emit reconciles to a no-op.
    if replace:
        owner._emit_gallery(
            GalleryPoolReplaced(
                folder=str(display_folder) if display_folder is not None else None,
                entries=[(str(it.path), it.mtime_ns) for it in merged],
            )
        )
    elif uniq:
        owner._emit_gallery(
            GalleryPathsAppended(
                entries=[(str(it.path), it.mtime_ns) for it in uniq],
            )
        )
    # Thumbnails only for truly-new items — old ones are already loaded.
    for item in uniq:
        owner._load_thumbnail(item)
    # S2 append: NEW files only join the nearest EXISTING series
    # (in-memory attach — existing membership untouched, no retriage)
    # when a grouped view is live and quiet; otherwise the existing
    # seed pipeline runs over the merged pool. A fresh pool (or
    # replace) covers until first groups; appends keep groups visible.
    if replace:
        # Fresh world: stable ids restart.
        owner._series_next_id = 1
        owner._start_triage(merged, cover_grid=True)
    elif not old_items:
        owner._start_triage(merged, cover_grid=True)
    elif prev_series and prev_triage != TriageState.RUNNING:
        setattr(owner.state, "series", prev_series)  # type: ignore[arg-type]
        setattr(owner.state, "mode", prev_mode)  # type: ignore[arg-type]
        setattr(owner.state, "source_path", prev_source)  # type: ignore[arg-type]
        try:
            owner._attach_append_items(uniq)
        except Exception:
            logger.debug("append attach failed", exc_info=True)
        # S2 tail regroup: attach never compares new files with each
        # other, so mutually-similar drops would sit UNGROUPED until a
        # manual re-cluster. Regroup the tail (old singletons + fresh
        # misses) into new series; existing membership untouched.
        try:
            owner._cluster_tail_into_series()
        except Exception:
            logger.debug("append tail cluster failed", exc_info=True)
        # Stage-2 analyses (artifacts + fidelity + camera) for the NEW
        # items. The attach path deliberately skips re-clustering ("no
        # retriage"), but analysis is per-item and independent of
        # membership — without this the appended card kept "not measured"
        # rows while the first-drop cards were fully analyzed. Mirror
        # _apply_triage_result's fingerprint bookkeeping so a later
        # regroup does not re-run the whole pool.
        try:
            owner._last_analysis_fingerprint = owner._analysis_fingerprint(
                list(owner.state.items), prev_source
            )
        except Exception:
            pass
        setattr(owner.state, "triage_state", TriageState.DONE)
        # Newer than any in-flight triage: its delivery drops (sgen).
        owner._next_series_gen()
        try:
            owner._apply_series_view(owner.state.series)
        except Exception:
            logger.debug("append attach view failed", exc_info=True)
        # Post-first-load drops get the SAME processing feedback as a
        # first load: per-card activity pill + toolbar spinner/count.
        # Shown AFTER ``_apply_series_view`` — its ``set_triage`` /
        # ``set_triage_done`` retires the S1 spinner and would otherwise
        # clobber this indicator in the same event-loop turn, so it never
        # painted. The proxy ``on_done`` retires it when the batch settles.
        owner._begin_append_processing(uniq)
        try:
            owner._start_proxy_analysis(
                list(uniq), prev_source, prev_mode,
                on_done=lambda its=list(uniq): owner._finish_append_processing(its),
            )
        except Exception:
            logger.debug("append analysis start failed", exc_info=True)
            owner._finish_append_processing(uniq)
    else:
        owner._start_triage(merged, cover_grid=False)


def _on_pick_folder(owner) -> None:
    start_dir = str(owner.state.folder) if owner.state.folder else ""
    chosen = owner.widget.pick_folder_dialog(start_dir=start_dir)
    if not chosen:
        return
    p = Path(chosen)
    _dbg("pick_folder_dialog chosen: %s is_file=%s is_dir=%s", p, p.is_file(), p.is_dir())
    # If dialog returned a file (image picked), open just that file
    # (replace: explicit pick, not an additive drop).
    if p.is_file():
        owner.open_paths([p], replace=True)
    elif p.is_dir():
        owner.open_folder(p)
    else:
        # Fallback: try as folder
        if Path(chosen).exists():
            if Path(chosen).is_file():
                owner.open_paths([Path(chosen)], replace=True)
            else:
                owner.open_folder(Path(chosen))
