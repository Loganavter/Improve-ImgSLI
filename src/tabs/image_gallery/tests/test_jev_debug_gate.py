"""Jev trace gate: silent without ``IMGSLI_AI_DEBUG``, ``[ai]``-tagged with it.

Falsification story: a Jev rank call that stays silent (no ``[ai] jev`` line) in
a normal run, and that emits the ``[ai] jev`` request/decision/cache lines — the
same ``IMGSLI_AI_DEBUG`` key ``ai_client._ai_debug`` already uses — when enabled.
Mirrors ``tests/test_hover_diag_gate.py`` (gate-zone dump recipe, LOGGING.md).

Level (P5, P4 leftover): the channel is opt-in through the env key, so its lines
are INFO, never WARNING — a debug run must not read like a cascade of alarms —
and the level is one named constant (``ai_client.AI_TRACE_LEVEL``) rather than a
literal at every call site.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.services import jev_cache
from tabs.image_gallery.services.ai_client import AI_TRACE_LEVEL
from tabs.image_gallery.services.jev_client import rank_series_jev_detailed
from core.log_names import APP_LOGGER_NAME


def _item(name: str, **metrics) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=0)
    it.metrics.update(metrics)
    # P7-B: Jev refuses a one-axis vector; mirror ssim onto sharpness so this
    # trace fixture still ranks (the refusal has its own focused test).
    if "sharpness" not in it.metrics and "ssim" in it.metrics:
        it.metrics["sharpness"] = float(it.metrics["ssim"]) * 400.0
    return it


def _client(payload: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps({"choice": "img_1", "score": 0.9})}}]}


def test_jev_trace_silent_without_key(tmp_path, caplog, monkeypatch) -> None:
    monkeypatch.delenv("IMGSLI_AI_DEBUG", raising=False)
    items = [_item("a.png", ssim=0.9), _item("b.png", ssim=0.4)]
    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        outcome = rank_series_jev_detailed(
            items, mode="fidelity", client=_client, cache=jev_cache.JevRankCache(tmp_path)
        )
    assert outcome.decided
    assert "[ai] jev" not in caplog.text


def test_jev_trace_dumps_with_key_and_marks_the_pin(tmp_path, caplog, monkeypatch) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = [_item("a.png", ssim=0.9), _item("b.png", ssim=0.4)]
    cache = jev_cache.JevRankCache(tmp_path)
    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        first = rank_series_jev_detailed(items, mode="fidelity", client=_client, cache=cache)
    assert first.decided
    assert "[ai] jev rank mode=fidelity items=2 (call)" in caplog.text
    assert "[ai] jev rank => decided=True reason=None" in caplog.text
    assert AI_TRACE_LEVEL == logging.INFO, (
        "the [ai] channel must keep its own non-alarm level"
    )
    assert all(
        record.levelno == AI_TRACE_LEVEL
        for record in caplog.records
        if record.getMessage().startswith("[ai]")
    ), "an [ai] trace line was logged at a level other than the channel's own"

    caplog.clear()
    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        second = rank_series_jev_detailed(items, mode="fidelity", client=_client, cache=cache)
    assert "[ai] jev rank cache HIT items=2" in caplog.text
    assert second.cached


def test_domain_switch_trace_under_key(caplog, monkeypatch) -> None:
    """The controller layer states WHY Jev ran or not — same ``[ai]`` key."""
    from types import SimpleNamespace

    from tabs.image_gallery.controller import GalleryController

    class _Ctrl:
        def __init__(self) -> None:
            self.state = SimpleNamespace(series=[], judgment_domain="", rank_domain="")

        def _apply_fusion_ranks(self, series, *, mode=None):
            return None

        def _clear_series_priority(self):
            return None

        def _run_ai_for_visible(self):
            return None

        def _run_jev_ranks(self):
            GalleryController._run_jev_ranks(self)

        def _run_series_priority(self):
            return None

    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    ctrl = _Ctrl()
    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        GalleryController.activate_judgment_domain(ctrl, "algorithms")
    assert "[ai] judgment domain -> algorithms (Jev off)" in caplog.text

    caplog.clear()
    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        GalleryController.activate_judgment_domain(ctrl, "ai")
    assert "[ai] judgment domain -> ai (Jev on)" in caplog.text
    assert "[ai] jev ranks: no series — nothing to rank" in caplog.text


def test_judgment_domain_survives_state_rebuild() -> None:
    """S1: the domain is the controller's durable authority, NOT ``state``
    (open_folder / append / clear_to_empty replace the ``GalleryState``)."""
    from types import SimpleNamespace

    from tabs.image_gallery.controller import GalleryController
    from tabs.image_gallery.models import GalleryState

    ctrl = SimpleNamespace(state=GalleryState())
    GalleryController._set_judgment_domain(ctrl, "ai")
    assert ctrl._judgment_domain == "ai"
    assert ctrl.state.rank_domain == "ai"  # projection

    ctrl.state = GalleryState()  # open_folder/append/clear replaces the object
    assert ctrl.state.rank_domain == "algorithms"  # projection lost...
    assert ctrl._judgment_domain == "ai"  # ...but the authority survives

