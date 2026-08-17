"""Tab-agnostic save-flow toast plumbing shared by both canvas tabs.

Image Compare's ``ExportSaveFlowCoordinator`` and Multi Compare's
``MultiCompareSaveFlowCoordinator`` used to carry byte-identical copies of
toast-update helpers. This mixin is the single shared implementation; both
coordinators inherit it and keep only their tab-specific worker wiring.

Methods here are deliberately generic: they only touch ``self.main_window_app``
(toast manager lookup), ``self.tr`` (translation of caller-provided keys) and
the ``os`` path helpers, so no tab-specific import direction is created.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("ImproveImgSLI")


class SaveToastMixin:
    """Shared toast/path helpers for save-flow coordinators."""

    def _get_toast_manager(self):
        return getattr(self.main_window_app, "toast_manager", None)

    def _update_toast_safe(
        self,
        save_task_id: int | None,
        message: str,
        *,
        success: bool,
        duration: int = 0,
        progress: int | None = None,
        actions=None,
    ) -> None:
        toast_manager = self._get_toast_manager()
        if toast_manager is None or save_task_id is None:
            return
        try:
            kwargs = {
                "success": success,
                "duration": duration,
                "progress": progress,
            }
            if actions is not None:
                kwargs["actions"] = actions
            toast_manager.update_toast(
                save_task_id,
                message,
                **kwargs,
            )
        except Exception as exc:
            logger.error("Toast update failed for %s: %s", save_task_id, exc)

    def _build_toast_path_line(self, final_path_for_display: str) -> str:
        directory, file_name = os.path.split(final_path_for_display)
        if not directory:
            return file_name
        normalized_dir = os.path.normpath(directory)
        dir_parts = [part for part in normalized_dir.split(os.sep) if part]
        if len(dir_parts) <= 2:
            compact_dir = normalized_dir
        else:
            compact_dir = os.path.join("...", dir_parts[-2], dir_parts[-1])
        return os.path.join(compact_dir, file_name)
