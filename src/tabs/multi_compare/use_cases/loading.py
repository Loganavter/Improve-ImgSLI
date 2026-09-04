"""Image loading, pyramid build, and "loading full version of image" toast
for the Multi Compare tab -- split out of ``MultiCompareController`` to keep
that class down to wiring/composition, mirroring image_compare's own
``use_cases/loading.py`` split. Every function here takes the controller as
its first argument and reads/writes its instance state
(``_loading_toasts``, ``_pyramid_builds``, ``_pyramid_toast_slot``) directly,
same calling convention as image_compare's use_cases modules.
Audit-Meta: pattern=thin-owner reason="Controller delegate fan-out: toast/pyramid/full-res stages share one module; batch planning stays beside the primitives it stages"
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from core.events import CoreErrorOccurredEvent

logger = logging.getLogger("ImproveImgSLI")


def _same_fs_path(a: Path | str, b: Path | str) -> bool:
    """Normalized path equality for slot-ownership guards.

    ``slot.path`` strict ``==`` false-positives on textual variants of the
    same file (``/x/./f.png`` vs ``/x/f.png``, ``str`` vs ``Path``,
    trailing separators): the guard then dismisses a good preview and the
    slot stays imageless forever with no error surfaced. ``normpath``
    over ``os.fspath`` keeps identical paths equal and heals those
    variants; it never equates distinct files.
    """
    try:
        return os.path.normpath(os.fspath(a)) == os.path.normpath(os.fspath(b))
    except Exception:
        return a == b


def _format_worker_error(err) -> str:
    if isinstance(err, tuple) and len(err) >= 2:
        return str(err[1])
    return str(err)


def _emit_mc_load_error(controller, path: Path | str, err) -> None:
    """Surface a failed MC load via the shared EventBus/toast plumbing (IC parity).

    Mirrors ``image_compare._session_controller._load_image_async`` /
    ``_on_full_resolution_error`` — a dropped corrupt file must not silently
    vanish; it emits ``CoreErrorOccurredEvent`` so MainController shows a toast.
    """
    try:
        event_bus = getattr(controller.context, "event_bus", None) if getattr(controller, "context", None) else None
        # controller.translate is TabContext.tr wrapper (already language-aware)
        try:
            prefix = controller.translate("msg.failed_to_load_image", "Failed to load image")
        except Exception:
            prefix = "Failed to load image"
        message = f"{prefix}:\n{path}\n\n{_format_worker_error(err)}"
        if event_bus is not None:
            event_bus.emit(CoreErrorOccurredEvent(message))
        else:
            # Fallback: try main_window's presenter error pathway (kept for tests without TabContext)
            main_window = getattr(controller.context, "main_window", None) if getattr(controller, "context", None) else None
            presenter = getattr(main_window, "presenter", None) if main_window else None
            fallback_bus = getattr(presenter, "event_bus", None) if presenter else None
            if fallback_bus is not None:
                fallback_bus.emit(CoreErrorOccurredEvent(message))
    except Exception:
        logger.exception("Failed to emit MC load error event for %s", path)

# Single source now in tabs._shared.loading_toast (B2 dedup).
from tabs._shared.loading_toast import DECODE_DONE_PROGRESS, PYRAMID_START_PROGRESS  # noqa: F401


def get_toast_manager(controller):
    main_window = getattr(controller.context, "main_window", None) if controller.context else None
    toast_manager = getattr(main_window, "toast_manager", None)
    if toast_manager is None:
        logger.debug(
            "[FullImageLoad] no toast_manager available (context=%r)", controller.context
        )
    return toast_manager


def show_loading_toast(controller, slot_id: int) -> None:
    coord = getattr(controller, "_loading_toast_coordinator", None)
    if coord is not None:
        coord.show(slot_id)
        return
    if slot_id in controller._loading_toasts:
        return
    toast_manager = get_toast_manager(controller)
    if toast_manager is None:
        return
    message = controller.translate("msg.loading_full_image_in_progress")
    try:
        controller._loading_toasts[slot_id] = toast_manager.show_toast(
            message, duration=0, progress=0
        )
    except Exception:
        logger.exception("Failed to show full-image loading toast")


def set_loading_toast_progress(controller, slot_id: int, percent: int) -> None:
    coord = getattr(controller, "_loading_toast_coordinator", None)
    if coord is not None:
        coord.set_progress(slot_id, percent)
        return
    toast_manager = get_toast_manager(controller)
    toast_id = controller._loading_toasts.get(slot_id)
    if toast_manager is None or toast_id is None:
        return
    try:
        toast_manager.update_toast(
            toast_id,
            controller.translate("msg.loading_full_image_in_progress"),
            success=False,
            duration=0,
            progress=max(0, min(99, percent)),
        )
    except Exception:
        logger.exception("Failed to update full-image loading toast")


def mark_full_res_ready(controller, slot_id: int) -> None:
    coord = getattr(controller, "_loading_toast_coordinator", None)
    if coord is not None:
        coord.mark_full_res_ready(slot_id)
        return
    set_loading_toast_progress(controller, slot_id, DECODE_DONE_PROGRESS)


def bump_loading_toast_pyramid_started(controller, slot_id: int) -> None:
    coord = getattr(controller, "_loading_toast_coordinator", None)
    if coord is not None:
        coord.bump_pyramid_started(slot_id)
        return
    set_loading_toast_progress(controller, slot_id, PYRAMID_START_PROGRESS)


def finish_loading_toast(controller, slot_id: int) -> None:
    coord = getattr(controller, "_loading_toast_coordinator", None)
    if coord is not None:
        coord.finish(slot_id)
        return
    toast_manager = get_toast_manager(controller)
    toast_id = controller._loading_toasts.pop(slot_id, None)
    if toast_manager is None or toast_id is None:
        return
    try:
        toast_manager.update_toast(
            toast_id,
            controller.translate("msg.loading_full_image_done"),
            success=True,
            duration=2000,
            progress=100,
        )
    except Exception:
        logger.exception("Failed to complete full-image loading toast")


def dismiss_loading_toast(controller, slot_id: int) -> None:
    """Closes a slot's loading toast without the "done" success banner --
    used when the load fails or the slot vanished mid-load, as opposed to
    ``finish_loading_toast``'s success path."""
    coord = getattr(controller, "_loading_toast_coordinator", None)
    if coord is not None:
        coord.dismiss(slot_id)
        return
    toast_manager = get_toast_manager(controller)
    toast_id = controller._loading_toasts.pop(slot_id, None)
    if toast_manager is None or toast_id is None:
        return
    try:
        toast_manager.close_toast(toast_id)
    except Exception:
        logger.exception("Failed to dismiss full-image loading toast")


