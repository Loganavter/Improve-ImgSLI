"""INVARIANT: the AI wire reuses the Stage-2 proxy pixels, never re-reads the file.

Audit R6: the gallery already decoded the item at ``PROXY_MAX_EDGE`` (1024) for
the local metrics; the per-card AI upload then opened and decoded the SAME file
again at the SAME edge. This test primes the proxy cache, forbids any further
``Image.open``/``Path.read_bytes``, runs the real ``analyze_image_sync`` and
asserts the request is still built (non-vacuity: the transport was reached with a
wire image).

Red before the change (measured): one ``Image.open`` during the analyze call,
i.e. a second full decode of the same file.
"""

from __future__ import annotations

from pathlib import Path

import io
import json

from PIL import Image

import tabs.image_gallery.services.ai_client as ai_client
from tabs.image_gallery.services.ai_client import analyze_image_sync
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.services.proxy import proxy_for


def _image(tmp_path: Path) -> Path:
    path = tmp_path / "shot.jpg"
    Image.new("RGB", (1600, 900), (90, 120, 150)).save(path, quality=92)
    return path


def _profile() -> MetricProfile:
    return MetricProfile(axis_ids=("sharpness",), mode="camera", source="vlm")


def test_ai_wire_reuses_the_proxy_pixels(tmp_path, counters, monkeypatch) -> None:
    path = _image(tmp_path)
    # Prime the ONE shared proxy decode (what the Stage-2 pass does per item).
    proxy_for(path)

    opens: list = []
    real_open = Image.open

    def _counted_open(*args, **kwargs):
        opens.append(args)
        return real_open(*args, **kwargs)

    monkeypatch.setattr(Image, "open", _counted_open)

    def _no_reread(self):
        raise AssertionError(f"the AI wire re-read the file: {self}")

    monkeypatch.setattr(Path, "read_bytes", _no_reread)

    sent: list = []

    def _transport(_base_url, _api_key, payload):
        sent.append(payload)
        return {
            "model": "m",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"axes": {"sharpness": 80}, "reason": "ok"}
                        )
                    }
                }
            ],
        }

    monkeypatch.setattr(ai_client, "call_sync", _transport)

    result = analyze_image_sync(
        path,
        base_url="http://x",
        api_key="k",
        model="m",
        mode="camera",
        profile=_profile(),
        samples=1,
    )

    # ``encode_wire_image`` decodes the in-memory PNG we just serialized (no
    # file/disk access); a FILE open here is the second decode this test kills.
    file_opens = [a for a in opens if not isinstance(a[0], io.BytesIO)]
    assert file_opens == [], (
        f"the AI wire opened the source file again ({len(file_opens)}x)"
    )
    assert len(sent) == 1, "non-vacuity: the request must still be sent"
    assert result is not None
