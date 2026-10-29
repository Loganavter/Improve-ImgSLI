"""The one-shot GPU warm-up must cover every offscreen service the exporter owns.

The video exporter runs two offscreen QRhiWidgets — one for preview/export, one
for the 160x90 filmstrip tiles — and keeps them separate on purpose (sharing one
forces resize thrash: paint_gl_ms 50 -> 1100 ms). Only the first one used to be
warmed, so the thumbnail widget paid its cold shader/pipeline compile inside the
first filmstrip render: ~1.5 s for the first tile after opening the video editor
(measured 2026-10-29 21:24), with every later tile still slower than it should
be. These tests pin that the single warm-up call reaches both services, that a
partly-cold exporter keeps the caller's retry alive, and that an absent service
is not invented.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

_APP = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


class _SpyService:
    """Stand-in for ``GpuExportService``; counts warm-up calls, reports ready."""

    def __init__(self, ready=True, error=None):
        self.calls = 0
        self.ready = ready
        self.error = error

    def warm_up(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.ready


def _exporter(gpu_export_service=None):
    _app()
    from tabs.image_compare.plugins.video_editor.services.video_export.service import (
        VideoExporterService,
    )

    store = SimpleNamespace(settings=SimpleNamespace(export_default_dir="/tmp"))
    return VideoExporterService(
        recorder=SimpleNamespace(snapshots=[]),
        store=store,
        main_controller=None,
        gpu_export_service=gpu_export_service,
    )


def _exporter_with(main, thumbnail):
    exporter = _exporter(gpu_export_service=main)
    # ``__init__`` pairs the two services; the second widget is swapped for a
    # spy so both call sites are observable without creating a real canvas.
    exporter._thumbnail_gpu_export_service = thumbnail
    return exporter


def test_warm_up_reaches_both_offscreen_services():
    main, thumb = _SpyService(), _SpyService()
    exporter = _exporter_with(main, thumb)

    assert exporter.warm_up_gpu_widgets() is True
    assert main.calls == 1
    assert thumb.calls == 1, (
        "the thumbnail offscreen service was left cold: its first filmstrip "
        "tile then pays the ~4 s shader/pipeline compile on a worker thread"
    )


def test_warm_up_fails_when_the_thumbnail_service_is_not_ready():
    main, thumb = _SpyService(ready=True), _SpyService(ready=False)
    exporter = _exporter_with(main, thumb)

    assert exporter.warm_up_gpu_widgets() is False, (
        "a cold thumbnail widget must keep the caller's one-shot retry alive"
    )
    assert main.calls == 1 and thumb.calls == 1


def test_warm_up_fails_when_the_main_service_is_not_ready():
    main, thumb = _SpyService(ready=False), _SpyService(ready=True)
    exporter = _exporter_with(main, thumb)

    assert exporter.warm_up_gpu_widgets() is False
    assert thumb.calls == 1, "an unready main service must not block the thumbnail"


def test_warm_up_survives_one_service_raising():
    main = _SpyService(error=RuntimeError("no canvas provider"))
    thumb = _SpyService()
    exporter = _exporter_with(main, thumb)

    assert exporter.warm_up_gpu_widgets() is False
    assert thumb.calls == 1, "one raising service must not skip the other"


def test_absent_services_are_not_warmed_and_report_failure():
    exporter = _exporter_with(None, None)

    assert exporter.warm_up_gpu_widgets() is False, (
        "with no offscreen service there is nothing ready, so the caller must "
        "not record the warm-up as done"
    )


def test_only_the_existing_service_is_warmed():
    main = _SpyService()
    exporter = _exporter_with(main, None)

    assert exporter.warm_up_gpu_widgets() is True
    assert main.calls == 1


def test_a_service_without_warm_up_is_skipped_not_crashed():
    main = _SpyService()
    exporter = _exporter_with(main, object())

    assert exporter.warm_up_gpu_widgets() is True
    assert main.calls == 1


def test_repeated_calls_ask_each_service_once_per_call():
    main, thumb = _SpyService(), _SpyService()
    exporter = _exporter_with(main, thumb)

    assert exporter.warm_up_gpu_widgets() is True
    assert exporter.warm_up_gpu_widgets() is True
    # Idempotence lives in ``GpuExportService.warm_up`` (its widget is cached),
    # so the exporter must not add a second flag: it asks, the service decides.
    assert (main.calls, thumb.calls) == (2, 2)