def _get_crop_service(controller):
    """DI helper — mirror SessionController._get_crop_service."""
    try:
        getter = getattr(controller, "_get_crop_service", None)
        if callable(getter):
            return getter()
    except Exception:
        pass
    try:
        svc = getattr(controller, "_crop_service", None)
        if svc is not None:
            # check setting manually if controller has no getter
            store = getattr(controller, "store", None)
            if store is not None:
                should = getattr(getattr(store, "settings", None), "auto_crop_black_borders", True)
                if not should:
                    return None
            return svc
    except Exception:
        pass
    return None


def read_image(controller, path: Path, *, slot_id: int | None = None, start_pyramid: bool = True):
    try:
        from shared.image_processing.pixel_cache_loader import load_pixel_store

        crop_service = _get_crop_service(controller)
        _emb_mc = None
        try:
            _emb_mc = getattr(getattr(controller, "store", None), "get_session_state_slot", lambda *_: None)("pipeline")
            # pipeline state vs cache instance fallback
            from shared.image_processing import embedded_pixel_cache as _emb_mod

            _emb_mc = _emb_mod  # host-owned injection from tab context
        except Exception:
            _emb_mc = None
        store = load_pixel_store(path, crop_service=crop_service, embedded_cache=_emb_mc)
        if start_pyramid:
            start_pyramid_build(controller, store, slot_id=slot_id)
        return store
    except Exception as e:
        logger.error("Failed to load %s: %s", path, e, exc_info=True)
        if slot_id is not None:
            try:
                dismiss_loading_toast(controller, slot_id)
            except Exception:
                pass
        _emit_mc_load_error(controller, path, e)
        return None


