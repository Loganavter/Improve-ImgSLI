"""The profile selector's probe must not ride full-resolution images.

Owner report 2026-10-22 ("долгая заминка перед анализом"), measured from the
real log:

```
12:43:44,930  metric profile: select scheduled
12:43:44,976  POST ... body_bytes=11271911        <- six full-res probe images
12:43:44,979  settle: AI/jev tails deferred until the metric profile resolves
12:43:51,818  HTTP 200                            <- 6.9 s before ANY card analysis
```

The selector asks a coarse question ("which axes separate these variants?"), so
its probe is capped at a fixed edge and encoded as JPEG regardless of the
per-card setting (which exists for the analysis payloads, not for this probe).
The per-card path must stay untouched: same setting, same mime.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _noisy_png(path: Path, size=(1440, 1080)) -> Path:
    """An incompressible image (noise) so the payload size is honest."""
    import random

    w, h = size
    rnd = random.Random(7)
    img = Image.new("RGB", (w, h))
    img.putdata([
        (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
        for _ in range(w * h)
    ])
    img.save(path, format="PNG")
    return path


def test_the_selector_probe_ignores_the_full_resolution_setting(tmp_path, monkeypatch) -> None:
    from tabs.image_gallery.services import vlm

    img = _noisy_png(tmp_path / "probe.png")
    monkeypatch.setattr(vlm, "get_vlm_max_edge", lambda: 0)  # user: send originals

    full_mime, full_b64 = vlm._encode_image(img)
    sel_mime, sel_b64 = vlm._encode_image(
        img, max_edge=512, prefer_jpeg=True
    )

    assert full_mime == "png" and full_b64 == full_b64  # sanity: original bytes
    assert sel_mime == "jpeg", sel_mime
    assert len(sel_b64) * 4 < len(full_b64), (
        f"the selector probe is not smaller: {len(sel_b64)} vs {len(full_b64)}"
    )
    # Base64 of a 512-edge JPEG stays far below the old multi-MB payload.
    assert len(sel_b64) < 400_000, len(sel_b64)


def test_the_per_card_path_keeps_the_user_setting(tmp_path, monkeypatch) -> None:
    from tabs.image_gallery.services import vlm

    img = _noisy_png(tmp_path / "card.png", size=(1200, 900))
    monkeypatch.setattr(vlm, "get_vlm_max_edge", lambda: 768)

    mime, data = vlm._encode_image(img)
    with Image.open(io.BytesIO(__import__("base64").b64decode(data))) as out:
        assert max(out.size) == 768, out.size
    assert mime == "png"


def test_build_profile_request_passes_the_cap(monkeypatch, tmp_path) -> None:
    from tabs.image_gallery.services import vlm
    from tabs.image_gallery.use_cases import profile_ai

    calls: list[dict] = []
    monkeypatch.setattr(
        vlm,
        "_encode_image",
        lambda path, **kw: (calls.append(kw), ("jpeg", "AAAA"))[1],
    )
    items = [type("I", (), {"path": tmp_path / f"{i}.png"})() for i in range(3)]

    profile_ai.build_profile_request(items, model="m", salience={})

    assert calls, "no probe was encoded"
    assert all(c.get("max_edge") == profile_ai.PROFILE_PROBE_MAX_EDGE for c in calls), calls
    assert all(c.get("prefer_jpeg") is True for c in calls), calls


# -- the judge's axis row shows a readable title ----------------------------


def test_a_judged_axis_row_shows_a_short_title_and_puts_the_definition_in_the_tooltip(qtbot):
    """Owner saw "cl…" — a definition-long title elided in the fixed column."""
    from pathlib import Path
    from types import SimpleNamespace

    from PySide6.QtWidgets import QWidget

    from tabs.image_gallery.models import (
        AiAnalysisResult,
        AiAxisProposal,
        GalleryItem,
        Mode,
    )
    from tabs.image_gallery.services.metric_profile import MetricProfile
    from tabs.image_gallery.ui.quick_look import metrics as m
    from tabs.image_gallery.tests.runtime.test_ql_metric_rows_profile import _RowsStub, _row_titles

    entry = AiAxisProposal(
        name="clarity",
        definition="0 = muddy and hard to read, 100 = crisp and legible in one glance",
        scale="0-100",
        direction="higher-is-better",
    )
    profile = MetricProfile(
        axis_ids=("clarity",), mode="camera", source="vlm", axis_entries=(entry,)
    )
    item = GalleryItem(path=Path("/gallery/x.png"), mtime_ns=1)
    item.analysis = AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t", axes={"clarity": 78}
    )
    ov = _RowsStub(item, profile)
    ov._mode = Mode.CAMERA
    # The judge's axis exists on the AI domain (the algorithms read has no
    # producer for an invented name) — the owner's report came from AI mode.
    ov._owner._judgment_domain = "ai"  # the report reads the OWNER authority
    qtbot.addWidget(ov._report_host)

    m.rebuild_metrics(ov, item, False, "CAMERA")

    titles = _row_titles(ov)
    assert titles, "the judged axis did not render"
    # The header is the axis' HUMAN name (the model's label, else the id read
    # as words) — never a definition that elides to "cl…". "clarity" is the
    # whole name, so the old length proxy (`len > 12`, which only held while the
    # header carried the definition) is replaced by the name itself.
    assert titles[0] == "clarity", titles
    # …and the meaning is not lost: the row tooltip is where the prose lives.
    tips = [row.toolTip() for row in ov._metric_rows if row.toolTip()]
    assert any("muddy and hard to read" in t for t in tips), tips
