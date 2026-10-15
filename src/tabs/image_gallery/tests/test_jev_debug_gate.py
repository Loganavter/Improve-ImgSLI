"""Jev trace gate: silent without ``IMGSLI_AI_DEBUG``, ``[ai]``-tagged with it.

Falsification story: a Jev rank call that stays silent (no ``[ai] jev`` line) in
a normal run, and that emits the ``[ai] jev`` request/decision/cache lines — the
same ``IMGSLI_AI_DEBUG`` key ``ai_client._ai_debug`` already uses — when enabled.
Mirrors ``tests/test_hover_diag_gate.py`` (gate-zone dump recipe, LOGGING.md).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.services import jev_cache
from tabs.image_gallery.services.jev_client import rank_series_jev_detailed


def _item(name: str, **metrics) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=0)
    it.metrics.update(metrics)
    return it


def _client(payload: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps({"choice": "img_1", "score": 0.9})}}]}


def test_jev_trace_silent_without_key(tmp_path, caplog, monkeypatch) -> None:
    monkeypatch.delenv("IMGSLI_AI_DEBUG", raising=False)
    items = [_item("a.png", ssim=0.9), _item("b.png", ssim=0.4)]
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        outcome = rank_series_jev_detailed(
            items, mode="fidelity", client=_client, cache=jev_cache.JevRankCache(tmp_path)
        )
    assert outcome.decided
    assert "[ai] jev" not in caplog.text


def test_jev_trace_dumps_with_key_and_marks_the_pin(tmp_path, caplog, monkeypatch) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = [_item("a.png", ssim=0.9), _item("b.png", ssim=0.4)]
    cache = jev_cache.JevRankCache(tmp_path)
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        first = rank_series_jev_detailed(items, mode="fidelity", client=_client, cache=cache)
    assert first.decided
    assert "[ai] jev rank mode=fidelity items=2 (call)" in caplog.text
    assert "[ai] jev rank => decided=True reason=None" in caplog.text

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        second = rank_series_jev_detailed(items, mode="fidelity", client=_client, cache=cache)
    assert "[ai] jev rank cache HIT items=2" in caplog.text
    assert second.cached