def start_pyramid_build(controller, store, *, slot_id: int | None = None) -> None:
    """Kicks off background mipmap-pyramid construction for a slot's
    full-res store, mirroring image_compare's
    ``_session_controller._start_pyramid_builds``. Without this, a slot
    displayed below native resolution samples the unmipmapped native
    texture directly, which aliases; the pyramid lets the per-frame LOD
    selector in ``BaseImagesPass`` pick a downsampled level instead
    (see ``docs/dev/rendering/...`` LOD selection, ``shared/rendering/lod.py``).

    ``slot_id``, when given, drives the "loading full version of image"
    toast (docs/dev/KNOWN_BUGS.md same-slot-swap SSIM follow-up) through
    its pyramid-build stage -- every early return below that skips the
    actual build (nothing to build, no thread pool, already in flight
    with no new work) also finishes that slot's toast instead of leaving
    it stuck at "pyramid started" forever.
    """
    coord = getattr(controller, "_pyramid_coordinator", None)
    if coord is not None:
        # Use coordinator's worker lifecycle + toast routing (B3).
        # MC abort predicate: pyramid.valid
        from shared.image_processing.pyramid_registry import ensure_pyramid as _ensure

        _pyr = _ensure(store)

        def _should_abort(_p=_pyr):
            return not getattr(_p, "valid", True) if _p is not None else False

        coord.start_build(store, slot_id=slot_id, should_abort=_should_abort)
        return
    from shared.image_processing.pyramid_registry import ensure_pyramid
    from shared.image_processing.tiled_pixel_store import TiledPixelStore
    from shared.rendering.image_identity import image_uid

    if not isinstance(store, TiledPixelStore) or not store.is_open:
        if slot_id is not None:
            finish_loading_toast(controller, slot_id)
        return
    pyramid = ensure_pyramid(store)
    if pyramid is None or pyramid.is_complete():
        if slot_id is not None:
            finish_loading_toast(controller, slot_id)
        return
    uid = image_uid(store)
    if uid in controller._pyramid_builds:
        return
    thread_pool = getattr(controller.context, "thread_pool", None) if controller.context else None
    if thread_pool is None:
        if slot_id is not None:
            finish_loading_toast(controller, slot_id)
        return

    from shared.image_processing.pyramid_pixel_store import estimate_total_levels
    from sli_ui_toolkit.workers import GenericWorker

    controller._pyramid_builds.add(uid)
    if slot_id is not None:
        controller._pyramid_toast_slot[uid] = slot_id
        bump_loading_toast_pyramid_started(controller, slot_id)
    total_levels = estimate_total_levels(store.width, store.height)

    def should_abort() -> bool:
        return not pyramid.valid

    def build_task(progress_callback=None):
        while pyramid.build_next_level(should_abort=should_abort):
            complete = pyramid.is_complete()
            if progress_callback is not None:
                progress_callback((uid, pyramid.level_count, total_levels, complete))
        return None

    worker = GenericWorker(build_task)
    worker.kwargs["progress_callback"] = worker.signals.partial_result.emit
    worker.signals.partial_result.connect(controller._on_pyramid_level_ready)
    worker.signals.finished.connect(
        lambda uid=uid: controller._pyramid_builds.discard(uid)
    )
    thread_pool.start(worker)


def on_pyramid_level_ready(controller, payload=None) -> None:
    coord = getattr(controller, "_pyramid_coordinator", None)
    if coord is not None:
        # coordinator handles canvas refresh via injected callback, but MC's
        # canvas is on widget; ensure refresh if coordinator didn't inject.
        coord.on_level_ready(payload)
        # keep legacy canvas refresh for fakes without injected callback
        try:
            canvas = getattr(controller.widget, "canvas", None)
            if canvas is not None:
                canvas.request_view_update()
        except Exception:
            pass
        return
    canvas = getattr(controller.widget, "canvas", None)
    if canvas is not None:
        canvas.request_view_update()
    if not isinstance(payload, tuple) or len(payload) != 4:
        return
    uid, level_count, total_levels, complete = payload
    slot_id = controller._pyramid_toast_slot.get(uid)
    if slot_id is None:
        return
    if complete:
        controller._pyramid_toast_slot.pop(uid, None)
        finish_loading_toast(controller, slot_id)
    else:
        fraction = level_count / max(total_levels, 1)
        percent = PYRAMID_START_PROGRESS + int(
            fraction * (100 - PYRAMID_START_PROGRESS)
        )
        set_loading_toast_progress(controller, slot_id, percent)


