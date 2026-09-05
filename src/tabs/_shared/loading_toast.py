"""Shared loading-toast lifecycle for IC and MC.

Single source for toast progress checkpoints and for the
``_loading_toasts: dict[int, int]`` state that both tabs previously
duplicated (B2). State-owning collaborator per CODE_PATTERNS.md
"who owns the state" — owns its own ``dict[int, int]`` plus the
toast-manager / translate callables.

Constants mirror the original per-tab values so progress math stays
identical; only the home moves.

Usage::

    coordinator = LoadingToastCoordinator(
        get_toast_manager=lambda: ...,
        translate=lambda key, default=None: ...,
    )
    coordinator.show(slot_id)
    coordinator.mark_full_res_ready(slot_id)
    coordinator.bump_pyramid_started(slot_id)
    coordinator.finish(slot_id)

Both tabs keep thin delegators that forward to their coordinator
instance; ``use_cases/loading_toast.py`` wrappers delegate as well so
existing fake-controller tests without a coordinator still work.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger("ImproveImgSLI")


def toast_debug_enabled() -> bool:
    """Env-gated toast/pyramid diagnostic stream (LOGGING.md convention)."""
    import os

    return os.environ.get("IMGSLI_TOAST_DEBUG", "").strip().lower() not in (
        "",
        "0",
        "false",
        "no",
        "off",
    )


def toast_debug(message: str, *args) -> None:
    """Temporary [toast-debug] diagnostic: warning level (no --debug needed),
    gated on IMGSLI_TOAST_DEBUG. Remove together with all call sites."""
    if toast_debug_enabled():
        logger.warning("[toast-debug] " + message, *args)

# Progress checkpoints for "loading full version of image" toast:
# 0 at quick preview, DECODE_DONE_PROGRESS once full-res decode lands,
# PYRAMID_START_PROGRESS..100 tracking pyramid level build-out.
DECODE_DONE_PROGRESS = 20
PYRAMID_START_PROGRESS = 40


class LoadingToastCoordinator:
    """Owns per-slot loading toasts (B2 dedup).

    Args:
        get_toast_manager: zero-arg callable returning a toast manager
            with ``show_toast``/``update_toast``/``close_toast`` or None.
        translate: ``(key, default=None) -> str``; if None, the key itself
            is used as fallback. IC passes ``tr`` via current language,
            MC passes ``controller.translate``.
    """

    def __init__(
        self,
        get_toast_manager: Callable[[], Any | None],
        translate: Callable[..., str] | None = None,
    ) -> None:
        self._get_toast_manager = get_toast_manager
        self._translate = translate
        # slot_id / image_number -> toast_id
        self._loading_toasts: dict[int, int] = {}

    # --- translation helper ---

    def _tr(self, key: str, default: str | None = None) -> str:
        if self._translate is None:
            return default if default is not None else key
        try:
            # try MC-style single-arg, then IC-style with default
            try:
                # many MC translates accept (key, default) either
                return self._translate(key, default if default is not None else key)  # type: ignore[call-arg]
            except TypeError:
                val = self._translate(key)  # type: ignore[call-arg]
                return str(val) if val is not None else (default or key)
        except Exception:
            return default if default is not None else key

    # --- public API ---

    @property
    def loading_toasts(self) -> dict[int, int]:
        """Direct dict view (also exposed as ``_loading_toasts`` for compat)."""
        return self._loading_toasts

    def show(self, slot_id: int) -> None:
        if slot_id in self._loading_toasts:
            toast_debug("show: slot=%s already tracked, skip", slot_id)
            return
        toast_manager = self._get_toast_manager()
        if toast_manager is None:
            toast_debug("show: slot=%s NO manager, toast never created", slot_id)
            return
        message = self._tr("msg.loading_full_image_in_progress", "Loading full image…")
        try:
            toast_id = toast_manager.show_toast(message, duration=0, progress=0)
            self._loading_toasts[slot_id] = toast_id
            toast_debug("show: slot=%s toast_id=%s created", slot_id, toast_id)
            logger.debug(
                "[FullImageLoad] toast shown (slot=%s toast_id=%s)",
                slot_id,
                toast_id,
            )
        except Exception:
            logger.exception("Failed to show full-image loading toast")

    # Alias for IC call sites that use image_number naming
    def show_loading_toast(self, slot_id: int) -> None:
        self.show(slot_id)

    def set_progress(self, slot_id: int, percent: int) -> None:
        toast_manager = self._get_toast_manager()
        toast_id = self._loading_toasts.get(slot_id)
        if toast_manager is None or toast_id is None:
            toast_debug(
                "progress: slot=%s has_manager=%s toast_id=%s percent=%d SKIPPED",
                slot_id,
                toast_manager is not None,
                toast_id,
                percent,
            )
            logger.debug(
                "[FullImageLoad] skip toast update (slot=%s has_manager=%s toast_id=%s percent=%d)",
                slot_id,
                toast_manager is not None,
                toast_id,
                percent,
            )
            return
        try:
            toast_manager.update_toast(
                toast_id,
                self._tr("msg.loading_full_image_in_progress", "Loading full image…"),
                success=False,
                duration=0,
                progress=max(0, min(99, percent)),
            )
        except Exception:
            logger.exception("Failed to update full-image loading toast")

    def set_loading_toast_progress(self, slot_id: int, percent: int) -> None:
        self.set_progress(slot_id, percent)

    def mark_full_res_ready(self, slot_id: int) -> None:
        self.set_progress(slot_id, DECODE_DONE_PROGRESS)

    def bump_pyramid_started(self, slot_id: int) -> None:
        self.set_progress(slot_id, PYRAMID_START_PROGRESS)

    def finish(self, slot_id: int) -> None:
        toast_manager = self._get_toast_manager()
        toast_id = self._loading_toasts.pop(slot_id, None)
        if toast_manager is None or toast_id is None:
            toast_debug(
                "finish: slot=%s has_manager=%s toast_id=%s SKIPPED",
                slot_id,
                toast_manager is not None,
                toast_id,
            )
            return
        try:
            toast_manager.update_toast(
                toast_id,
                self._tr("msg.loading_full_image_done", "Full image loaded"),
                success=True,
                duration=2000,
                progress=100,
            )
            toast_debug("finish: slot=%s toast_id=%s DONE", slot_id, toast_id)
            logger.debug("[FullImageLoad] toast done (slot=%s toast_id=%s)", slot_id, toast_id)
        except Exception:
            logger.exception("Failed to complete full-image loading toast")

    def finish_loading_toast(self, slot_id: int) -> None:
        self.finish(slot_id)

    def dismiss(self, slot_id: int) -> None:
        """Close without success banner (MC failure / slot vanished)."""
        toast_manager = self._get_toast_manager()
        toast_id = self._loading_toasts.pop(slot_id, None)
        if toast_manager is None or toast_id is None:
            return
        try:
            # prefer close_toast; some managers expose only update_toast
            closer = getattr(toast_manager, "close_toast", None)
            if callable(closer):
                closer(toast_id)
            else:
                toast_manager.update_toast(toast_id, "", success=False, duration=0, progress=0)
        except Exception:
            logger.exception("Failed to dismiss full-image loading toast")

    def dismiss_loading_toast(self, slot_id: int) -> None:
        self.dismiss(slot_id)

    # Back-compat alias used by wrappers
    def get_toast_manager(self):
        return self._get_toast_manager()
