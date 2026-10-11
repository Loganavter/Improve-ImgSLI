"""A1 — ``ask_context.build_ask_context`` (scope → measured context dict).

The frozen seam: metrics must come from the canonical registry
(``metric_scores.measured_scores``) and severities from
``use_cases.quality`` — never a second derivation from raw ``item.metrics``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.models import (
    AiAnalysisResult,
    AiAxisFlag,
    GalleryItem,
    Mode,
    Series,
)
from tabs.image_gallery.services.ask_context import (
    ASK_SELECTION,
    ASK_SERIES,
    AskScope,
    build_ask_context,
    deanonymize_answer,
)
from tabs.image_gallery.services.metric_scores import SPECS, measured_scores


def _fake_controller(items, *, selected=(), mode=Mode.FIDELITY, source=None, series=None):
    state = SimpleNamespace(
        items=list(items),
        selected_paths=set(selected),
        selected_order=list(selected),
        series=list(series or []),
        mode=mode,
        source_path=source,
    )
    ctrl = SimpleNamespace(state=state)
    ctrl._find_item = lambda p: next(
        (it for it in items if str(it.path) == str(p)), None
    )
    return ctrl


def test_selection_metrics_come_from_registry_not_raw_item_metrics():
    metrics = {"sharpness": 200.0, "ssim": 0.9}
    it = GalleryItem(path=Path("/g/a.png"), mtime_ns=1, metrics=dict(metrics))
    ctrl = _fake_controller([it], selected=[it.path])

    ctx = build_ask_context(AskScope(kind=ASK_SELECTION), controller=ctrl)

    expected = {
        mid: score for mid, _label, _raw, score in measured_scores(metrics)
    }
    assert ctx["kind"] == ASK_SELECTION
    assert ctx["count"] == 1
    assert ctx["mode"] == "fidelity"
    assert ctx["items"][0]["metrics"] == expected
    # No second derivation: an unmeasured raw key must not leak in.
    assert "sharpness_raw" not in ctx["items"][0]["metrics"]
    # Human labels ride along so the model never sees a bare metric id.
    assert ctx["metric_labels"]["sharpness"] == "Sharpness"


def test_explicit_selection_paths_order_is_preserved_and_missing_skipped():
    a = GalleryItem(path=Path("/g/a.png"), mtime_ns=1)
    b = GalleryItem(path=Path("/g/b.png"), mtime_ns=2)
    ctrl = _fake_controller([a, b])
    scope = AskScope(kind=ASK_SELECTION, paths=(b.path, Path("/g/gone.png"), a.path))

    ctx = build_ask_context(scope, controller=ctrl)

    assert [i["name"] for i in ctx["items"]] == ["b.png", "a.png"]


def test_selection_falls_back_to_controller_selection_state():
    a = GalleryItem(path=Path("/g/a.png"), mtime_ns=1)
    ctrl = _fake_controller([a], selected=[a.path])

    ctx = build_ask_context(AskScope(kind=ASK_SELECTION), controller=ctrl)

    assert ctx["count"] == 1
    assert ctx["items"][0]["path"] == str(a.path)


def test_series_scope_resolves_members_from_state_and_labels():
    m1 = GalleryItem(path=Path("/g/1.png"), mtime_ns=1, series_id="series_1")
    m2 = GalleryItem(path=Path("/g/2.png"), mtime_ns=2, series_id="series_1")
    other = GalleryItem(path=Path("/g/3.png"), mtime_ns=3, series_id="series_2")
    series = Series(id="series_1", members=[m1, m2])
    ctrl = _fake_controller([m1, m2, other], series=[series])

    ctx = build_ask_context(AskScope(kind=ASK_SERIES, series_id="series_1"), controller=ctrl)

    assert ctx["kind"] == ASK_SERIES
    assert [i["name"] for i in ctx["items"]] == ["1.png", "2.png"]
    assert "series_1" in ctx["label"]


def test_series_scope_falls_back_to_explicit_paths_when_no_id():
    m1 = GalleryItem(path=Path("/g/1.png"), mtime_ns=1)
    ctrl = _fake_controller([m1])
    ctx = build_ask_context(
        AskScope(kind=ASK_SERIES, paths=(m1.path,), label="My series"),
        controller=ctrl,
    )
    assert ctx["label"] == "My series"
    assert ctx["count"] == 1


def test_non_ask_scope_defaults_to_selection_without_raising():
    ctrl = _fake_controller([])
    ctx = build_ask_context(None, controller=ctrl)
    assert ctx["kind"] == ASK_SELECTION
    assert ctx["items"] == []


def test_source_and_mode_are_reported():
    a = GalleryItem(path=Path("/g/a.png"), mtime_ns=1)
    ctrl = _fake_controller([a], source=Path("/g/source.png"), mode=Mode.CAMERA)

    ctx = build_ask_context(AskScope(kind=ASK_SELECTION, paths=(a.path,)), controller=ctrl)

    assert ctx["mode"] == "camera"
    assert ctx["source"] == "/g/source.png"


def test_items_are_anonymized_with_alias_and_name_map():
    """The model sees opaque img_N labels, never descriptive filenames."""
    a = GalleryItem(path=Path("/g/Archivist Soft.png"), mtime_ns=1)
    b = GalleryItem(path=Path("/g/Archivist Rough.png"), mtime_ns=2)
    ctrl = _fake_controller([a, b], selected=[a.path, b.path])
    ctrl.state.selected_order = [a.path, b.path]

    ctx = build_ask_context(AskScope(kind=ASK_SELECTION), controller=ctrl)

    aliases = [it["alias"] for it in ctx["items"]]
    assert aliases == ["img_1", "img_2"]
    # Real names are still carried for the app, but only under `name`.
    assert ctx["items"][0]["name"] == "Archivist Soft.png"
    assert ctx["names"] == {"img_1": "Archivist Soft.png", "img_2": "Archivist Rough.png"}


def test_deanonymize_maps_aliases_back_and_handles_longest_first():
    names = {"img_1": "soft.png", "img_10": "rough.png"}
    text = "img_10 is softer than img_1, but IMG_1 has more detail."
    out = deanonymize_answer(text, names)
    assert "rough.png is softer than soft.png" in out
    assert "soft.png has more detail" in out
    assert "img_" not in out


def test_deanonymize_noop_without_map():
    assert deanonymize_answer("img_1 is fine", None) == "img_1 is fine"


def _analysis(*flags):
    return AiAnalysisResult(
        description="",
        tags=(),
        model="m",
        analyzed_at_iso="",
        axis_flags=tuple(flags),
    )


def test_item_carries_axis_kind_for_every_spec_even_without_scores():
    a = GalleryItem(path=Path("/g/a.png"), mtime_ns=1)
    ctrl = _fake_controller([a], selected=[a.path])

    ctx = build_ask_context(AskScope(kind=ASK_SELECTION), controller=ctrl)

    item = ctx["items"][0]
    assert item["metrics"] == {}
    assert item["kinds"] == {s.id: s.kind.value for s in SPECS}
    assert set(item["kinds"]) == {s.id for s in SPECS}
    assert set(item["kinds"].values()) <= {"measured", "candidate", "judgment"}


def test_flags_keep_candidate_and_judgment_and_drop_measured():
    a = GalleryItem(
        path=Path("/g/a.png"),
        mtime_ns=1,
        analysis=_analysis(
            AiAxisFlag(id="halo_delta", label="halo", kind="candidate", note="rim"),
            AiAxisFlag(id="flag-for-review", label="odd", kind="judgment"),
            AiAxisFlag(id="sharpness", label="soft", kind="measured", note="nope"),
        ),
    )
    ctrl = _fake_controller([a], selected=[a.path])

    ctx = build_ask_context(AskScope(kind=ASK_SELECTION), controller=ctrl)

    assert ctx["items"][0]["flags"] == [
        {"id": "halo_delta", "label": "Halo vs source", "kind": "candidate", "note": "rim"},
        {"id": "flag-for-review", "label": "odd", "kind": "judgment", "note": ""},
    ]


def test_flags_empty_without_analysis_and_no_duplicate_label_map():
    a = GalleryItem(path=Path("/g/a.png"), mtime_ns=1)
    ctrl = _fake_controller([a], selected=[a.path])

    ctx = build_ask_context(AskScope(kind=ASK_SELECTION), controller=ctrl)

    assert ctx["items"][0]["flags"] == []
    assert ctx["metric_labels"]["halo_delta"] == "Halo vs source"
    assert "axis_labels" not in ctx