def load_full_resolution_async(controller, path: Path, slot_id: int) -> None:
    """Full-res second stage (A2): per-slot workers via ``preview_decode``'s bounded FIFO."""
    thread_pool = getattr(controller.context, "thread_pool", None) if controller.context else None
    if thread_pool is None:
        store = read_image(controller, path, start_pyramid=False)
        apply_full_resolution(controller, slot_id, path, store)
        return

    from tabs.multi_compare.use_cases import preview_decode as _preview

    _preview.queue_full_resolution(controller, path, slot_id)


def on_full_resolution_error(controller, path: Path, slot_id: int, err) -> None:
    """Full-res worker failed: orphan/recycled stays silent, live slot reports via bus."""
    try:
        slots = list(controller.widget.state.slots)
    except Exception:
        slots = None
    if slots is not None:
        slot = next((s for s in slots if s.id == slot_id), None)
        if slot is None:
            # Orphan (slot removed mid-load, e.g. user-cancelled): silent
            # dismiss, no error-toast — the load was abandoned on purpose.
            dismiss_loading_toast(controller, slot_id)
            return
        try:
            same = _same_fs_path(slot.path, path)
        except Exception:
            same = False
        if not same:
            # Id recycled by a newer slot: its toast is live, don't touch it.
            return
    logger.error("Failed to load full resolution for %s: %s", path, err, exc_info=True)
    if slot.image is None:
        # Imageless (preview-miss path): sync-UX parity — drop the
        # pre-created slot instead of leaving an imageless leaf (blank
        # hole). A slot holding its preview tier keeps it; only its toast
        # is dismissed.
        from tabs.multi_compare.scene import actions as mc_actions

        try:
            controller.widget.store.dispatch(mc_actions.remove_slot(slot_id))
        except Exception:
            logger.exception("Failed to remove failed-load slot %s", slot_id)
    dismiss_loading_toast(controller, slot_id)
    _emit_mc_load_error(controller, path, err)


def apply_full_resolution(controller, slot_id: int, path: Path, store) -> None:
    if store is None:
        dismiss_loading_toast(controller, slot_id)
        return
    slot = next((s for s in controller.widget.state.slots if s.id == slot_id), None)
    if slot is None:
        # Slot was removed while the full-res decode was in flight — the
        # store would just leak. Dismiss (never finish: an orphan must not
        # show toast-done).
        from shared.image_processing.tiled_pixel_store import close_pixel_store

        close_pixel_store(store)
        dismiss_loading_toast(controller, slot_id)
        return
    if not _same_fs_path(slot.path, path):
        # Id recycled (``max+1``): the newer generation owns id+toast —
        # touch neither. Close this ownerless store (memmap leak guard).
        # Normalized compare (P8): str-vs-Path/"./" variants must not read
        # as stale and orphan a good decode.
        from shared.image_processing.tiled_pixel_store import close_pixel_store

        close_pixel_store(store)
        return
    mark_full_res_ready(controller, slot_id)
    from tabs.multi_compare.scene import actions as mc_actions

    controller.widget.store.dispatch(mc_actions.replace_slot_image(slot_id, store))
    start_pyramid_build(controller, store, slot_id=slot_id)


def load_external_paths(controller, paths) -> int:
    """Chrome/carry/paste drops without a canvas position (P3A).

    Direct-load like IC (``image_compare.use_cases.drag_drop.handle_drop``):
    auto-place each file through the P2 async path — imageless slot +
    loading toast synchronously, bounded preview in a ``GenericWorker``
    (``load_preview_async``), full-res second stage. No
    ``begin_pending_paste`` arming: nothing waits for a canvas click, so
    there is no armed highlight and ``Esc`` has nothing to cancel for this
    path. The ``(None, False)`` target falls back to auto placement inside
    ``add_image_at`` (empty canvas → root, otherwise largest-leaf split),
    so window-chrome ``slot`` hints and carry drops with no position both
    map to append-like placement. Internal-drag Move stays in
    ``ui/drag_drop`` and is untouched by this path.

    Returns the number of slots created synchronously.
    """
    from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS as _EXTENSIONS

    valid: list[Path] = []
    for raw in paths or []:
        path = raw if isinstance(raw, Path) else Path(raw)
        if path.suffix.lower() not in _EXTENSIONS:
            continue
        if not path.is_file():
            logger.debug("load_external_paths: skipped missing file %s", path)
            continue
        valid.append(path)
    if not valid:
        return 0
    before = len(controller.widget.state.slots)
    on_images_dropped(controller, valid, (None, False), None)
    return len(controller.widget.state.slots) - before


