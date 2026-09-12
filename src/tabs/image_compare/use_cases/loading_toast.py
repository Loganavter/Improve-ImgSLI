"""Loading-toast lifecycle: show, update, finish.

The toast is a thin progress notification that tracks the full-res decode
and pyramid build for each image slot.  Pyramid code calls into these
functions via the controller's bound methods (``controller._finish_loading_toast``,
etc.) — the dependency is one-directional: **pyramid --> toast**.
"""

from __future__ import annotations

import logging

from sli_ui_toolkit.i18n import get_current_language, tr

logger = logging.getLogger("ImproveImgSLI")

# Single source for checkpoints now lives in tabs._shared.loading_toast
# (B2 dedup); re-exported here for backward compat of direct importers.
from tabs._shared.loading_toast import (  # noqa: F401
    DECODE_DONE_PROGRESS,
    PYRAMID_START_PROGRESS,
)


def get_toast_manager(controller):
    # controller.presenter is a MainWindowPresenter, not the window shell
    # itself -- it owns main_window_app, which is where toast_manager
    # actually lives (see ExportSaveFlowCoordinator._get_toast_manager,
    # the same lookup used by the save-image toast).
    toast_manager = getattr(
        getattr(controller.presenter, "main_window_app", None), "toast_manager", None
    )
    if toast_manager is None:
        logger.debug(
            "[FullImageLoad] no toast_manager available (presenter=%r)",
            controller.presenter,
        )
    return toast_manager


def show_loading_toast(controller, image_number: int) -> None:
    coord = getattr(controller, "_loading_toast_coordinator", None)
    if coord is not None:
        coord.show(image_number)
        return


def set_loading_toast_progress(controller, image_number: int, percent: int) -> None:
    coord = getattr(controller, "_loading_toast_coordinator", None)
    if coord is not None:
        coord.set_progress(image_number, percent)
        return


def mark_full_res_ready(controller, image_number: int) -> None:
    coord = getattr(controller, "_loading_toast_coordinator", None)
    if coord is not None:
        coord.mark_full_res_ready(image_number)
        return


def bump_loading_toast_pyramid_started(controller, image_number: int) -> None:
    coord = getattr(controller, "_loading_toast_coordinator", None)
    if coord is not None:
        coord.bump_pyramid_started(image_number)
        return


def finish_loading_toast(controller, image_number: int) -> None:
    coord = getattr(controller, "_loading_toast_coordinator", None)
    if coord is not None:
        coord.finish(image_number)
        return


def finish_toast_for_unpaired_slot(controller, document, image_number: int) -> None:
    """Unify -- and the pyramid build that normally closes the loading
    toast -- only ever runs once both slots hold an image. When the other
    slot has no image at all, unify will never fire, so the toast for this
    slot would otherwise hang forever. Close it here once this slot's own
    full-res decode has actually landed.
    """
    # PipelineCache is single source — check via store peek
    store = getattr(controller, "store", None)
    own = None
    if store is not None:
        path = document.image1_path if image_number == 1 else document.image2_path
        if path:
            # try viewport
            try:
                vp = store.viewport.session_data.image_state
                cand = vp.image1 if image_number == 1 else vp.image2
                if cand is not None and getattr(cand, "is_open", True):
                    try:
                        if hasattr(cand, "isNull") and cand.isNull():
                            cand = None
                    except Exception:
                        pass
                    own = cand
            except Exception:
                pass
            if own is None:
                pl = getattr(controller, "pipeline", None)
                if pl is not None:
                    try:
                        own = pl.peek(path) or pl.peek_preview(path)
                    except Exception:
                        pass
                else:
                    try:
                        ps = store.get_session_state_slot("pipeline")
                        if ps is not None:
                            import os

                            from tabs.image_compare.pipeline.cache import _pixel_key

                            k = _pixel_key(path, None, None)
                            v = ps.pixel.get(k)  # type: ignore[attr-defined]
                            if v is not None and getattr(v, "is_open", True):
                                own = v
                    except Exception:
                        pass
    other_number = 2 if image_number == 1 else 1
    other_path = getattr(document, f"image{other_number}_path", None)
    if own is not None and not other_path:
        controller._finish_loading_toast(image_number)
