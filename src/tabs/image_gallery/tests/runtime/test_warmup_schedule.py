"""The local-backend warm-up starts at tab activation: once, off the UI path."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.services import warmup


@pytest.fixture(autouse=True)
def _reset():
    warmup.reset_for_tests()
    os.environ.pop("IMGSLI_GALLERY_NO_WARMUP", None)
    yield
    warmup.reset_for_tests()
    os.environ.pop("IMGSLI_GALLERY_NO_WARMUP", None)


def test_the_warmup_thread_starts_once(monkeypatch) -> None:
    started: list = []

    class _Thread:
        def __init__(self, *, target, name, daemon):
            started.append((target, name, daemon))

        def start(self):
            return None

    monkeypatch.setattr(warmup.threading, "Thread", _Thread)
    assert warmup.schedule_warmup(reason="t") is True
    assert warmup.schedule_warmup(reason="t") is False, "the warm-up must run once"
    assert len(started) == 1
    target, name, daemon = started[0]
    assert target is warmup.warm_local_backends
    assert name == "gallery-backend-warmup" and daemon is True, (
        "the warm-up must never keep the process alive"
    )


def test_the_kill_switch_disables_the_warmup(monkeypatch) -> None:
    monkeypatch.setenv("IMGSLI_GALLERY_NO_WARMUP", "1")
    assert warmup.schedule_warmup() is False
    assert warmup.schedule_warmup() is False


def test_the_report_names_the_learned_status_and_the_cost(monkeypatch) -> None:
    from tabs.image_gallery.services import quality_models

    monkeypatch.setattr(quality_models, "backend_status", lambda: "ready")
    report = warmup.warm_local_backends()
    assert report["learned"] == "ready"
    assert report["decode"] is True
    assert report["ms"] >= 0