def resolve_auto_triple(widget, scratch):
    """Auto-placement triple ``(target_path, side, target_root)`` without dispatch.

    Read-only replica of ``placement.add_image_auto`` target resolution
    (``placement.py`` itself is untouched — A1 owns it): empty tree →
    root, otherwise the widget's auto target. A canvas that cannot answer
    (headless fakes) falls back to the deterministic ``((), "right")``
    A1 will converge on, instead of raising mid-drop.
    """
    if scratch.root is None:
        return None, None, True
    try:
        target_path, side = widget._pick_auto_target()
        return target_path, side, False
    except Exception:
        return (), "right", False


def on_images_dropped(controller, paths: list, target, side) -> None:
    """target: tuple (target_path_or_None, target_root_bool); side: 'left'/'right'/...

    P2: only placement + imageless slot creation run on the GUI thread —
    no decode here (a preview-miss used to be a full synchronous
    ``read_image`` stall, measured 381ms drop→finish). Each slot's
    preview decodes in a ``GenericWorker`` (``load_preview_async``) and
    fills the slot on result, with full-res as the second stage.
    Internal-drag Move semantics live in ``ui/drag_drop`` and are
    untouched by this path.

    A3: the N per-file ``add_image_at/auto`` dispatches are planned first
    against a scratch state through the pure ``scene.store.reduce`` (same
    chain rule — file 0 at the drop target, later files beside the
    previously added slot, auto fallback when its path is gone, capacity
    guard per file) and committed with one ``store.transact`` → 1
    dispatch / 1 emit. Toast + preview workers stay per-slot (not store
    dispatches) and run after the single commit.
    """
    from tabs.multi_compare.models import find_path
    from tabs.multi_compare.scene import actions as mc_actions
    from tabs.multi_compare.scene.store import reduce as mc_reduce
    from tabs.multi_compare.use_cases import preview_decode as _preview

    target_path, target_root = (
        target if isinstance(target, tuple) else (None, False)
    )

    widget = controller.widget
    scratch = widget.state
    built: list = []
    planned: list[tuple[int, Path]] = []
    last_added: int | None = None
    for i, raw_path in enumerate(paths):
        path = Path(raw_path) if not isinstance(raw_path, Path) else raw_path
        if len(scratch.slots) >= scratch.max_slots:
            continue
        if i == 0:
            eff_path, eff_side, eff_root = target_path, side, target_root
            if (
                not eff_root
                and (eff_path is None or eff_side is None)
                and scratch.root is not None
            ):
                eff_path, eff_side, eff_root = resolve_auto_triple(widget, scratch)
            else:
                eff_root = bool(eff_root or scratch.root is None)
            action = mc_actions.add_slot(
                path=path,
                image=None,
                label=path.stem,
                target_path=eff_path,
                side=eff_side,
                target_root=eff_root,
            )
        else:
            next_side = "right" if side in ("left", "right") else "bottom"
            next_path: tuple[int, ...] | None = None
            if last_added is not None:
                found = find_path(scratch.root, last_added)
                next_path = tuple(found) if found is not None else None
            if next_path is None:
                auto_path, auto_side, auto_root = resolve_auto_triple(widget, scratch)
                action = mc_actions.add_slot(
                    path=path,
                    image=None,
                    label=path.stem,
                    target_path=auto_path,
                    side=auto_side,
                    target_root=auto_root,
                )
            else:
                action = mc_actions.add_slot(
                    path=path,
                    image=None,
                    label=path.stem,
                    target_path=next_path,
                    side=next_side,
                    target_root=False,
                )
        before = len(scratch.slots)
        scratch = mc_reduce(scratch, action)
        if len(scratch.slots) <= before:
            continue
        built.append(action)
        last_added = scratch.slots[-1].id
        planned.append((last_added, path))
    if not built:
        return
    store = widget.store
    transact = getattr(store, "transact", None)
    if callable(transact):
        store.transact(built)
    else:  # headless fakes pre-dating the batch API: same end state, N dispatches
        for sub in built:
            store.dispatch(sub)
    live_ids = {s.id for s in widget.state.slots}
    for sid, path in planned:
        if sid not in live_ids:
            continue
        show_loading_toast(controller, sid)
        _preview.load_preview_async(controller, path, sid)