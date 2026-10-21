"""W3 — series AI context + AI candidate axis flags (two-domain-axes)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.services import ai_client
from tabs.image_gallery.services.series_context import build_series_context


class _State:
    def __init__(self, source=None):
        self.source_path = source


class _Item:
    def __init__(self, name, metrics=None):
        self.path = Path(name)
        self.metrics = metrics or {}
        self.badge = ""


class _Ctrl:
    def __init__(self, source=None):
        self.state = _State(source)


def test_series_context_includes_source_and_caps_variants():
    items = [_Item(f"/g/{i}.png", {"sharpness": 100.0 + i}) for i in range(5)]
    ctx = build_series_context(_Ctrl(source="/g/source.png"), items)
    assert ctx["source"] == "/g/source.png"
    assert ctx["count"] == 5
    assert len(ctx["variants"]) == 2  # source + 2 default cap
    assert [v["alias"] for v in ctx["variants"]] == ["img_1", "img_2"]
    assert all("sharpness" in v["metrics"] for v in ctx["variants"])


def test_series_context_accepts_series_dataclass_and_max_variants():
    items = [_Item("/g/a.png"), _Item("/g/b.png")]
    series = SimpleNamespace(id="s1", members=items)
    ctx = build_series_context(_Ctrl(), series, max_variants=1)
    assert ctx["count"] == 2
    assert len(ctx["variants"]) == 1
    assert ctx["source"] is None


def test_series_context_is_fail_open_without_metrics():
    ctx = build_series_context(_Ctrl(), [_Item("/g/a.png")])
    assert ctx["variants"][0]["metrics"] == {}


def test_parse_response_maps_defects_to_candidate_flags_not_numbers():
    raw = {
        "choices": [
            {
                "message": {
                    "content": '{"reason":"ok","defects":[{"kind":"halo","severity":"mild","note":"x"}]}'
                }
            }
        ]
    }
    res = ai_client.parse_response(raw, model="m")
    assert res.axis_flags
    assert all(f.kind == "candidate" for f in res.axis_flags)
    assert all(f.kind != "measured" for f in res.axis_flags)
