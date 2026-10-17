"""P3 — adaptive probe size + reference choice (pure, deterministic).

Falsification story (what each test would catch):

- an adaptive K that ignores the spread (a scattered series probing the same
  two members as a uniform one), is not monotonic in the spread, or escapes
  ``[2, len]``;
- the reference counted as a probe member (the hub would be sent as a probe AND
  used as context — a duplicated, biased probe set);
- a probe ranking that depends on the input order (dict/set iteration leaking
  into the choice) — checked by permutation equality;
- a reference that ignores the source hub when its path resolves, or that picks
  a near-median member instead of the farthest;
- a salience summary whose axes are unordered or unbounded (the model would see
  noise instead of the top signals).

Pure-python ``SimpleNamespace`` fakes only — no Qt, no torch, no PIL.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.use_cases import profile_probe
from tabs.image_gallery.use_cases.profile_probe import (
    PROBE_BASE_K,
    PROBE_GAIN,
    PROBE_MAX_K,
    SALIENCE_TOP_N,
    adaptive_k,
    probe_members,
    reference_choice,
    salience_summary,
)


def _item(name: str, **metrics) -> SimpleNamespace:
    return SimpleNamespace(path=Path(f"/gallery/{name}"), metrics=dict(metrics))


def _sharpness_spread(span_raw: float, n: int = 10, name: str = "sharpness") -> list:
    """``n`` items whose sharpness scores span ``0..span_raw`` (raw Laplacian)."""
    return [
        _item(f"{i:02d}.png", **{name: (span_raw * i / (n - 1))})
        for i in range(n)
    ]


# --------------------------------------------------------------------------
# adaptive K — monotonic in the spread, clamped to [2, len]
# --------------------------------------------------------------------------


def test_adaptive_k_uniform_series_probes_the_base():
    items = [_item(f"i{i}.png", sharpness=200.0, noise=0.5) for i in range(6)]
    assert adaptive_k(items) == PROBE_BASE_K


def test_adaptive_k_fully_scattered_probes_the_max():
    items = _sharpness_spread(400.0)
    assert adaptive_k(items) == PROBE_MAX_K


def test_adaptive_k_is_monotonic_in_spread_and_in_range():
    sizes = [adaptive_k(_sharpness_spread(raw)) for raw in (0.0, 100.0, 200.0, 400.0)]
    assert sizes == sorted(sizes)
    assert sizes[0] == PROBE_BASE_K and sizes[-1] == PROBE_MAX_K
    assert all(PROBE_BASE_K <= size <= 10 for size in sizes)


def test_adaptive_k_never_exceeds_member_count():
    assert adaptive_k([]) == 0
    assert adaptive_k([_item("a.png")]) == 1
    assert adaptive_k([_item("a.png"), _item("b.png")]) == 2
    assert adaptive_k([_item("a.png", sharpness=400.0), _item("b.png", sharpness=0.0)]) == 2


def test_adaptive_k_is_permutation_invariant():
    items = _sharpness_spread(300.0)
    assert adaptive_k(items) == adaptive_k(list(reversed(items)))


def test_adaptive_k_never_raises_on_garbage():
    assert adaptive_k(None) == 0
    assert adaptive_k(object()) == 0
    assert adaptive_k([None, 3, "x"]) == PROBE_BASE_K


def test_probe_constants_match_the_formula():
    assert PROBE_BASE_K == 2 and PROBE_GAIN == 4.0 and PROBE_MAX_K == 6
    assert PROBE_BASE_K + round(PROBE_GAIN * 1.0) == PROBE_MAX_K


# --------------------------------------------------------------------------
# reference choice — hub, else farthest from the per-axis median
# --------------------------------------------------------------------------


def test_reference_choice_prefers_the_source_hub_when_the_path_resolves():
    a, b, c = _item("a.png"), _item("b.png"), _item("c.png")
    assert reference_choice([a, b, c], reference_path=b.path) is b
    assert reference_choice([a, b, c], reference_path=str(b.path)) is b


def test_reference_choice_falls_back_to_the_farthest_from_median():
    a = _item("a.png", sharpness=0.0)  # score 0
    b = _item("b.png", sharpness=400.0)  # score 100
    c = _item("c.png", sharpness=400.0)  # score 100
    # median 100 → a deviates by 100, b/c by 0.
    assert reference_choice([a, b, c]) is a


def test_reference_choice_ties_break_by_path():
    a = _item("a.png", sharpness=0.0)  # 0
    b = _item("b.png", sharpness=400.0)  # 100
    c = _item("c.png", sharpness=200.0)  # 50 → median
    # a and b are both 50 away from the median → smallest path wins.
    assert reference_choice([c, b, a]) is a


def test_reference_choice_needs_two_items():
    assert reference_choice([]) is None
    assert reference_choice([_item("a.png", sharpness=400.0)]) is None


def test_reference_choice_honours_the_axis_subset():
    a = _item("a.png", sharpness=0.0, ssim=0.9)
    b = _item("b.png", sharpness=400.0, ssim=0.9)
    c = _item("c.png", sharpness=200.0, ssim=0.1)
    assert reference_choice([a, b, c], axes=["ssim"]) is c
    assert reference_choice([a, b, c], axes=["sharpness"]) is a


# --------------------------------------------------------------------------
# probe membership — reference is context, permutation-invariant
# --------------------------------------------------------------------------


def test_probe_members_excludes_the_reference():
    a = _item("a.png", sharpness=0.0)
    b = _item("b.png", sharpness=400.0)
    c = _item("c.png", sharpness=200.0)
    d = _item("d.png", sharpness=200.0)
    probes = probe_members([a, b, c, d], k=3, reference_path=c.path)
    assert c not in probes
    assert {p.path for p in probes} == {a.path, b.path, d.path}


def test_probe_members_orders_by_deviation_then_path():
    a = _item("a.png", sharpness=0.0)  # 0 → median 50 → dev 50
    b = _item("b.png", sharpness=400.0)  # 100 → dev 50
    c = _item("c.png", sharpness=200.0)  # 50 → dev 0
    d = _item("d.png", sharpness=200.0)  # 50 → dev 0
    assert probe_members([a, b, c, d], k=2) == (a, b)
    assert probe_members([d, c, b, a], k=2) == (a, b)


def test_probe_members_is_permutation_invariant():
    items = _sharpness_spread(400.0)
    assert probe_members(items) == probe_members(list(reversed(items)))


def test_probe_members_measures_against_the_reference_when_present():
    hub = _item("hub.png", sharpness=200.0)  # 50
    far = _item("far.png", sharpness=0.0)  # 0 → dev 50
    near = _item("near.png", sharpness=200.0)  # 50 → dev 0
    probes = probe_members([near, hub, far], k=1, reference_path=hub.path)
    assert probes == (far,)


def test_probe_members_returns_every_candidate_when_k_covers_them():
    items = _sharpness_spread(400.0, n=4)  # adaptive K would be 4
    probes = probe_members(items, k=99)
    assert {p.path for p in probes} == {i.path for i in items}
    assert len(probes) == len(items)


def test_probe_members_default_k_is_adaptive():
    items = _sharpness_spread(400.0)  # spread 100 → adaptive K = 6
    assert len(probe_members(items)) == PROBE_MAX_K


def test_probe_members_empty_inputs():
    assert probe_members([]) == ()
    assert probe_members(None) == ()
    only = _item("a.png")
    assert probe_members([only], reference_path=only.path) == ()


# --------------------------------------------------------------------------
# salience summary — shape, ordering, bound
# --------------------------------------------------------------------------


def test_salience_summary_shape_and_order():
    items = [
        _item("a.png", sharpness=0.0, noise=0.9),
        _item("b.png", sharpness=400.0, noise=1.0),
    ]
    summary = salience_summary(items)
    assert summary["members"] == 2
    assert summary["k"] == adaptive_k(items)
    ids = [row["id"] for row in summary["axes"]]
    spreads = [row["spread"] for row in summary["axes"]]
    assert ids == ["sharpness", "noise"]  # both 100 → registry order
    assert spreads == sorted(spreads, reverse=True)


def test_salience_summary_top_n_is_bounded():
    items = _sharpness_spread(400.0)
    assert len(salience_summary(items, top_n=1)["axes"]) <= 1
    assert salience_summary(items, top_n=SALIENCE_TOP_N)["k"] == PROBE_MAX_K


def test_salience_summary_never_raises():
    summary = salience_summary(None)
    assert summary == {"members": 0, "k": 0, "axes": []}


def test_profile_probe_is_pure_no_qt_contract():
    source = Path(profile_probe.__file__).read_text(encoding="utf-8")
    assert "PySide6" not in source and "import Qt" not in source


def test_module_exports_are_the_frozen_interface():
    assert set(profile_probe.__all__) == {
        "PROBE_BASE_K",
        "PROBE_GAIN",
        "PROBE_MAX_K",
        "SALIENCE_TOP_N",
        "adaptive_k",
        "probe_members",
        "reference_choice",
        "salience_summary",
    }
