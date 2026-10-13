"""Shared clipboard paste coordinator — single source for image paste.

Tab-owned clipboard services were ~50 LOC each doing the same
collect/split/download dance over ``shared/clipboard_images.py``.
Gallery needs the same. Per ``docs/dev/CODE_PATTERNS.md:114`` a concern
owning its own lifecycle (worker + pending paths) is a small collaborator
object, not a copy-paste function. ``docs/dev/ARCHITECTURE.md:252``
extension points table says reusable paste → ``shared/`` (not ``core/``).

This module owns only the clipboard → local-paths pipeline:

* ``collect_clipboard_image_items()`` → deduped ``list[str]``
* split into ``local_files`` (``os.path.exists``) vs ``http(s)`` URLs
* optional async URL download via ``GenericWorker`` + ``thread_pool``

Placement is tab-specific and injected as a callback:
``on_ready(list[Path])`` — caller decides where paths land.

Two-phase use (direction-dialog caller): the dialog must appear
*before* the download starts, so the tab collects first, shows the
dialog, then calls ``run_with_items`` with the pre-collected items once
the user picks a direction. Single-phase use (direct-placement callers):
just call ``run()``.

Tabs keep a thin ``ClipboardService`` that only wires
``collect`` → ``coordinator`` → ``placement`` (keeps ``create_service``
contract stable).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable

from sli_ui_toolkit.workers import GenericWorker

from shared.clipboard_images import (
    collect_clipboard_image_items,
    download_images_from_urls,
)

logger = logging.getLogger("ImproveImgSLI")


def split_clipboard_items(items: list[str]) -> tuple[list[str], list[str]]:
    """Split ``collect_clipboard_image_items`` output.

    Returns ``(local_files, http_urls)``. ``local_files`` are existing
    filesystem paths, ``http_urls`` are ``http://``/``https://`` strings.
    Everything else (non-existent text) is dropped.
    """
    local_files = [i for i in items if os.path.exists(i)]
    urls = [i for i in items if i.startswith(("http://", "https://"))]
    return local_files, urls


class ClipboardPasteCoordinator:
    """One-shot coordinator: collect → maybe download → call ``on_ready``.

    No singleton, no Qt parent — hold one per paste. Keeps ``_pending_local``
    for URL-combine, matching MC pattern.
    """

    def __init__(
        self,
        *,
        thread_pool=None,
        on_ready: Callable[[list[Path]], None],
        on_empty: Callable[[], None] | None = None,
        on_download_started: Callable[[list[str]], None] | None = None,
    ) -> None:
        self._thread_pool = thread_pool
        self._on_ready = on_ready
        self._on_empty = on_empty
        self._on_download_started = on_download_started
        self._pending_local: list[str] = []

    def run(self) -> bool:
        """Collect from the clipboard, then resolve via ``run_with_items``."""
        try:
            items = collect_clipboard_image_items()
        except Exception as e:
            logger.error("clipboard paste collect failed: %s", e)
            return False

        if not items:
            if self._on_empty:
                self._on_empty()
            return False

        return self.run_with_items(items)

    def run_with_items(self, items: list[str]) -> bool:
        """Resolve pre-collected clipboard items (split → download → ready).

        Split-drops-everything returns ``False`` without firing
        ``on_empty`` (matches the old tab services: only a truly empty
        clipboard counts as "nothing to paste").
        """
        local_files, urls = split_clipboard_items(items)

        if not local_files and not urls:
            return False

        if urls:
            self._pending_local = list(local_files)
            if self._on_download_started:
                try:
                    self._on_download_started(list(urls))
                except Exception as e:
                    logger.error("clipboard paste on_download_started failed: %s", e)
            try:
                worker = GenericWorker(download_images_from_urls, urls, 15)
                worker.signals.result.connect(self._on_urls_downloaded)
                tp = self._thread_pool
                if tp is not None:
                    tp.start(worker)
                else:
                    # Synchronous fallback (tests, no pool)
                    paths = download_images_from_urls(urls, 15)
                    self._on_urls_downloaded(paths)
            except Exception as e:
                logger.error("clipboard paste download worker failed: %s", e)
                # Still deliver locals
                if local_files:
                    self._on_ready([Path(p) for p in local_files])
            return True

        # Local-only fast path
        self._on_ready([Path(p) for p in local_files])
        return True

    def _on_urls_downloaded(self, paths: list[str] | None) -> None:
        pending = list(self._pending_local)
        self._pending_local = []
        downloaded = [Path(p) for p in (paths or []) if os.path.exists(p)]
        combined = [Path(p) for p in pending] + downloaded
        if combined:
            try:
                self._on_ready(combined)
            except Exception as e:
                logger.error("clipboard paste on_ready failed: %s", e)
